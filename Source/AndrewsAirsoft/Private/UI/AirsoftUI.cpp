// Andrew's Airsoft - public UI factory functions (see UI/AirsoftUI.h).

#include "UI/AirsoftUI.h"

#include "AirsoftUIScreens.h"
#include "Widgets/SWidget.h"

namespace AirsoftUI
{
	TSharedRef<SWidget> MakeHUD(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateHUD(PC);
	}

	TSharedRef<SWidget> MakeMainMenu(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateMainMenu(PC);
	}

	TSharedRef<SWidget> MakeGameMenu(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateGameMenu(PC);
	}

	TSharedRef<SWidget> MakeArmory(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateArmory(PC);
	}

	TSharedRef<SWidget> MakeSettings(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateSettings(PC);
	}

	TSharedRef<SWidget> MakeScoreboard(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateScoreboard(PC);
	}

	TSharedRef<SWidget> MakeSummary(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateSummary(PC);
	}

	TSharedRef<SWidget> MakeChatInput(AAirsoftPlayerController* PC)
	{
		return AirsoftUIScreens::CreateChatInput(PC);
	}
}
