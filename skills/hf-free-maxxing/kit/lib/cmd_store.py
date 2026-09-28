#!/usr/bin/env python3
"""hfx store — durable storage & sharing on HuggingFace free storage.

Implements the MEASURED frictionless paths (findings/storage-upload-benchmark.md):
  <10MB  → hub upload_file (Xet)                        ~4-5s fixed overhead
  ≥10MB  → hub upload_file + HF_XET_HIGH_PERFORMANCE=1  1.36× faster (measured)
  bucket → boto3 upload_file, auto-multipart ≥8MB       best for >5GB + deletable
  share  → SigV4 presigned URL (SigV2 presign → 403!)   anon-fetchable, expiring
  copy   → duplicate API (Xet hash migration)           341MB repo in 0.82s
  pin    → git tag → resolve/<tag>/<path>               versioned asset URLs

Repos (dataset type) = durable, versioned, CDN-served. Buckets = deletable,
quota-frees ≤90s. Both share the same pool: 100GB private / 8.7TB public per
entity, 500GB max file.

Usage:
  hfx store put FILE [--repo NAME | --public] [--bucket B] [--entity NS] [--path P]
  hfx store get REPO_OR_URL PATH [--out F]  |  hfx store get KEY --bucket B [--out F]
  hfx store ls [--repo NAME] [--bucket B] [--entity NS]
  hfx store rm PATH... --repo NAME [--purge-lfs]  |  hfx store rm KEY... --bucket B
  hfx store rm-bucket NAME [--entity NS] [--force]
  hfx store share KEY --bucket B [--ttl 3600]
  hfx store cp-repo SRC DST [--private] [--entity NS]
  hfx store tag REPO TAG [--rev main] [--message MSG] [--delete]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import time
from urllib.parse import urlparse

import hfx

DEFAULT_REPO = "hfx-store"          # private dataset repo (100GB pool)
PUBLIC_REPO = "hfx-store-public"    # public dataset repo (8.7TB best-effort pool)
BIG_BYTES = 10 * 1024 * 1024        # ≥10MB → HF_XET_HIGH_PERFORMANCE=1 (measured 1.36×)

# terse CLI: no tqdm bars from huggingface_hub (set before hub import)
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


# ------------------------------------------------------------------ helpers

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _mbps(size: float, sec: float) -> float:
    return (size / sec) / (1 << 20) if sec > 0 else 0.0


def _resolve_ns(a, token: str) -> str:
    """Namespace for bare repo/bucket names: --entity (validated) or the user."""
    ents = hfx.entities(token)
    names = [e["name"] for e in ents]
    if getattr(a, "entity", None):
        if a.entity not in names:
            hfx.die(f"--entity '{a.entity}' is not one of your entities "
                    f"(valid: {', '.join(names)})", hfx.EXIT_CONFIG)
        return a.entity
    return names[0]


def _full_repo(name: str, ns: str) -> str:
    return name if "/" in name else f"{ns}/{name}"


def _s3(env: dict, ns: str):
    """boto3 client on the PER-NAMESPACE endpoint https://s3.hf.co/<ns>.

    SigV4 forced (default SigV2 presign → 403 SignatureDoesNotMatch — measured);
    path addressing; checksums only when required (gateway can't parse trailing
    checksums)."""
    import boto3
    from botocore.config import Config
    key = hfx.need(env, "HF_S3_ACCESS_KEY_ID",
                   "Generate at https://huggingface.co/settings/tokens → "
                   "'Generate S3 credentials' (web session needed; the secret is "
                   "shown once), then export HF_S3_ACCESS_KEY_ID=... "
                   "HF_S3_SECRET_ACCESS_KEY=... (or put them in .env).")
    sec = hfx.need(env, "HF_S3_SECRET_ACCESS_KEY",
                   "Comes together with HF_S3_ACCESS_KEY_ID (shown once at "
                   "generation time).")
    cfg = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path"},
        request_checksum_calculation="when_required",
        response_checksum_validation="when_required",
    )
    return boto3.client("s3", endpoint_url=f"{hfx.S3_ENDPOINT}/{ns}",
                        aws_access_key_id=key, aws_secret_access_key=sec,
                        region_name="us-east-1", config=cfg)


def _s3_guard(op: str, fn, *args, bucket: str = "", key: str = "", **kw):
    """Run a boto3 call; convert any client error into a clean hfx death.
    404/NoSuchKey/NoSuchBucket and 403/AccessDenied get recovery hints
    (U1 friction #3) — pass bucket=/key= for the friendly wording."""
    try:
        return fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 — botocore ClientError & friends
        resp = getattr(e, "response", None)
        code, status = "", 0
        if isinstance(resp, dict):
            code = str((resp.get("Error") or {}).get("Code", ""))
            try:
                status = int((resp.get("ResponseMetadata") or {})
                             .get("HTTPStatusCode", 0))
            except (TypeError, ValueError):
                pass
        what = f"bucket '{bucket}'" if bucket else "bucket"
        if key:
            what += f" or key '{key}'"
        if status == 404 or code in ("NoSuchKey", "NoSuchBucket", "NotFound"):
            hint = (f"hfx store ls --bucket {bucket}" if (bucket and key)
                    else "hfx store ls")
            hfx.die(f"{what} not found — try `{hint}` to see what exists",
                    hfx.EXIT_FAIL)
        if status == 403 or code in ("AccessDenied", "SignatureDoesNotMatch"):
            hint = ""
            if bucket:
                hint = (f" — bucket {bucket} is private: your S3 credentials "
                        "(HF_S3_ACCESS_KEY_ID/SECRET) must carry access. To hand "
                        f"someone an anonymous link instead: hfx store share <key> "
                        f"--bucket {bucket}")
            hfx.die(f"S3 {op}: 403/AccessDenied{hint}", hfx.EXIT_FAIL)
        hfx.die(f"S3 {op} failed: {str(e).splitlines()[0][:300]}", hfx.EXIT_FAIL)


def _ensure_bucket(token: str, ns: str, name: str) -> bool:
    """Create bucket via Hub API, then FORCE private.

    The SDK/rclone mkdir (raw S3 CreateBucket) creates buckets PUBLIC by default
    — the #1 trap. Returns True if the bucket was created now."""
    st, _, _ = hfx.api("POST", f"/api/buckets/{ns}/{name}", token=token,
                       json_body={"private": True}, expect=(200, 409))
    created = st == 200
    if created:
        time.sleep(1)  # API pacing
    # mandatory private flip (idempotent; settings is PUT-only, no GET)
    hfx.api("PUT", f"/api/buckets/{ns}/{name}/settings", token=token,
            json_body={"private": True})
    time.sleep(1)
    # verify via the namespace bucket list (the only private-flag read)
    _, lst, _ = hfx.api("GET", f"/api/buckets/{ns}", token=token)
    private = None
    for b in lst or []:
        if b.get("id") == f"{ns}/{name}" or b.get("name") == name:
            private = bool(b.get("private"))
    if private is not True:
        hfx.die(f"bucket {ns}/{name}: private=True could not be verified "
                f"(got {private!r}) — refusing to upload; check it manually at "
                f"{hfx.HF}/buckets/{ns}/{name}", hfx.EXIT_FAIL)
    return created


def _repo_tree(token: str, repo_id: str) -> dict:
    """{path: entry} for every file on main (recursive, cursor-paginated ≤1000/
    page). Entry: {"type","oid","size","path","lfs":{"oid","size"},"xetHash"}."""
    entries: dict = {}
    url = (f"{hfx.HF}/api/datasets/{repo_id}/tree/main"
           f"?recursive=true&limit=1000&expand=false")
    while url:
        st, hs, raw = hfx.http("GET", url, token=token)
        if st != 200:
            hfx.die(f"tree of {repo_id} -> {st}: {raw[:200]!r}", hfx.EXIT_FAIL)
        try:
            page = hfx.json.loads(raw)
        except ValueError:
            hfx.die(f"tree of {repo_id}: non-JSON response", hfx.EXIT_FAIL)
        if isinstance(page, dict):  # tolerate both shapes
            page = page.get("files") or page.get("tree") or []
        for e in page:
            entries[e.get("path", "")] = e
        nxt = ""
        for part in (hs.get("Link") or "").split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip().strip("<>")
        url = nxt
        if url:
            time.sleep(1)  # API pacing between pages
    return entries


def _lfs_files(token: str, repo_id: str) -> dict:
    """{filename: sha256} for EVERY LFS object in the repo — including files
    already deleted from the tip (still billing quota from git history).
    Endpoint: GET /api/datasets/{ns}/{repo}/lfs-files (live-verified: lists
    history-only objects with fileOid = sha256)."""
    _, lst, _ = hfx.api("GET", f"/api/datasets/{repo_id}/lfs-files", token=token)
    out = {}
    for f in lst or []:
        oid = f.get("fileOid") or (f.get("lfs") or {}).get("oid")
        if oid and f.get("filename"):
            out[f["filename"]] = oid
    return out


def _commit_delete(token: str, repo_id: str, paths: list[str], msg: str):
    """Delete file(s) from the repo tip via huggingface_hub CommitOperationDelete.
    NOTE: LFS history keeps the bytes (and quota) — use --purge-lfs to reclaim."""
    hfx.require_py([("huggingface_hub", "huggingface_hub<2.0")])
    from huggingface_hub import CommitOperationDelete, HfApi
    HfApi(token=token).create_commit(
        repo_id=repo_id, repo_type="dataset",
        operations=[CommitOperationDelete(path_in_repo=p) for p in paths],
        commit_message=msg)


def _parse_resolve_target(a, token: str) -> tuple[str, str, str]:
    """TARGET positional → (repo_id, revision, path_in_repo)."""
    tgt = a.target
    if tgt.startswith("http://") or tgt.startswith("https://"):
        seg = [s for s in urlparse(tgt).path.split("/") if s]
        if seg and seg[0] in ("datasets", "models", "spaces"):
            seg = seg[1:]
        if len(seg) < 5 or seg[2] != "resolve":
            hfx.die(f"not a resolve URL: {tgt}\n  expected "
                    f"https://huggingface.co/datasets/<ns>/<repo>/resolve/<rev>/<path>",
                    hfx.EXIT_CONFIG)
        if a.path:
            hfx.die("PATH is not needed when TARGET is a full resolve URL",
                    hfx.EXIT_CONFIG)
        repo_id, rev, path = f"{seg[0]}/{seg[1]}", seg[3], "/".join(seg[4:])
        if not path:
            hfx.die(f"URL has no file path after revision '{rev}'", hfx.EXIT_CONFIG)
        return repo_id, rev, path
    if not a.path:
        hfx.die("PATH is required when TARGET is a repo id — e.g. "
                "`hfx store get my-user/my-repo data/file.bin` — or pass a full "
                "resolve URL as TARGET", hfx.EXIT_CONFIG)
    return _full_repo(tgt, _resolve_ns(a, token)), "main", a.path


def _next(label: str, cmd: str):
    print(f"  {label:<11} {cmd}")


# ------------------------------------------------------------------ put

def cmd_put(a, ctx) -> int:
    env, token = ctx["env"], hfx.need_token(ctx["env"])
    src = a.file
    if not os.path.isfile(src):
        hfx.die(f"no such file: {src}", hfx.EXIT_CONFIG)
    if a.bucket and a.public:
        hfx.die("--bucket and --public are mutually exclusive (buckets are "
                "forced private by this command)", hfx.EXIT_CONFIG)
    if a.bucket and a.repo:
        hfx.die("--bucket and --repo are mutually exclusive", hfx.EXIT_CONFIG)
    size = os.path.getsize(src)
    path_in = a.path or os.path.basename(os.path.abspath(src))

    # ---- bucket path (S3, auto-multipart, deletable storage)
    if a.bucket:
        ns = _resolve_ns(a, token)
        created = _ensure_bucket(token, ns, a.bucket)
        client = _s3(env, ns)
        t0 = time.time()
        _s3_guard(f"upload {path_in}", client.upload_file, src, a.bucket, path_in,
                  bucket=a.bucket, key=path_in)
        sec = time.time() - t0
        out = {
            "op": "put", "target": "bucket", "bucket": a.bucket, "entity": ns,
            "key": path_in, "bytes": size, "elapsed_s": round(sec, 2),
            "throughput_mbps": round(_mbps(size, sec), 2), "private": True,
            "transfer": "S3 upload_file (auto-multipart >=8MB, 8MB x 10 threads)",
            "object_url": f"{hfx.S3_ENDPOINT}/{ns}/{a.bucket}/{path_in}",
            "bucket_url": f"{hfx.HF}/buckets/{ns}/{a.bucket}",
            "bucket_created": created,
            "get_cmd": f"hfx store get {path_in} --bucket {a.bucket}",
            "share_cmd": f"hfx store share {path_in} --bucket {a.bucket} --ttl 3600",
        }
        if ctx["json"]:
            hfx.jprint(out)
            return hfx.EXIT_OK
        print(f"hfx store put — bucket {ns}/{a.bucket} "
              f"({'created on demand' if created else 'already there'}, private)")
        print(f"  key        {path_in}")
        print(f"  bytes      {size:,} ({hfx.human_bytes(size)})")
        print(f"  elapsed    {sec:.2f} s ({_mbps(size, sec):.2f} MB/s)")
        print(f"  transfer   {out['transfer']}")
        print(f"  object     {out['object_url']}   (S3-authed)")
        print(f"  bucket     {out['bucket_url']}")
        print("NEXT STEPS")
        _next("get back", f"hfx store get {path_in} --bucket {a.bucket} "
                          f"--out {os.path.basename(path_in)}")
        _next("share", f"hfx store share {path_in} --bucket {a.bucket} --ttl 3600"
                       "   # anon presigned URL (SigV4)")
        return hfx.EXIT_OK

    # ---- repo path (dataset; Xet upload, size-selected)
    name = a.repo or (PUBLIC_REPO if a.public else DEFAULT_REPO)
    if "/" in name:
        repo_id = name
    else:
        repo_id = f"{_resolve_ns(a, token)}/{name}"
    private = not a.public
    transfer = "hub upload_file (Xet)"
    if size >= BIG_BYTES:
        # must be set BEFORE huggingface_hub is imported (constants read at import)
        os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"
        transfer = "hub upload_file + HF_XET_HIGH_PERFORMANCE=1 (1.36x, measured)"
    hfx.require_py([("huggingface_hub", "huggingface_hub<2.0")])
    from huggingface_hub import HfApi
    api = HfApi(token=token)

    existed = api.repo_exists(repo_id=repo_id, repo_type="dataset")
    if not existed:
        api.create_repo(repo_id=repo_id, repo_type="dataset", private=private,
                        exist_ok=True)
    else:
        try:  # best-effort visibility sync (e.g. pre-existing repo + --public)
            api.update_repo_visibility(repo_id=repo_id, private=private,
                                       repo_type="dataset")
        except Exception:  # noqa: BLE001 — visibility may already match
            pass
    time.sleep(1)  # API pacing

    t0 = time.time()
    try:
        api.upload_file(path_or_fileobj=src, path_in_repo=path_in,
                        repo_id=repo_id, repo_type="dataset",
                        commit_message=f"hfx store put {path_in}")
    except Exception as e:  # noqa: BLE001
        hfx.die(f"upload failed: {str(e).splitlines()[0][:300]}", hfx.EXIT_FAIL)
    sec = time.time() - t0

    resolve = f"{hfx.HF}/datasets/{repo_id}/resolve/main/{path_in}"
    page = f"{hfx.HF}/datasets/{repo_id}/blob/main/{path_in}"
    out = {
        "op": "put", "target": "repo", "repo_id": repo_id, "path": path_in,
        "bytes": size, "elapsed_s": round(sec, 2),
        "throughput_mbps": round(_mbps(size, sec), 2), "private": private,
        "transfer": transfer, "repo_created": not existed,
        "file_url": page, "resolve_url": resolve,
        "get_cmd": f"hfx store get {repo_id} {path_in}",
    }
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store put — dataset {repo_id} "
          f"({'private' if private else 'PUBLIC'}, "
          f"{'created on demand' if not existed else 'already there'})")
    print(f"  path       {path_in} @ main")
    print(f"  bytes      {size:,} ({hfx.human_bytes(size)})")
    print(f"  elapsed    {sec:.2f} s ({_mbps(size, sec):.2f} MB/s)")
    print(f"  transfer   {transfer}")
    if private:
        print(f"  file page  {page}   (authed)")
        print(f"  resolve    {resolve}   (authed)")
    else:
        print(f"  resolve    {resolve}")
        print("             anonymous CDN URL — add ?download=true for attachment;"
              " range/ETag supported")
    print("NEXT STEPS")
    _next("get back", f"hfx store get {repo_id} {path_in} "
                      f"--out {os.path.basename(path_in)}")
    if private:
        _next("public link", f"re-put with --public (8.7TB pool), or use --bucket "
                             "+ `hfx store share` for expiring links")
    else:
        _next("fetch anon", f"curl -L -o {os.path.basename(path_in)} '{resolve}'")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ get

