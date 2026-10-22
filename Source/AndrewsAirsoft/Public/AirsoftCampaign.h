// Andrew's Airsoft - the single-player story campaign ("Last Contract").
//
// Each mission is one of the existing maps played against computer-controlled enemies:
// the player has health (Call of Duty style: it comes back once you're out of fire),
// a narrated cinematic opens the mission, enemies come in waves until the mission's head
// count is cleared, then the mission's boss steps in. Checkpoints (half the crew down, the
// boss fight) are saved in the profile; a death puts Andrew back at the last one. Beating the
// boss unlocks the next mission. The last mission ends on an ending shot and the credits.
//
// The story (titles, narration, objectives, enemies, bosses, combat barks, credits) is data:
// Content/Airsoft/Data/Campaign.json. Tools/Audio/make_voice_neural.py voices it into
// /Game/Airsoft/Audio/VO_M<n>_I<k>, _Boss, _Outro, _Andrew_Start, _Andrew_Boss, _Boss_Mid,
// _Boss_Death and the barks' VO_Andrew_* / VO_Crew_<A|B|C>_* files. Every voice line is subtitled.
// The referee is AAirsoftCampaignGameMode, a single-player cousin of the airsoft match referee.
//
// The main menu drives the story through the progress functions below (Continue / New Game /
// Mission Select).

#pragma once

#include "CoreMinimal.h"
#include "AirsoftGameMode.h"
#include "AirsoftCampaign.generated.h"

class ACameraActor;
class AAirsoftBotController;
class SWidget;

namespace AirsoftCampaign
{
	struct FBoss
	{
		FString Name;
		FName Weapon;
		float Health = 300.f;
		FString Taunt;
		/** Said at half health, and as the boss goes down. */
		FString Mid;
		FString Death;
		/** Andrew's answer to the taunt. */
		FString AndrewReply;
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
		/** Andrew, under his breath, as the opening cinematic ends. */
		FString AndrewStart;
		/** Regular enemies to clear before the boss, and how many may be up at once. */
		int32 Enemies = 8;
		int32 MaxAlive = 5;
		/** Primary weapons the regular enemies carry (sidearms are always pistols). */
		TArray<FName> EnemyWeapons;
		/** Steps in once the regulars are down (no boss when Name is empty). */
		FBoss Boss;
		/** Narrated when the mission is won. */
		FString Outro;
		/** Fractions of the crew head count at which a checkpoint is saved (the boss fight always is one). */
		TArray<float> Checkpoints;
	};

	/** One voiced line: the sound's asset name and what is said. */
	struct FLine
	{
		FName File;
		FString Text;
	};

	/** A block of the end credits: a heading (may be empty) and its lines. */
	struct FCreditsBlock
	{
		FString Heading;
		TArray<FString> Lines;
	};

	ANDREWSAIRSOFT_API const TArray<FMission>& Missions();
	/** 1-based; nullptr when out of range. */
	ANDREWSAIRSOFT_API const FMission* FindMission(int32 Number);
	ANDREWSAIRSOFT_API FString GameTitle();
	/** Combat barks for an event (Campaign.json "Barks"), e.g. "CrewSpotted"; nullptr when there are none. */
	ANDREWSAIRSOFT_API const TArray<FLine>* FindBarks(FName Event);
	ANDREWSAIRSOFT_API const TArray<FCreditsBlock>& Credits();

	/** Damage of one hit (one pellet for shotguns) before the difficulty scale. */
	ANDREWSAIRSOFT_API float WeaponDamage(FName WeaponId, bool bHeadshot);
	/** How hard enemies hit the player at each difficulty (the "bot skill" setting). */
	ANDREWSAIRSOFT_API float EnemyDamageScale(EAirsoftBotSkill Skill);

	/** URL options that open a mission with the campaign referee (bFromCheckpoint: resume at the saved checkpoint). */
	ANDREWSAIRSOFT_API FString MissionOptions(int32 Number, bool bFromCheckpoint = false);
	/** Voice-over sound key, e.g. VoiceKey(2, "I1") -> VO_M2_I1. */
	ANDREWSAIRSOFT_API FName VoiceKey(int32 Number, const FString& Line);

	// --- Progress, for the main menu (all read/write the local profile) ------------------

	/** Highest mission that can be started (1-based). Beating mission N unlocks N+1. */
	ANDREWSAIRSOFT_API int32 HighestUnlocked(const UObject* WorldContext);
	ANDREWSAIRSOFT_API bool IsUnlocked(const UObject* WorldContext, int32 Number);
	/** True once the last mission has been beaten. */
	ANDREWSAIRSOFT_API bool IsFinished(const UObject* WorldContext);
	/** Mission of the saved mid-mission checkpoint, 0 when there is none. */
	ANDREWSAIRSOFT_API int32 CheckpointMission(const UObject* WorldContext);
	/** e.g. "MISSION 2 · VELVET · 7 OF 14 DOWN" or "... · SILAS VARGA" (the boss fight); empty when there is none. */
	ANDREWSAIRSOFT_API FString CheckpointLabel(const UObject* WorldContext);
	/** The mission Continue opens: the checkpoint's mission, else the furthest unlocked. */
	ANDREWSAIRSOFT_API int32 ContinueMission(const UObject* WorldContext);
	/** True when there is anything to continue (a checkpoint or a mission past the first). */
	ANDREWSAIRSOFT_API bool CanContinue(const UObject* WorldContext);
	/** Continue: resumes at the saved checkpoint, or starts the furthest unlocked mission. */
	ANDREWSAIRSOFT_API void Continue(const UObject* WorldContext);
	/** New Game: forgets the checkpoint and starts mission 1 (unlocked missions stay unlocked). */
	ANDREWSAIRSOFT_API void NewGame(const UObject* WorldContext);
	/** Mission Select: starts an unlocked mission from its beginning. Returns false if it is locked. */
	ANDREWSAIRSOFT_API bool StartMission(const UObject* WorldContext, int32 Number);
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
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual bool HandleTag(AController* Shooter, AController* Victim, FName WeaponId) override;
	virtual bool HandleHit(AController* Shooter, AController* Victim, FName WeaponId, const FVector& HitLocation) override;

