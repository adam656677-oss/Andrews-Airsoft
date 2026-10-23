# Blender → Unreal asset conventions

Every generator in `Tools/Blender/` follows these rules. The editor setup script (`Content/Python/airsoft_setup.py`) and the C++ game code rely on them to import and assemble assets with no hand-placement.

## Running the generators

- Python with `bpy` (Blender 4.2+ or 5.x), or `blender -b -P <script>.py -- [ids...]`.
- Scripts are deterministic (fixed seeds) and re-runnable. Passing IDs after `--` rebuilds only those assets.
- Scripts take `--res 4096|2048|1024`. The default is 4096; previews and CI use 1024.
- They render and bake with Cycles. They use the GPU (OptiX/CUDA) when one exists and fall back to CPU otherwise.
- Output goes under `SourceAssets/` (git-ignored; shipped as GitHub Release zips).
- Small JSON data goes under `Content/Airsoft/Data/` (committed).

## Units and axes

| | Blender (author here) | Unreal (after import) |
|---|---|---|
| Units | 1 unit = 1 metre | 1 unit = 1 cm |
| Forward (barrel / front of prop) | **+X** | +X |
| Up | +Z | +Z |
| Right | −Y | +Y |

- Export FBX with `axis_forward='X', axis_up='Z', apply_unit_scale=True, global_scale=1.0, apply_scale_options='FBX_SCALE_ALL'`, `use_tspace=True`, `mesh_smooth_type='FACE'`, and `add_leaf_bones=False`.
- In JSON, every position is in **Unreal space, centimetres**: `ue = (bx*100, -by*100, bz*100)`, rounded to 0.1.

## Pivots

Every piece of an asset is exported as its **own FBX**, with its origin at the **asset origin** rather than at its own centre. Importing all of an asset's pieces at (0,0,0) therefore reassembles it exactly.

| Category | Asset origin |
|---|---|
| Guns | Centre of the pistol grip where the hand holds it, barrel along +X |
| Attachments | The mount point (optic and grip: bottom-centre of the clamp; muzzle device: rear of the bore; magazine: top-centre where it seats in the mag well) |
| Props and architecture | Floor-centre of the footprint, front facing +X |
| Gear | The bone pivot it attaches to (see the gear spec) |

## Files

```
SourceAssets/<Category>/<AssetId>/
  SM_<AssetId>_<Piece>.fbx        one per piece (Body, Mag, Slide, Bolt, Pump, Glass, ...)
  T_<AssetId>_<Piece>_BC.png      base colour, sRGB
  T_<AssetId>_<Piece>_N.png       normal map, DirectX convention (green = -Y), as Unreal expects
  T_<AssetId>_<Piece>_ORM.png     R = ambient occlusion, G = roughness, B = metallic (linear)
  T_<AssetId>_<Piece>_M.png       role mask (linear): R = Primary, G = Secondary, B = Accent (team tape)
```

- Categories: `Weapons`, `Attachments`, `Gear`, `Props`, `Architecture`, `Materials` (tileable sets: `T_<Mat>_BC/N/ORM/H.png`).
- Material slot names in the FBX must be one of:
  - `M_<AssetId>_<Piece>`, for a unique baked texture set;
  - `MI_<MaterialId>`, for a shared tileable material from `Materials/` (architecture uses these).

## Textures

- **Resolution (at `--res 4096`):**
  - 4096: gun bodies, hero props, tileable materials
  - 2048: magazines, slides, attachments, small props
  - 1024: role masks
- Bake at the target size with denoising. Use 8-bit PNGs, except height maps, which are 16-bit.
- **Neutral base colour for tinted areas:** where the role mask is set, bake the base colour as a neutral light grey (about 0.75 linear). Keep wear, grime and edge highlights as luminance variation only. The game multiplies in the finish or team colour. All other areas keep their real colours (bare metal, wood, rubber, glass).
- **What to bake:** realism comes from the bake. That means edge wear (curvature-driven), cavity dirt (AO), micro-surface variation in roughness, and fine detail in the normal map (stippling, texture, small screws and engraving that the mesh doesn't carry).

## Geometry

- **Nanite is on for all opaque meshes.** High poly counts are fine and encouraged: bevel every edge with a real chamfer and model the actual detail. Typical budgets:
  - gun body: 150k–400k triangles
  - prop: 20k–200k
  - architecture module: 5k–50k
- **Glass and lenses** are separate pieces named `Glass`. They are not Nanite (Unreal translucency), so keep each under 5k triangles.
- UV-unwrap every baked piece: smart project plus pack with island margin, around 4 px at 4K, uniform texel density.
- **Architecture** is UV'd at real-world scale (1 UV unit = 2 m) so tileable materials line up across modules.

## JSON data (committed)

`Content/Airsoft/Data/<Category>.json`:

```json
{
  "Version": 1,
  "Assets": {
    "M4": {
      "Pieces": [ { "Name": "Body", "Kind": "Body", "Slots": ["M_M4_Body"] }, { "Name": "Mag", "Kind": "Mag" } ],
      "Points": { "Muzzle": [x, y, z], "Aim": [x, y, z], "LeftHand": [x, y, z], "MagWell": [x, y, z],
                  "Optic": [x, y, z], "Underbarrel": [x, y, z], "MuzzleMount": [x, y, z], "Side": [x, y, z] },
      "Bounds": { "Min": [x, y, z], "Max": [x, y, z] }
    }
  }
}
```

- Valid `Kind` values: `Body`, `Mag`, `Slide`, `Bolt`, `Pump`, `Glass`, `Static`.
- Points that don't apply are left out.
- Attachments add `AimOffset` (optics) or `MuzzleOffset` (muzzle devices), relative to their mount point.

## Renders

- Per asset: 1920 × 1080 product shot at `Docs/Renders/<Category>/<AssetId>.png`.
- Per category: a 3840 × 2160 lineup at `Docs/Renders/<Category>/_Lineup_4K.png`.
- Use the AgX view transform, a soft three-point studio with a gradient world, and a subtle ground contact shadow.
- **Look at every render with the Read tool and iterate** until it would hold up as a product photo.
