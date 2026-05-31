# Packaging any MCP server as a Docker Space

Concrete recipe for hosting an existing/non-Gradio MCP server (Node, Python, Go,
…) on a Hugging Face **Docker** Space. The HF Spaces docs cover Docker generally
(https://huggingface.co/docs/hub/spaces-sdks-docker) and the metadata fields
(https://huggingface.co/docs/hub/spaces-config-reference); this file fills the
MCP-specific gaps.

## 1. The server must serve HTTP

Expose a **Streamable HTTP** (preferred) or **SSE** MCP endpoint and listen on
`0.0.0.0:<port>`. stdio-only servers cannot be reached remotely — wrap them in
an HTTP transport first.

## 2. `README.md` metadata (this is the Space config)

The Space's `README.md` MUST start with a YAML block. `app_port` is the critical
one — HF routes external HTTPS to that container port (default 7860 if unset).
If it doesn't match your server's listen port, the build succeeds but nothing
connects.

```yaml
---
title: My MCP Server
emoji: 🛠️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 3000        # MUST equal the port your server listens on
pinned: false
short_description: <= 60 chars
---
```

## 3. Dockerfile (shape)

```dockerfile
FROM node:22-alpine          # or python:3.12-slim, etc.
WORKDIR /app
COPY . .
RUN <install deps> && <build>
ENV PORT=3000                # whatever your server reads; must match app_port
EXPOSE 3000
CMD ["<start your HTTP MCP server, bound to 0.0.0.0:$PORT>"]
```

Gotchas:
- Bind `0.0.0.0`, not `127.0.0.1`.
- Confirm which env var your server actually reads for the port (it is not always
  `PORT`) — set that one, and make it equal `app_port`.
- Mind your build tool's non-interactive/CI quirks (lockfile-frozen installs,
  ignored build scripts, etc.) — a Space build runs headless.

## 4. Create + deploy

```bash
hf repos create <user>/<space> --type space --space-sdk docker [--private]
# push code: either `git push` to the Space remote, or:
hf upload <user>/<space> . . --repo-type space    # or huggingface_hub.upload_folder
```

## 5. Config that doesn't go in the image

- **Secrets** (tokens, keys) and **variables** (non-secret config): set in the
  Space *Settings* (or `huggingface_hub.add_space_secret` / `add_space_variable`).
  Never bake secrets into the Dockerfile/image.
- **Persistent data or a shared catalog** (e.g. a skills bucket): mount a volume
  ```bash
  hf spaces volumes set <user>/<space> -v hf://buckets/<ns>/<bucket>:/mnt/data:ro
  ```
  then point your server at the mount path via a variable.

## 6. Access + auth

- URL: `https://<user>-<space>.hf.space/<mcp-endpoint>`.
- **Public** Space → open endpoint (anyone with the URL). **Private** Space →
  clients must send `Authorization: Bearer <hf_token>`; or wire "Sign in with HF"
  OAuth. Choose deliberately — a public MCP endpoint with a baked-in default
  token acts on that token's behalf for any caller.

## 7. Operational notes

- **Cold starts**: free CPU Spaces sleep after inactivity; set `sleep_time` or
  use paid hardware. First request after sleep is slow — clients may time out.
- **Stateless**: Spaces restart/scale; keep no in-memory state you can't lose,
  or persist to a mounted volume/bucket.
- **Logs/build**: watch the build + runtime logs (`hf spaces logs <space>
  [--build]`) — `BUILD_ERROR` usually means the Dockerfile; a running container
  that won't connect usually means `app_port`.

## Smoke test

Minimal MCP `initialize` over HTTP (add `Authorization: Bearer <token>` for a
private Space), confirm `serverInfo` + capabilities, then `tools/list` (and
`resources/list` if applicable). The MCP Inspector or a real client
(Claude Desktop, fast-agent) works too — but note some clients only consume
tools, not resources/skills.
