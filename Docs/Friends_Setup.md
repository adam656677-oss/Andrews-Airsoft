# Andrew's Airsoft: setup for players

This page is for friends who just want to play. You don't need Unreal Engine or anything else from the developer side.

## What you need

- A Windows 10 or 11 PC with a graphics card about as fast as an RTX 2060 or better.
- Free disk space of about twice the size of the zip, for the zip plus the extracted game.
- A free Tailscale account. Tailscale puts everyone on one private network, so nobody has to open router ports.

## 1. Join the Tailscale network (once)

1. Install Tailscale from https://tailscale.com/download and sign in.
2. Open the invite link the host sent you, and accept it.
3. The Tailscale icon in the system tray should say **Connected**.

## 2. Install the game (once per new build)

1. Download the zip the host shared, for example `AndrewsAirsoft_v1.0.zip`.
2. Right-click it, choose **Extract All**, and pick a folder such as `C:\Games\AndrewsAirsoft`.
3. Run `AndrewsAirsoft.exe`. If Windows SmartScreen appears, click **More info → Run anyway**.
4. When Windows Firewall asks, allow **Private networks**.

When the host sends a new build, delete the old folder and extract the new zip. Everyone must run the same build, or joining fails. Your rank, stats and settings are kept, because they're stored separately in `%LOCALAPPDATA%\AndrewsAirsoft`.

## 3. Join a game

1. Start the game and type your call sign.
2. Click **Join**, type the host's Tailscale address (it starts with `100.`), and press **Enter**.
3. You arrive in the **Staging Area**. Try guns at the range, and vote for the next mode with **F1** and the next map with **F2**.
4. When the vote timer runs out, everyone deploys together.

## Controls you need first

| Action | Keyboard / mouse |
|---|---|
| Move / look | WASD / mouse |
| Fire / aim | Left / right mouse |
| Sprint / crouch / slide | Shift / C (C while sprinting slides) |
| Reload / grenade | R / G |
| Lean | Q / E |
| Loadout | L |
| Scoreboard | Tab |
| Chat to everyone / team | Enter / Y |
| First or third person | F5 |

A controller works too. Every control is listed in **Settings**.

## Settings for smooth play

Open **Settings → Graphics**. On an RTX 2060 or 2070, use *Quality: High* and *Render scale: 60%*. If it stutters, drop to 50%.

## If something goes wrong

| Problem | Fix |
|---|---|
| "Connection failed" when joining | Check both your Tailscale icon and the host's say Connected, and that the address starts with `100.` |
| Join starts, then drops back to the menu | Your build differs from the host's. Get the newest zip. |
| Very low frame rate | Lower Render scale in Settings, and close browsers or recording apps. |
| The game crashes | Send the host the newest folder inside `%LOCALAPPDATA%\AndrewsAirsoft\Saved\Crashes`. |
