// Andrew's Airsoft - the host's referee. The staging map is the lobby (armory,
// range, the mode + map vote); match maps run
//   Waiting -> [Briefing -> Live -> PostRound] x rounds -> travel back to staging
// Single-round modes (TDM, Domination, Gun Game) play one round; Elimination and
// VIP play several, with a short PostRound (final-tag replay) between them and
// the after-action report after the last. What differs per mode is asked from
// AirsoftModeRules.h; mode-specific scoring lives in the Tick*/HandleTag paths here.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "AirsoftTypes.h"
#include "AirsoftGameMode.generated.h"

class AAirsoftBotController;
class AAirsoftCharacter;
class AAirsoftGameState;
class AAirsoftObjective;
class AAirsoftPlayerController;
class AAirsoftPlayerState;
class APlayerState;

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
	/** One life per round: nobody (not even a late joiner) spawns mid-round in Elimination / VIP. */
	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override;
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
	/** A lobby vote changed (VoteFrom may be null). Re-tallies and queues a chat line for the voter. */
	void OnVotesChanged(AAirsoftPlayerController* VoteFrom = nullptr);
	void ForceStart(AAirsoftPlayerController* Requester);
	void SwitchTeam(AAirsoftPlayerController* PC);
	/** The player's profile (call sign) arrived: posts "<name> joined" once per session. */
	void OnPlayerProfileReady(AAirsoftPlayerController* PC);

	/** The loadout this player actually carries under the current rules (Gun Game ladder gun, VIP pistol). */
	FAirsoftLoadout GetEffectiveLoadout(const AAirsoftPlayerState* PS) const;

	// --- Chat (server) ------------------------------------------------------------
	/** Sends a player's (or bot's) line to everyone, or to their team. Text must already be cleaned. */
	void BroadcastChat(APlayerState* From, const FString& Text, bool bTeamOnly);
	/** Joins, leaves, votes, round results: a sender-less line to everyone. */
	void BroadcastSystem(const FString& Text);

	AAirsoftGameState* GetAirsoftGameState() const;

protected:
	void SetPhase(EAirsoftPhase NewPhase, float Duration);
	void TickStaging(float DeltaSeconds);
	void TickMatch(float DeltaSeconds);
	void TickDomination(float DeltaSeconds);
	void TickElimination(float DeltaSeconds);
	void TickVIP(float DeltaSeconds);
	/** Round clock ran out: who wins depends on the mode. */
	void HandleTimeUp();

	/** Everyone has loaded: reset the match and start round 1. */
	void BeginMatch();
	/** Respawn everyone frozen at their spawns (briefing / loadout freeze) for the next round. */
	void BeginRound();
	void BeginLive();
	/** Ends the current round of a round-based mode (scores it; the match may end with it). */
	void EndRound(EAirsoftTeam RoundWinnerTeam, const FString& Reason);
	/** Ends the match: XP, after-action report, PostRound, then back to staging. */
	void FinishMatch(EAirsoftTeam WinnerTeam, AAirsoftPlayerState* WinnerPlayer);
	void TravelToMatch();
	void ReturnToStaging();
	void FreezeAll(bool bFreeze);

	EAirsoftTeam SmallerTeam() const;
	void AssignTeam(AAirsoftPlayerState* PS);
	/** Keeps the teams the players picked, moving people only if one side has 2+ more. */
	void BalanceTeams();
	/** Free-for-all: everyone drops their team (kept in SavedTeam for the lobby). */
	void ClearTeamsForFreeForAll();
	void RecountVotes();
	void PostPendingVotes();
	/**
	 * Picks the mode and map with the most votes (ties at random). The map always supports the mode and
	 * its level exists; false if no map at all can be played.
	 */
	bool PickNextMatch(EAirsoftMode& OutMode, int32& OutMapIndex);
	void ScheduleRespawn(AController* Controller, float Delay);
	void Respawn(AController* Controller);
	int32 CountPlayers();
	/** Standing (spawned, not tagged) players per team. */
	void CountAlive(int32& OutBlue, int32& OutRed) const;
	void UpdateAliveCounts();
	void AnnounceAll(const FString& Title, const FString& Sub, const FLinearColor& Color, float Duration);
	void GiveXP(AController* Controller, int32 Amount, const FString& Reason);
	/** Re-issues the mode's loadout (and grenade rule) to this player's pawn right now. */
	void ApplyModeLoadout(AController* Controller);
	/** Gun Game: the shooter climbs a rung (or wins with the last gun). */
	void AdvanceGunGame(AController* Shooter, AAirsoftPlayerState* ShooterPS);

	// --- VIP ----------------------------------------------------------------------
	void ChooseVIP();
	void ChooseExtraction();
	AAirsoftCharacter* FindCharacterFor(const APlayerState* PS) const;

	// --- Bots (match maps only, server only) ---------------------------------
	/** The host's choice (their saved settings): players per team to fill to (0 = off) and difficulty. */
	void GetBotSettings(int32& OutTeamSize, EAirsoftBotSkill& OutSkill) const;
	/** Adds / removes bots so each side has max(fill, humans on the bigger side) players (free-for-all: 2 x fill in total). */
	void UpdateBots();
	AAirsoftBotController* AddBot(EAirsoftTeam Team, EAirsoftBotSkill Skill);
	void RemoveBot(AAirsoftBotController* Bot);
	void RemoveAllBots();
	FString MakeBotName() const;
	FAirsoftLoadout MakeBotLoadout() const;
	/** Now and then a bot says a short canned line (rate-limited, can be turned off in the settings). */
	void BotChatter(AController* Speaker, int32 Situation);

	UPROPERTY() TArray<TObjectPtr<AAirsoftBotController>> Bots;
	bool bBotsDirty = false;
	float BotClock = 0.f;
	double NextBotChatterAt = 0.0;

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

	/** Round-based modes: players per side when the round went live (no elimination check against an empty side). */
	int32 RoundStartBlue = 0;
	int32 RoundStartRed = 0;
	bool bLastStandAnnounced[2] = { false, false };
	/** VIP: seconds the VIP has stood in the extraction zone. */
	float ExtractClock = 0.f;
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
