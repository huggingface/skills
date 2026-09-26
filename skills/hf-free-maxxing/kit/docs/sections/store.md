### store — durable storage & sharing

```bash
# durable upload — fastest path auto-selected by size (measured)
hfx store put ./mymodel.bin                      # private repo hfx-store (100GB pool)
hfx store put ./mymodel.bin --public             # public repo hfx-store-public (8.7TB pool)
# → https://huggingface.co/datasets/<you>/hfx-store-public/resolve/main/mymodel.bin  (anon CDN URL)
hfx store put ./big.bin --bucket my-bucket       # S3 bucket (created PRIVATE on demand)

# get it back (repo id, full resolve URL, or bucket key)
hfx store get <you>/hfx-store mymodel.bin --out mymodel.bin
hfx store get mymodel.bin --bucket my-bucket --out mymodel.bin

# list / delete
hfx store ls                                     # every repo + bucket in your namespace
hfx store ls --repo hfx-store                    # files (dataset repos)
hfx store ls --bucket my-bucket                  # objects (S3)
hfx store rm mymodel.bin --repo hfx-store --purge-lfs   # ALSO reclaims quota (history rewrite)
hfx store rm mymodel.bin --bucket my-bucket              # bucket delete frees quota ≤90s
hfx store rm-bucket my-bucket                     # delete the whole bucket (refuses if not empty)
hfx store rm-bucket my-bucket --force             # …or empty it first, then delete

# private sharing (expiring, anonymous-fetchable)
hfx store share mymodel.bin --bucket my-bucket --ttl 3600   # SigV4 presigned URL

# instant copy (server-side Xet migration — 341MB in 0.82s) + versioned pins
hfx store cp-repo src-repo dst-repo [--private]
hfx store tag hfx-store v1.0.0                   # → resolve/v1.0.0/<path> asset URLs
```

Path selection is automatic (`put`): <10MB → hub `upload_file` (Xet); ≥10MB → same
+ `HF_XET_HIGH_PERFORMANCE=1` (1.36× measured); `--bucket` → boto3 `upload_file`
(auto-multipart ≥8MB, 8MB×10 threads). `hf_transfer` is a deprecated no-op —
don't install it.

| Scenario | Winner | Measured | Gotchas |
|---|---|---|---|
| Small file public (<10MB) | hub `upload_file` | 10MB in 6.8s | ~4–5s fixed overhead; served on CDN instantly |
| Large public (10MB–5GB) | hub + `HF_XET_HIGH_PERFORMANCE=1` | 100MB in 22.6s (4.6MB/s) | hf_transfer never engages in hub ≥1.x |
| Huge (5–500GB) | S3 bucket + boto3 `upload_file` | 100MB in 30.3s | endpoint `https://s3.hf.co/<ns>` (per-namespace); `request_checksum_calculation='when_required'` |
| Private store | bucket via Hub API (forced private) | 10MB PUT 7.7s | SDK/rclone mkdir = PUBLIC — `hfx store` flips it |
| Private share | SigV4 presigned URL | anon 8.8MB/s via CDN | SigV2 presign → 403; expiry enforced |
| Instant copy | duplicate API (`cp-repo`) | 341MB in 0.82s | counts toward quota; default visibility public |
| Public serve | resolve URL on public repo | 6.8MB/s; 1MB range in 1.3s | anon 3000/5min per-IP; `?download=true` |
| Deletable storage | bucket (`rm --bucket`) | quota freed ≤90s | repo files need `--purge-lfs` to reclaim |
| Bucket teardown | `rm-bucket` (empty) / `rm-bucket --force` | delete → 204; quota ≤90s | refuses non-empty buckets unless `--force` (deletes objects first) |

**Limits:** 100GB private / 8.7TB public (best-effort) **per entity** (user + each
org — `hfx status` shows all pools). Max file 500GB. Buckets share the same pool.

**Gotchas (all handled by `hfx store`):**
1. **Public-bucket trap** — SDK/rclone `mkdir` creates buckets PUBLIC. The kit
   creates via Hub API and force-flips `PUT /api/buckets/{ns}/{name}/settings
   {"private":true}`, then verifies.
2. **Dedup ≠ quota** — Xet chunk dedup saves upload wire (13.7× re-uploads), but
   identical content in different repos/buckets bills separately (within one
   repo, identical LFS content counts once).
3. **Presigned URLs are SigV4-only** — boto3's default SigV2 presign gets 403
   `SignatureDoesNotMatch`. (`hfx store share` forces s3v4.)
4. **LFS history keeps quota** — `rm` on a repo file only deletes the tip; bytes
   stay in git history. `--purge-lfs` batch-deletes the LFS objects with
   `rewriteHistory:true` (quota back in ~25–80s). Whole-repo delete = `hfx etl rm`
   (≤60s); whole-bucket delete = `hfx store rm-bucket` (≤90s).
5. S3 creds: generate at settings/tokens → "Generate S3 credentials" (web
   session) → `HF_S3_ACCESS_KEY_ID`/`HF_S3_SECRET_ACCESS_KEY` in env or `.env`.

**Evidence:** findings/storage-upload-benchmark.md (all speeds) ·
findings/storage-probe.md (S3 gateway, duplicate API) ·
findings/review-storage-cluster.md (multipart, tags, LFS batch delete) ·
live-test transcripts: data/kit-tests/store/ (SUMMARY.md = verdict matrix)
