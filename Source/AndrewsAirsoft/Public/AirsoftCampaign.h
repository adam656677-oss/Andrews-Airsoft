// Andrew's Airsoft - the single-player story campaign ("Last Contract").
//
// Each mission is one of the existing maps played against computer-controlled enemies:
// the player has health (Call of Duty style: it comes back once you're out of fire),
// a narrated cinematic opens the mission, enemies come in waves until the mission's head
// count is cleared, then the mission's boss steps in. A death restarts the mission;
// beating the boss unlocks the next one (saved in the profile).
//
// The story (titles, narration, objectives, enemies, bosses) is data:
// Content/Airsoft/Data/Campaign.json. Its narration is voiced by Tools/Audio/make_voice.ps1
// into /Game/Airsoft/Audio/VO_M<n>_I<k>, VO_M<n>_Boss and VO_M<n>_Outro.
// The referee is AAirsoftCampaignGameMode, a single-player cousin of the airsoft match referee.

#pragma once

#include "CoreMinimal.h"
#include "AirsoftGameMode.h"
#include "AirsoftCampaign.generated.h"

class ACameraActor;
class AAirsoftBotController;

namespace AirsoftCampaign
{
	struct FBoss
	{
		FString Name;
		FName Weapon;
		float Health = 300.f;
		FString Taunt;
	};

	struct FMission
	{
		/** Shown as "MISSION n · TITLE". */
		FString Title;
		/** Long package name of the map, e.g. /Game/Maps/L_VelvetClub. */
		FString MapPath;
		/** Narrated story lines that open the mission (cinematic subtitles). */
		TArray<FString> Intro;
		/** Objective line on the HUD. */
		FString Objective;
		/** Regular enemies to clear before the boss, and how many may be up at once. */
		int32 Enemies = 8;
		int32 MaxAlive = 5;
		/** Primary weapons the regular enemies carry (sidearms are always pistols). */
		TArray<FName> EnemyWeapons;
		/** Steps in once the regulars are down (no boss when Name is empty). */
		FBoss Boss;
		/** Narrated when the mission is won. */
		FString Outro;
	};

	ANDREWSAIRSOFT_API const TArray<FMission>& Missions();
	/** 1-based; nullptr when out of range. */
	ANDREWSAIRSOFT_API const FMission* FindMission(int32 Number);
	ANDREWSAIRSOFT_API FString GameTitle();

	/** Damage of one hit (one pellet for shotguns) before the difficulty scale. */
	ANDREWSAIRSOFT_API float WeaponDamage(FName WeaponId, bool bHeadshot);
	/** How hard enemies hit the player at each difficulty (the "bot skill" setting). */
	ANDREWSAIRSOFT_API float EnemyDamageScale(EAirsoftBotSkill Skill);

	/** URL options that open a mission with the campaign referee. */
	ANDREWSAIRSOFT_API FString MissionOptions(int32 Number);
	/** Voice-over sound key, e.g. VoiceKey(2, "I1") -> VO_M2_I1. */
	ANDREWSAIRSOFT_API FName VoiceKey(int32 Number, const FString& Line);
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
	/** Ends the opening cinematic early (Space / Enter during the intro). */
	void SkipCinematic();

protected:
	/** Applies Damage to Victim; handles kills (score, ammo, waves, boss, mission end). Returns true if anything was hit. */
	bool ApplyCampaignDamage(AController* Shooter, AController* Victim, FName WeaponId, float Damage, bool bHeadshot);

	// --- Opening cinematic -------------------------------------------------------
	void BeginCinematic();
	void PlayIntroLine(int32 Index);
	void EndCinematic();
	void UpdateCinematicCamera(float DeltaSeconds);

	// --- Fight -------------------------------------------------------------------
	/** Brings enemies in until MaxAlive are up or the mission's head count is used up. */
	void TopUpEnemies();
	AAirsoftBotController* SpawnEnemy();
	FAirsoftLoadout MakeEnemyLoadout(FName WeaponId = NAME_None) const;
	void SpawnBoss();
	void OnEnemyKilled(AController* Shooter, AController* Victim, FName WeaponId, bool bHeadshot);
	void OnPlayerKilled(AController* Victim, const FString& KilledBy);
	void CompleteMission();
	void UpdateObjectiveText();
	EAirsoftBotSkill Difficulty() const;
	APawn* FindPlayerPawn() const;
	/** Plays a voice line for the player; returns its length in seconds (0 if the sound isn't imported). */
	float PlayVoice(const FString& Line);

	int32 MissionNumber = 1;
	int32 EnemiesSpawned = 0;
	int32 EnemiesKilled = 0;
	bool bEnemiesStarted = false;
	bool bMissionOver = false;
	FTimerHandle IntroTimer;
	FTimerHandle EndTimer;
	UPROPERTY() TArray<TObjectPtr<AAirsoftBotController>> Enemies;
	UPROPERTY() TObjectPtr<AAirsoftBotController> BossController;

	UPROPERTY() TObjectPtr<ACameraActor> CinematicCamera;
	bool bInCinematic = false;
	float CinematicTime = 0.f;
	float CinematicLength = 1.f;
	FVector CamFrom = FVector::ZeroVector;
	FVector CamTo = FVector::ZeroVector;
	FRotator CamRotFrom = FRotator::ZeroRotator;
	FRotator CamRotTo = FRotator::ZeroRotator;
};
