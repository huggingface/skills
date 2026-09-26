## watch — events: webhooks, bucket change-feed, notifications

Three event surfaces, all free:

```bash
hfx watch webhooks ls        # your webhook inventory (PAT)
hfx watch webhooks add --url https://ntfy.sh/my-topic \
    --watch <you>/my-space          # PAT, no CSRF; rm --id N to delete
hfx watch bucket <you>/my-bucket --duration 30   # live change-feed SSE
hfx watch notifications     # your notification feed (PAT; --mark-all-read)
```

### Webhooks (CRUD + replay, 1000 triggers/24h per webhook)

`add` posts `{watched: [{type, name}], url, domains}` to
`POST /api/settings/webhooks` — watch **any** repo (not just yours); type
autodetected, or force with `--type space|model|dataset|bucket`; domains
`repo,discussion`. **Payload v3** on commit-style events:

```json
{"event":{"action":"update","scope":"repo.content"},
 "repo":{"type":"space","name":"…","url":{…},"headSha":"…"},
 "webhook":{"id":"…","version":3},
 "updatedRefs":[{"ref":"refs/heads/main","oldSha":"…","newSha":"…"}]}
```

- Receiver gotcha: HF's delivery workers **cannot resolve webhook.site**
  (DNS ENOTFOUND) — use ntfy.sh (verified) or your own endpoint. Read ntfy
  deliveries: `curl https://ntfy.sh/<topic>/json?poll=1&since=15m`.
- Failed deliveries auto-retry with backoff to the CURRENT url; replay needs
  the HTML-only activity page (`/settings/webhooks/{id}/activity`, cookie) —
  `logId` from there feeds `POST …/{id}/replay/{logId}`.
- Trigger one: `POST /api/spaces/{repo}/commit/main` (NDJSON, no `eof` record).

### Bucket change-feed (SSE — stop polling /tree)

`hfx watch bucket NS/NAME` streams `GET /api/buckets/{ns}/{name}/events`:
`ready {cursor}` first (replay done), then `changes {cursor, changes:
[{path, op: add|update|delete, size?, xetHash?}]}` — batches coalesced over
~200 ms, **~6-10 s after the actual upload**. `reset` = your `--cursor` is
older than the ~15-min server buffer (re-list); `reconnect` = server
restart/20-min mark — reconnect with the last cursor. A `: ping` comment
every 30 s. (Live demo: upload via S3 `s3.hf.co/<ns>` mid-stream → the change
lands in the window.)

### Notifications

`GET /api/notifications` (PAT works; cookie fallback) →
`{notifications[], count{view,all,unread}}` — discussion events, bot threads
(e.g. parquet-converter), job status. `--mark-all-read` →
`POST /api/notifications/mark-as-read`. Per-category settings exist but are
write-only (`PATCH /api/settings/notifications`, ≥20 booleans).

Evidence: findings/infra-probe.md §B (webhook CRUD/replay/payload, ntfy
recipe) · findings/storage-probe.md §4a (bucket SSE) ·
findings/review-identity-infra-cluster.md §C7 (notifications) ·
live tests: data/kit-tests/k7/ (add→ls→rm cycle on the test space ✓,
bucket SSE with a live S3-upload change event ✓, notifications 2 unread ✓).
