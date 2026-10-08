# Andrew's Airsoft

A tactical airsoft team shooter for Roblox, built for grown-up players. Think a Sunday skirmish shot like an action film: BBs that actually fly and drop, honest hit calls, a hotel-style armory where you pick your gun, a neon nightclub in the rain, and a slow-motion replay of every round's final tag.

The whole game lives in code. Maps, gun models, player kit and HUD are all built procedurally, so it runs with zero uploads. When you want to go further, realistic Blender gun models (`assets/meshes/`) and synthesized gun sounds (`assets/audio/`) are ready to import, and the game uses them automatically.

---

## Quick start

1. **Install Roblox Studio**: <https://create.roblox.com/docs/studio/setting-up-roblox-studio>
2. **Install Rojo 7.7.1**, either with [Rokit](https://github.com/rojo-rbx/rokit) (`rokit install` in this folder) or from the [Rojo releases page](https://github.com/rojo-rbx/rojo/releases/tag/v7.7.1).
3. **Install the Rojo Studio plugin** by running `rojo plugin install` (or follow <https://rojo.space/docs/v7/getting-started/installation/>).
4. Clone the repo:
   ```bash
   git clone https://github.com/adam656677-oss/Andrews-Airsoft.git
   cd Andrews-Airsoft
   ```

### Option A: build a place file

```bash
rojo build default.project.json -o build/AndrewsAirsoft.rbxlx
```

Open `build/AndrewsAirsoft.rbxlx` in Studio and press **Play**. Lighting is already set to *Future*.

You can also download a ready-made place file from the latest run of the **Build** workflow: [Actions → Build](https://github.com/adam656677-oss/Andrews-Airsoft/actions/workflows/build.yml), then download the `AndrewsAirsoft-place` artifact.

### Option B: live sync while you edit

```bash
rojo serve
```

In Studio, open any place, click **Rojo → Connect**, and every save in `src/` appears in Studio instantly.

> Rojo can't set `Lighting.Technology` when it syncs into an existing place, so set **Lighting → Technology → Future** once in that place. Places made with `rojo build` already have it.

### Testing multiplayer

In Studio go to **Test → Clients and Servers**, choose 2–4 players and press **Start**. In Studio a match starts with a single player so you can test alone; live servers need 2.

### Saving progress in Studio

Ranks and stats are stored in a DataStore. To test that in Studio, turn on **Game Settings → Security → Enable Studio Access to API Services** (the place has to be published first). Without it the game still runs, it just doesn't save.

---

## The game

| | |
|---|---|
| **Ironwood Yard** | A 340×250-stud outdoor field at dusk with floodlights: a two-storey container yard (A), a CQB shoot house (B), a woodline bunker (C), barricades, sandbag walls, tyre stacks, cable spools, wrecks and team watchtowers. |
| **Velvet Club** | Night-time close quarters in the rain. A two-level nightclub with a neon street out front and a loading dock out back: the bar (A), an LED dance floor with moving lights (B), and a VIP balcony upstairs (C). Wet tarmac, puddles, lightning. |
| **Staging area** | Lobby with a chrono station, rules board and a **practice range** with steel targets that ding. Through the side door is **the Armory**: a walnut-and-brass gun room with every weapon hanging in its own lit bay. Walk up to one and press **E** to customise it. |
| **Modes** | **Team Deathmatch**: first to 30 tags. **Domination**: hold A/B/C; every held point scores every 2 s; first to 200. Players vote on **map and mode** between rounds. Both maps are mirrored, so neither side has an advantage. |
| **Round flow** | Intermission and vote (20 s) → Briefing, frozen at spawn (6 s) → Live (5 min) → **final tag replay** in slow motion → After-action report. |
| **Hit rules** | One BB anywhere is a hit. A tagged player calls "HIT!", gets an orange dead rag and walks off for 4 s. 3 s spawn protection, which ends as soon as you fire. No friendly fire. |
| **Progression** | XP for tags, captures, wins and finished matches. 10 ranks from *Recruit* to *Field Marshal*. Ranks unlock gun finishes, up to *Gilded*. Career stats, settings and every gun's attachments are saved. |

### Arsenal

| Gun | Class | Type | Character |
|---|---|---|---|
| M4A1 Carbine | Rifle | AEG | The benchmark: auto/semi, red dot and vertical grip by default |
| AK-74 Classic | Rifle | AEG | Wood and steel; harder-hitting, more kick |
| SR-25 DMR | DMR | AEG | Semi-auto marksman rifle with a 4× scope |
| VSR-10 | Sniper | Spring | Bolt action, whisper quiet, 10× scope overlay |
| M249 SAW | LMG | AEG | 100-round box, slow to aim |
| MP5 SD | SMG | AEG | Integrally suppressed CQB classic |
| Vector .45 | SMG | AEG | Absurd fire rate, three-round burst mode |
| MP7 | SMG | Gas | Snappy gas-blowback PDW |
| P90 | SMG | AEG | 50-round top-loading bullpup |
| M870 Tri-Shot | Shotgun | Gas | Three BBs per shell, pump between shots |
| G17 / G18C | Pistol | Gas | Reliable sidearm / full-auto machine pistol |
| 1911 | Pistol | Gas | Steel classic, flat shooting |
| Desert Eagle | Pistol | Gas | Huge velocity, huge kick |
| BB Burst Grenade | Utility | – | One per life, 16-stud burst, blocked by cover |

**Attachments** change real stats, and the armory shows the difference live:

| Slot | Options |
|---|---|
| Optic | Micro red dot, holographic, 4× combat scope, 10× sniper scope |
| Muzzle | Mock suppressor (quiet, different report), compensator (less climb) |
| Grip | Vertical (steadier auto), angled (faster aim) |
| Laser | Laser/light module (tighter hip fire, visible beam; **F** toggles) |

**Finishes:** Factory Black, Flat Dark Earth, Ranger Green, Cerakote Gunmetal, Arctic, Crimson Lacquer, Carbon Weave and Gilded. Each unlocks at a rank.

BBs are simulated as real projectiles with muzzle velocity, hop-up-limited drop, and spread that grows when you move, jump or hip-fire. Team-coloured tape on guns and armbands makes friendlies readable.

### Gun handling

- **Animated reloads:** the mag drops out and your support hand seats a fresh one. Empty reloads also charge the gun.
- **Gun actions:** pistols' slides blow back and lock open on empty. Snipers work the bolt and shotguns rack the pump between shots.
- **Inspect (I):** turn the gun over in your hands.
- **Slide:** crouch while sprinting to slide into cover.
- **Lean:** Q and E to lean around corners.

### Controls

| Action | Keyboard / mouse | Gamepad | Touch |
|---|---|---|---|
| Fire | LMB | RT | FIRE |
| Aim down sights | RMB (hold or toggle) | LT | AIM |
| Reload | R | X | R |
| Primary / sidearm | 1 / 2 / mouse wheel | Y | SWAP |
| Grenade | G | RB | G |
| Fire mode | B | D-pad ↑ | – |
| Weapon light | F | D-pad → | – |
| Sprint | Shift | L3 (toggle) | – |
| Crouch | C / Ctrl | B | C |
| Lean | Q / E | – | – |
| Inspect weapon | I | – | – |
| Slide | Crouch while sprinting | B while sprinting | C while sprinting |
| Customise at armory | E at a display | X | tap prompt |
| Scoreboard | Tab (hold) | D-pad ↓ | SCORES |
| Armory / loadout | L | D-pad ← | LOADOUT |
| Settings | P | Select | SETTINGS |
| Vote (frees mouse) | V | – | tap |

The settings menu has look sensitivity, aim sensitivity (scaled by zoom), field of view, and hold or toggle aim. These save to the player's profile.

---

## Project layout

```
default.project.json   Rojo project: maps src/ into the place, sets lighting and player settings
assets/
  meshes/              Blender-made .glb gun and attachment models to import
  audio/               Synthesized .ogg sounds to upload
  gunmodels/           Save imported gun models here as .rbxm so builds include them
tools/
  blender/             build_guns.py: generates assets/meshes, GunMeshData.lua and docs/renders
  audio/               make_sounds.py: generates assets/audio
src/
  shared/              → ReplicatedStorage.Shared
    Config.lua         All tuning: round timers, modes, maps, XP, ranks, movement, sounds
    Weapons.lua        Gun stats, attachments, finishes and stat resolution
    Ballistics.lua     BB flight simulation used by client and server
    GunBuilder.lua     Builds every gun: imported meshes if present, otherwise parts
    GunMeshData.lua    Generated by the Blender script: mesh piece layout per gun
    AssetIds.lua       Paste uploaded sound IDs here
    Remotes.lua        Every network channel in one place
  server/              → ServerScriptService.Server
    Main.server.lua    Entry point: builds the world, wires services, handles joins
    MapBuilder.lua     Ironwood Yard, staging area, armory, lighting presets
    ClubBuilder.lua    Velvet Club night map
    Gear.lua           Plate carrier, goggles, mask and armband for every player
    PlayerService.lua  Spawning, loadouts, ammo, spawn protection, out state
    CombatService.lua  Server-side shot and hit validation, grenades
    RoundService.lua   Match state machine, voting, teams, scoring, objectives
    DataService.lua    DataStore profiles (XP, stats, settings)
    Build.lua          Part-building helpers
  client/              → StarterPlayer.StarterPlayerScripts.Client
    Main.client.lua    Entry point
    WeaponController   Input, firing, ADS, recoil, sprint/crouch/lean, mobile + gamepad
    Viewmodel.lua      First-person gun and arms; draw, reload, inspect, bolt/pump/slide animation
    HUD.lua            Compass, scores, objectives, crosshair, ammo, kill feed, scope
    Menu.lua           Armory/loadout, settings, scoreboard, map+mode vote, after-action report
    Cinematic.lua      Slow-motion final tag replay
    Ambience.lua       Rain, lightning, armory prompts
    Effects.lua        BB tracers, impacts, sounds, grenade burst
    State.lua / UI.lua Client state and UI helpers
```

### Anti-cheat model

Each client simulates its own BBs so hits feel instant. The server keeps a record of every shot it accepted and checks each hit claim against that record before anyone is tagged:

- **Fire:** rate of fire, ammo, equipped weapon, pellet count, and muzzle near the head.
- **Hit:** shot exists and wasn't already used, flight time, range, hit position near the victim, angle from the original direction, line of sight, teams, spawn protection.

### Tuning

Most balance changes are a one-line edit in `src/shared/Config.lua` or `src/shared/Weapons.lua`. Some examples:

- Shorter rounds: `Config.RoundTime = 180`
- Longer walk-off: `Config.RespawnTime = 6`
- Snappier M4: lower `Weapons.List.M4.FireInterval`

## Realistic gun models and sounds

Out of the box, every gun is built from parts and every shot uses a built-in Roblox sound, so the game works with nothing uploaded. The repo also ships upgrade assets that the game picks up automatically.

### Gun models (Blender)

`assets/meshes/` contains a `.glb` file for every gun (`M4.glb`, `AK74.glb`, …) and attachment (`ATT_RedDot.glb`, …). They're generated by `tools/blender/build_guns.py`; preview renders are in `docs/renders/`.

1. In Studio, open the **Asset Manager** and use **Bulk Import**, or use **Home → Import 3D** one file at a time. Pick the `.glb` files from `assets/meshes/`.
2. In the import dialog, keep the defaults and import each file as a **Model**.
3. Move each imported model into **ReplicatedStorage → GunModels**. Make sure its name matches the file name exactly (`M4`, `ATT_RedDot`, …).
4. Press Play. Guns with an imported model use it; anything missing falls back to the part-built version. Finishes, team tape, attachments and reload animations work on both.

To keep the models in builds made with `rojo build`, right-click each model → **Save to File…** and save it as `assets/gunmodels/<ID>.rbxm`. Rojo then puts it back into `ReplicatedStorage.GunModels` every build. While using `rojo serve`, models you import straight into GunModels are left alone.

### Sounds

`assets/audio/` has synthesized `.ogg` files for each gun class (rifle, SMG, DMR, LMG, sniper, shotgun, pistol, magnum, suppressed) plus magazine, bolt, hit-marker, steel-target and grenade sounds. They come from `tools/audio/make_sounds.py`.

1. Upload them at <https://create.roblox.com/dashboard/creations> → **Development Items → Audio** (or the Asset Manager's bulk import).
2. Paste each asset ID into `src/shared/AssetIds.lua` under the matching name.

Any ID left at `0` falls back to the built-in sound, pitched per gun class so guns still sound different. Recorded airsoft audio will always beat synthesis; drop real recordings in the same slots whenever you have them.

---

## Publishing

### From Studio
Open the built place, then **File → Publish to Roblox**. Docs: <https://create.roblox.com/docs/production/publishing/publishing-experiences-and-places>

### From GitHub (one click)
The **Publish to Roblox** workflow builds the place and uploads it through Open Cloud.

1. Create an API key at <https://create.roblox.com/dashboard/credentials> with the **universe-places → write** permission for your experience.
2. In this repo go to **Settings → Secrets and variables → Actions**:
   - Secret `ROBLOX_API_KEY`: the key
   - Variable `ROBLOX_UNIVERSE_ID`: the experience ID (Creator Dashboard → your experience → *Copy Universe ID*)
   - Variable `ROBLOX_PLACE_ID`: the start place ID
3. Go to [Actions → Publish to Roblox](https://github.com/adam656677-oss/Andrews-Airsoft/actions/workflows/publish.yml) → **Run workflow**. Choose *Saved* for a draft or *Published* to go live.

### Before going public
- Experience settings: **Avatar → R15**, **Max players 16–20**, **Genre → Shooter**.
- Fill in the **Experience Questionnaire** so the maturity label is accurate. The game has no blood or gore and players are "tagged", not killed.
- Add a thumbnail and icon (screenshots from the staging area at dusk work well).

---

## Useful links

- Rojo docs: <https://rojo.space/docs/v7/>
- Roblox Creator Docs: <https://create.roblox.com/docs>
- Open Cloud place publishing API: <https://create.roblox.com/docs/cloud/reference/features/places>
- Luau language: <https://luau.org>
- Repo: <https://github.com/adam656677-oss/Andrews-Airsoft>
