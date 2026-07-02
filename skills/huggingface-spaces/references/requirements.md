# requirements.txt for Spaces

Rules for what to pin, what to leave alone, where to source CUDA wheels, and which torch-side-cars drift silently.

## What's preinstalled (do not list)

The Gradio SDK base image already installs these on every hardware tier — listing them in `requirements.txt` causes resolution failures or, worse, lets pip silently drift the runtime out of compatibility:

| Package | Pinning rules |
|---|---|
| `gradio` | Don't list. Locked by `sdk_version:` in README frontmatter; pinning here is ignored or breaks. |
| `spaces` | Don't list. Platform-pinned; a user pin always loses. |
| `huggingface_hub` | Don't list by default. Pin only as a workaround for old `gradio<5` that imports the removed `HfFolder` symbol (see [`known-errors.md`](known-errors.md)). |
| `torch` | **Pinnable, but only within `{2.8.0, 2.9.1, 2.10.0, 2.11.0}`.** Anything outside causes `CONFIG_ERROR: torch version in requirements.txt is not compatible`. Default is to leave unpinned (runtime preinstalls 2.11), but pinning is appropriate when (a) a specific version is known-good for your model, (b) you're matching a CUDA-extension wheel's `torch2.X` tag, or (c) a dep would otherwise drag torch outside the supported set. When you pin torch, also pin `torchvision` / `torchaudio` to the matching minor — see the "Torch-family side-car drift" section below. |

## What to list

Everything you actually `import`, including the often-forgotten:

- `torchvision`, `torchaudio` — **not** preinstalled. Leave unpinned; pip resolves against the installed `torch` major.minor.
- `accelerate` — needed whenever you use `device_map=`. Listing it also silences `low_cpu_mem_usage=False` warnings.
- `sentencepiece` — required by most LLM tokenizers; rarely transitive.
- `einops` — required by `flash_attn.layers.rotary` and many model repos.
- Domain libs: `diffusers`, `transformers`, `safetensors`, `pillow`, `numpy`, etc.

If a research repo ships a Python package directory (`models/`, `pipeline/`, …), just upload the directory with the rest of the Space — the whole repo root is importable as `/home/user/app`. **Do not** try to reference local paths from `requirements.txt`.

## Pinning torch

ZeroGPU accepts only `2.8.0`, `2.9.1`, `2.10.0`, `2.11.0`. Default is unpinned (runtime preinstalls the latest). Pinning is fine — and sometimes warranted — within that set:

- A specific torch is known-good for your model (numerics, attention kernel availability, etc.).
- A direct-URL CUDA wheel encodes a `torch2.X` tag (see "Prebuilt CUDA wheels" below) — pin torch to match.
- A dep's `setup.py` would otherwise downgrade torch outside the supported set.

`2.8.0` is the safest fallback for old requirements that refuse modern torch. `2.10.0` / `2.11.0` is the sweet spot for new code. When you pin torch, also pin `torchvision` / `torchaudio` to the matching minor — see the side-car drift section.

When a dep would silently downgrade torch (e.g. some forks of `demucs`, `audiocraft` pin `torchaudio<2.1`), install the offender from `app.py` with `--no-deps` rather than pinning torch around it:

```python
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps",
                "git+https://github.com/facebookresearch/demucs"], check=True)
import spaces  # safe now — torch wasn't touched
```

List the offender's real runtime deps yourself in `requirements.txt`.

## Torch-family side-car drift

`torchvision`, `torchaudio`, `torchcodec` are built against a specific `torch` major.minor. Listing them unpinned **usually** works, but two known drift patterns:

- `torchaudio==2.11.0` (and later) **dropped its `Requires-Dist: torch==X.Y.Z` line**. With torch pinned to 2.10, pip silently resolves torchaudio to 2.11.0 and the import fails on ABI mismatch.
- `torchcodec` declares no torch dependency in PyPI metadata at all.

Verification after `pip install` or `uv lock --upgrade`:

```bash
curl -s https://pypi.org/pypi/<pkg>/<version>/json \
  | python3 -c "import json,sys,re; rd=json.load(sys.stdin)['info'].get('requires_dist') or []; \
                print('\n'.join(x for x in rd if re.match(r'^torch(?![a-z])', x)) or '(no torch constraint)')"
```

