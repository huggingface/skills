<!-- SECTION:mcp -->
## MCP — the hosted agent API (huggingface.co/mcp)

HuggingFace hosts an MCP server at `https://huggingface.co/mcp` — plain
JSON-RPC 2.0 over POST, PAT Bearer auth (anonymous works for 4 read-only
tools, at lower rate limits). It is the single-protocol gateway to Hub search,
the Hub filesystem, **and free media compute** (ZeroGPU Spaces). Verified:
findings/mcp-probe.md, findings/review-compute-cluster.md.

```bash
hfx mcp tools                     # initialize + tools/list (the tool table)
hfx mcp call hf_whoami            # who am I / token role (free)
hfx mcp call dynamic_space --args-json '{"operation":"discover"}'
hfx mcp call dynamic_space --args-json '{"operation":"view_parameters","space_name":"ResembleAI/Chatterbox"}'
hfx mcp call dynamic_space --args-json '{"operation":"invoke","space_name":"mcp-tools/DeepSeek-OCR-experimental","parameters":"{\"image\":\"https://…/ocr.png\",\"model_size\":\"Tiny\",\"task_type\":\"Free OCR\"}"}'
hfx mcp resources                 # 155 skill:// Agent-Skills docs
hfx mcp resources --uri skill://huggingface-zerogpu/references/how-quota-works.md
```

**The 11-tool surface** (this account, all built-ins enabled; toggle at
<https://huggingface.co/settings/mcp> — the tool set applies to new sessions
immediately):

| Tool | Free? | What it does |
|---|---|---|
| `hf_whoami` | ✅ | auth context: account, orgs, credential role |
| `hf_fs` | ✅ | Hub filesystem: ls/cat/find/search over `hf://models\|datasets\|spaces\|collections\|papers\|docs`, 30 ops/call |
| `hub_repo_search` | ✅ | search models/datasets/Spaces with filters |
| `hub_repo_details` | ✅ | repo details + dataset structure/preview |
| `dynamic_space` | ✅ metadata / ⚠ invoke | discover (16 curated Spaces) + view_parameters are FREE; **every invoke = 1 ZeroGPU run (8/24h account-global — the binding limit)**; accepts ANY `mcp-server`-tagged Space, not just the curated ones |
| `hf_fs_write` | ✅ | put/rm files in repos+buckets, `--create-pr` (needs PAT write) |
| `hf_sandbox` | ❌ 402 | sandbox CRUD — needs PREPAID credits (free $0.10 inference credit does NOT count) |
| `hf_sandbox_exec` / `hf_sandbox_fs` | ❌ | shell + files INSIDE a (paid) sandbox |
| `hf_jobs` | ❌ 402 | Jobs API incl. cron scheduling — prepaid credits only |
| `gr1_z_image_turbo_generate` | ✅ quota-metered | Z-Image-Turbo image gen (account Space tool; measured 3.48 GPU-s/run) |

**Invoke gotchas (the #1 bugs):** `parameters` must be a **JSON-encoded
STRING**, not a nested object; file inputs are public URLs (HF dataset
`resolve/` URLs verified) or base64 data-URLs; unknown kwargs are
warned-then-passed-through and rejected at argument binding BEFORE GPU attach
($0, no run); outputs arrive as content blocks — download URL outputs
IMMEDIATELY (same session-bound rules as the GPU section).

**The sandbox verdict** (why hf_sandbox is ❌): `create` → 402 Payment
Required; the underlying Jobs API wants a prepaid balance. With credits it
would be the cheapest full-Linux agent compute on HF ($0.01/h cpu-basic,
per-minute billing) — but it is not free.

**skill:// resources** — 155 Agent-Skills docs (hf-cli, zerogpu quota
mechanics, training/eval recipes, AWS SageMaker deploy skills…) readable
with `hfx mcp resources --uri skill://…`. Free goldmine for any MCP client.

**Budget note:** MCP `dynamic_space` invokes and `hfx gpu run` hit the SAME
account-global ZeroGPU budget (8 runs + 300 GPU-s / rolling 24h — see the
GPU section). `$0` in inference credits either way.

**Evidence:** findings/mcp-probe.md (handshake, tool catalog, sandbox 402s,
skill:// resources) · findings/mcp-dynamic-spaces.md (16 curated Spaces +
measured costs) · findings/mcp-arbitrary-spaces.md (arbitrary-Space verdict,
mcp-server tag enumeration) · data/kit-tests/gpu-mcp/ (live K5 tests: 11
tools, 155 resources, discover).
<!-- /SECTION:mcp -->
