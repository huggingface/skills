# CUDA extensions for 3D Spaces on ZeroGPU

General ZeroGPU rules live in [`zerogpu.md`](zerogpu.md); wheel-tag anatomy and the prebuilt Blackwell wheel dataset live in [`requirements.md`](requirements.md). This file covers what makes 3D generation models harder than diffusion image models: native CUDA/C++ extensions and heavyweight multi-stage pipelines.

## The core constraint: no nvcc at build time

The ZeroGPU build container has **no CUDA toolkit and no GPU**. Any package that compiles CUDA at pip-install time (nvdiffrast, diff-gaussian-rasterization, torchmcubes, spconv-from-source, custom rasterizers, flash-attn sdist) **cannot be installed from `requirements.txt`** the normal way. At *runtime*, a CUDA toolkit is mounted at `/cuda-image/usr/local/cuda-13.0` (nvcc available once the app process is up), and the GPUs are RTX PRO 6000 Blackwell (**sm_120**).

Every working 3D Space uses one of three strategies, in order of preference:

### Strategy 1 — prebuilt wheels in requirements.txt (best)

Direct wheel URLs whose tags match the runtime exactly. Check sources in this order:

1. **The `multimodalart/zerogpu-blackwell-wheels` dataset** — covers `nvdiffrast`, `diff_gaussian_rasterization` (upstream Inria API), `torchmcubes`, `flash_attn`, `xformers`, `pytorch3d`. Cell-picking rules and per-package caveats in [`requirements.md`](requirements.md).
2. **The official Space for your model family** — its requirements.txt often links wheels for the model's bespoke extensions (e.g. `microsoft/TRELLIS.2` links Blackwell wheels for `flex_gemm`, `nvdiffrast`, `nvdiffrec_render`, `cumesh`, `o_voxel` on GitHub Releases).
3. **Build one yourself** on any CUDA machine (`TORCH_CUDA_ARCH_LIST="12.0+PTX" pip wheel .`) and host it in a Hub repo or commit it to the Space. No CUDA machine at hand? **Build it on HF Jobs** — pick a devel image matching the target runtime and let the job upload the wheel to a Hub repo:

   ```bash
   hf jobs run --flavor rtx-pro-6000 --timeout 30m --secrets HF_TOKEN \
     pytorch/pytorch:2.11.0-cuda13.0-cudnn9-devel \
     bash -c 'export TORCH_CUDA_ARCH_LIST="12.0+PTX" && \
              pip wheel --no-build-isolation --no-deps \
                  git+https://github.com/<org>/<extension>.git -w /tmp/wheels && \
              pip install -U huggingface_hub && \
              hf upload <user>/zerogpu-wheels /tmp/wheels wheels --repo-type dataset'
   ```

   Then reference `https://huggingface.co/datasets/<user>/zerogpu-wheels/resolve/main/wheels/<file>.whl` in requirements.txt, or download and commit the wheel to the Space (Strategy 2). Three things to line up: the image's **torch + CUDA** must match the Space's pins (the tag above matches today's torch 2.11/cu130 ZeroGPU runtime — adjust as it moves), and the image's **Python** sets the wheel's cp tag, so check it matches the Space's `python_version:`. The `rtx-pro-6000` flavor is the same Blackwell sm_120 silicon as ZeroGPU, so the same job can `pip install` the fresh wheel and smoke-test the kernel before uploading; a cheaper flavor also works for compile-only (the arch comes from `TORCH_CUDA_ARCH_LIST`, not the attached GPU). Jobs bill by the minute and require a paid plan — a typical extension builds in well under 30 minutes.

When requirements contain a wheel URL, **pin `torch==` and `python_version:` to match its tags** (see `requirements.md`) — otherwise a base-image bump silently breaks the wheel. A tag mismatch is an `ImportError` (or a kernel-launch crash for a missing arch) at first import.

### Strategy 2 — wheel file committed to the Space repo

Same as Strategy 1 but the `.whl` lives in the Space repo and is installed at module-import time in `app.py` (the Hunyuan3D pattern, for their bespoke `custom_rasterizer`):

```python
import subprocess, shlex
subprocess.run(shlex.split("pip install custom_rasterizer-0.1-cp310-cp310-linux_x86_64.whl"), check=True)
```

Use when you built the wheel yourself and don't want an external URL dependency. The cp tag dictates `python_version:`.

### Strategy 3 — JIT compile at startup (fallback, e.g. for forks with no wheel)

**CPU-only extensions** (pybind11, plain C++): compile at module import with g++ — seconds, no GPU needed. Hunyuan3D's mesh painter:

```python
os.system("cd /home/user/app/hy3dpaint/DifferentiableRenderer && bash compile_mesh_painter.sh")
# the script is one line: c++ -O3 -shared -std=c++11 -fPIC $(python -m pybind11 --includes) x.cpp -o x$(python3-config --extension-suffix)
```

**CUDA extensions**, two variants seen in production:

*At module import, no GPU attached* (TripoSR's torchmcubes before its wheel existed, SF3D's texture_baker). Compiling needs only nvcc/headers, not a GPU — but you **must force the arch list** since nvcc can't probe a device:

```python
subprocess.run(
    shlex.split("pip install --no-build-isolation ./texture_baker"),
    env={**os.environ, "TORCH_CUDA_ARCH_LIST": "12.0+PTX"},
    check=True,
)
```

*Inside a one-shot `@spaces.GPU(duration=600)` setup function called at module import* (`trellis-community/TRELLIS`, `dylanebert/LGM-mini` — the latter for the ashawkey diff-gaussian-rasterization fork that has no wheel). The full pattern: point `CUDA_HOME` at `/cuda-image/usr/local/cuda-13.0`, silence torch's CUDA-version check (torch cu128 vs nvcc 13.0) via a `sitecustomize.py` that no-ops `torch.utils.cpp_extension._check_cuda_version`, `pip install --no-build-isolation --no-deps git+<repo>`, then preload `ctypes.CDLL(".../libcudart.so.13", mode=ctypes.RTLD_GLOBAL)`. Copy it verbatim from one of those Spaces; don't reinvent it.

JIT costs: slower cold starts, a burned GPU allocation (second variant), and breakage when the runtime image moves. Prefer wheels; when you do JIT-build, log clearly so failures are diagnosable from the run logs — **a failed `os.system("pip install ...")` does not kill the app**; it resurfaces later as an ImportError or a silently degraded feature.

## Attention backends on Blackwell

Covered in [`requirements.md`](requirements.md) (flash_attn / xformers wheels, FA3-on-sm_120 crashes) and [`zerogpu.md`](zerogpu.md) → Attention backends. 3D-specific note: when a model exposes a backend env var (`ATTN_BACKEND` in TRELLIS: `xformers|flash_attn|sdpa|naive`), `sdpa` is the zero-dependency safe choice; set it before importing the model library.

## Durations for 3D workloads

Declared duration is billed against quota as requested (not actual runtime) and drives queue priority — declare honestly:

| Task | duration |
|---|---|
| Fast-tier single forward (TripoSR, SF3D), splat decode (TripoSplat, LGM) | default 60 (or lower for queue priority) |
| Hunyuan3D shape-only | 40–60 |
| TRELLIS / TRELLIS.2 generation; GLB extraction | 120 each |
| Hunyuan3D shape + RGB texture | 90 |
| Hunyuan3D-2.1 shape + PBR texture | 180 |

Multi-stage pipelines: split stages into separate `@spaces.GPU` functions **only when the user can act between them** (TRELLIS's generate → re-extract-at-different-quality split). Otherwise one decorated function per user action — each GPU entry costs a queue pass and a pickle round-trip.

## Passing 3D data across the GPU boundary

`@spaces.GPU` functions run in a forked process; args/returns cross via pickle (full rules in [`zerogpu.md`](zerogpu.md)). For 3D specifically:

- **Meshes/splats**: write files to a per-session temp path inside the GPU function, return the path string. Gaussian objects in these codebases are custom classes (CUDA tensors, sometimes locks) — they can never cross the boundary; do preprocess → sample → decode → file-write in one decorated function and return only paths.
- **Intermediate latents between GPU calls**: CPU numpy dicts in `gr.State` (the TRELLIS pattern), rebuilt on cuda in the next call.
- **`torch.cuda.empty_cache()` at the end of each GPU function** — 3D pipelines fragment VRAM fast on warm workers.
- Never decorate bound methods (ml-sharp's `ModelWrapper` holds a non-picklable `threading.RLock`; wrap module-level functions instead).

## Memory

ZeroGPU `large` (48 GB) fits everything covered here (heaviest: Hunyuan3D-2.1 full PBR ~29 GB, TRELLIS.2 ≥24 GB). Don't request `size="xlarge"` unless a real OOM shows in the run logs. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (before importing torch) is the first fix for fragmentation OOMs on multi-stage pipelines.

## Failure checklist for 3D Spaces

(Also grep [`known-errors.md`](known-errors.md) — general errors are catalogued there.)

1. `ImportError: ...so: undefined symbol` / `cannot open shared object` → wheel-tag mismatch. Re-check torch pin, `python_version:`, CUDA suffix.
2. `RuntimeError: CUDA error: invalid argument` at first attention call → FA3-on-Blackwell dispatch; see `requirements.md`.
3. `nvcc not found` in **build** logs → a source CUDA dep leaked into requirements.txt; move it to a wheel or startup compile.
4. `No space left on device` → offload-disk overflow; too many model variants/stages pinned at module scope.
5. Hang at first request right after generation completes → a CUDA tensor (often nested in a dict/dataclass) crossed the pickle boundary.
6. App RUNNING but a feature is missing (e.g. texture button gone) → a startup `pip install`/compile failed silently; read the run log from the top.
