// Andrew's Airsoft - internal constructors for each screen (one .cpp per screen).
// AirsoftUI.cpp forwards the public factory functions to these.

#pragma once

#include "CoreMinimal.h"

class SWidget;
class AAirsoftPlayerController;

namespace AirsoftUIScreens
{
	TSharedRef<SWidget> CreateHUD(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateMainMenu(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateGameMenu(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateArmory(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateSettings(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateScoreboard(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateSummary(AAirsoftPlayerController* PC);
	/** SAirsoftChat.cpp: the typing line, and the fading message box the HUD embeds. */
	TSharedRef<SWidget> CreateChatInput(AAirsoftPlayerController* PC);
	TSharedRef<SWidget> CreateChatBox(AAirsoftPlayerController* PC);
}
