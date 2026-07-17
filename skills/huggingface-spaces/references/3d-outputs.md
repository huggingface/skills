# Mesh outputs: formats, viewers, preprocessing

## Formats

**GLB is the default output format.** It's self-contained (geometry + materials + textures in one binary file), renders in every in-browser viewer, and is what all the major official 3D Spaces produce. Offer OBJ/PLY/STL as secondary downloads, not as the primary view.

| Format | Carries | When to offer |
|---|---|---|
| GLB | geometry + normals + UVs + PBR materials + embedded textures | always — primary output |
| OBJ (+MTL) | geometry, UVs; textures via sidecar files | DCC-tool users; note multi-file awkwardness in a web download |
| PLY | geometry, vertex colors; also the container for gaussian splats (see `3d-gsplat.md`) | point clouds, vertex-colored meshes, splats |
| STL | bare geometry | 3D-printing crowd |

Conversion is trimesh one-liners — the Hunyuan3D Spaces expose exactly this as an "export" accordion:

```python
mesh = trimesh.load("out.glb")
mesh.export("out.obj")   # or .ply / .stl — inferred from extension
```

Two exceptions to "just use trimesh":

- **PBR materials**: trimesh's GLB export handles baseColor fine but degrades full PBR (metallic/roughness/normal maps). Hunyuan3D-2.1 exports OBJ then converts with obj2gltf specifically because its direct GLB export core-dumps — when a pipeline ships its own exporter (`to_glb`, `convert_utils`, `o_voxel.postprocess`), use it instead of round-tripping through trimesh.
- **Normals**: pass `include_normals=True` on trimesh GLB exports (SF3D does) — missing normals render matte-black in some viewers.

## Orientation

The #1 "it works but looks wrong" bug. Model output conventions (often Z-up, or −Y-forward from the training renders) don't match the viewers' glTF convention (Y-up, +Z toward camera), so meshes come out lying face-down or backwards. TripoSR's fix:

```python
def to_gradio_3d_orientation(mesh):
    mesh.apply_transform(trimesh.transformations.rotation_matrix(-np.pi/2, [1, 0, 0]))  # Z-up → Y-up
    mesh.apply_transform(trimesh.transformations.rotation_matrix( np.pi/2, [0, 1, 0]))
    return mesh
```

The exact rotation is per-model — copy it from the official Space's app (search for `rotation_matrix` or `apply_transform`). If output is mirrored, the model bakes a flipped X; TripoSR's OBJ export flips `mesh.vertices[:, 0]` back. Verify orientation visually during the smoke-test; it can't be caught from exit codes.

## Viewers

- **`gr.Model3D`** — built-in, zero extra deps, fine for untextured or baseColor meshes; also renders gaussian splat `.ply`/`.splat` natively (see `3d-gsplat.md`). Useful kwargs: `display_mode="solid"` (default point cloud rendering ruins meshes in some versions; ignored for splats), `clear_color=(0.25, 0.25, 0.25, 1.0)`, `height=...`. Default choice.
- **`LitModel3D`** (`gradio_litmodel3d==0.0.1`, a Hub custom component) — adds image-based lighting with HDR environment maps. Worth the extra dep for **textured/PBR** output, where flat lighting hides the texture quality (SF3D and trellis-community both use it, SF3D with a selectable `.hdr` set). Textured model + plain `gr.Model3D` undersells the result.
- **Custom `<model-viewer>` iframe + FastAPI static mount** — what the Hunyuan Spaces do. Maximum control, but requires abandoning `demo.launch()` for manual uvicorn plus a manual `spaces.zero.startup()` call. Don't build this fresh; only keep it when duplicating a Space that already has it.
- **Turntable preview** — TRELLIS renders a 120-frame orbit video (`imageio.mimsave`, fps=15) shown in `gr.Video` *before* the user commits to GLB extraction; TRELLIS.2 uses a base64-JPEG JS orbiter. Good pattern when extraction is a separate, slower step; skip it for fast-tier models where the mesh is ready immediately.

Always pair the viewer with `gr.DownloadButton` for the raw file — the viewer is a preview, the file is the deliverable.

## Input preprocessing (image-to-3D)

Every image-to-3D model expects a **segmented foreground object**, roughly centered, on neutral/transparent background. The shared recipe, run on CPU *outside* the GPU function:

1. **Respect an existing alpha channel.** If the upload is RGBA with a real alpha, skip segmentation (TRELLIS checks this first).
2. **Otherwise remove the background** — `rembg` (u2net, onnxruntime; the common choice), `transparent-background` (InSPyReNet; SPAR3D), or BiRefNet. TRELLIS.2 outsources to the `briaai/BRIA-RMBG-2.0` Space via `gradio_client` — fine for an official Space, but a fragile external dependency for a user Space; prefer local rembg.
3. **Crop to the alpha bbox, resize** (≤1024 for TRELLIS-class, 512 for fast tier), **rescale the foreground** to ~85% of frame (`foreground_ratio` slider in the Stability Spaces), composite onto neutral gray or keep alpha.

