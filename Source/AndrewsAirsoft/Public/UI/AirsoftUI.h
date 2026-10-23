// Andrew's Airsoft - Slate user interface. Everything is built in code, so the
// game needs no widget blueprints. AAirsoftPlayerController owns the widgets.

#pragma once

#include "CoreMinimal.h"

class SWidget;
class AAirsoftPlayerController;
class UAirsoftGameInstance;

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

	/** The chat line (Enter / Y). Focusable; Enter sends, Tab switches everyone/team, Esc cancels. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeChatInput(AAirsoftPlayerController* PC);

	/**
	 * Full-screen loading card shown by the movie player between maps. Pure Slate (no UObjects):
	 * it is painted from the loading thread while the world is torn down and rebuilt.
	 */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeLoadingScreen(const FString& Title, const FString& Subtitle);

	/** Practice-range walkthrough prompts (move, aim, shoot, reload, grenade, slide); added over the HUD. */
	ANDREWSAIRSOFT_API TSharedRef<SWidget> MakeWalkthrough(UAirsoftGameInstance* GameInstance);
}
