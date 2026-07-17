# 3D models: TRELLIS / TRELLIS.2, TripoSR, Stable Fast 3D, SPAR3D, Hunyuan3D

Per-family deployment recipes for mesh-generation models, distilled from the live files of their official Spaces. Gaussian splatting models live in [`3d-gsplat.md`](3d-gsplat.md); the overall workflow in [`3d-generation.md`](3d-generation.md).

## TRELLIS family

The TRELLIS family covers `microsoft/TRELLIS-image-large` (TRELLIS 1, ~1.2B) and `microsoft/TRELLIS.2-4B` (TRELLIS.2). Both are image-to-3D. Both are MIT licensed and ungated — no token needed to download weights.

| Variant | Model repo | Output | VRAM | Official Space (working reference) |
|---|---|---|---|---|
| TRELLIS 1 | `microsoft/TRELLIS-image-large` (mirror: `JeffreyXiang/TRELLIS-image-large`) | Gaussians + mesh → textured GLB, gaussian `.ply` | ~16 GB | `trellis-community/TRELLIS` (ZeroGPU, running) |
| TRELLIS.2 | `microsoft/TRELLIS.2-4B` | High-fidelity PBR-textured GLB | ≥24 GB | `microsoft/TRELLIS.2` (ZeroGPU, running) |

There is no usable pip package (`trellis-3d` on PyPI ships only the pure-Python tree without the CUDA extensions or real dependency set; nothing exists for TRELLIS.2). **Both official Spaces vendor the library source (`trellis/` or `trellis2/`) directly in the Space repo.** Deploying means duplicating the official Space or copying its tree — not `pip install`.

> **Verify against the live official Space before writing files.** Every pin below (torch/CUDA/Python versions, wheel URLs) reflects what the official Space shipped as of 2026-07 and tracks the ZeroGPU runtime, which changes. Fetch the current files first — `hf download <space-id> --repo-type space --local-dir .` or read `https://huggingface.co/spaces/<space-id>/raw/main/requirements.txt` — and treat those as source of truth.

### TRELLIS.2 recipe (prebuilt-wheels strategy)

The `microsoft/TRELLIS.2` Space compiles nothing: every CUDA extension is a prebuilt wheel whose tags match the ZeroGPU runtime exactly (`+torch2.11.0.cu130`, `cp312`, built for Blackwell sm_120). Its frontmatter pins `python_version: 3.12` and `sdk_version: 6.1.0`, and requirements.txt (as of 2026-07) is:

```
--extra-index-url https://download.pytorch.org/whl/cu130

torch==2.11.0
torchvision==0.26.0
triton==3.6.0
pillow==12.0.0
imageio==2.37.2
imageio-ffmpeg==0.6.0
tqdm==4.67.1
easydict==1.13
opencv-python-headless==4.12.0.88
trimesh==4.10.1
transformers==4.57.3
zstandard==0.25.0
kornia==0.8.2
timm==1.0.22
git+https://github.com/EasternJournalist/utils3d.git@9a4eb15e4021b67b12c460c7057d642626897ec8
https://github.com/adithyaxx/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu13torch2.11cxx11abiTRUE-cp312-cp312-linux_x86_64.whl
https://github.com/LDYang694/Storages/releases/download/rtxpro6000/flex_gemm-1.0.0%2Btorch2.11.0.cu130-cp312-cp312-linux_x86_64.whl
https://github.com/LDYang694/Storages/releases/download/rtxpro6000/nvdiffrast-0.4.0%2Btorch2.11.0.cu130-cp312-cp312-linux_x86_64.whl
https://github.com/LDYang694/Storages/releases/download/rtxpro6000/nvdiffrec_render-0.0.0%2Btorch2.11.0.cu130-cp312-cp312-linux_x86_64.whl
https://github.com/LDYang694/Storages/releases/download/rtxpro6000/cumesh-0.0.1%2Btorch2.11.0.cu130-cp312-cp312-linux_x86_64.whl
https://github.com/LDYang694/Storages/releases/download/rtxpro6000/o_voxel-0.0.1%2Btorch2.11.0.cu130-cp312-cp312-linux_x86_64.whl
```

Wheel tags, torch pin, and `python_version:` must agree — see `3d-cuda-extensions.md` for the tag anatomy. TRELLIS.2 uses `flex_gemm` for sparse conv (no spconv).

Module-level setup (order matters — env vars before any torch/trellis import):

