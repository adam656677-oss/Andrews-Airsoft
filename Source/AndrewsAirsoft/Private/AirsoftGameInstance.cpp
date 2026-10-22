#include "AirsoftGameInstance.h"

#include "AirsoftCampaign.h"
#include "AirsoftCharacter.h"
#include "AirsoftKeyBindings.h"
#include "AirsoftModeRules.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "AirsoftWeaponData.h"
#include "AudioDevice.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/PackageName.h"
#include "MoviePlayer.h"
#include "UI/AirsoftUI.h"
#include "UObject/UObjectGlobals.h"
#include "Widgets/SWidget.h"

namespace AirsoftGameInstanceLocal
{
	/** Loading-screen heading for a map nobody announced (opened from the editor, a console travel...). */
	void DescribeMap(const FString& MapName, FString& OutTitle, FString& OutSubtitle)
	{
		const FString Short = FPackageName::GetShortName(MapName);
		for (const FAirsoftMapInfo& Info : AirsoftRules::Maps())
		{
			if (!Info.LevelPath.IsEmpty() && FPackageName::GetShortName(Info.LevelPath).Equals(Short, ESearchCase::IgnoreCase))
			{
				// Story missions and skirmishes share these maps; their own starts name what is coming.
				OutTitle = AirsoftRules::MapDisplayName(Info.Key);
				OutSubtitle = FString();
				return;
			}
		}
		const UAirsoftSettings* S = UAirsoftSettings::Get();
		if (FPackageName::GetShortName(S->MainMenuMap).Equals(Short, ESearchCase::IgnoreCase))
		{
			OutTitle = AirsoftCampaign::GameTitle();
			OutSubtitle = FString();
			return;
		}
		if (FPackageName::GetShortName(S->StagingMap).Equals(Short, ESearchCase::IgnoreCase))
		{
			OutTitle = TEXT("The Range");
			OutSubtitle = TEXT("Armory and firing lanes");
			return;
		}
		OutTitle = Short.StartsWith(TEXT("L_")) ? Short.Mid(2) : Short;
		OutSubtitle = FString();
	}
}

void UAirsoftGameInstance::Init()
{
	Super::Init();
	if (GEngine)
	{
		GEngine->OnNetworkFailure().AddUObject(this, &UAirsoftGameInstance::HandleNetworkFailure);
		GEngine->OnTravelFailure().AddUObject(this, &UAirsoftGameInstance::HandleTravelFailure);
	}
	FCoreUObjectDelegates::PreLoadMap.AddUObject(this, &UAirsoftGameInstance::HandlePreLoadMap);
	FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(this, &UAirsoftGameInstance::HandlePostLoadMap);
	GetProfile();
	ApplyUserSettings();
}

void UAirsoftGameInstance::Shutdown()
{
	FCoreUObjectDelegates::PreLoadMap.RemoveAll(this);
	FCoreUObjectDelegates::PostLoadMapWithWorld.RemoveAll(this);
	CloseWalkthrough();
	SaveProfile();
	Super::Shutdown();
}

void UAirsoftGameInstance::HostGame()
{
	SaveProfile();
	UGameplayStatics::OpenLevel(this, FName(*UAirsoftSettings::Get()->StagingMap), true, TEXT("listen"));
}

void UAirsoftGameInstance::JoinGame(const FString& Address)
{
	FString Clean = Address.TrimStartAndEnd();
	if (Clean.IsEmpty())
	{
		return;
	}
	FAirsoftUserSettings Settings = GetUserSettings();
	Settings.LastJoinAddress = Clean;
	SetUserSettings(Settings);
	SaveProfile();
	UGameplayStatics::OpenLevel(this, FName(*Clean), true);
}

void UAirsoftGameInstance::StartMission(int32 Number, bool bFromCheckpoint)
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(Number);
	if (!Mission)
	{
		Number = 1;
		Mission = AirsoftCampaign::FindMission(1);
	}
	if (!Mission)
	{
		return;
	}
	PendingMenuMessage.Reset();
	SaveProfile();
	OpenMap(Mission->MapPath, AirsoftCampaign::MissionOptions(Number, bFromCheckpoint), Mission->Title,
		FString::Printf(TEXT("Mission %d  \u00B7  %s"), Number, *AirsoftDifficulty::Label(AirsoftDifficulty::FromIndex(GetUserSettings().Difficulty))));
}

void UAirsoftGameInstance::StartNewGame(EAirsoftDifficulty Difficulty)
{
	FAirsoftUserSettings Settings = GetUserSettings();
	Settings.Difficulty = static_cast<int32>(Difficulty);
	// The campaign referee reads the bot skill for its enemies; keep the two in step.
	Settings.BotSkill = static_cast<int32>(AirsoftDifficulty::BotSkill(Difficulty));
	SetUserSettings(Settings);
	// A fresh start: drop any mid-mission checkpoint so mission 1 begins at its opening.
	GetProfile()->CheckpointMission = 0;
	StartMission(1);
}

