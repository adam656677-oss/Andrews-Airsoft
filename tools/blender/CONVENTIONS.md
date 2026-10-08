# Blender asset conventions

Every generator in `tools/blender/` follows these rules so the game code can place assets without hand-tweaking.

## Running

- Python with `bpy` (Blender 5.2): use `/tmp/claude-0/-home-user-andrews-airsoft/1e18fa5f-f99a-57ee-8af3-4f8388e850fd/scratchpad/bvenv/bin/python` in the cloud session, or any Blender 4.2+ with `blender -b -P script.py`.
- Scripts must be deterministic (fixed random seeds) and re-runnable. Passing asset IDs on the command line rebuilds only those.
- No GPU: render and bake with Cycles on CPU, with denoising on.

## Roblox limits (hard)

| Limit | Value | Notes |
|---|---|---|
| Triangles per mesh object | 20,000 max | Aim for 15,000 or fewer per object |
| Texture size | 1024 × 1024 | Roblox downsamples anything larger. Bake at 2048 with supersampling, then downscale to 1024 with high-quality filtering |
| Textures per object | 1 set | Colour, normal, roughness, metalness (SurfaceAppearance) |

## Coordinates

- Model in Blender with forward = +Y, up = +Z, right = +X, 1 Blender unit = 1 Roblox stud.
- Game coordinates = (bx, bz, −by), so Roblox −Z is forward.
- Every position written into a `*MeshData.lua` module is in game coordinates, rounded to 3 decimals.
- Before export, every mesh object must have its transforms applied and its origin at the centre of its bounding box.

## Export

- One `.glb` per asset, containing only that asset's objects: `bpy.ops.export_scene.gltf(export_format='GLB', export_yup=True)`.
- Mesh object names inside the GLB must match the `Name` fields in the metadata exactly.
- Textures are embedded in the GLB with a glTF metallic-roughness material per object, and every object is UV-unwrapped:
  - base colour as JPEG, quality 92
  - normal map as PNG, OpenGL convention
  - metallic and roughness packed as glTF expects (G = roughness, B = metallic)
- **Tintable roles** (`Primary`, `Secondary`, `Accent`) must be baked as **neutral light grey**: about 0.8 linear, with wear, grime and edge highlights as luminance variation only. The game tints them per skin or team via `SurfaceAppearance.Color`. All other roles (`Metal`, `Wood`, `Glass`, `Rubber`, `Fabric`, …) are baked in their real colours.

## Quality bar

- Real proportions taken from real-world references.
- Bevelled edges everywhere (no razor-sharp box corners).
- Boolean detail: cuts, vents, screws, serrations, stitching.
- Fabric gets seams and folds; metal gets edge wear; polymer gets texture.
- Look at every render with the Read tool and iterate until it holds up at 4K.
- Renders go to `docs/renders/<category>/`. Make a 3840 × 2160 hero render for each category's lineup sheet, and smaller 1600 × 900 renders per asset.