def cmd_get(a, ctx) -> int:
    env, token = ctx["env"], hfx.need_token(ctx["env"])
    t0 = time.time()
    if a.bucket:
        if a.path:
            hfx.die("with --bucket, pass the object KEY as the single positional "
                    f"(got extra PATH '{a.path}')", hfx.EXIT_CONFIG)
        ns = _resolve_ns(a, token)
        key = a.target
        out_file = a.out or os.path.basename(key) or "download"
        client = _s3(env, ns)
        _s3_guard(f"download {key}", client.download_file, a.bucket, key, out_file,
                  bucket=a.bucket, key=key)
        src_desc = f"bucket {ns}/{a.bucket}"
    else:
        repo_id, rev, path = _parse_resolve_target(a, token)
        hfx.require_py([("huggingface_hub", "huggingface_hub<2.0")])
        from huggingface_hub import hf_hub_download
        try:
            local = hf_hub_download(repo_id=repo_id, filename=path,
                                    repo_type="dataset", revision=rev, token=token)
        except Exception as e:  # noqa: BLE001
            hfx.die(f"download failed: {str(e).splitlines()[0][:300]}",
                    hfx.EXIT_FAIL)
        out_file = a.out or local
        if a.out:
            shutil.copyfile(local, a.out)
        src_desc = f"dataset {repo_id}@{rev}"
    sec = time.time() - t0
    size = os.path.getsize(out_file)
    digest = _sha256(out_file)
    out = {
        "op": "get", "source": src_desc, "path": a.target, "out": out_file,
        "bytes": size, "elapsed_s": round(sec, 2),
        "throughput_mbps": round(_mbps(size, sec), 2), "sha256": digest,
    }
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store get — {src_desc} / {a.path or ''}".rstrip(" /"))
    print(f"  saved      {os.path.abspath(out_file)}")
    print(f"  bytes      {size:,} ({hfx.human_bytes(size)})")
    print(f"  elapsed    {sec:.2f} s ({_mbps(size, sec):.2f} MB/s)")
    print(f"  sha256     {digest}")
    print(f"NEXT STEP    verify: sha256sum {os.path.basename(out_file)}")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ ls

