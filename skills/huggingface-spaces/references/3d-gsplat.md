# Gaussian splatting reference

Image-to-3D models whose output is a **gaussian splat** (a point cloud of oriented 3D gaussians) rather than a mesh. Deliverable file: gaussian `.ply` (the INRIA convention — the interchange format everything reads) and optionally `.splat` (antimatter15 32-byte records; smaller, no view-dependent color).

| Model | Repo | License / gating | Official Space (working reference) |
|---|---|---|---|
| TripoSplat | `VAST-AI/TripoSplat` | **MIT, ungated** | `VAST-AI/TripoSplat` (ZeroGPU, running, Gradio 6) |
| LGM | `ashawkey/LGM` (+ `dylanebert/LGM` diffusers port) | **MIT, ungated** | `dylanebert/LGM-mini` and `ashawkey/LGM` (ZeroGPU, running) |
| Apple SHARP | `apple/Sharp` | **apple-amlr — research-only**, ungated | `notaneimu/ml-sharp-3d-viewer` (currently CPU; code is ZeroGPU-ready) |
| Splatter Image | `szymanowiczs/splatter-image-v1` | MIT | `szymanowiczs/splatter_image` (ZeroGPU, running; old Gradio, minimal skeleton) |
| Splatt3R (stereo pair → scene) | `brandonsmart/splatt3r_v1.0` | research code | `brandonsmart/splatt3r` (ZeroGPU, running) |

TRELLIS 1 also exports gaussian `.ply` alongside its mesh — covered in `3d-models.md`.

> **Verify against the live official Space before writing files.** Facts below are as of 2026-07.

## The one decision that shapes everything: rasterize server-side or not?

Rendering gaussians on the server needs a CUDA rasterizer (`diff-gaussian-rasterization` or `gsplat`). Prebuilt Blackwell (sm_120) wheel availability is narrow: the `multimodalart/zerogpu-blackwell-wheels` dataset (see [`requirements.md`](requirements.md)) ships `diff_gaussian_rasterization` with the **upstream Inria API only** (2-tuple return) — the ashawkey fork most LGM-family code imports (4-tuple with alpha+depth) has no wheel, and gsplat's own wheel index tops out at torch 2.4/cu124. Two viable shapes:

**Shape A — no server-side rendering (default, strongly preferred).** The model decodes gaussians as plain PyTorch tensors; you write a `.ply` and let the *browser* render it. No CUDA extension at all — `requirements.txt` can be as small as `gradio, torch, torchvision, numpy, safetensors, pillow, tqdm` (TripoSplat's, in full). This is how every modern splat Space works (TripoSplat, SHARP, Splatt3R, Splatter Image; Splatt3R's requirements literally comment out the rasterizer dep).

**Shape B — a real rasterizer (only for server-rendered orbit videos).** If the code uses the upstream Inria API, take the prebuilt wheel from `requirements.md`'s dataset and be done. `ashawkey/LGM` needs its fork, so its Space JIT-builds it — the GPU-worker bootstrap documented in `3d-cuda-extensions.md` Strategy 3: `@spaces.GPU(duration=600)` setup function at module import, `CUDA_HOME=/cuda-image/usr/local/cuda-13.0`, `TORCH_CUDA_ARCH_LIST="12.0"`, sitecustomize no-op of `_check_cuda_version`, `pip install --no-build-isolation --no-deps git+https://github.com/graphdeco-inria/diff-gaussian-rasterization.git`, then `ctypes.CDLL(".../libcudart.so.13", RTLD_GLOBAL)`. Copy it from `dylanebert/LGM-mini` verbatim. Don't take this on unless the user explicitly wants server-rendered video output.

## Viewing splats

