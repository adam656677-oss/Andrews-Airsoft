#include "AirsoftGameInstance.h"

#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "AirsoftWeaponData.h"
#include "AudioDevice.h"
#include "Engine/Engine.h"
#include "GameFramework/GameUserSettings.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "Kismet/GameplayStatics.h"

void UAirsoftGameInstance::Init()
{
	Super::Init();
	if (GEngine)
	{
		GEngine->OnNetworkFailure().AddUObject(this, &UAirsoftGameInstance::HandleNetworkFailure);
		GEngine->OnTravelFailure().AddUObject(this, &UAirsoftGameInstance::HandleTravelFailure);
	}
	GetProfile();
	ApplyUserSettings();
}

void UAirsoftGameInstance::Shutdown()
{
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

void UAirsoftGameInstance::ReturnToMainMenu(const FString& Reason)
{
	PendingMenuMessage = Reason;
	SaveProfile();
	UGameplayStatics::OpenLevel(this, FName(*UAirsoftSettings::Get()->MainMenuMap), true);
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