def cmd_ls(a, ctx) -> int:
    env, token = ctx["env"], hfx.need_token(ctx["env"])

    if a.repo and a.bucket:
        hfx.die("--repo and --bucket are mutually exclusive", hfx.EXIT_CONFIG)

    # ---- repo files
    if a.repo:
        ns = _resolve_ns(a, token)
        repo_id = _full_repo(a.repo, ns)
        hfx.require_py([("huggingface_hub", "huggingface_hub<2.0")])
        from huggingface_hub import HfApi
        try:
            files = sorted(HfApi(token=token).list_repo_files(
                repo_id=repo_id, repo_type="dataset"))
        except Exception as e:  # noqa: BLE001
            hfx.die(f"list {repo_id} failed: {str(e).splitlines()[0][:300]}",
                    hfx.EXIT_FAIL)
        if ctx["json"]:
            hfx.jprint({"op": "ls", "repo_id": repo_id, "files": files})
            return hfx.EXIT_OK
        print(f"hfx store ls — dataset {repo_id} ({len(files)} files)")
        for f in files:
            print(f"  {f}")
        print(f"\nNEXT STEP   get one: hfx store get {repo_id} <path> --out <file>")
        return hfx.EXIT_OK

    # ---- bucket objects (ListObjectsV2 — the only list op the gateway supports)
    if a.bucket:
        ns = _resolve_ns(a, token)
        client = _s3(env, ns)
        objs = []
        pg = client.get_paginator("list_objects_v2")
        for page in _s3_guard("list_objects_v2",
                              lambda: list(pg.paginate(Bucket=a.bucket)),
                              bucket=a.bucket):
            objs.extend(page.get("Contents", []))
        objs.sort(key=lambda o: o["Key"])
        if ctx["json"]:
            hfx.jprint({"op": "ls", "bucket": a.bucket, "entity": ns,
                        "objects": [{"key": o["Key"], "bytes": o["Size"],
                                     "last_modified": o["LastModified"].isoformat()
                                     + "Z"} for o in objs]})
            return hfx.EXIT_OK
        total = sum(o["Size"] for o in objs)
        print(f"hfx store ls — bucket {ns}/{a.bucket} "
              f"({len(objs)} objects, {hfx.human_bytes(total)})")
        for o in objs:
            lm = o["LastModified"].strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"  {hfx.human_bytes(o['Size']):>10}  {lm}  {o['Key']}")
        print(f"\nNEXT STEP   get one: hfx store get <key> --bucket {a.bucket} "
              f"--out <file>")
        return hfx.EXIT_OK

    # ---- default: everything in the namespace
    ns = _resolve_ns(a, token)
    _, repos, _ = hfx.api("GET", f"/api/datasets?author={ns}", token=token)
    time.sleep(1)  # API pacing
    _, buckets, _ = hfx.api("GET", f"/api/buckets/{ns}", token=token)
    repos = sorted(repos or [], key=lambda r: r.get("id", ""))
    buckets = sorted(buckets or [], key=lambda b: b.get("id", ""))
    if ctx["json"]:
        hfx.jprint({"op": "ls", "entity": ns, "repos": repos, "buckets": buckets})
        return hfx.EXIT_OK
    print(f"hfx store ls — entity {ns}")
    print(f"  dataset repos ({len(repos)}):")
    for r in repos:
        print(f"    {r.get('id', '?'):60} {r.get('lastModified', '')[:19]}")
    print(f"  buckets ({len(buckets)}):")
    for b in buckets:
        print(f"    {b.get('id', '?'):60} "
              f"{hfx.human_bytes(b.get('size', 0)):>10} "
              f"{'private' if b.get('private') else 'PUBLIC'}")
    print("\nNEXT STEP   files in one: hfx store ls --repo <name> | "
          "hfx store ls --bucket <name>")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ rm