When PyPI is silent, fall back to the project's README compatibility table (torchcodec's lives at https://github.com/pytorch/torchcodec).

## Prebuilt CUDA wheels — the Blackwell wheels dataset

This is the **first** thing to reach for when a CUDA-extension package has no upstream wheel matching the ZeroGPU torch / CUDA / cxx11-abi cell. Prefer it over any runtime workaround (`pip install git+…` inside `@spaces.GPU`, committed stub packages, `sys.modules` injection, monkey-patch shims), all of which are slower, fragile, and eat `duration` budget. Canonical prebuilt sm_120 wheels:

> https://huggingface.co/datasets/multimodalart/zerogpu-blackwell-wheels

Wheels live at `wheels/<cell>/<wheel>`. A **cell** encodes torch × CUDA × Python as `pt<torch>-cu<cuda>-cp<pyver>`. Every cell ships the same seven packages:

`flash_attn` (two versions: `2.8.3` and `2.7.4.post1`), `xformers`, `pytorch3d`, `nvdiffrast`, `diff_gaussian_rasterization`, `torchmcubes`.

Current cells (12):

| torch | CUDA | Python cells available |
|---|---|---|
| 2.8.0 (`pt28`) | 12.8 | cp310, cp311, cp312 |
| 2.9.1 (`pt291`) | 12.8 | cp310 |
| 2.10.0 (`pt210`) | 12.8 / 13.0 | cp310 (cu128), cp312 (cu130) |
| 2.11.0 (`pt211`) | 13.0 | cp312, cp313 |
| 2.12.0 (`pt212`) | 13.0 | cp310, cp311, cp312, cp313 |

### Picking a cell

1. **Match `cp<pyver>` to your `python_version:`.** The wheels are cp-ABI-specific — a `cp310` wheel needs Python 3.10, `cp312` needs 3.12, etc. (`flash_attn` now ships cp310 **through** cp313, so this is a free choice, not a forced pin to 3.10 as in older versions of this doc.)
2. **The wheels are torch-minor-tolerant.** The `flash_attn` / `xformers` filenames encode no torch version, so a `pt212-cu130-cp310` wheel runs fine on the live torch-2.11 cp310 runtime. `flash_attn` ships cp310 through cp313, so the Python choice is free. Pick the highest-torch cell for your Python version unless you've pinned an older torch — then match it (torch 2.8 → a `pt28-cu128-cp3XX` cell).
3. **Copy the *exact* filename from the cell you pick.** The `xformers` build hash differs across cells (`0.0.34+3da0fc92…` on the cu130 / torch≥2.10 cells, `0.0.34+41531cee…` on the cu128 / torch 2.8–2.9 cells). Don't hardcode one filename across cells — list the cell (`hf download --repo-type dataset multimodalart/zerogpu-blackwell-wheels --include "wheels/<cell>/*"` or the Hub file browser) and copy what's there.

Reference by direct URL in `requirements.txt`:

```
https://huggingface.co/datasets/multimodalart/zerogpu-blackwell-wheels/resolve/main/wheels/<cell>/<wheel>
```

### Per-package status

Each package's version is constant across cells; only the `cp`/torch/CUDA tags in the filename change. The "instead of" column is the runtime workaround to avoid — the wheel is the clean path.

