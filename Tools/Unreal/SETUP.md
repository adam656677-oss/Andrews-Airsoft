# Andrew's Airsoft: Unreal editor setup

`Content/Python/airsoft_setup.py` turns a fresh checkout into a playable project in one run. It does four things:

1. **Imports** every generated asset: FBX pieces, PNG textures and WAV audio.
2. **Builds** the master materials and their instances.
3. **Assigns** the instances to each mesh's material slots.
4. **Builds all five maps**, with lighting.

The script is **idempotent**:

- An asset whose source file is unchanged is skipped. Change detection uses a metadata tag holding the source file's mtime, size and an import version.
- Map actors created by the script carry the tag `AirsoftGen`. A re-run deletes and rebuilds them.
- Anything you place by hand, without that tag, is never touched.

When a mesh is missing, the script places engine basic shapes sized from the JSON bounds (or the table in `layouts.py`) and gives them matching tileable materials. The game is playable before any 4K asset exists.

## Before you run it

1. Open `AndrewsAirsoft.uproject` in **UE 5.8** and let it compile the `AndrewsAirsoft` module (or build it in your IDE first). The script needs these classes from the module:
   - `AirsoftTeamStart`, `AirsoftObjective`, `AirsoftPracticeTarget`, `AirsoftArmoryDisplay`
   - `AirsoftGameMode`, `AirsoftMenuGameMode`

   If they are missing, the summary says so and those actors are skipped.
2. Make sure these plugins are enabled. The `.uproject` already enables them; check **Edit > Plugins** if unsure.
   - **Python Editor Script Plugin**
   - **Editor Scripting Utilities**
3. Put the generated content in place:
   - `SourceAssets/` (Blender generators, or the GitHub Release zips)
   - `Tools/Audio/Generated/*.wav`
   - `Content/Airsoft/Data/*.json` (committed)

   Partial content is fine. Re-run the script whenever more assets land.
4. **Save your open level.** Loading or creating maps can otherwise pop a "save changes?" dialog.

## Running