def cmd_rm(a, ctx) -> int:
    env, token = ctx["env"], hfx.need_token(ctx["env"])
    if not a.repo and not a.bucket:
        hfx.die("need --repo NAME (repo files) or --bucket B (bucket objects)",
                hfx.EXIT_CONFIG)
    if a.repo and a.bucket:
        hfx.die("--repo and --bucket are mutually exclusive", hfx.EXIT_CONFIG)

    # ---- bucket objects: delete_objects, quota frees ≤90s (measured 15-90s)
    if a.bucket:
        ns = _resolve_ns(a, token)
        client = _s3(env, ns)
        keys = list(dict.fromkeys(a.paths))  # dedupe, keep order
        if len(keys) > 1000:
            hfx.die("delete_objects takes <=1000 keys per call; "
                    f"got {len(keys)}", hfx.EXIT_CONFIG)
        resp = _s3_guard("delete_objects", client.delete_objects,
                         Bucket=a.bucket, bucket=a.bucket,
                         Delete={"Objects": [{"Key": k} for k in keys]})
        deleted = [d.get("Key") for d in resp.get("Deleted", [])]
        errors = resp.get("Errors", [])
        out = {"op": "rm", "bucket": a.bucket, "entity": ns,
               "requested": keys, "deleted": deleted, "errors": errors}
        if ctx["json"]:
            hfx.jprint(out)
            return hfx.EXIT_OK
        print(f"hfx store rm — bucket {ns}/{a.bucket}: "
              f"deleted {len(deleted)}/{len(keys)} object(s)")
        for k in deleted:
            print(f"  deleted  {k}")
        for e in errors:
            print(f"  ERROR    {e.get('Key')}: {e.get('Message')}")
        print("  quota     frees within ~90s (bucket deletes are near-immediate; "
              "verify: hfx status)")
        return hfx.EXIT_FAIL if errors else hfx.EXIT_OK

    # ---- repo files
    ns = _resolve_ns(a, token)
    repo_id = _full_repo(a.repo, ns)
    paths = list(dict.fromkeys(a.paths))

    if a.purge_lfs:
        # shas from the LFS index (covers files already tip-deleted but still
        # billing quota from history) + tree for plain git blobs
        lfs = _lfs_files(token, repo_id)
        time.sleep(1)  # API pacing
        tree = _repo_tree(token, repo_id)
        shas, regular = [], []
        for p in paths:
            if p in lfs:
                shas.append(lfs[p])
            elif p in tree and not tree[p].get("lfs"):
                regular.append(p)  # plain git blob → normal commit delete
            else:
                hfx.die(f"'{p}' not found in {repo_id} — list with: "
                        f"hfx store ls --repo {a.repo}", hfx.EXIT_CONFIG)
        if regular:
            _commit_delete(token, repo_id, regular, f"hfx store rm (purge) {regular}")
            time.sleep(1)  # API pacing
        if shas:
            hfx.api("POST", f"/api/datasets/{repo_id}/lfs-files/batch",
                    token=token,
                    json_body={"deletions": {"sha": shas, "rewriteHistory": True}})
        out = {"op": "rm", "repo_id": repo_id, "paths": paths,
               "lfs_purged_shas": shas, "regular_deleted": regular,
               "note": "history rewrite settles in ~25-80s; quota freed after"}
        if ctx["json"]:
            hfx.jprint(out)
            return hfx.EXIT_OK
        print(f"hfx store rm — dataset {repo_id} (purge-lfs)")
        for p in paths:
            print(f"  removed   {p}")
        print(f"  lfs       {len(shas)} object(s) batch-deleted with "
              "rewriteHistory:true — quota reclaims in ~25-80s")
        print("  verify    hfx status   (or: hfx store ls --repo "
              f"{a.repo} → should be gone)")
        return hfx.EXIT_OK

    _commit_delete(token, repo_id, paths, f"hfx store rm {paths}")
    out = {"op": "rm", "repo_id": repo_id, "paths": paths,
           "note": "tip-only delete; LFS history keeps quota — use --purge-lfs"}
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store rm — dataset {repo_id}")
    for p in paths:
        print(f"  removed   {p} (from main; history keeps the bytes)")
    print("  quota     NOT freed yet — LFS history retains deleted files; "
          "re-run with --purge-lfs to rewrite history and reclaim")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ rm-bucket

