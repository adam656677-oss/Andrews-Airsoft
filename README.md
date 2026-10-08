# Andrew's Airsoft

A tactical airsoft team shooter for Roblox, aimed at grown-up players who want the feel of a real Sunday skirmish: BBs that actually fly and drop, honest hit calls, spawn discipline and a field built for flanking.

The whole game lives in code. The map, every gun model, player kit and the HUD are built procedurally, so the repo is the single source of truth and there are no uploaded assets to lose.

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
| **Field** | *Ironwood Yard*: a 340×250-stud outdoor field at dusk with floodlights, a two-storey container yard (A), a CQB shoot house (B), a woodline bunker (C), barricades, sandbag walls, tyre stacks, cable spools, wrecks and team watchtowers. Mirrored, so neither side has an advantage. |
| **Staging area** | Lobby with a chrono station, field rules board, gun racks and a **practice range** with steel targets that ding when hit. |
| **Modes** | **Team Deathmatch**: first to 30 tags. **Domination**: hold A/B/C; every held point scores every 2 s; first to 200. Players vote between rounds. |
| **Round flow** | Intermission and vote (20 s) → Briefing, frozen at spawn (6 s) → Live (5 min) → After-action report (12 s). |
| **Hit rules** | One BB anywhere is a hit. A tagged player calls "HIT!", gets an orange dead rag and walks off for 4 s. 3 s spawn protection, which ends as soon as you fire. No friendly fire. |
| **Progression** | XP for tags, captures, wins and finished matches. 10 ranks from *Recruit* to *Field Marshal*. Career stats and settings are saved. |

### Arsenal

| Gun | Type | Notes |
|---|---|---|
| M4A1 Carbine | AEG | All-rounder, red dot, full auto / semi |
| MP5 SD | AEG | CQB, fastest handling, 40-round mags |
| SR-25 DMR | AEG | Semi-auto, 4× scope |
| VSR-10 | Spring | Bolt-action sniper, quiet, 18 FOV scope |
| M870 Tri-Shot | Gas | Three BBs per shell |
| G17 GBB | Gas | Sidearm for everyone |
| BB Burst Grenade | Utility | One per life, 16-stud burst, blocked by cover |

BBs are simulated as real projectiles with muzzle velocity, hop-up-limited drop, and spread that grows when you move, jump or hip-fire. Each gun can carry a weapon light, and team-coloured tape on guns and armbands makes friendlies readable.

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
| Scoreboard | Tab (hold) | D-pad ↓ | SCORES |
| Loadout | L | D-pad ← | LOADOUT |
| Settings | P | Select | SETTINGS |
| Vote (frees mouse) | V | – | tap |

The settings menu has look sensitivity, aim sensitivity (scaled by zoom), field of view, and hold or toggle aim. These save to the player's profile.

---

## Project layout

```
default.project.json   Rojo project: maps src/ into the place, sets lighting and player settings
src/
  shared/              → ReplicatedStorage.Shared
    Config.lua         All tuning: round timers, modes, XP, ranks, movement, sounds
    Weapons.lua        Gun stats (velocity, drop, spread, recoil, mags…)
    Ballistics.lua     BB flight simulation used by client and server
    GunBuilder.lua     Builds every gun model from parts
    Remotes.lua        Every network channel in one place
  server/              → ServerScriptService.Server
    Main.server.lua    Entry point: builds the world, wires services, handles joins
    MapBuilder.lua     Ironwood Yard + staging area + lighting
    Gear.lua           Plate carrier, goggles, mask and armband for every player
    PlayerService.lua  Spawning, loadouts, ammo, spawn protection, out state
    CombatService.lua  Server-side shot and hit validation, grenades
    RoundService.lua   Match state machine, voting, teams, scoring, objectives
    DataService.lua    DataStore profiles (XP, stats, settings)
    Build.lua          Part-building helpers
  client/              → StarterPlayer.StarterPlayerScripts.Client
    Main.client.lua    Entry point
    WeaponController   Input, firing, ADS, recoil, sprint/crouch/lean, mobile + gamepad
    Viewmodel.lua      First-person gun and arms, sway, bob, reload pose
    HUD.lua            Compass, scores, objectives, crosshair, ammo, kill feed, scope
    Menu.lua           Loadout, settings, scoreboard, mode vote, after-action report
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

### Sounds

The game uses audio that ships with every Roblox client, so nothing fails to load. For a more premium mix, upload your own sounds at <https://create.roblox.com/dashboard/creations> and replace the IDs in `Config.Sounds`.

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
