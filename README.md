# Andrew's Airsoft — Unreal Engine 5

A tactical airsoft team shooter for a private group of friends (10–20 players), built in **Unreal Engine 5.8** for 4K on an **RTX 2070**. One person hosts; everyone else joins over **Tailscale**.

Real airsoft rules: BBs are real projectiles (muzzle velocity, drag, hop-up lift, end-of-flight drop). One hit and you're out: call it, the dead rag goes up, you walk off and respawn. 14 replica guns, 13 attachments, 8 earned finishes, 10 ranks. Three match maps (Ironwood Yard, Velvet Club and Nightjar Garage), a staging lobby with a walnut-and-brass armory and a practice range, five modes (Team Deathmatch, Domination, Elimination, Gun Game and VIP Escort), bots to fill teams or practise alone, text chat, and a slow-motion replay of the final tag.

---

## Map stills

![Velvet Club](Docs/Screens/00_Poster_1920x1080.jpg)

| | |
|---|---|
| ![Velvet Club first person](Docs/Screens/04_VelvetClub_FirstPerson_HUD.jpg) | ![Velvet Club dance floor](Docs/Screens/02_VelvetClub_DanceFloor.jpg) |
| ![The Armory](Docs/Screens/03_Staging_Armory.jpg) | ![M4 in its case](Docs/Screens/08_Armory_M4_Hero.jpg) |
| ![Ironwood Yard at golden hour](Docs/Screens/05_Ironwood_GoldenHour.jpg) | ![Objective A](Docs/Screens/06_Ironwood_ObjectiveA.jpg) |
| ![Practice range](Docs/Screens/07_Staging_Range.jpg) | ![Watchtower](Docs/Screens/09_Ironwood_Watchtower_Backlit.jpg) |
| ![Nightjar Garage ramp](Docs/Screens/11_NightjarGarage_Ramp.jpg) | ![Nightjar Garage roof deck](Docs/Screens/10_NightjarGarage_RoofDeck.jpg) |
| ![Nightjar Garage parking row](Docs/Screens/12_NightjarGarage_ParkingRow.jpg) | ![Nightjar Garage objective C](Docs/Screens/13_NightjarGarage_ObjectiveC.jpg) |

![Team gear, Blue and Red](Docs/Renders/Gear/_TeamGear_Lineup.jpg)

These are offline Blender renders of the real map layouts and assets (`Tools/Blender/render_scenes.py`), not in-engine screenshots: path tracing instead of Lumen, no players shown, and the HUD is a mock-up.

## Gallery (generated 4K art)

| | |
|---|---|
| ![Weapons](Docs/Renders/Weapons/_Lineup_4K.jpg) | ![Attachments](Docs/Renders/Attachments/_Lineup_4K.jpg) |
| ![First-person gloves](Docs/Renders/Gear/Gloves_FirstPerson.jpg) | ![Pistol grip](Docs/Renders/Gear/Gloves_FirstPerson_Pistol.jpg) |
| ![Velvet Club props](Docs/Renders/PropsClub/_Lineup_Club_4K.jpg) | ![The Armory](Docs/Renders/PropsClub/_Lineup_Armory_4K.jpg) |
| ![Field props](Docs/Renders/Props/_Lineup_4K.jpg) | ![Architecture kit](Docs/Renders/Architecture/_Lineup_4K.jpg) |
| ![Materials](Docs/Renders/Materials/_Lineup_4K.jpg) | ![Ironwood Yard plan](Tools/Unreal/Plans/IronwoodYard.png) |

Every asset has its own product shot in `Docs/Renders/<Category>/`.

## 1. Install (once per PC)

| What | Notes |
|---|---|
| **Epic Games Launcher → Unreal Engine 5.8** | In *Options*, include **Starter Content** and **Templates and Feature Packs**. |
| **Visual Studio 2022 Community** | Workloads: **Game development with C++** (with *Unreal Engine installer* and the latest **Windows 11 SDK**) and **.NET desktop development**. |
| **Tailscale** (tailscale.com) | Everyone signs in to the same tailnet (the host invites friends). Gives each PC a `100.x.y.z` address. |
| Blender 4.2+ | *Optional.* Only needed to regenerate the 4K art. |
| Python 3 + numpy | *Optional.* Only needed to regenerate the sounds. |

## 2. First-time setup (the host, or anyone building the game)