def cmd_rm_bucket(a, ctx) -> int:
    """Delete a whole bucket via DELETE /api/buckets/{ns}/{name} (204).
    U1 friction #1: put --bucket creates the only kit resource the CLI
    couldn't remove. Refuses non-empty buckets unless --force."""
    env, token = ctx["env"], hfx.need_token(ctx["env"])
    ns = _resolve_ns(a, token)

    # existence check via the namespace bucket list (the only bucket read)
    _, buckets, _ = hfx.api("GET", f"/api/buckets/{ns}", token=token)
    info = next((b for b in buckets or []
                 if b.get("id") == f"{ns}/{a.name}" or b.get("name") == a.name),
                None)
    if info is None:
        hfx.die(f"bucket {ns}/{a.name} not found — list what exists with: "
                f"hfx store ls", hfx.EXIT_CONFIG)
    time.sleep(1)  # API pacing

    # refuse if not empty (list_objects first) unless --force
    client = _s3(env, ns)
    objs = []
    pg = client.get_paginator("list_objects_v2")
    for page in _s3_guard("list_objects_v2",
                          lambda: list(pg.paginate(Bucket=a.name)),
                          bucket=a.name):
        objs.extend(page.get("Contents", []))
    if objs and not a.force:
        total = sum(o["Size"] for o in objs)
        hfx.die(f"bucket {ns}/{a.name} still holds {len(objs)} object(s) "
                f"({hfx.human_bytes(total)}) — empty it first: "
                f"hfx store rm <key> --bucket {a.name}   "
                f"(or --force to delete objects + bucket in one go)",
                hfx.EXIT_FAIL)
    n_deleted = 0
    if objs:  # --force: delete objects first (S3 buckets refuse non-empty deletes)
        keys = [o["Key"] for o in objs]
        for i in range(0, len(keys), 1000):  # delete_objects cap: 1000/call
            _s3_guard("delete_objects", client.delete_objects, Bucket=a.name,
                      bucket=a.name,
                      Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]]})
            n_deleted += len(keys[i:i + 1000])
        time.sleep(1)  # API pacing

    # hfx.api defaults expect=(200, 201, 204) — DELETE returns 204 (U1 #2)
    hfx.api("DELETE", f"/api/buckets/{ns}/{a.name}", token=token)
    out = {"op": "rm-bucket", "bucket": a.name, "entity": ns,
           "objects_deleted": n_deleted, "forced": bool(a.force),
           "note": "bucket deleted; quota frees within ~90s (verify: hfx status)"}
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store rm-bucket — bucket {ns}/{a.name} deleted")
    if n_deleted:
        print(f"  objects    {n_deleted} deleted first (--force)")
    print("  quota      frees within ~90s (bucket deletes are near-immediate; "
          "verify: hfx status)")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ share