```python
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["ATTN_BACKEND"] = "flash_attn"
os.environ["FLEX_GEMM_AUTOTUNE_CACHE_PATH"] = os.path.join(..., "autotune_cache.json")

pipeline = Trellis2ImageTo3DPipeline.from_pretrained("microsoft/TRELLIS.2-4B")
pipeline.rembg_model = None   # official Space outsources rembg to briaai/BRIA-RMBG-2.0 via gradio_client
pipeline.low_vram = False
pipeline.cuda()
```

**Keep `autotune_cache.json` when duplicating.** The Space commits a pre-computed flex_gemm autotune cache so kernel autotuning doesn't re-run on every fresh ZeroGPU worker. Deleting it makes first-request latency much worse.

GPU functions in the official Space: `@spaces.GPU(duration=120)` on generation (`pipeline.run(...)` with per-stage sampler params, `pipeline_type` of `512` / `1024_cascade` / `1536_cascade`) and `@spaces.GPU(duration=120)` on GLB extraction (`pipeline.decode_latent(...)` + `o_voxel.postprocess.to_glb(...)`). Generation and extraction are split into two GPU calls with latents passed between them as CPU numpy in `gr.State` — keep that split; it lets users re-extract at different decimation/texture sizes without regenerating.

### TRELLIS 1 recipe (JIT-compile strategy)

The `trellis-community/TRELLIS` Space demonstrates the other viable strategy: compile nvdiffrast + diff-gaussian-rasterization **at first boot on a GPU worker**, inside `@spaces.GPU(duration=600)`, using the nvcc that ZeroGPU mounts at runtime (`/cuda-image/usr/local/cuda-13.0`). Its requirements.txt (torch 2.8.0, `spconv-cu120==2.3.6`, `xformers`, `rembg`, no python_version pin → 3.10) installs everything that *can* come from PyPI; the JIT step handles the rest with:

- `TORCH_CUDA_ARCH_LIST="12.0"` (Blackwell — nvcc can't probe a GPU that isn't attached yet)
- a `sitecustomize.py` that no-ops `torch.utils.cpp_extension._check_cuda_version` (torch built for cu128, nvcc is 13.0)
- `pip install --no-build-isolation ./extensions/nvdiffrast` (vendored source), then the mip-splatting `diff-gaussian-rasterization` from a shallow git clone
- afterwards, `ctypes.CDLL("<cuda-libdir>/libcudart.so.13", mode=ctypes.RTLD_GLOBAL)` so the freshly built extensions find the CUDA 13 runtime

Backend env vars, set at the very top of `app.py`: `SPCONV_ALGO=native`, `ATTN_BACKEND=xformers`. Because ZeroGPU is Blackwell, xformers must be forced onto Cutlass kernels (its Flash-Attn-3 dispatch crashes on sm_120) — the Space monkeypatches `xformers.ops.memory_efficient_attention` to default `op=(fmha.cutlass.FwOp, fmha.cutlass.BwOp)`. Don't drop that patch when duplicating.

GPU functions: `@spaces.GPU(duration=120)` for generate-and-extract-GLB (single- and multi-image modes, 120-frame turntable preview video via `render_utils.render_video`, GLB via `postprocessing_utils.to_glb(gs, mesh, simplify=0.95, texture_size=1024)`); bare `@spaces.GPU` for gaussian `.ply` extraction. Viewer: `LitModel3D` from `gradio_litmodel3d==0.0.1` (installed at runtime with `--no-deps` if missing). The Space also sets `demo.launch(mcp_server=True)` — TRELLIS demos double as MCP servers; keep it.

### Deploying a finetuned TRELLIS variant

Both pipelines resolve everything from a `pipeline.json` at the model repo root, so a finetuned checkpoint that keeps the repo layout is a one-line swap:

```python
pipeline = TrellisImageTo3DPipeline.from_pretrained("user/my-finetuned-trellis")   # or Trellis2ImageTo3DPipeline
```

If the finetuned repo is private, pass the token via env (`HF_TOKEN` Space secret) — `from_pretrained` in the vendored trellis code goes through `huggingface_hub` and picks it up. If the user only has raw checkpoint files (no `pipeline.json`), copy `pipeline.json` + config layout from the base repo into their model repo first.

### Picking between the two