void UAirsoftGameInstance::StartSkirmish(EAirsoftMode Mode, int32 MapIndex, int32 BotFill, EAirsoftDifficulty Difficulty)
{
	const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
	if (!Maps.IsValidIndex(MapIndex))
	{
		return;
	}
	const FAirsoftMapInfo& Map = Maps[MapIndex];
	if (!Map.SupportsMode(Mode))
	{
		Mode = Map.Modes.Num() > 0 ? Map.Modes[0] : EAirsoftMode::TDM;
	}
	// The match reads its bots from these (AAirsoftGameMode::GetBotSettings); no listen server, so nobody can join.
	FAirsoftUserSettings Settings = GetUserSettings();
	Settings.BotFill = FMath::Clamp(BotFill, 1, AirsoftBots::NumFillOptions - 1);
	Settings.BotSkill = static_cast<int32>(AirsoftDifficulty::BotSkill(Difficulty));
	Settings.Difficulty = static_cast<int32>(Difficulty);
	SetUserSettings(Settings);
	PendingMenuMessage.Reset();
	OpenMap(Map.LevelPath, FString::Printf(TEXT("Mode=%s?Skirmish"), *AirsoftRules::ModeOption(Mode)),
		AirsoftRules::MapDisplayName(Map.Key),
		FString::Printf(TEXT("%s  \u00B7  %s  \u00B7  %s bots"), *AirsoftRules::ModeName(Mode),
			*AirsoftDifficulty::Label(Difficulty), *AirsoftBots::FillLabel(Settings.BotFill)));
}

void UAirsoftGameInstance::StartPractice(bool bWalkthrough)
{
	PendingMenuMessage.Reset();
	SaveProfile();
	bWalkthroughPending = bWalkthrough;
	OpenMap(UAirsoftSettings::Get()->PracticeMap, TEXT("Practice"), TEXT("The Range"),
		bWalkthrough ? TEXT("How to play") : TEXT("Free practice"));
}

void UAirsoftGameInstance::FinishWalkthrough()
{
	if (UAirsoftSaveGame* P = GetProfile())
	{
		if (!P->Settings.bTutorialDone)
		{
			P->Settings.bTutorialDone = true;
			SaveProfile();
		}
	}
}

void UAirsoftGameInstance::CloseWalkthrough()
{
	if (WalkthroughWidget.IsValid())
	{
		if (UGameViewportClient* Viewport = GetGameViewportClient())
		{
			Viewport->RemoveViewportWidgetContent(WalkthroughWidget.ToSharedRef());
		}
		WalkthroughWidget.Reset();
	}
}

void UAirsoftGameInstance::OpenMap(const FString& LevelPath, const FString& Options, const FString& Title, const FString& Subtitle)
{
	LoadingTitle = Title;
	LoadingSubtitle = Subtitle;
	UGameplayStatics::OpenLevel(this, FName(*LevelPath), true, Options);
}

void UAirsoftGameInstance::HandlePreLoadMap(const FString& MapName)
{
	CloseWalkthrough();
	FString Title = LoadingTitle;
	FString Subtitle = LoadingSubtitle;
	LoadingTitle.Reset();
	LoadingSubtitle.Reset();
	if (Title.IsEmpty())
	{
		AirsoftGameInstanceLocal::DescribeMap(MapName, Title, Subtitle);
	}
	if (IsRunningDedicatedServer() || !IsMoviePlayerEnabled())
	{
		return;
	}
	FLoadingScreenAttributes Attributes;
	Attributes.bAutoCompleteWhenLoadingCompletes = true;
	// Long enough to read the tip, short enough not to stall a quick load.
	Attributes.MinimumLoadingScreenDisplayTime = 2.f;
	Attributes.WidgetLoadingScreen = AirsoftUI::MakeLoadingScreen(Title, Subtitle);
	GetMoviePlayer()->SetupLoadingScreen(Attributes);
}

void UAirsoftGameInstance::HandlePostLoadMap(UWorld* World)
{
	if (!bWalkthroughPending || !World || World->GetGameInstance() != this)
	{
		return;
	}
	bWalkthroughPending = false;
	if (UGameViewportClient* Viewport = GetGameViewportClient())
	{
		WalkthroughWidget = AirsoftUI::MakeWalkthrough(this);
		// Above the HUD (10), below menus (50).
		Viewport->AddViewportWidgetContent(WalkthroughWidget.ToSharedRef(), 30);
	}
}

int32 UAirsoftGameInstance::GetContinueMission()
{
	return AirsoftCampaign::HighestUnlocked(this);
}

void UAirsoftGameInstance::ReturnToMainMenu(const FString& Reason)
{
	PendingMenuMessage = Reason;
	SaveProfile();
	OpenMap(UAirsoftSettings::Get()->MainMenuMap, FString(), AirsoftCampaign::GameTitle(), FString());
}

