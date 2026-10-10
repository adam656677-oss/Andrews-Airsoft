// Andrew's Airsoft - the host's referee. The staging map is the lobby (armory,
// range, votes); match maps run Waiting -> Briefing -> Live -> PostRound and
// then everyone travels back to staging together (seamless travel).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "AirsoftTypes.h"
#include "AirsoftGameMode.generated.h"

class AAirsoftBotController;
class AAirsoftCharacter;
class AAirsoftGameState;
class AAirsoftPlayerController;
class AAirsoftPlayerState;

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AAirsoftGameMode();

	virtual void InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage) override;
	virtual void InitGameState() override;
	virtual void StartPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void PostLogin(APlayerController* NewPlayer) override;
	virtual void Logout(AController* Exiting) override;
	virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;
	virtual AActor* ChoosePlayerStart_Implementation(AController* Player) override;
	virtual bool ShouldSpawnAtStartSpot_Implementation(AController* Player) override { return false; }
	virtual void SetPlayerDefaults(APawn* PlayerPawn) override;
	virtual void PostSeamlessTravel() override;
	/** Bots are made fresh on every match map: their PlayerStates never travel. */
	virtual void GetSeamlessTravelActorList(bool bToTransition, TArray<AActor*>& ActorList) override;

	/** Server: a validated BB (or grenade) hit. Returns true if it counted as a tag. */
	bool HandleTag(AController* Shooter, AController* Victim, FName WeaponId);

	/** Server: someone fired (validated shot). Bots use it as hearing. */
	void NotifyShotFired(AAirsoftCharacter* Shooter, const FVector& Origin, const FVector& Direction, bool bQuiet);

	void SpawnGrenade(AController* Thrower, const FVector& Origin, const FVector& Direction);

	/** A player's loadout changed: re-equip now if the rules allow, otherwise on next spawn. */
	void OnLoadoutChanged(AAirsoftPlayerController* PC);
	void OnVotesChanged();
	void ForceStart(AAirsoftPlayerController* Requester);
	void SwitchTeam(AAirsoftPlayerController* PC);

	AAirsoftGameState* GetAirsoftGameState() const;

protected:
	void SetPhase(EAirsoftPhase NewPhase, float Duration);
	void TickStaging(float DeltaSeconds);
	void TickMatch(float DeltaSeconds);
	void TickDomination(float DeltaSeconds);
	void BeginBriefing();
	void BeginLive();
	void EndRound(EAirsoftTeam Winner);
	void TravelToMatch();
	void ReturnToStaging();
	void FreezeAll(bool bFreeze);

	EAirsoftTeam SmallerTeam() const;
	void AssignTeam(AAirsoftPlayerState* PS);
	/** Keeps the teams the players picked, moving people only if one side has 2+ more. */
	void BalanceTeams();
	void RecountVotes();
	void ScheduleRespawn(AController* Controller, float Delay);
	void Respawn(AController* Controller);
	int32 CountPlayers();
	void AnnounceAll(const FString& Title, const FString& Sub, const FLinearColor& Color, float Duration);
	void GiveXP(AController* Controller, int32 Amount, const FString& Reason);

	// --- Bots (match maps only, server only) ---------------------------------
	/** The host's choice (their saved settings): players per team to fill to (0 = off) and difficulty. */
	void GetBotSettings(int32& OutTeamSize, EAirsoftBotSkill& OutSkill) const;
	/** Adds / removes bots so each side has max(fill, humans on the bigger side) players. */
	void UpdateBots();
	AAirsoftBotController* AddBot(EAirsoftTeam Team, EAirsoftBotSkill Skill);
	void RemoveBot(AAirsoftBotController* Bot);
	void RemoveAllBots();
	FString MakeBotName() const;
	FAirsoftLoadout MakeBotLoadout() const;

	UPROPERTY() TArray<TObjectPtr<AAirsoftBotController>> Bots;
	bool bBotsDirty = false;
	float BotClock = 0.f;

	/** Parsed in InitGame, applied to the game state in InitGameState. */
	EAirsoftMode PendingMode = EAirsoftMode::TDM;
	FName PendingMapId;
	bool bPendingMatchMap = false;

	bool bTravelling = false;
	bool bForceStarted = false;
	float DominationScoreClock = 0.f;
	double WaitingSince = 0.0;
	FAirsoftFinalTag LastTag;
	TMap<TWeakObjectPtr<AController>, FTimerHandle> RespawnTimers;
};

/** Main menu map: no pawn, just the title screen. */
UCLASS()
class ANDREWSAIRSOFT_API AAirsoftMenuGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AAirsoftMenuGameMode();

	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override { return false; }
};