| Package | Instead of | Version + caveats |
|---|---|---|
| `flash_attn` | committing a `flash_attn/` stub package; `sys.modules["flash_attn"] = …` injection | **2.8.3** (default) or **2.7.4.post1** (repos that pin `flash-attn<2.8`). Ships **cp310–cp313**. Needs `einops` for `flash_attn.layers.rotary`. Built `FLASH_ATTN_CUDA_ARCHS=120` (sm_120 only). This is FlashAttention-**2** — FA3/FA4 do **not** run on sm_120 (no TMEM); see [`zerogpu.md`](zerogpu.md) → Attention backends. Its real `flash_attn_2_cuda` also satisfies xformers' `flash_attn_gpu` probe. |
| `xformers` | an MEA→SDPA monkey-patch shim; a Cutlass-force shim | **0.0.34** (`Requires: torch>=2.10`). **Build hash differs per cell** — copy the exact filename. Auto-dispatch picks FA2 (`fa2F`) on sm_120; classic Cutlass / FA3 reject sm_120 but auto-dispatch never selects them. |
| `pytorch3d` | a runtime `pip install git+…pytorch3d.git` inside `@spaces.GPU` | **0.7.9**. Needs `numpy`, `iopath`, `fvcore` listed. No torch pin in metadata; loads cleanly on torch 2.11. |
| `nvdiffrast` | a runtime build with `TORCH_CUDA_ARCH_LIST=12.0` | **0.4.0**. Needs `numpy`. `RasterizeGLContext` is a deprecation alias for `RasterizeCudaContext` — no headless-GL footgun. |
| `diff_gaussian_rasterization` | a runtime build from `graphdeco-inria/diff-gaussian-rasterization.git` | **Upstream Inria API only** (returns 2-tuple `(color, radii)`). Does NOT match the ashawkey fork (4-tuple incl. alpha+depth) used by `ashawkey/LGM`, `dylanebert/LGM-mini`, etc. Forks need their own wheel. |
| `torchmcubes` | a runtime `pip install git+…torchmcubes.git` | **0.1.0**. **sm_120 only** (no fatbin for older archs). Works on ZeroGPU / Blackwell; not portable to a dedicated T4 / L4 / A10G Space. |

### Pattern

Resolve the exact filenames from your chosen cell, then:

```
# requirements.txt  (cell = pt212-cu130-cp310 → needs python_version "3.10")
numpy
einops
https://huggingface.co/datasets/multimodalart/zerogpu-blackwell-wheels/resolve/main/wheels/pt212-cu130-cp310/flash_attn-2.8.3-cp310-cp310-linux_x86_64.whl
https://huggingface.co/datasets/multimodalart/zerogpu-blackwell-wheels/resolve/main/wheels/pt212-cu130-cp310/xformers-0.0.34+3da0fc92.d20260528-cp39-abi3-linux_x86_64.whl
```

```yaml
# README frontmatter — pin Python to match the wheel cell's cp tag
python_version: "3.10"
```

**Do not** install these from `@spaces.GPU` startup. A `subprocess.check_call` pip-install at first GPU acquire is strictly worse than the wheel URL — slower cold start, eats `duration` budget, breaks reproducibility, and the build sometimes exceeds the `@spaces.GPU(duration=1500)` cap.

### When you need a wheel that's not in the dataset

Three options, in preference order:

1. **kernels-community** — https://huggingface.co/kernels-community handles ABI matching for you. Often the simplest path; no version pinning needed.
2. **Upstream wheel matrix** — e.g. flash-attention's releases page ships a fairly complete `cu12 / torch / Python` matrix at https://github.com/Dao-AILab/flash-attention/releases. Pin `torch==X.Y.Z` in `requirements.txt` to match the wheel's `torch2.X` tag.
3. **Build it yourself and host on HF Hub.** Last resort — see [`debugging.md`](debugging.md) for the in-`@spaces.GPU` source-build pattern as a stopgap while a wheel is being built.

## Reading a CUDA wheel filename

```
flash_attn-2.8.3+cu130torch2.12cxx11abiFALSE-cp310-cp310-linux_x86_64.whl
```

| Tag | Meaning |
|---|---|
| `cu130` | CUDA major version (13.0) |
| `torch2.12` | torch major.minor the wheel was compiled against |
| `cxx11abiFALSE` | C++ stdlib ABI choice (`TRUE` or `FALSE`) |
| `cp310-cp310` | CPython version (3.10) |

ABI / symbol mismatches at any of these → `ImportError` on first import. Pin `torch` to match `torch2.X`. Set `python_version:` to match `cp3XX`.

## Don't pin `xformers`

Leave bare in `requirements.txt` (or use the prebuilt URL above). Pip picks the wheel matching your installed torch.

## Don't pin `spaces`

Even if a `uv export` produces it, exclude with `--no-emit-package spaces`. The platform always pins its own version.

## Specifically about Python version

Pinning `python_version:` is effectively required:

- ZeroGPU officially supports **3.10.13** and **3.12.12**.
- The runtime default is 3.10.
- Pinning to a `cp3XX` wheel matrix (e.g. `cp310` flash_attn wheel) forces matching Python.

Both `"3.12"` and `"3.12.12"` forms are accepted in YAML.