1. **Get the code:** `git clone --single-branch -b unreal https://github.com/adam656677-oss/Andrews-Airsoft.git` (`--single-branch` skips the large art branch).
2. **Get the 4K art** (about 3 GB). It lives on its own `art` branch so code clones stay small. From the project root:
   ```
   git fetch origin art
   git checkout FETCH_HEAD -- SourceAssets
   git reset -q SourceAssets
   ```
   Or run the Blender generators yourself (see [Regenerating art](#7-regenerating-art-and-audio)).
   **Shortcut for steps 3–6:** double-click **`Airsoft.bat`** in the project folder and choose **6** (*check, build code, build content*). It checks your PC first, compiles the game, then opens the editor, builds all the maps and closes it again. See [The build helper](#the-build-helper-airsoftbat). Do step 5 (Third Person pack) once in the editor afterwards, then run option 3 again.
3. **Build the code:** right-click `AndrewsAirsoft.uproject` → *Generate Visual Studio project files*. Open `AndrewsAirsoft.sln`, choose **Development Editor / Win64**, then **Build**.
4. **Open the project:** double-click `AndrewsAirsoft.uproject`. If asked to rebuild modules, click **Yes**.
5. **Add the character pack:** *Content Drawer → Add → Add Feature or Content Pack → Third Person → Add to Project.* This provides the Manny body and its animations that other players see.
6. **Build the game content:** run `Content/Python/airsoft_setup.py`. In the editor console (backtick key), type `py airsoft_setup.py`, or use *Tools → Execute Python Script*. The script:
   - imports every mesh, texture and sound;
   - creates the materials;
   - builds all six maps with lighting.

   See `Tools/Unreal/SETUP.md` for options.
7. **Play:** press **Play** in the editor, or package the game (section 5).

If you have no art yet, the game still runs: guns, targets and maps fall back to simple stand-in shapes until the 4K assets are imported.

### The build helper (`Airsoft.bat`)

Double-click `Airsoft.bat` for a menu:

| Option | What it does |
|---|---|
| 1 Check my PC | Finds Unreal 5.8, Visual Studio C++, the Windows SDK, free disk space, GPU and RAM, the 4K art, the Third Person pack and Tailscale (and shows your Tailscale IP). |
| 2 Build the game code | Compiles the C++ module (close the editor first). |
| 3 Build the game content | Opens the editor, runs `airsoft_setup.py` (art, sound, materials, all maps) and closes it. The first run can take 30–90 minutes. |
| 4 Open the editor | |
| 5 Package the game for friends | Shipping build into `Packaged\Windows`, plus a zip to share. |
| 6 Do 1, 2 and 3 in order | The first-time path. |
| 7 Make Visual Studio project files | Only needed to read or debug the code in Visual Studio. |

Each run writes `Saved\BuildReport\latest.txt`. **If anything fails, the report opens in Notepad and is copied to your clipboard: paste it to Claude to get the fix.** Paths in it are shortened so it doesn't include your Windows user name. You can also run one step directly, e.g. `Airsoft.bat build`. If Unreal is installed somewhere unusual, set the environment variable `AIRSOFT_UE_ROOT` to the folder that contains `Engine\`.

## 3. Playing together

**Host:**
1. Start the game, enter your call sign, and click **Host Game**.
2. Allow the Windows Firewall prompt (Private networks).
3. Read your Tailscale IP from the main menu, or from the Tailscale tray icon (`100.x.y.z`), and send it to your friends.

**Friends:** start the game, type the host's Tailscale IP in **Join**, and press Enter.

Everyone lands in the **Staging Area**: armory, range and lobby. Once at least 2 players are in, a 25-second vote starts. The vote panel (top left) lists every mode and every map with the current votes, the leading pick and the countdown:
- **F1** steps your mode vote along the list (Team Deathmatch, Domination, Elimination, Gun Game, VIP Escort);
- **F2** steps your map vote (Ironwood Yard, Velvet Club, Nightjar Garage), each with its recommended head count;
- or open the menu (**Esc** / **P**) and click a mode and a map under *Next match*.

Most votes wins (ties are drawn at random); a map that can't run the winning mode, or that hasn't been built yet, is skipped for the next best one. Votes are posted in chat. Everyone then deploys together. After the match, the after-action report shows, and the whole group travels back to staging. The host can also open the menu and choose **Start Match Now**: it deploys with the leading votes.

**Chat:** **Enter** talks to everyone, **Y** to your team (**Tab** switches while typing, **Esc** cancels). Messages show bottom left with the sender's call sign in their team colour and fade after a few seconds; joins, leaves, votes and round results appear there too. While the chat line is open nothing you type reaches the game. The host caps message length and rate (Project Settings → Game → Airsoft → Chat).

The match maps live in *Project Settings → Game → Airsoft → Maps* (key, display name, level, the modes each map runs, recommended players), so adding a map to the vote is a settings change.

### Game modes

| Mode | Teams | How it plays |
|---|---|---|
| **Team Deathmatch** | 2 | Tag the other team; first to 40 tags. Respawns. |
| **Domination** | 2 | Hold A, B and C; every held point scores each second; first to 250. Respawns. |
| **Elimination** | 2 | Rounds with one life each. An 8-second freeze starts every round (pick your loadout with **L**); the side with players left takes the round (on time-out: the side with more standing). First to 5 rounds. Once you're out you watch a teammate (**LMB** / **Space** for the next one). Each round ends with the slow-motion replay of its last tag. |
| **Gun Game** | Free-for-all | Everyone fights everyone and carries the same gun in both slots, no grenade. Every tag moves you up the ladder: G18 → Desert Eagle → MP7 → Vector → P90 → MP5 → M4 → AK-74 → M249 → SR-25 → M870 → VSR-10 → 1911. A tag with the final 1911 wins. Being tagged never moves you down. If the 10-minute clock runs out, the highest level wins (tie on level and tags = draw). Respawn after 3 s from any spawn on the map. |
| **VIP Escort** | 2 | Rounds with one life each; the attacking side gets a VIP (one of its people at random, the least-used first; a bot only if the side has no people). The VIP carries only a pistol (their own sidearm, or a G17) and no grenade, and has a gold marker: teammates see it through walls, defenders when the VIP is in sight or within 15 m. Attackers win the round by getting the VIP to stand in the **extraction** zone for 3 s (or by tagging every defender); defenders win by tagging the VIP or holding out for 2:30. Three rounds per half, then the sides swap; most round wins after six rounds takes it. |

Why Gun Game is free-for-all: with a fixed ladder per player, team scoring would let one hot player carry a side while everyone else's progress meant nothing; free-for-all keeps every tag yours and the rule set to one line.

**Extraction point:** a map can place a dedicated extraction objective with letter **X** (it never counts as a Domination point). Without one, the extraction is the objective furthest from the attackers' spawn: **C** while Blue attacks on the stock maps, **A** after the swap, so both halves walk the same distance. On Nightjar Garage that puts it on the roof deck for Blue and on the street for Red.

Round rules, the Gun Game ladder and the timers are in *Project Settings → Game → Airsoft → Rules*. Bots play every mode: they hunt in Elimination and Gun Game, take points in Domination, and in VIP the VIP bot heads for extraction, escorts stay with the VIP and defenders split between guarding extraction and pushing out to meet them. Now and then a bot says a short line in chat (turn off with *Bot Chatter*).

### Bots

Practise alone or fill out a small game with computer players. As host, open **Settings → Host · Bots** (or the in-game menu next to **Start Match Now**) and pick a team size (4v4 to 10v10) and skill (Easy, Normal, Hard, Expert). Bots join on match maps only: they fill both teams around the people playing and step aside as friends join. They never count toward the lobby vote. **To practise solo:** host, turn bots on, then press **Start Match Now**.

Bots play by the same rules as everyone else: they fire real BBs through the same hit checks, call their hits, raise the rag and walk off. They show a **BOT** tag on the scoreboard and after-action report and never touch anyone's rank or XP. They spot you by line of sight, hear gunfire, lead moving targets, burst-fire, crouch and strafe, take and defend points in Domination, and now and then throw a grenade. Tune them in **Project Settings → Game → Airsoft → Bots**. Match maps get a Nav Mesh Bounds Volume from the setup script and the navmesh is built on the host when the map loads; if bots stand still, see `Tools/Unreal/SETUP.md`.

**Ports:** the game uses UDP 7777. Tailscale handles NAT, so you don't need to open router ports.

Your profile (rank, XP, stats, loadout, settings) is saved on your own PC: `%LOCALAPPDATA%/AndrewsAirsoft/Saved/SaveGames/AirsoftProfile.sav`.

## 4. Controls

| Action | Keyboard / mouse | Gamepad |
|---|---|---|
| Move / look | WASD / mouse | Left / right stick |
| Fire / aim | LMB / RMB (hold, or toggle in Settings) | RT / LT |
| Sprint | Left Shift (hold) | L3 (toggle) |
| Crouch / slide | C (toggle; while sprinting = slide), Left Ctrl (hold) | B |
| Jump | Space | A |
| Lean left / right | Q / E | — |
| Reload | R | X |
| Swap weapon / primary / secondary | Mouse wheel / 1 / 2 | Y |
| Grenade | G | RB |
| Fire mode | B | D-pad ↓ |
| Weapon light / laser | T | D-pad ↑ |
| Inspect weapon | V | D-pad ← |
| Interact (armory racks) | F | D-pad → |
| Loadout | L | — |
| Scoreboard | Tab (hold) | View |
| Menu | Esc or P | Menu |
| Vote (staging): next mode / next map | F1 / F2 (or click in the menu) | — |
| Chat: everyone / team | Enter / Y (Tab switches, Esc cancels) | — |
| Next teammate (out for the round) | LMB or Space | RT or A |

## 5. Packaging a build for friends

Easiest: `Airsoft.bat` → **5**. Or in the editor: *Platforms → Windows → Package Project* (Development or Shipping). Zip the output folder and share it (e.g. Google Drive). Friends unzip it and run `AndrewsAirsoft.exe`; they don't need Unreal installed. Every player must run the **same build**.

## 6. Graphics on an RTX 2070 at 4K

The project is tuned for:
- Lumen software global illumination and reflections;
- Nanite;
- Virtual Shadow Maps;
- **TSR** upscaling (internal render at ~60% of 4K).

In **Settings**, *Quality: High* with *Render scale: 60%* is the recommended 2070 setup. Use 50% for higher frame rates, or 70–75% on faster cards.

## 7. Regenerating art and audio

- **Art:** Blender generators live in `Tools/Blender/` (rules: `Tools/Blender/CONVENTIONS.md`). They write to `SourceAssets/` and `Content/Airsoft/Data/*.json`, and their renders go to `Docs/Renders/`. Re-run `airsoft_setup.py` afterwards.
- **Audio:** `python3 Tools/Audio/make_sounds.py` regenerates every sound into `Tools/Audio/Generated/`. All sounds are synthesized; no samples are used.

## 8. Code map

| Area | Files (`Source/AndrewsAirsoft/`) |
|---|---|
| Rules, phases, teams, scoring, travel | `AirsoftGameMode`, `AirsoftGameState`, `AirsoftPlayerState` |
| Mode rules, map list, vote | `AirsoftModeRules` (tunables in Project Settings → Game → Airsoft) |
| Bots | `AirsoftBotController` (tuning in Project Settings → Game → Airsoft → Bots) |
| Effects (muzzle, tracers, impacts, tag pulse) | `AirsoftEffects` (Project Settings → Game → Airsoft Effects) |
| Player, movement, lean, hit state | `AirsoftCharacter`, `AirsoftMovementComponent` |
| Guns, ballistics, server hit validation | `AirsoftCombatComponent`, `AirsoftBallistics`, `AirsoftWeaponData`, `AirsoftGunVisual` |
| Input, menus, HUD feed, replay camera | `AirsoftPlayerController`, `UI/*` (Slate) |
| World actors | `AirsoftObjective`, `AirsoftTeamStart`, `AirsoftPracticeTarget`, `AirsoftArmoryDisplay`, `AirsoftGrenade` |
| Profile, hosting/joining, settings | `AirsoftGameInstance`, `AirsoftSaveGame`, `AirsoftSettings` (Project Settings → Game → Airsoft) |

**Tuning:**
- weapon stats: `AirsoftWeaponData.cpp`;
- round rules (round time, score limits, respawn time, friendly fire): *Project Settings → Game → Airsoft*.

## 9. Troubleshooting

- **The build or setup failed:** paste `Saved\BuildReport\latest.txt` (already on your clipboard after a failure) to Claude. The code was written without an Unreal install to test against, so a round of compile fixes on the first build is expected.

- **"Couldn't connect":** check that both PCs show as connected in Tailscale, that the host allowed the firewall prompt, and that both run the same build.
- **Players see grey stand-in bodies:** the Third Person content pack is missing (step 5).
- **Everything is stand-in shapes:** `SourceAssets/` is empty, or the setup script wasn't run after adding it.
- **Testing in the editor:** Esc stops Play-In-Editor; use **P** for the in-game menu. For multiplayer tests use *Play → Net Mode: Play As Listen Server* with 2+ players. Seamless travel in PIE needs the console command `net.AllowPIESeamlessTravel 1`.
