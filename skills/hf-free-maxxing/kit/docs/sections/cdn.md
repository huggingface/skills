## cdn — instant media hosting (quota-free, PERMANENT)

`hfx cdn put FILE` → one POST to the web editor's `POST /uploads` surface →
a permanent CDN URL on `cdn-uploads.huggingface.co` (S3 + CloudFront) that is
**outside both the storage AND bandwidth quotas**. CORS `*`, HTTP Range
(video seeking works), content-type preserved, byte-identical downloads.

```bash
hfx cdn put ./photo.png
# → https://cdn-uploads.huggingface.co/production/uploads/<userId>/<key>.png

hfx cdn put ./clip.mp4 --json        # {"url": ..., "bytes": ..., "type": "video/mp4"}
hfx cdn put ./maybe.webm --check     # dry-run: sniff magic bytes, upload nothing
hfx cdn put ./doc.pdf                # → rejected LOCALLY (exit 2), zero rate-limit cost
```

| Limit | Value |
|---|---|
| Type allowlist (magic-byte sniffed, client **and** server) | GIF · JPEG/JPG · MOV · MP3 · MP4 · MPGA · PNG · QT · WAV · WEBM · WEBP |
| Size | ≥5 MiB verified (floor, not cap) — be a good citizen, self-cap ~5 MB |
| Auth | `HF_JWT` cookie → user-scoped URLs (`/production/uploads/<userId>/`); **no cookie = ANON lane** (`/production/uploads/noauth/`) — works without any account; a PAT is ignored (≠ web auth) |
| Rate limit | `pages` bucket: **200/5min** (cookie) · **100/5min** (anon); each upload ≈1–2 units; even server-rejected 415s cost a unit → the kit sniffs client-side FIRST |
| Lifetime | **PERMANENT — no delete endpoint exists. Never upload anything sensitive.** |
| URL shape | random 22-char key + extension; no custom names; identical re-uploads mint NEW URLs |

Notes:
* The server re-sniffs magic bytes — declaring `Content-Type: image/png` on
  random data gets a 415 (you can't smuggle arbitrary files).
* No `Cache-Control` (CloudFront default TTL) — treat URLs as immutable.
* Best for: blog/social images, generated media, static-site assets.
  For arbitrary files (zip/pdf/binaries) use `hfx store put` instead.

Evidence: findings/uploads-cdn-probe.md · live test: data/kit-tests/cdn-host-md/