- **`gr.Model3D` renders gaussian `.ply` and `.splat` natively** (Babylon.js; supported at least since Gradio 4.25, current in 6.x). Return the file path like any other output. `display_mode` is ignored for splats; `clear_color`, `camera_position`, `height` still apply. This is the zero-effort default — use it.
- **Custom JS viewers** give better splat sorting and controls when the demo is the product: TripoSplat serves a Spark.js (`@sparkjsdev/spark`) viewer page in an iframe; ml-sharp vendors a static PlayCanvas SuperSplat build and serves it via `gr.set_static_paths(...)` + `gr.HTML` iframe with `/gradio_api/file=...` URLs. Only go here if `gr.Model3D`'s rendering visibly undersells the model.
- Always add a `gr.DownloadButton` for the `.ply` — splat users take the file to their own viewer/engine.

## Output writing

Gaussian `.ply` (INRIA convention): binary little-endian, vertex props `x,y,z,nx,ny,nz,f_dc_0..2,(f_rest_*),opacity(logit),scale_0..2(log),rot_0..3(quat)`. Model codebases ship their own writer (`save_ply` in LGM/SHARP/TripoSplat) — use it; don't hand-roll unless porting.

Optional `.splat` conversion for lighter downloads (~32 bytes/gaussian, drops view-dependent SH): TripoSplat's `triposplat.py::to_splat_bytes` is a complete pure-numpy reference — position f32×3, scale f32×3 (linear), RGBA u8×4 (`rgb = (f_dc·0.2820948 + 0.5)·255`, alpha = sigmoid(opacity)), quaternion u8×4 (`q·128+128`), records sorted by opacity×volume.

Watch orientation here too: splat conventions differ from viewers' (TripoSplat applies `[[1,0,0],[0,0,-1],[0,1,0]]` on export). If the splat renders sideways in `gr.Model3D`, fix it at export, same as meshes.

## ZeroGPU pickle discipline (bites harder here)

Gaussian objects in these codebases are custom classes (often holding CUDA tensors or locks) — **they cannot cross the `@spaces.GPU` boundary**. Two proven patterns:

- Do *everything* — preprocess, sample, decode, `.ply` write — inside one decorated function and return only path strings (TripoSplat, with an explicit comment to that effect).
- Never decorate bound methods; wrap module-level functions (`spaces.GPU(duration=180)(predict_to_ply)` — ml-sharp, whose `ModelWrapper` holds a non-picklable `threading.RLock`).

Durations: TripoSplat and LGM-mini run on the bare `@spaces.GPU` default 60s; SHARP uses 180. Splat decoding is fast — the multiview-diffusion stage (LGM) is what eats time.

## Model-specific notes

- **TripoSplat** — the current default pick: MIT, running official ZeroGPU Space, fp16 weights well within 48 GB, ~262k gaussians per generation, BiRefNet background removal built in. Caveat when duplicating: the official Space uses a fully custom Gradio 6 `gradio.Server` + `index.html` frontend, not `gr.Blocks` — its HTTP API is bespoke, so either keep it wholesale or rebuild a plain `gr.Blocks` + `gr.Model3D` UI around `TripoSplatPipeline` (the pipeline code is self-contained in `triposplat.py`/`model.py`). Weights download at startup via `hf download VAST-AI/TripoSplat --local-dir ckpts`.
- **LGM** — image → 4 multiview images (ImageDream) → gaussians. `dylanebert/LGM-mini` is the clean diffusers-style duplicate target (both pipelines via `from_pretrained(..., trust_remote_code=True)`, output straight into `gr.Model3D`); `ashawkey/LGM` is the video-rendering variant (Shape B). Both carry an xformers→SDPA monkeypatch for Blackwell — keep it when duplicating (the `xformers 0.0.34` Blackwell wheel in `requirements.md`'s dataset makes the patch unnecessary if you modernize the requirements instead, but the patch is harmless).
- **SHARP** — pip-installable (`sharp @ git+https://github.com/apple/ml-sharp.git@<sha>`), predicts a camera-space *scene* splat from one photo. Research-only license (`apple-amlr`) — tell the user before they build anything commercial. `preload_from_hub` in the frontmatter pre-bakes the checkpoint into the Space image.
- **Splatter Image** — the minimal skeleton (~CVPR 2024, per-pixel gaussians, MIT): good template bones, but its Space pins Gradio 4.27 and a cu113 torch via `pre-requirements.txt` — modernize rather than copy pins.