def cmd_share(a, ctx) -> int:
    env, token = ctx["env"], hfx.need_token(ctx["env"])
    ns = _resolve_ns(a, token)
    client = _s3(env, ns)
    head = _s3_guard("head_object", client.head_object, Bucket=a.bucket,
                     Key=a.key, bucket=a.bucket, key=a.key)
    size = head.get("ContentLength", 0)
    # SigV4 is forced in _s3() — SigV2 presign gets 403 SignatureDoesNotMatch
    url = client.generate_presigned_url(
        "get_object", {"Bucket": a.bucket, "Key": a.key}, ExpiresIn=a.ttl)
    expires = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(time.time() + a.ttl))
    out = {"op": "share", "bucket": a.bucket, "entity": ns, "key": a.key,
           "bytes": size, "ttl_s": a.ttl, "expires_at": expires, "url": url,
           "verify_cmd": f"curl -L -o /dev/null -w '%{{http_code}}\\n' '<url>'"}
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store share — {ns}/{a.bucket}/{a.key} "
          f"({hfx.human_bytes(size)})")
    print(f"  expires    {expires} (ttl {a.ttl}s; 403 after expiry — enforced)")
    print(f"  url        {url}")
    print("             presigned SigV4 — anonymous GET works (302 → CDN); "
          "treat the URL like a password")
    print("NEXT STEP    anon fetch: curl -L -o out.bin '<url>'")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ cp-repo

