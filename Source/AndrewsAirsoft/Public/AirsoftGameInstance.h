// Andrew's Airsoft - hosting/joining, local profile and user settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "Engine/EngineBaseTypes.h"
#include "AirsoftTypes.h"
#include "AirsoftSettings.h"
#include "AirsoftGameInstance.generated.h"

class SWidget;
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
	/** Main menu > New Game: save the difficulty, then mission 1. */
	void StartNewGame(EAirsoftDifficulty Difficulty);

	/**
	 * Main menu > Skirmish: an offline match against bots, run on this PC with no hosting.
	 * MapIndex indexes AirsoftRules::Maps(); BotFill is an AirsoftBots fill option (1 = 4v4 .. 4 = 10v10).
	 */
	void StartSkirmish(EAirsoftMode Mode, int32 MapIndex, int32 BotFill, EAirsoftDifficulty Difficulty);

	/** Main menu > Practice Range. bWalkthrough adds the step-by-step how-to-play prompts. */
	void StartPractice(bool bWalkthrough);
	/** The walkthrough reached its last step (marks it done in the profile). */
	void FinishWalkthrough();
	void CloseWalkthrough();

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

	/** Loading screen: shown by the movie player while a map loads (packaged builds; skipped in the editor). */
	void HandlePreLoadMap(const FString& MapName);
	void HandlePostLoadMap(UWorld* World);
	/** Open a map, telling the loading screen what is coming. */
	void OpenMap(const FString& LevelPath, const FString& Options, const FString& Title, const FString& Subtitle);

	UPROPERTY()
	TObjectPtr<UAirsoftSaveGame> Profile;

	/** Heading and subheading for the next loading screen (empty = worked out from the map name). */
	FString LoadingTitle;
	FString LoadingSubtitle;

	/** The practice walkthrough overlay is wanted on the next map, and the overlay when shown. */
	bool bWalkthroughPending = false;
	TSharedPtr<SWidget> WalkthroughWidget;
};