**Tools > Execute Python Script...**, then pick `Content/Python/airsoft_setup.py`. Or use the editor console (`` ` ``):

```
py airsoft_setup.py                                   # everything (first run: allow 10-40 min for 4K imports + shaders)
py airsoft_setup.py --maps Staging --skip-import      # rebuild one map only, fast
py airsoft_setup.py --maps IronwoodYard,VelvetClub --skip-import --skip-materials
py airsoft_setup.py --skip-import --maps none         # rebuild materials + slot assignment only
py airsoft_setup.py --force-import --only M4,AK74     # re-import specific assets
py airsoft_setup.py --skip-audio                      # leave sounds alone
py airsoft_setup.py --skip-import --rebuild-masters --maps none   # after editing a master graph in materials.py
```

The map names are `MainMenu`, `Transition`, `Staging`, `IronwoodYard` and `VelvetClub`. Aliases such as `menu`, `field`, `club` and `L_Staging` also work.

From Python you can call the script directly: `import airsoft_setup; airsoft_setup.main(["--maps", "Staging", "--skip-import"])`.

When it finishes, the Output Log (filter on `AirsoftSetup`) prints a **summary**:

- counts of imported, skipped and created assets
- **missing** sources, where a fallback was used
- per-map actor counts
- the save status of every map

## What it does

### Import (`airsoft_setup_lib/importers.py`)

**Asset list.** The script reads every `Content/Airsoft/Data/<Category>*.json`. `PropsClub.json` maps to the `Props` category. It then adds anything found on disk under `SourceAssets/<Category>/<Id>/SM_<Id>_<Piece>.fbx` that the JSON doesn't list yet.

**FBX.** While importing, the script switches FBX to the **legacy importer** (`Interchange.FeatureFlags.Import.FBX False`) and restores the previous value afterwards. Since UE 5.5 Interchange ignores the `FbxImportUI` options.

Each piece is imported to `/Game/Airsoft/Meshes/<Category>/<Id>/SM_<Id>_<Piece>` with these settings:

- no materials or textures created
- normals and tangents imported
- no lightmap UVs
- combine off, and if the importer names the result after the FBX node, it is renamed to `SM_<Id>_<Piece>`

**Nanite.** Nanite is on for opaque, emissive and masked (leaf or net) pieces. Masked Nanite is supported in UE 5.1+ and controlled by `NANITE_MASKED_FOLIAGE` in `common.py`. Nanite is off for `Glass` pieces, which are translucent.

**Collision** follows the JSON `Collision` field:

| `Collision` value | Result |
|---|---|
| `Box` | simple box |
| `Convex` | convex decomposition, with a 26-DOP fallback |
| `Complex` | use complex as simple |
| (missing) | architecture uses `layouts.KNOWN_ASSETS` (walls `Box`, door and window walls `Complex`) |

Exceptions:

- Trees always use `Complex`, so the trunk and branches collide but not a hull around the crown.
- Glass, emissive, leaf, net, flag and rope pieces get no collision.
- The `Weapons`, `Attachments` and `Gear` categories get no collision at all.
- `SteelTarget` Plate keeps a box, for BB hits.

**Textures** go to `/Game/Airsoft/Textures/<Category>/<Id>/`, and tileables to `/Game/Airsoft/Textures/Materials/<Mat>/`:

| Map | Colour space | Compression | LOD group |
|---|---|---|---|
| `_BC` | sRGB | Default | World (Weapon for guns) |
| `_N` | linear | Normal map | WorldNormalMap (DirectX green, no flip) |
| `_ORM`, `_M`, `_H`, `_Opacity` | linear | Masks | WorldSpecular |

Virtual texture streaming is **off** by default (`USE_VIRTUAL_TEXTURES`). With VT on, every texture in a material instance must match its parent's sampler type, so mixing VT and non-VT sets breaks instances. Regular mip streaming handles 4K fine.

**Default textures** are written to `Saved/AirsoftSetup` and imported to `/Game/Airsoft/Textures/Defaults`: white base colour, flat normal, ORM (1, 0.55, 0) and a black mask. Every material parameter therefore has a valid default with the correct sampler type.

**Audio.** Every `Tools/Audio/Generated/*.wav` is imported to `/Game/Airsoft/Audio/<Key>`. These keys are set to **loop**: `AmbienceField`, `AmbienceClubStreet`, `AmbienceClubInterior`, `ClubMusic`, `AmbienceStaging`, `MenuMusic`, plus any other `Ambience*` or `*Music` key. The game code adds attenuation to its own 3D one-shots.

### Materials (`airsoft_setup_lib/materials.py`)

These are built node by node in `/Game/Airsoft/Materials/`. Each master is stamped with `MASTER_VERSION`, and a re-run skips any master whose stamp is current, which avoids a full shader recompile. Pass `--rebuild-masters` or `--force-import` to rebuild them anyway.

| Material | Purpose and parameters |
|---|---|
| `M_AirsoftPBR` | `BaseColor` / `Normal` / `ORM` / `Mask` textures; `PrimaryTint` / `SecondaryTint` / `AccentTint` (white, white, orange); `TintMetallic` (0) and `TintRoughness` (0.55); `RoughnessScale`, `NormalStrength`, `BaseTint`; static switch `UseMask`. Base colour = BC × lerp(1, tint, mask) per role. Metallic and roughness lerp toward the tint values inside the masks. The game sets the tints on every gun-part MID at runtime. |
| `M_Tileable` | `BaseColor` / `Normal` / `ORM` / `Height`; `TileMeters` (UV × 2 / TileMeters, because architecture UVs are 1 UV = 2 m); `WorldAligned` (dominant-axis planar world projection for floors, boxes and fallbacks); `ColorVariation` (a macro-scale variation that breaks up tiling); `Tint`, `RoughnessScale`, `RoughnessAdd`, `MetallicScale`, `HeightAO`. |
| `M_Emissive` | Unlit. `Color`, `Intensity` and an optional `EmissiveMap`. This is the material `DefaultGame.ini` names as `BBMaterial`. |
| `M_Glass` | Translucent, Surface Forward Shading. `Tint`, `Opacity`, Fresnel opacity, `Roughness`, `IOR` 1.05 (subtle refraction), and `Glow` for lamp glass. |
| `M_Masked` | Two-sided foliage, masked by an `Opacity` texture, with subsurface colour. Used for leaves and netting. |
| `M_SignText` | Unlit glowing TextRender letters. |

Instances live in `/Game/Airsoft/Materials/Instances/`:

| Folder | Instances |
|---|---|
| `Tileable/` | `MI_<Material>` for every `Materials.json` entry. A material without textures gets a flat colour. |
| `Tileable/Variants/` | World-aligned and tinted variants for blocks and fallbacks |
| `<Category>/` | `MI_<Id>_<Piece>` for every unique texture set, plus paint variants such as `MI_Container_20ft_Body_Red` / `_Blue` / `_Green` / `_Rust` / `_Sand` / `_Grey`, and car variants (`Black`, `DeepRed`, `Gunmetal`, `White`). Variant names come from `layouts.TINT_VARIANTS` and the JSON `TintVariants`. |
| `Emissive/` | `MI_Emissive_<Colour>_<Intensity>` |
| `Glass/` | glass instances, including the editor-only translucent blocker material |
| `Special/` | puddle, foliage and other special instances |

Slots are assigned by name:

- `M_<Id>_<Piece>` gets `MI_<Id>_<Piece>`.
- `MI_<Mat>` gets the tileable instance.
- Blender `.001` and `_R` suffixes are tolerated.

A prop placed with a `tint` uses the matching paint variant as a per-placement override.

### Maps (`airsoft_setup_lib/levels.py`, `lighting.py`, `layouts.py`)

All five maps are non-World-Partition levels in `/Game/Maps/`. Every playable map gets:

- SkyAtmosphere and a DirectionalLight (atmosphere sun, Virtual Shadow Maps)
- a SkyLight with real-time capture
- VolumetricCloud outdoors
- ExponentialHeightFog with volumetric fog
- an infinite PostProcessVolume:
  - Lumen GI and reflections at quality 1 (high, not epic), suited to an RTX 2070
  - histogram auto exposure clamped to a tight EV100 range per map
  - bloom, vignette 0.3–0.4, film grain 0.1–0.15, chromatic aberration ≤ 0.1, local exposure
- reflection captures
- a KillZ
- AirsoftTeamStart actors only (plain PlayerStarts are removed)

| Map | Contents |
|---|---|
| `L_MainMenu` | A corner of The Armory: walnut panels, five gun bays showing hero guns, counter with gun case and banker's lamp, Persian rug, brass ceiling lights, haze. A CineCamera (35 mm, f/2.8, focused on the counter) auto-activates for Player 0. GameMode override `AirsoftMenuGameMode`. 2D `MenuMusic`. |
| `L_Transition` | Empty, used for seamless travel. |
| `L_Staging` | The lobby, at golden hour. Spawn and briefing hall with an "ANDREW'S AIRSOFT" sign and 18 neutral starts. **The Armory**: 14 bays, one display per weapon. Outdoor range: firing line under a roof, chrono tables, barricades between four lanes, practice targets at 10/25/40/60 m, a berm. Open-top plywood kill house, movement lane, storage yard. `AmbienceStaging`. |
| `L_IronwoodYard` | 130 × 90 m field, golden hour turning to dusk. Point-symmetric, with three lanes. Container yard at A, CQB village with a catwalk bridge at B, log bunker at C. Watchtowers, four floodlight towers (on at dusk), netting perimeter, trees and invisible walls. Each side has a concrete spawn pen with a baffled exit and 12 starts. `AmbienceField`. |
| `L_VelvetClub` | Rain-soaked night city block. Wet street with puddles, parked cars, a box truck, kiosks, street lamps, and the velvet-rope queue under the neon sign. Two-level club: island bar (B), dance floor and DJ stage (C side), west VIP mezzanine on stairs, east VIP lounge, kitchen. Back alley and loading dock. Blue spawns in a valet lot off the street; Red spawns in a walled loading yard. Street, interior and music ambience. |

Layouts are **pure data** in `airsoft_setup_lib/layouts.py`: metres, Unreal axes, yaw in degrees. Tune them there, check them with the layout checker, then rebuild one map:

```
python3 Tools/Unreal/check_layouts.py            # rules + plans -> Tools/Unreal/Plans/<Map>.png
py airsoft_setup.py --maps IronwoodYard --skip-import
```

The checker validates:

- asset ids, materials and tints
- spawns inside the bounds and not inside props
- at least 10 Blue and 10 Red starts with ≥ 1.5 m spacing
- objectives A/B/C present and reachable from both spawns
- no sight line from one spawn to the other
- spawn exposure
- cover spacing
- staging rules: 16+ neutral starts, 14 displays, targets at 10/25/40/60 m

## Things to do by hand

- **Third-person mannequin.** `DefaultGame.ini` points at `/Game/Characters/Mannequins/...`. Add it with **Add > Add Feature or Content Pack > Third Person** (Blueprint). The pack's own maps and GameMode can be deleted. Until then the game uses its built-in capsule body.
- **Rain.** The club is "rain-soaked" through wet asphalt, low-roughness puddles and haze. A Niagara rain system is not created by the script. Drop the engine or Marketplace rain emitter near the street if you want falling rain.
- **Shaders.** After the first run, let shader compilation finish (bottom-right counter) before judging the lighting.
- **Packaging.** `DefaultGame.ini` already lists the maps and `/Game/Airsoft` for cooking.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `unreal.AirsoftTeamStart not found` in the summary | The C++ module isn't compiled or loaded. Build it, restart the editor, re-run. |
| Meshes import with auto-created materials or ignore settings | Interchange is still active. Run `Interchange.FeatureFlags.Import.FBX False` in the console, then re-run with `--force-import`. |
| **Meshes face the wrong way** (summary: "imported rotated 90 deg vs JSON bounds") | Set `FBX_IMPORT_YAW = 90` (or `-90`), or `FBX_FORCE_FRONT_X = True`, in `common.py`, then run with `--force-import`. |
| "static switch parameters cannot be set" | Harmless. `UseMask` stays on, and the black default mask leaves untinted assets unchanged. |
| A map didn't save, or a "save changes?" dialog appeared | Save or close the current level and re-run with `--skip-import --maps <Map>`. |
| Grey or flat-colour blocks everywhere | Those assets haven't been generated or imported yet: see "missing" in the summary. Generate them, then re-run without `--skip-import`. |
| Lighting looks blown out or too dark | Check post-process exposure: the per-map EV100 ranges are in `lighting.PRESETS`. Local light intensities are in candela at the same low scale as the game's C++ (sun 5–10 lux). |
| Everything re-imports every run | The metadata tag couldn't be written (see the log). Bump `IMPORT_VERSION` only when you change import settings. |
| Ambient sounds missing | WAVs weren't present at import. Generate them (`Tools/Audio`), then run with `--maps <Map> --skip-import`. The audio import still runs unless `--skip-audio` is set. |

## Files

```
Content/Python/airsoft_setup.py            entry point (main(), CLI flags)
Content/Python/airsoft_setup_lib/
    common.py      paths, logging, summary, registry (JSON + disk), PNG writer, switches
    importers.py   FBX / PNG / WAV import, Nanite, collision, change detection
    materials.py   master materials, instances, tint variants, slot assignment
    lighting.py    per-map presets (sun, sky, clouds, fog, post), fixture lights
    levels.py      opens/creates maps, clears generated actors, spawns everything, saves
    layouts.py     pure-data layouts, asset size/fallback table (no unreal import)
Tools/Unreal/check_layouts.py              plain-Python checker + plan renderer
Tools/Unreal/Plans/<Map>.png               top-down plans (regenerated by the checker)
```
