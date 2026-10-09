// Andrew's Airsoft - Slate user interface. Everything is built in code, so the
// game needs no widget blueprints. AAirsoftPlayerController owns the widgets.

#pragma once

#include "CoreMinimal.h"

class SWidget;
class AAirsoftPlayerController;

namespace AirsoftUI
{
	/** Always-on HUD: crosshair, ammo, timer/score, objectives, kill feed, hit markers, scope, prompts, vote panel. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeHUD(AAirsoftPlayerController* PC);

	/** Title screen: host, join by IP, call sign, armory, settings, quit. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeMainMenu(AAirsoftPlayerController* PC);

	/** In-game pause menu: resume, armory, settings, votes/start (staging), switch team, leave. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeGameMenu(AAirsoftPlayerController* PC);

	/** Loadout editor: weapons, attachments per slot, finishes, stats. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeArmory(AAirsoftPlayerController* PC);

	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeSettings(AAirsoftPlayerController* PC);

	/** Held-Tab scoreboard. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeScoreboard(AAirsoftPlayerController* PC);

	/** After-action report shown during the post-round phase. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeSummary(AAirsoftPlayerController* PC);
}