	/** Developer console shortcuts (airsoft.campaign.killenemies / airsoft.campaign.complete). */
	void DebugKillEnemies();
	void DebugCompleteMission();
	/** Space during a cinematic: ends the opening early, skips the ending shot, or ends the credits. */
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
	/** The story's neon-noir look: an unbound post-process volume over the whole map. */
	void ApplyNoirGrade();
	/** Plays this mission's voice line VO_M<n>_<Line> for the player; returns its length in seconds (0 if the sound isn't imported). */
	float PlayVoice(const FString& Line);
	/** Plays a voice line (2D, or at Location when bAt) and shows its subtitle; returns how long to hold the subtitle. */
	float SpeakLine(FName File, const FString& Speaker, const FString& Text, const FLinearColor& Color, const FVector* At = nullptr);

	// --- Checkpoints ---------------------------------------------------------------
	/** Saves a checkpoint at the current progress (Andrew's position, crew killed, boss phase). */
	void SaveCheckpoint(bool bBossPhase);
	/** Puts the mission back to the last checkpoint: clears the enemies that are up, respawns Andrew there, resumes the fight. */
	void RestoreCheckpoint(bool bAnnounce);
	/** Mid-mission: a checkpoint is due when the crew killed crosses one of the mission's fractions. */
	void CheckCrewCheckpoint();

	// --- Barks ---------------------------------------------------------------------
	/** Watches Andrew and the crew for bark-worthy moments (spotted, reloading, flanking, hurt...). */
	void UpdateBarks();
	/** Plays one of an event's barks; a crew bark comes from Speaker's body in that enemy's voice. */
	bool Bark(FName Event, AController* Speaker = nullptr, float Chance = 1.f);
	/** Crew voice letter for an enemy (A, B or C), stable for that controller. */
	TCHAR CrewVoiceFor(const AController* Enemy);

	// --- Ending ----------------------------------------------------------------------
	void BeginEnding();
	void UpdateEndingCamera(float DeltaSeconds);
	void RollCredits();
	void FinishCredits();

	int32 MissionNumber = 1;
	int32 EnemiesSpawned = 0;
	int32 EnemiesKilled = 0;
	bool bEnemiesStarted = false;
	bool bMissionOver = false;
	/** Guns this mission's completion unlocked ("MP7 GBB and G34 Competition"), shown with MISSION COMPLETE / after the credits. */
	FString UnlockedGunsText;
	/** The main menu's line after the last mission (names any guns it unlocked). */
	FString CompletionMessage() const;
	FTimerHandle IntroTimer;
	FTimerHandle EndTimer;
	FTimerHandle BossTimer;
	FTimerHandle RefillTimer;
	FTimerHandle VoiceTimer;
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

	/** In-level checkpoint (also written to the profile from the first mid-mission one on). */
	bool bHasCheckpoint = false;
	int32 CheckpointKills = 0;
	bool bCheckpointBoss = false;
	FVector CheckpointLocation = FVector::ZeroVector;
	float CheckpointYaw = 0.f;
	/** Next fraction in the mission's Checkpoints list to watch for, and checkpoints reached so far. */
	int32 NextCheckpoint = 0;
	int32 CheckpointsReached = 0;
	/** ?Checkpoint=1: resume at the profile's checkpoint instead of playing the opening. */
	bool bResumeFromSave = false;
	/** Andrew is down and about to be put back at the checkpoint. */
	bool bRespawning = false;
	/** The boss is down; his last words play before the mission ends. */
	bool bBossDown = false;

	/** Bark pacing: one voice at a time, a few seconds between crew barks, longer between Andrew's. */
	double VoiceBusyUntil = 0.0;
	double NextCrewBark = 0.0;
	double NextAndrewBark = 0.0;
	bool bBossMidSaid = false;
	bool bFearSaid = false;
	bool bLastKillSaid = false;
	bool bAndrewWasReloading = false;
	bool bAndrewWasThrowing = false;
	bool bAndrewHurtArmed = true;
	struct FCrewWatch
	{
		uint8 LastState = 0;
		bool bWasReloading = false;
		bool bWasThrowing = false;
		/** 'A', 'B' or 'C' once handed out (CrewVoiceFor). */
		TCHAR Voice = 0;
	};
	TMap<TWeakObjectPtr<AController>, FCrewWatch> CrewWatch;
	int32 CrewVoicesHanded = 0;

	/** Ending: the camera rises away from Andrew while the narrator closes the story, then the credits. */
	bool bInEnding = false;
	float EndingTime = 0.f;
	float EndingLength = 8.f;
	/** The credits roll (an SAirsoftCredits) while it is on screen. */
	TSharedPtr<SWidget> CreditsWidget;
	/** On the way back to the main menu. */
	bool bLeaving = false;
};
