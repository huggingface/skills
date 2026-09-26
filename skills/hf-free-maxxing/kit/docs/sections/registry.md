## registry — the free Docker pull-library (registry.hf.space)

Every **public Docker-SDK Space's built image** is pullable by any logged-in
user from `registry.hf.space` — a read-only mirror of Space builds. Think of
it as a free prebuilt-environment library: skip hours of Dockerfile builds by
pulling e.g. `enzostvs-deepsite` (426 MB, 9 layers) directly.

```bash
hfx registry login-cmd      # mints a 600s token + prints ready-to-run:
#   docker login registry.hf.space -u <you> -p <TOKEN>
#   docker pull registry.hf.space/enzostvs-deepsite:<tag>
hfx registry manifest enzostvs/deepsite   # tags, digest, config + layer sizes
```

`login-cmd` output (copy-paste):

```bash
docker login registry.hf.space -u <you> -p <minted-600s-token>
docker pull registry.hf.space/enzostvs-deepsite:cpu-0165c57
# prefer shell-history-safe:  docker login … --password-stdin <<< <token>
```

The token comes from the hub's Basic-auth mint endpoint
(`GET /api/registry/token?service=registry.hf.space`, **Basic** `:PAT` —
Bearer is 401, cookie silently mints an anonymous token). Your **PAT also
works directly as the docker password** (the registry realm echoes it back) —
handy for sessions longer than the token's 600 s.

Gotchas (all live-verified):
- **Read-only**: pushes 404 (`allow: GET,HEAD,OPTIONS`). You cannot host your
  own images here — for HF-built images, create a Docker Space (PRO-gated for
  young accounts; the kit's `host` module covers static instead).
- **Login mandatory even for public images** (anon → 401 everywhere).
- Image names are **hyphenated**: `owner/space` → `owner-space`. Tags look
  like `cpu-<shortsha>` (+ PR-build suffixes); `latest` usually doesn't exist
  — get one from `hfx registry manifest`.
- **Static and Gradio/ZeroGPU spaces have no images** (404 on tags/list);
  **secret-bearing Docker spaces 401** for non-authors. The 404 error carries
  a recovery hint (known-good example: `hfx registry manifest
  enzostvs/deepsite`). The real pre-flight is the Space's **sdk field**:
  `GET /api/spaces/{id}` → `.sdk == "docker"` ⇒ image exists;
  `gradio`/`static` ⇒ none. (`GET /api/spaces/{id}/registry-auth-check`
  only answers the secrets gate — `{"imageHasSecrets":false}` — and returns
  the same answer for a gradio Space that has no image at all.)
- Blob pulls 307 to 20-min presigned S3 URLs — don't cache them; images are
  ephemeral per Jobs docs ("can be lost to registry maintenance or a region
  move").
- The *containers product* (`registry.hf.co`, container repo type) is still
  dark-launched globally (flag `containers:false`, creation 403, dead DNS) —
  `login-cmd` targets the LIVE registry only.

Evidence: findings/containers-registry.md (auth matrix, pull round-trip,
availability matrix) · live tests: data/kit-tests/k7/
(login-cmd verified against `GET /v2/` ✓, deepsite manifest + static-404
negative ✓).