- **TRELLIS.2** — best quality, PBR materials, 3 resolution tiers; heavier (≥24 GB, fine on ZeroGPU large's 48 GB), Gradio 6, Python 3.12. Default choice for a new Space.
- **TRELLIS 1** — lighter (~16 GB), dual gaussian+mesh output (the gaussian `.ply` path matters if the user wants splats), multi-image conditioning modes, and the community Space is a cleaner codebase to modify. Choose when the user wants gaussians, multi-image input, or minimal VRAM.

### Durations and misc

- Generation: `duration=120` is what both official Spaces use; TRELLIS.2 at 1536³ pushes ~60s of pure compute on H100-class hardware, so don't go below 120.
- Call `torch.cuda.empty_cache()` at the end of each GPU function (both Spaces do) — sequential calls on a warm worker otherwise accumulate.
- TRELLIS.2's mesh simplify cap: `mesh.simplify(16777216)` — nvdiffrast's face-count limit.
- Preprocessing (alpha-bbox crop, resize to ≤1024, background removal) runs on CPU outside the GPU function.

## Mesh workhorses: TripoSR, Stable Fast 3D, SPAR3D, Hunyuan3D

Two groups in this file. The **fast tier** (TripoSR, SF3D, SPAR3D): single-forward-pass image-to-mesh, seconds per generation, small VRAM, simple codebases — pick when the user wants a snappy demo, a high-traffic public Space (short `@spaces.GPU` durations = less quota per click and better queue priority), or can accept lower fidelity than TRELLIS.2. And **Hunyuan3D-2/2.1** (Tencent): two-stage — a flow-matching DiT generates the shape, then an optional multiview-diffusion "Paint" stage textures it — pick when the user wants textured output and TRELLIS.2 doesn't fit, or when they finetuned a Hunyuan3D DiT (the 2.1 release includes official training code, so finetuned shape checkpoints are common).

| Model | Repo | Output | License / gating | Official Space |
|---|---|---|---|---|
| TripoSR | `stabilityai/TripoSR` | untextured mesh (OBJ + GLB) | **MIT, ungated** | `stabilityai/TripoSR` (ZeroGPU, running) |
| Stable Fast 3D (SF3D) | `stabilityai/stable-fast-3d` | UV-unwrapped **textured** GLB | stabilityai-ai-community, **gated (auto)** | `stabilityai/stable-fast-3d` (ZeroGPU, running) |
| SPAR3D | `stabilityai/stable-point-aware-3d` | textured GLB + editable point cloud | stabilityai-ai-community, **gated (auto)** | `stabilityai/stable-point-aware-3d` (dedicated L4, **currently BUILD_ERROR** — reference code only) |
| Hunyuan3D-2.0 | `tencent/Hunyuan3D-2` (subfolder `hunyuan3d-dit-v2-0`; also `-mini`, `-mv`) | GLB, RGB-textured (Paint 2.0) | tencent-hunyuan-community, **ungated, non-commercial** | `tencent/Hunyuan3D-2` (ZeroGPU, running) |
| Hunyuan3D-2.1 | `tencent/Hunyuan3D-2.1` (subfolder `hunyuan3d-dit-v2-1`) | GLB, **PBR**-textured (Paint 2.1) | tencent-hunyuan-community, **ungated, non-commercial** | `tencent/Hunyuan3D-2.1` (ZeroGPU, **paused** — code is still the reference) |

**Licenses and gating matter here.** The two Stability models are `gated: auto` — the deploying user must accept the license on the model page, and the Space needs their `HF_TOKEN` as a secret to download weights at startup; if the gate isn't accepted, `from_pretrained` fails with 401 at build — check before publishing. The Hunyuan models are ungated (no token needed) but the community license restricts commercial use — surface that before the user flips a Space public. TripoSR is MIT and needs nothing.

> **Verify against the live official Space before writing files.** Pins below are as of 2026-07. Fetch current files via `https://huggingface.co/spaces/<id>/raw/main/<path>` first.

### TripoSR — the minimal recipe (~200-line app)

The simplest working 3D Space on the Hub, and the best starting skeleton for a from-scratch mesh demo. `tsr/` package vendored in the Space; frontmatter pins `python_version: 3.10.13`, `sdk_version: 4.20.1`.

One CUDA extension, JIT-built at module import (marching cubes):

```python
subprocess.run(
    shlex.split("pip install --no-build-isolation git+https://github.com/tatsy/torchmcubes.git"),
    env={**os.environ, "TORCH_CUDA_ARCH_LIST": "12.0+PTX"},   # no GPU visible at startup — force Blackwell arch
    check=True,
)
```

requirements.txt carries the build toolchain for it (`scikit-build-core>=0.10`, `pybind11>=2.10`, `cmake`, `ninja`) plus `rembg`, `onnxruntime`, `trimesh`, `omegaconf`, `einops`, `transformers`, `Pillow`, `huggingface-hub`. No torch pin (base image). (A prebuilt `torchmcubes` Blackwell wheel now exists in the dataset described in [`requirements.md`](requirements.md) — cleaner than the JIT build when building fresh.)

```python
model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
model.renderer.set_chunk_size(131072)
model.to(device)

@spaces.GPU  # default 60s is plenty — the forward pass is ~1s
def generate(image, mc_resolution):
    scene_codes = model(image, device)
    mesh = model.extract_mesh(scene_codes, resolution=mc_resolution)[0]
    mesh = to_gradio_3d_orientation(mesh)   # axis fix — see 3d-outputs.md
    ...  # export OBJ + GLB to NamedTemporaryFiles, return both paths
```

Preprocessing on CPU, outside the GPU function: `rembg` background removal → `resize_foreground(image, 0.85)` → composite onto gray. UI: input image + "marching cubes resolution" slider (32–320) + two `gr.Model3D` tabs (OBJ and GLB).

### Stable Fast 3D — textured output, source-built extensions

`sf3d/` vendored; frontmatter `python_version: 3.10.13`, `sdk_version: 4.41.0`. Two vendored extension source dirs built at module import (they're commented out in requirements.txt with a note — the "HF hack"):

```python
os.system(
    'CPPFLAGS="-include utility" TORCH_CUDA_ARCH_LIST="12.0+PTX" USE_CUDA=1 '
    "pip install -vv --no-build-isolation ./texture_baker ./uv_unwrapper"
)
```

`texture_baker` is a torch CUDAExtension (the `CPPFLAGS="-include utility"` is required for its build), `uv_unwrapper` a plain C++ extension. Other deps of note: `open_clip_torch`, `rembg[gpu]`, `pynanoinstantmeshes` + `gpytoolbox` (remeshing), `gradio-litmodel3d==0.0.1`.

```python
model = SF3D.from_pretrained("stabilityai/stable-fast-3d",
                             config_name="config.yaml", weight_name="model.safetensors")
model.eval().to(device)   # gated repo — needs HF_TOKEN secret with accepted license

@spaces.GPU  # default 60s
def run(input_image, remesh_option, vertex_count, texture_size):
    with torch.autocast(device_type=device, dtype=torch.bfloat16):
        model_batch = create_batch(input_image)
        ...
    trimesh_mesh.export(tmp.name, file_type="glb", include_normals=True)
```

UI controls that earn their place: foreground ratio, remesh (None/Triangle/Quad), target vertex count, texture size (512–2048). Viewer: `LitModel3D` with selectable HDR environment maps — textured output deserves image-based lighting (see [`3d-outputs.md`](3d-outputs.md)).

### SPAR3D — reference code only, don't duplicate blindly

Two-stage: point-cloud diffusion → mesh, with a `gradio_pointcloudeditor` step so users can edit the intermediate point cloud before meshing. Distinctive UI idea worth stealing. But the official Space runs on **dedicated L4, not ZeroGPU** (no `import spaces`, torch pinned to 2.5.1, real nvcc assumed) and is currently in BUILD_ERROR. To deploy SPAR3D on ZeroGPU you'd port it: add `spaces`, drop the torch pin, apply the SF3D extension-build pattern (same vendored `texture_baker`/`uv_unwrapper` + a prebuilt `pynim` wheel), and decorate the two stages. Budget real debugging time; propose SF3D instead unless the user specifically needs the point-cloud editing stage. Its background removal uses `transparent-background` (InSPyReNet) rather than rembg.

### Hunyuan3D-2 / 2.1 — textured two-stage generation

Both official Spaces vendor the model code in the Space repo (`hy3dgen/` for 2.0; `hy3dshape/` + `hy3dpaint/` for 2.1) — there's a `setup.py` but nothing is pip-installed; imports resolve from cwd. Two native extensions are handled at module-import time in `gradio_app.py`:

```python
# custom_rasterizer: prebuilt CUDA wheel committed to the Space repo (no nvcc at build time)
subprocess.run(shlex.split("pip install custom_rasterizer-0.1-cp310-cp310-linux_x86_64.whl"), check=True)
# mesh painter: CPU-only pybind11 extension, compiled with plain g++ in seconds
os.system("cd /home/user/app/hy3dpaint/DifferentiableRenderer && bash compile_mesh_painter.sh")
```

The cp310 wheel means Python 3.10 — pin `python_version: "3.10"` explicitly when duplicating so a runtime default bump can't break it.

**Requirements notes (2.1)** — fully pinned; the non-obvious entries: `--extra-index-url https://download.blender.org/pypi/` + `bpy==4.0` (Blender-as-pip; installs headless with no display setup — see [`3d-outputs.md`](3d-outputs.md) → Headless Blender — though the Space's OBJ→GLB conversion actually runs on trimesh+pygltflib); `realesrgan==0.3.0` + `basicsr==1.4.2` (texture upscaling — needs the Space's `torchvision_fix.py` shim, applied at the top of `gradio_app.py` *and* again before the texgen import, because basicsr imports the removed `torchvision.transforms.functional_tensor`); `cupy-cuda12x`, `pymeshlab`, `xatlas`, `open3d`, `trimesh`, `pygltflib` (mesh stack); **no torch pin**; `pydantic==2.10.6` (gradio compat).

**Model loading** (module level):

```python
from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline   # hy3dgen.shapegen on 2.0
shape_pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "tencent/Hunyuan3D-2.1", subfolder="hunyuan3d-dit-v2-1", use_safetensors=False,
)  # 2.0: repo "tencent/Hunyuan3D-2", subfolder "hunyuan3d-dit-v2-0", use_safetensors=True, + .enable_flashvdm()

# Texture stage — wrap in try/except and degrade to shape-only if it fails (official HAS_TEXTUREGEN pattern)
from hy3dpaint.textureGenPipeline import Hunyuan3DPaintPipeline, Hunyuan3DPaintConfig
paint_pipe = Hunyuan3DPaintPipeline(Hunyuan3DPaintConfig(max_num_view=8, resolution=768))
```

**GPU decorators**: `@spaces.GPU(duration=40–60)` shape-only; `@spaces.GPU(duration=90)` (2.0) / `@spaces.GPU(duration=180)` (2.1 PBR) shape+texture. VRAM (2.1, per its README): ~10 GB shape, ~21 GB texture, ~29 GB both — fits ZeroGPU large, but the full PBR path is the heaviest recipe in these references; don't shave the duration.

**Output path gotcha (2.1)**: textured meshes export as **OBJ first, then convert to GLB** via the Space's `convert_utils` (obj2gltf with PBR materials) — direct GLB export from the paint pipeline core-dumps. Keep the conversion step when duplicating.

**Serving quirk**: both official Spaces use a custom `<model-viewer>` HTML iframe + FastAPI `StaticFiles` + `gr.mount_gradio_app` + manual `uvicorn.run` instead of `demo.launch()` — which requires calling `from spaces import zero; zero.startup()` manually before uvicorn. **When building fresh rather than duplicating, skip all of this** — export a GLB, show it in `gr.Model3D`/`LitModel3D`, and let `demo.launch()` do its job. Only keep the iframe machinery when duplicating wholesale.

**Local-run pattern worth copying**: 2.1's `gradio_app.py` defines a no-op `spaces.GPU` decorator when not running on Spaces (`ENV != "Huggingface"`), so the same file runs on a local GPU box unchanged.

**Deploying a finetuned Hunyuan3D variant** — the official 2.1 release ships training code (`hy3dshape/` includes trainers and configs), so "I finetuned Hunyuan3D, make me a demo" is a real request. The shape pipeline resolves `subfolder` inside the model repo:

```python
shape_pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "user/my-finetuned-hunyuan3d", subfolder="hunyuan3d-dit-v2-1",
)
```

If the user's repo keeps the official layout (config + checkpoint under the dit subfolder), it's a repo-id swap; if they saved a bare checkpoint, mirror the base repo's subfolder structure into their repo first. Finetunes are almost always **shape-only** — keep the stock Paint stage from the base repo for texturing (it conditions on the input image, not the shape checkpoint). Private repo → `HF_TOKEN` Space secret.

**Which Hunyuan variant**: **2.1** — PBR texturing, the one with official training code, the default for finetunes, heaviest. **2.0** — lighter, faster (flashvdm), RGB textures, official Space actually running today (known-good duplicate target); `-mini` and `-mv` (multiview-conditioned) subfolder variants live in the same repo. **Shape-only demo** (skip Paint entirely) — halves the dependency surface (no bpy/realesrgan/basicsr/cupy) and cuts duration to 40–60s; offer it when the user just wants geometry.