UAirsoftSaveGame* UAirsoftGameInstance::GetProfile()
{
	if (!Profile)
	{
		if (UGameplayStatics::DoesSaveGameExist(UAirsoftSaveGame::SlotName, 0))
		{
			Profile = Cast<UAirsoftSaveGame>(UGameplayStatics::LoadGameFromSlot(UAirsoftSaveGame::SlotName, 0));
		}
		if (!Profile)
		{
			Profile = Cast<UAirsoftSaveGame>(UGameplayStatics::CreateSaveGameObject(UAirsoftSaveGame::StaticClass()));
			Profile->Loadout = AirsoftWeapons::DefaultLoadout();
		}
		// Make sure stored loadouts are still valid if weapon data changed.
		Profile->Loadout.Primary = AirsoftWeapons::Clean(Profile->Loadout.Primary);
		Profile->Loadout.Secondary = AirsoftWeapons::Clean(Profile->Loadout.Secondary);
		if (!AirsoftWeapons::Find(Profile->Loadout.Primary.WeaponId) || !AirsoftWeapons::Find(Profile->Loadout.Secondary.WeaponId))
		{
			Profile->Loadout = AirsoftWeapons::DefaultLoadout();
		}
	}
	return Profile;
}

void UAirsoftGameInstance::SaveProfile()
{
	if (Profile)
	{
		UGameplayStatics::SaveGameToSlot(Profile, UAirsoftSaveGame::SlotName, 0);
	}
}

const FAirsoftUserSettings& UAirsoftGameInstance::GetUserSettings()
{
	return GetProfile()->Settings;
}

void UAirsoftGameInstance::SetUserSettings(const FAirsoftUserSettings& NewSettings)
{
	GetProfile()->Settings = NewSettings;
	ApplyUserSettings();
	SaveProfile();
}

void UAirsoftGameInstance::ApplyUserSettings()
{
	const FAirsoftUserSettings& S = GetUserSettings();
	if (UGameUserSettings* GUS = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		GUS->SetOverallScalabilityLevel(FMath::Clamp(S.Quality, 0, 3));
		// Window keeps the title bar (minimise / close); borderless and fullscreen fill the monitor.
		const EWindowMode::Type Mode = S.WindowMode == 2 ? EWindowMode::Fullscreen : (S.WindowMode == 1 ? EWindowMode::WindowedFullscreen : EWindowMode::Windowed);
		GUS->SetFullscreenMode(Mode);
		if (Mode == EWindowMode::Windowed)
		{
			// A window the size of the desktop would hide its own title bar: leave room for it and the taskbar.
			const FIntPoint Desktop = GUS->GetDesktopResolution();
			FIntPoint Size = GUS->GetScreenResolution();
			if (Size.X <= 0 || Size.Y <= 0 || Size.X >= Desktop.X || Size.Y >= Desktop.Y - 80)
			{
				Size = FIntPoint(FMath::RoundToInt(Desktop.X * 0.85f), FMath::RoundToInt(Desktop.Y * 0.85f));
			}
			GUS->SetScreenResolution(Size);
		}
		else
		{
			GUS->SetScreenResolution(GUS->GetDesktopResolution());
		}
		GUS->ApplySettings(false);
	}
	if (IConsoleVariable* ScreenPct = IConsoleManager::Get().FindConsoleVariable(TEXT("r.ScreenPercentage")))
	{
		ScreenPct->Set(FMath::Clamp(S.RenderScale, 33.f, 100.f), ECVF_SetByGameSetting);
	}
	if (UWorld* World = GetWorld())
	{
		if (FAudioDeviceHandle Device = World->GetAudioDevice())
		{
			Device->SetTransientPrimaryVolume(FMath::Clamp(S.MasterVolume, 0.f, 1.f));
		}
	}

	// Accessibility: team colours are read through AirsoftColors::Team everywhere; repaint the people already out there.
	const AirsoftColors::EPalette Palette = static_cast<AirsoftColors::EPalette>(FMath::Clamp(S.ColorblindMode, 0, 2));
	const bool bPaletteChanged = Palette != AirsoftColors::ActivePalette;
	AirsoftColors::ActivePalette = Palette;
	if (UWorld* World = GetWorld())
	{
		for (FConstPlayerControllerIterator It = World->GetPlayerControllerIterator(); It; ++It)
		{
			AirsoftKeyBindings::Apply(It->Get());
		}
		if (bPaletteChanged)
		{
			for (TActorIterator<AAirsoftCharacter> It(World); It; ++It)
			{
				It->ApplyTeamLook();
			}
		}
	}
}

FString UAirsoftGameInstance::GetPlayerName()
{
	const FString& Name = GetUserSettings().PlayerName;
	if (!Name.IsEmpty())
	{
		return Name.Left(20);
	}
	return FPlatformProcess::UserName();
}

void UAirsoftGameInstance::HandleNetworkFailure(UWorld* World, UNetDriver* NetDriver, ENetworkFailure::Type FailureType, const FString& ErrorString)
{
	ReturnToMainMenu(FString::Printf(TEXT("Disconnected: %s"), *ErrorString));
}

void UAirsoftGameInstance::HandleTravelFailure(UWorld* World, ETravelFailure::Type FailureType, const FString& ErrorString)
{
	ReturnToMainMenu(FString::Printf(TEXT("Couldn't connect: %s"), *ErrorString));
}
