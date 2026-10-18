// Andrew's Airsoft - hosting/joining, local profile and user settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "Engine/EngineBaseTypes.h"
#include "AirsoftTypes.h"
#include "AirsoftGameInstance.generated.h"

class UAirsoftSaveGame;
class UNetDriver;
class UWorld;
struct FAirsoftUserSettings;

UCLASS()
class ANDREWSAIRSOFT_API UAirsoftGameInstance : public UGameInstance
{
	GENERATED_BODY()

public:
	virtual void Init() override;
	virtual void Shutdown() override;

	/** Start a listen server on the staging map. Friends join with your Tailscale/LAN IP. */
	void HostGame();

	/** Connect to a host, e.g. "100.101.102.103" or "100.101.102.103:7777". */
	void JoinGame(const FString& Address);

	void ReturnToMainMenu(const FString& Reason = FString());

	/** Story campaign: open mission Number (1-based) on its map with the campaign referee. */
	void StartMission(int32 Number);
	/** The mission "Continue" resumes (the furthest unlocked). */
	int32 GetContinueMission();

	UAirsoftSaveGame* GetProfile();
	void SaveProfile();

	const FAirsoftUserSettings& GetUserSettings();
	void SetUserSettings(const FAirsoftUserSettings& NewSettings);
	void ApplyUserSettings();

	FString GetPlayerName();

	/** Shown on the main menu after a disconnect. */
	FString PendingMenuMessage;

private:
	void HandleNetworkFailure(UWorld* World, UNetDriver* NetDriver, ENetworkFailure::Type FailureType, const FString& ErrorString);
	void HandleTravelFailure(UWorld* World, ETravelFailure::Type FailureType, const FString& ErrorString);

	UPROPERTY()
	TObjectPtr<UAirsoftSaveGame> Profile;
};
