---
name: deploy-mcp-server-on-hf
description: >-
  Deploy/host an MCP server on Hugging Face Spaces. Use when the user wants to
  publish an MCP server on HF, turn a Gradio app or Python tools into an MCP
  server, package an existing (Node/Python/etc.) HTTP/SSE MCP server as a Space,
  or choose between the Gradio-native and Docker paths. Covers the non-obvious
  parts (transport, app_port routing, private-Space auth, secrets, bucket
  mounts, cold starts) and points to the official docs instead of duplicating
  them.
---

# Deploy an MCP server on Hugging Face

Hugging Face **Spaces** are the way to host a long-running MCP server (Jobs are
ephemeral; Inference Endpoints are model-oriented). There are two paths — pick
by what the server *is*.

## Decision

| Situation | Path |
|---|---|
| Python functions/tools you want exposed as MCP tools | **A — Gradio Space (native MCP)** |
| An existing MCP server, or non-Python (Node, Go…), or you need full control of the endpoint/transport | **B — Docker Space** |
| You just want an existing **Gradio Space** as a tool (not to host a server) | Don't deploy anything — proxy it via `huggingface.co/mcp` / `hf-mcp-server` (see Pointers) |

Hard rule for both: a Space is reached over HTTP, so the server **must** speak
**Streamable HTTP** (preferred) or **SSE** (legacy). **stdio does not work
remotely.**

## Path A — Gradio Space (native MCP)

Lowest effort for Python. Gradio turns decorated functions (their type hints +
**docstrings** become the MCP tool schema) into MCP tools when you enable the
MCP server.

1. `requirements.txt` includes `gradio[mcp]`.
2. Enable it: `demo.launch(mcp_server=True)` (or env `GRADIO_MCP_SERVER=true`).
3. Create a **Gradio SDK** Space and push the code.

The MCP endpoint is published by Gradio (path + SSE/Streamable-HTTP details are
in the guide). **Do not re-derive these steps — follow the canonical guide:**
- Gradio guide: https://www.gradio.app/guides/building-mcp-server-with-gradio
- Course walkthrough: https://huggingface.co/learn/mcp-course/en/unit2/gradio-server
- Spaces-as-MCP overview: https://huggingface.co/docs/hub/en/spaces-mcp-servers

## Path B — Docker Space (any MCP server)

For an existing/other-language MCP server. This generic path is **not** written
up as an MCP guide, so the concrete recipe + gotchas live in
[references/docker-space-mcp.md](references/docker-space-mcp.md). Base Spaces
docs: https://huggingface.co/docs/hub/spaces-sdks-docker and the config
reference: https://huggingface.co/docs/hub/spaces-config-reference

The parts that bite (covered in the reference):
- **`app_port`** in the Space `README.md` metadata MUST match the port your
  server listens on (HF routes external traffic there; default is 7860). This
  is the #1 reason a deploy "builds but won't connect".
- Listen on `0.0.0.0`, not localhost.
- **Private vs public**: a private Space requires clients to send
  `Authorization: Bearer <hf_token>`; or use "Sign in with HF" OAuth.
- **Secrets** (tokens) vs **variables** (config) in Space settings — never bake
  tokens into the image.
- **Persistent data / shared catalogs** via volume/bucket mounts
  (`hf spaces volumes set … -v hf://buckets/<ns>/<bucket>:/mnt/…:ro`).
- **Cold starts**: free CPU Spaces sleep after inactivity — set `sleep_time` or
  use paid hardware; the first request after sleep is slow.
- Design **stateless** (Spaces restart/scale).

## Verify it

1. URL pattern: `https://<user>-<space>.hf.space/<mcp-endpoint>`.
2. Quick check — do an MCP `initialize` POST (curl/Python) and confirm
   `serverInfo` + the capabilities you expect; for a private Space include the
   `Authorization: Bearer` header. Or use the **MCP Inspector**, or point a real
   client (Claude Desktop config, fast-agent, etc.).
3. Client caveat worth knowing: some clients surface **tools** but not
   **resources/skills** (e.g. `fast-agent go` consumes tools only) — test with a
   client that exercises the surface you care about.

## Pointers (don't duplicate these — link/read them)

- Spaces as MCP servers: https://huggingface.co/docs/hub/en/spaces-mcp-servers
- HF MCP server / proxying Spaces as tools: https://huggingface.co/docs/hub/hf-mcp-server · https://huggingface.co/docs/hub/en/agents-mcp
- Gradio MCP: https://www.gradio.app/guides/building-mcp-server-with-gradio · https://huggingface.co/blog/gradio-mcp · https://huggingface.co/blog/gradio-mcp-servers
- MCP Course: https://huggingface.co/learn/mcp-course
- Docker Spaces: https://huggingface.co/docs/hub/spaces-sdks-docker · config: https://huggingface.co/docs/hub/spaces-config-reference
- MCP spec (transports): https://modelcontextprotocol.io
