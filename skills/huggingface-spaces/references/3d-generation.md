# 3D generation Spaces

Building a Space whose output is a 3D asset — image (occasionally text) in, downloadable and in-browser-viewable **mesh** (GLB/OBJ/PLY/STL) or **gaussian splat** (`.ply`/`.splat`) out. Read this whenever the user wants a Space/demo/playground for a 3D generation model, whether a stock checkpoint or their own finetuned variant. NeRF pipelines and world/scene models (HunyuanWorld, HY-World) are not covered.

The standard workflow in `SKILL.md` applies (create → build → iterate → verify). This file and its siblings cover the 3D-specific deltas.

## What makes 3D Spaces different

1. **Native extensions.** These models need CUDA/C++ extensions (nvdiffrast, rasterizers, marching cubes, texture bakers) that cannot compile at Space build time. Working Spaces use prebuilt wheels or startup-compile tricks — [`3d-cuda-extensions.md`](3d-cuda-extensions.md). Getting this wrong is the dominant failure mode.
2. **Vendored model code.** None of the major 3D models are cleanly pip-installable; every official Space carries the model library as a source tree in the Space repo. There is no `diffusers`-style one-liner. (Don't trust PyPI lookalikes: `trellis-3d` ships the Python tree without the CUDA extensions or the real dependency set.)

Both points make **"duplicate the official Space, then edit"** beat "assemble from scratch" here more than for any other model class.

## Picking a model

| Priority | Pick | Why | Reference |
|---|---|---|---|
| Best quality, PBR textures | **TRELLIS.2** | current quality bar; MIT; ≥24 GB (fits ZeroGPU large) | [`3d-models.md`](3d-models.md) |
| Textured output, finetuning story | **Hunyuan3D-2.1** (2.0 for lighter/faster) | official training code → common finetune target; PBR paint stage; non-commercial license | [`3d-models.md`](3d-models.md) |
| Speed / high-traffic / simplicity | **TripoSR** (untextured, MIT) or **SF3D** (textured, gated) | single forward pass, ~60s duration, tiny codebase | [`3d-models.md`](3d-models.md) |
| Gaussians alongside mesh, multi-image input | **TRELLIS 1** | dual gaussian+mesh decoder; lighter than TRELLIS.2 | [`3d-models.md`](3d-models.md) |
| Gaussian splats as the deliverable | **TripoSplat** (or LGM) | pure-PyTorch splat decode, no rasterizer needed; `gr.Model3D` renders splat `.ply` natively | [`3d-gsplat.md`](3d-gsplat.md) |

**Check gating and license in Phase 0, not at first build.** `stabilityai/stable-fast-3d` and `stable-point-aware-3d` are gated (`gated: auto`) — the user must have accepted the license and the Space needs `HF_TOKEN` as a secret; verify access with `hf repos info` / `HfApi().model_info()` up front. `tencent/Hunyuan3D-*` is ungated but **non-commercial** — flag before the Space goes public. TRELLIS/TripoSR/TripoSplat/LGM are MIT. Apple SHARP is research-only (`apple-amlr`).

If the model isn't covered by a reference file (Direct3D, TripoSG, Step1X-3D, a new release…), proceed by analogy with the user's agreement: find its official/most-liked *working* Space, fetch its actual files, and apply the same analysis — never guess a 3D dependency stack from memory.

## Deployment path: duplicate vs build

**Duplicate the official Space** (default for stock checkpoints, and for finetunes that are a `from_pretrained` swap — each reference file documents the swap):

```python
from huggingface_hub import HfApi
api = HfApi()
api.duplicate_repo("tencent/Hunyuan3D-2", to_id=f"{username}/my-hunyuan3d",
                   repo_type="space", private=True, space_hardware="zero-a10g",
                   space_secrets=[{"key": "HF_TOKEN", "value": hf_token}],  # only if a gated/private repo is involved
                   exist_ok=True)
```

(`duplicate_space` is the deprecated older name.) Confirm the source Space is currently RUNNING first (`hf spaces info <id> --expand runtime`) — a paused/broken source means bitrot. Duplication copies *files only*; pass `space_hardware=`/`space_secrets=` explicitly. Then `hf download <repo> --repo-type space --local-dir .`, make the minimal edits (checkpoint repo-id, title/README, UI trims), and push back with `hf upload ... --repo-type space`. **Resist rewriting working extension-handling code you don't fully understand** — sitecustomize patches, `ctypes.CDLL` preloads, autotune caches, and `zero.startup()` calls all look redundant until removed.

**Build from source** (custom UI, shape-only trims, no live official Space): start from the TripoSR skeleton (the ~200-line app documented in [`3d-models.md`](3d-models.md) — the cleanest template), vendor the model library tree from the official Space or GitHub, and follow [`3d-cuda-extensions.md`](3d-cuda-extensions.md). Budget more debugging iterations than an image-model Space.

Either way, **fetch the official Space's live files first** (`https://huggingface.co/spaces/{id}/raw/main/{path}`) and treat them — not the reference files' pins — as source of truth. The reference files record what shipped as of mid-2026; the ZeroGPU runtime moves and official Spaces track it.

## UI design

Read [`3d-outputs.md`](3d-outputs.md) for formats, viewers, preprocessing, and temp-file patterns. Baseline image-to-3D UI:

- **Input**: image upload → visible preprocessing preview (background removal + crop — show what the model actually receives) → generate.
- **Controls**: only the knobs this model responds to. Seed + randomize always; then per family: sampler steps/guidance (TRELLIS, Hunyuan3D), marching-cubes resolution (TripoSR), remesh/vertex-count/texture-size (SF3D), decimation + texture size at extraction (TRELLIS.2). Don't surface every config field of a research codebase.
- **Output**: `gr.Model3D` (untextured meshes, splats) or `LitModel3D` with HDR lighting (textured/PBR), plus `gr.DownloadButton`s for GLB and secondary formats. Two-stage models (TRELLIS) show a fast turntable preview before the slower GLB extraction.
- **Examples**: 3–6 known-good images lifted from the official Space's assets, `cache_examples=True, cache_mode="lazy"`.

## Verify: 3D-specific additions

On top of the standard smoke test in `SKILL.md` §7:

1. These apps expose **chained endpoints, not one `/predict`** — e.g. TripoSR: `/preprocess` (image → segmented image) then `/generate` (→ mesh files). `Client(...).view_api()` first, then call in sequence, feeding the first result into the second via `handle_file(...)`.
2. **Validate the returned file, not its existence.** Meshes:

   ```python
   import trimesh
   m = trimesh.load("out.glb", force="scene")
   geoms = list(m.geometry.values()) if hasattr(m, "geometry") else [m]
   assert geoms and sum(g.faces.shape[0] for g in geoms) > 0, "empty mesh"
   ```

   Gaussian splat `.ply` (no faces — check point count and splat attributes):

   ```python
   from plyfile import PlyData
   v = PlyData.read("out.ply")["vertex"]
   assert v.count > 1000, "suspiciously few gaussians"
   assert {"f_dc_0", "opacity", "scale_0", "rot_0"} <= set(v.data.dtype.names), "not a gaussian ply"
   ```

3. **Look at it in the browser once.** Orientation (upright? facing forward?), texture presence, viewer lighting — the failure modes a programmatic check can't catch ([`3d-outputs.md`](3d-outputs.md) → Orientation).
4. Startup-time extension compiles fail *silently* (app still boots, feature degrades) — grep the run log from the top even when everything looks green. Failure checklist: bottom of [`3d-cuda-extensions.md`](3d-cuda-extensions.md).

## What to avoid

- Assembling a TRELLIS/Hunyuan-class Space from scratch when a running official Space exists to duplicate.
- Trusting reference-file version pins over the live official Space's files.
- Compiling CUDA extensions via `requirements.txt` (no nvcc at build time), or `pip install`-ing PyPI lookalike packages for the model libraries.
- Returning meshes/gaussians as in-memory objects from `@spaces.GPU` functions — write files, return paths.
- Fixed output filenames (`output.glb`) — concurrent users clobber each other.
- Declaring green after `RUNNING` + a returned file. Load the mesh, count faces/points, and look at it once.
