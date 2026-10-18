// Andrew's Airsoft - the single-player story campaign ("Last Contract").
//
// Each mission is one of the existing maps played against computer-controlled enemies:
// the player has health (Call of Duty style: it comes back once you're out of fire),
// enemies come in waves until the mission's head count is cleared, a death restarts
// the mission, and finishing one unlocks the next (saved in the profile).
// The mission list and the damage rules live in AirsoftCampaign::*; the referee is
// AAirsoftCampaignGameMode, a single-player cousin of the airsoft match referee.

#pragma once

#include "CoreMinimal.h"
#include "AirsoftGameMode.h"
#include "AirsoftCampaign.generated.h"

class AAirsoftBotController;

namespace AirsoftCampaign
{
	struct FMission
	{
		/** Shown as "MISSION n · TITLE". */
		FString Title;
		/** Long package name of the map, e.g. /Game/Maps/L_VelvetClub. */
		FString MapPath;
		/** Story cards shown one after another as the mission opens. */
		TArray<FString> Intro;
		/** Objective line on the HUD. */
		FString Objective;
		/** Total enemies to clear, and how many may be up at once (the rest arrive as the first fall). */
		int32 Enemies = 8;
		int32 MaxAlive = 5;
		/** Primary weapons the enemies carry on this mission (sidearms are always pistols). */
		TArray<FName> EnemyWeapons;
		/** Shown when the mission is won. */
		FString Outro;
	};

	ANDREWSAIRSOFT_API const TArray<FMission>& Missions();
	/** 1-based; nullptr when out of range. */
	ANDREWSAIRSOFT_API const FMission* FindMission(int32 Number);
	ANDREWSAIRSOFT_API FString GameTitle();

	/** Damage of one hit (one pellet for shotguns) before the difficulty scale. */
	ANDREWSAIRSOFT_API float WeaponDamage(FName WeaponId, bool bHeadshot);
	/** How hard enemies hit the player at each difficulty (the host "bot skill" setting). */
	ANDREWSAIRSOFT_API float EnemyDamageScale(EAirsoftBotSkill Skill);

	/** URL options that open a mission with the campaign referee. */
	ANDREWSAIRSOFT_API FString MissionOptions(int32 Number);
}

/** Single-player story mission referee. */
UCLASS()
class ANDREWSAIRSOFT_API AAirsoftCampaignGameMode : public AAirsoftGameMode
{
	GENERATED_BODY()

public:
	AAirsoftCampaignGameMode();

	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	virtual void InitGameState() override;
	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;
	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override { return true; }
	virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;
	virtual void SetPlayerDefaults(APawn* PlayerPawn) override;
	virtual bool HandleTag(AController* Shooter, AController* Victim, FName WeaponId) override;
	virtual bool HandleHit(AController* Shooter, AController* Victim, FName WeaponId, const FVector& HitLocation) override;

	/** Developer console shortcuts (airsoft.campaign.killenemies / airsoft.campaign.complete). */
	void DebugKillEnemies();
	void DebugCompleteMission();

protected:
	/** Applies Damage to Victim; handles kills (score, ammo, waves, mission end). Returns true if anything was hit. */
	bool ApplyCampaignDamage(AController* Shooter, AController* Victim, FName WeaponId, float Damage, bool bHeadshot);
	void PlayIntroCard(int32 Index);
	/** Brings enemies in until MaxAlive are up or the mission's head count is used up. */
	void TopUpEnemies();
	AAirsoftBotController* SpawnEnemy();
	FAirsoftLoadout MakeEnemyLoadout() const;
	void OnEnemyKilled(AController* Shooter, AController* Victim, FName WeaponId, bool bHeadshot);
	void OnPlayerKilled(AController* Victim, const FString& KilledBy);
	void CompleteMission();
	void UpdateObjectiveText();
	EAirsoftBotSkill Difficulty() const;
	APawn* FindPlayerPawn() const;

	int32 MissionNumber = 1;
	int32 EnemiesSpawned = 0;
	int32 EnemiesKilled = 0;
	bool bEnemiesStarted = false;
	bool bMissionOver = false;
	FTimerHandle IntroTimer;
	FTimerHandle EndTimer;
	UPROPERTY() TArray<TObjectPtr<AAirsoftBotController>> Enemies;
};