Show the preprocessed image in the UI before generation — users need to see what the model actually gets, and a bad segmentation explains a bad mesh. Loading the rembg session at startup (TRELLIS runs one dummy `preprocess_image` at boot) avoids a first-click latency spike.

## Temp files and concurrency

Handlers run concurrently; never write to fixed paths. The pattern used by the official Spaces:

```python
demo = gr.Blocks(delete_cache=(600, 600))   # sweep files older than 600s every 600s

@demo.load(outputs=...)
def start_session(req: gr.Request):
    session_dir = os.path.join(TMP_ROOT, str(req.session_hash))
    os.makedirs(session_dir, exist_ok=True)
```

or simply `tempfile.NamedTemporaryFile(suffix=".glb", delete=False)` per call (TripoSR/SF3D). Either works; never a bare `"output.glb"`.

## Headless Blender (bpy / renders)

Blender shows up in 3D Spaces two ways: as the **`bpy` pip module** (`--extra-index-url https://download.blender.org/pypi/` + `bpy==<pin>`; Hunyuan3D-2.1 pins `bpy==4.0` — which installs cleanly on ZeroGPU with no display setup, though that Space's actual GLB conversion runs on trimesh+pygltflib), or as a **standalone binary** driven by a render script (TRELLIS-dataset-toolkit-style turntables, rigging/preprocessing tools). Spaces containers have no display; the working patterns, all verified from running Spaces:

- **pip `bpy` needs no xvfb.** Mesh ops, Cycles, and Workbench renders work headless — bpy creates its GL context via EGL/Mesa, not X11. The `packages.txt` seen in every working bpy demo Space (e.g. `radames/gradio-blender-bpy`) is just:

  ```
  libegl1-mesa-dev
  libgl1-mesa-dev
  ```

  ZeroGPU gotcha: **`import bpy` takes 30–60 s** — never import it inside a `@spaces.GPU` function (it burns the duration budget and aborts the task). Import at module scope, or run a persistent bpy worker in the main process (`VAST-AI/SkinTokens` does file-based IPC to one).
- **A modern Blender binary (≥3.4) needs no xvfb either**: download the tarball at startup, run `blender -b -noaudio --python script.py -- <args>` as a subprocess (`MajorDaniel/UniRig` on ZeroGPU). `packages.txt` then carries the binary's shared-lib deps: `libx11-6 libxi6 libxrender1 libxxf86vm1 libfontconfig1 libsm6 libxkbcommon0 libxkbcommon-x11-0 libgl1-mesa-glx`. Blender's manual is explicit that CLI/background rendering needs no display; a GPU Cycles subprocess must be launched from **inside** `@spaces.GPU` (it inherits the worker's CUDA), while display/env setup is process-global and belongs at module scope.
- **Reach for Xvfb only when forced**: a pinned pre-3.4 Blender binary (no EGL headless support yet), EEVEE on legacy setups, or non-Blender GL stacks (Open3D/VTK offscreen, pyglet). On the **gradio SDK**, don't launch raw `Xvfb :99 &` — the container lacks the `/tmp/.X11-unix` permissions for it (UniRig documents this) — use `pyvirtualdisplay` at module scope, the pattern `gradient-spaces/GuideFlow3D` uses to render Cycles through Blender 3.0.1 headlessly. `packages.txt`:

  ```
  xvfb
  libx11-6
  libgl1
  libxrender1
  libxi6
  libxkbcommon-x11-0
  libsm6
  ```

  and at the very top of `app.py`, before anything touches Blender/GL (plus `pyvirtualdisplay` in requirements.txt):

  ```python
  if os.environ.get("DISPLAY") is None:
      from pyvirtualdisplay import Display   # drives Xvfb with user-owned sockets
      display = Display(visible=0, size=(1920, 1080))
      display.start()
      os.environ.setdefault("DISPLAY", f":{display.display}")
  ```

  On the **Docker SDK** you control the image: `xvfb-run -a -s '-screen 0 1024x768x24' <cmd>` (or `Xvfb :99 ... & export DISPLAY=:99`), adding Mesa software-GL env on CPU hardware (`LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvm`).
- **Keep Space renders on Cycles.** EEVEE is GPU-rasterization by design (no CPU path — headless EEVEE exists on Linux ≥3.4 via EGL, but under Xvfb/software-GL it crawls); Cycles renders fine on CPU or on CUDA inside `@spaces.GPU`.
- **pyrender** (not Blender, but the same "needs GL" problem): use EGL, not Xvfb — `os.environ["PYOPENGL_PLATFORM"] = "egl"` with `libgl1-mesa-dev libglu1-mesa-dev freeglut3-dev mesa-common-dev` in packages.txt (`H-Liu1997/EMAGE` on ZeroGPU).

## Examples

`gr.Examples` with a handful of good input images makes or breaks first impressions of a 3D demo. Source them from the official Space's `assets/`/`examples/` dir (they're chosen to work well) or the model repo. On ZeroGPU use `cache_examples=True, cache_mode="lazy"`. Objects that demo well: single centered objects with clear silhouettes — figurines, shoes, furniture, vehicles. Objects that demo poorly: scenes, flat images, humans (most mesh models aren't trained for them), thin structures.
