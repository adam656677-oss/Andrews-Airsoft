// Andrew's Airsoft - replicated match state read by every HUD.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "AirsoftTypes.h"
#include "AirsoftGameState.generated.h"

class AAirsoftObjective;
class AAirsoftPlayerState;

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftGameState : public AGameStateBase
{
	GENERATED_BODY()

public:
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftPhase Phase = EAirsoftPhase::Waiting;
	UPROPERTY(Replicated, BlueprintReadOnly) float PhaseEndsAt = 0.f;
	UPROPERTY(Replicated, BlueprintReadOnly) bool bIsMatchMap = false;
	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftMode Mode = EAirsoftMode::TDM;
	UPROPERTY(Replicated, BlueprintReadOnly) FName MapId;
	/** Team modes: tags (TDM), points (Domination) or round wins (Elimination, VIP). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 BlueScore = 0;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 RedScore = 0;
	/** See AirsoftRules::ScoreLimit (rounds to win, or the Gun Game ladder length). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 ScoreLimit = 40;
	UPROPERTY(Replicated, BlueprintReadOnly) FString StatusMessage;
	/** Lobby vote tallies: one entry per mode (AirsoftRules order) and per match map (AirsoftRules::Maps order). */
	UPROPERTY(Replicated, BlueprintReadOnly) TArray<int32> ModeVotes;
	UPROPERTY(Replicated, BlueprintReadOnly) TArray<int32> MapVotes;
	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftTeam Winner = EAirsoftTeam::None;
	UPROPERTY(Replicated, BlueprintReadOnly) TArray<TObjectPtr<AAirsoftObjective>> Objectives;

	/** Round-based modes: the current round (1-based; 0 before the first). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 RoundNumber = 0;
	/** Most rounds this match can last (0 = single-round mode). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 MaxRounds = 0;
	/** This PostRound ends the whole match (always true in single-round modes). */
	UPROPERTY(Replicated, BlueprintReadOnly) bool bMatchOver = false;
	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftTeam RoundWinner = EAirsoftTeam::None;
	/** Players still standing per side (live, not tagged out). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 BlueAlive = 0;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 RedAlive = 0;
	/** VIP: this round's VIP, the escorting side and where they are heading. */
	UPROPERTY(Replicated, BlueprintReadOnly) TObjectPtr<AAirsoftPlayerState> VIPPlayer;
	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftTeam AttackingTeam = EAirsoftTeam::None;
	UPROPERTY(Replicated, BlueprintReadOnly) TObjectPtr<AAirsoftObjective> ExtractionPoint;
	/** VIP: 0..1 while the VIP stands in the extraction zone. */
	UPROPERTY(Replicated, BlueprintReadOnly) float ExtractProgress = 0.f;
	/** Free-for-all winner's call sign once the match is over (empty = draw / team mode). */
	UPROPERTY(Replicated, BlueprintReadOnly) FString WinnerName;

	float GetTimeRemaining() const;
	int32 GetScore(EAirsoftTeam Team) const;
	int32 GetAlive(EAirsoftTeam Team) const;
	/** A match map running a free-for-all mode (Gun Game). */
	bool IsFreeForAll() const;
	/** A match map running a round-based mode (Elimination, VIP). */
	bool IsRoundBased() const;
	/** VIP: the side guarding extraction. */
	EAirsoftTeam DefendingTeam() const;
	/** Gun Game: the highest ladder level (then most tags), or null if nobody is playing. */
	AAirsoftPlayerState* GetGunGameLeader() const;

	/** Do these teams fight under the current rules? Free-for-all: everyone. Team modes: two different, assigned teams. */
	static bool AreHostile(const UObject* WorldContext, EAirsoftTeam A, EAirsoftTeam B);
	/**
	 * May a BB / grenade from ShooterTeam tag VictimTeam? Free-for-all, different teams, or friendly fire on.
	 * (Hit checks in AirsoftCombatComponent and AirsoftGrenade should use this so Gun Game tags register.)
	 */
	static bool CanTag(const UObject* WorldContext, EAirsoftTeam ShooterTeam, EAirsoftTeam VictimTeam);

	/** Match map keys in vote order. */
	static TArray<FName> MapIds();
	static FString MapDisplayName(FName Id);
	static FString ModeDisplayName(EAirsoftMode InMode);
	static FString ModeBlurb(EAirsoftMode InMode);
};