def cmd_cp_repo(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    if "/" in a.src and "/" in a.dst:
        ns = None
    else:
        ns = _resolve_ns(a, token)
    src = a.src if "/" in a.src else f"{ns}/{a.src}"
    dst = a.dst if "/" in a.dst else f"{ns}/{a.dst}"
    body = {"repository": dst}  # target must be FULL ns/name
    if a.private:
        body["private"] = True
    t0 = time.time()
    _, resp, _ = hfx.api("POST", f"/api/datasets/{src}/duplicate",
                         token=token, json_body=body)
    api_sec = time.time() - t0
    time.sleep(2)  # API pacing + give the server-side copy a beat
    _, st, _ = hfx.api("GET", f"/api/datasets/{dst}/duplicate/status",
                       token=token)
    pending = (st or {}).get("pending")
    out = {"op": "cp-repo", "src": src, "dst": dst, "private": a.private,
           "duplicate_api_s": round(api_sec, 2), "pending": pending,
           "url": (resp or {}).get("url") or f"{hfx.HF}/datasets/{dst}",
           "note": "Xet-hash server-side migration: instant even for huge repos "
                   "(341MB measured in 0.82s) BUT counts toward quota (no dedup "
                   "discount across repos)",
           "delete_cmd": (f"curl -X DELETE -H 'Authorization: Bearer $HF_TOKEN' "
                          f"{hfx.HF}/api/repos/delete "
                          f"-H 'Content-Type: application/json' "
                          f"-d '{{\"type\":\"dataset\",\"name\":\"{dst.split('/', 1)[1]}\"}}'")}
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store cp-repo — {src} → {dst}")
    print(f"  duplicate  {api_sec:.2f} s (server-side Xet migration)"
          + (" + ~2s settle" if not pending else ""))
    print(f"  pending    {pending} (filesCopyPending)")
    print(f"  url        {out['url']}")
    print("  quota      the copy COUNTS toward your quota (dedup saves wire, "
          "not bytes)")
    print(f"  visibility {'private' if a.private else 'inherited (default public)'}")
    print("NEXT STEPS")
    _next("list", f"hfx store ls --repo {dst}")
    _next("delete", out["delete_cmd"])
    return hfx.EXIT_OK


# ------------------------------------------------------------------ tag

def cmd_tag(a, ctx) -> int:
    token = hfx.need_token(ctx["env"])
    repo_id = _full_repo(a.repo, _resolve_ns(a, token))

    if a.delete:
        hfx.api("DELETE", f"/api/datasets/{repo_id}/tag/{a.tag}", token=token)
        out = {"op": "tag", "repo_id": repo_id, "tag": a.tag, "deleted": True}
        if ctx["json"]:
            hfx.jprint(out)
            return hfx.EXIT_OK
        print(f"hfx store tag — deleted tag '{a.tag}' from {repo_id}")
        return hfx.EXIT_OK

    msg = a.message or (f"pinned by hfx store tag "
                        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    hfx.api("POST", f"/api/datasets/{repo_id}/tag/{a.rev}", token=token,
            json_body={"tag": a.tag, "message": msg})
    pattern = f"{hfx.HF}/datasets/{repo_id}/resolve/{a.tag}/<path>"
    out = {"op": "tag", "repo_id": repo_id, "tag": a.tag, "rev": a.rev,
           "message": msg, "resolve_pattern": pattern,
           "note": "tags = free versioned asset URLs; files resolve at the "
                   "tagged commit forever (or until the tag is deleted)"}
    if ctx["json"]:
        hfx.jprint(out)
        return hfx.EXIT_OK
    print(f"hfx store tag — {repo_id}: '{a.rev}' pinned as '{a.tag}'")
    print(f"  message    {msg}")
    print(f"  resolve    {pattern}")
    print("             e.g. any file in the repo now resolves at the tagged "
          "commit — perfect for /releases/")
    print("NEXT STEPS")
    _next("list files", f"hfx store ls --repo {a.repo}")
    _next("fetch pinned", f"curl -L -o f '<{hfx.HF}/datasets/{repo_id}/resolve/{a.tag}/file.bin>'")
    _next("delete tag", f"hfx store tag {a.repo} {a.tag} --delete")
    return hfx.EXIT_OK


# ------------------------------------------------------------------ parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hfx store",
        description="durable storage & sharing on HuggingFace free storage — "
                    "dataset repos (versioned, CDN) + S3 buckets (deletable), "
                    "100GB private / 8.7TB public per entity, 500GB max file.",
        epilog="Measured paths & speeds: findings/storage-upload-benchmark.md · "
               "Full guide: kit/AGENTS.md §store",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="subcmd", metavar="COMMAND")

    def sp(name, help):
        s = sub.add_parser(name, prog=f"hfx store {name}", help=help,
                           description=help,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        s.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
        return s

    # ---- put
    s = sp("put", "upload a file durably — fastest path auto-selected by size")
    s.add_argument("file", help="local file to upload")
    s.add_argument("--repo", metavar="NAME",
                   help=f"dataset repo name (default {DEFAULT_REPO}; "
                        f"{PUBLIC_REPO} with --public). Bare name → your "
                        f"namespace; ns/name accepted")
    s.add_argument("--public", action="store_true",
                   help="PUBLIC repo (default name hfx-store-public, 8.7TB "
                        "best-effort pool) + prints the anonymous resolve CDN "
                        "URL. Default: private (100GB pool)")
    s.add_argument("--bucket", metavar="B",
                   help="S3 bucket instead of a repo — created on demand and "
                        "FORCED private (SDK mkdir creates PUBLIC buckets!). "
                        "Deletable storage; best for >5GB files (auto-multipart)")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.add_argument("--path", metavar="P",
                   help="path inside the repo/bucket (default: basename of FILE)")
    s.set_defaults(func=cmd_put)

    # ---- get
    s = sp("get", "download a file (repo id, resolve URL, or bucket key)")
    s.add_argument("target",
                   help="repo id (ns/name or bare name), OR a full resolve URL "
                        "(https://huggingface.co/datasets/ns/repo/resolve/rev/path), "
                        "OR the object KEY when --bucket is given")
    s.add_argument("path", nargs="?",
                   help="path within the repo (required unless TARGET is a URL; "
                        "not used with --bucket)")
    s.add_argument("--bucket", metavar="B", help="S3 bucket (TARGET = object key)")
    s.add_argument("--out", "-o", metavar="FILE",
                   help="output file (default: basename / hub-cache path)")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.set_defaults(func=cmd_get)

    # ---- ls
    s = sp("ls", "list storage: repo files, bucket objects, or everything")
    s.add_argument("--repo", metavar="NAME", help="list files of this dataset repo")
    s.add_argument("--bucket", metavar="B",
                   help="list objects of this S3 bucket (ListObjectsV2)")
    s.add_argument("--entity", metavar="NS",
                   help="user/org namespace (default: you; used when no "
                        "--repo/--bucket: lists all repos + buckets)")
    s.set_defaults(func=cmd_ls)

    # ---- rm
    s = sp("rm", "delete repo file(s) or bucket object(s)")
    s.add_argument("paths", nargs="+", metavar="PATH",
                   help="path(s) in the repo, or object key(s) with --bucket")
    s.add_argument("--repo", metavar="NAME", help="dataset repo to delete from")
    s.add_argument("--bucket", metavar="B",
                   help="S3 bucket to delete from (quota frees ≤90s)")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.add_argument("--purge-lfs", action="store_true",
                   help="ALSO batch-delete the LFS/Xet objects with "
                        "rewriteHistory:true (POST lfs-files/batch) — reclaims "
                        "quota in ~25-80s. Without it, deleting a repo file "
                        "keeps the bytes in git history (quota NOT freed)")
    s.set_defaults(func=cmd_rm)

    # ---- rm-bucket
    s = sp("rm-bucket", "delete a whole S3 bucket (refuses if not empty)")
    s.add_argument("name", help="bucket name (in your namespace; "
                    "--entity for an org)")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.add_argument("--force", action="store_true",
                   help="delete remaining objects too, then the bucket "
                        "(default: refuse while the bucket holds objects)")
    s.set_defaults(func=cmd_rm_bucket)

    # ---- share
    s = sp("share", "presigned SigV4 URL for a private bucket object")
    s.add_argument("key", help="object key in the bucket")
    s.add_argument("--bucket", metavar="B", required=True, help="S3 bucket")
    s.add_argument("--ttl", type=int, default=3600, metavar="S",
                   help="validity in seconds (default 3600; expiry is enforced)")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.set_defaults(func=cmd_share)

    # ---- cp-repo
    s = sp("cp-repo", "instant duplicate of a repo (server-side Xet migration)")
    s.add_argument("src", help="source repo (ns/name or bare name)")
    s.add_argument("dst", help="target repo (ns/name or bare name; created)")
    s.add_argument("--private", action="store_true",
                   help="make the copy private (default: inherited = public)")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.set_defaults(func=cmd_cp_repo)

    # ---- tag
    s = sp("tag", "pin a revision as a versioned asset URL (git tag)")
    s.add_argument("repo", help="dataset repo (ns/name or bare name)")
    s.add_argument("tag", help="tag name, e.g. v1.0.0")
    s.add_argument("--rev", default="main",
                   help="revision to tag (default: main)")
    s.add_argument("--message", metavar="MSG", help="tag message")
    s.add_argument("--delete", action="store_true",
                   help="delete the tag instead of creating it")
    s.add_argument("--entity", metavar="NS", help="user/org namespace (default: you)")
    s.set_defaults(func=cmd_tag)

    return p


# ------------------------------------------------------------------ dispatch

def run(argv: list[str], ctx: dict) -> int:
    p = build_parser()
    if not argv:
        print(p.format_help())
        return hfx.EXIT_OK
    a = p.parse_args(argv)
    if getattr(a, "json", False):
        ctx["json"] = True
    try:
        return a.func(a, ctx)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — consumer CLI: no tracebacks
        hfx.die(f"{a.subcmd}: {type(e).__name__}: "
                f"{str(e).splitlines()[0][:300] if str(e) else ''}",
                hfx.EXIT_FAIL)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], {"json": False, "env": hfx.load_env()}))
