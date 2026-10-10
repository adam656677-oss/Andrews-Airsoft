// Andrew's Airsoft - per-player replicated state.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerState.h"
#include "AirsoftTypes.h"
#include "AirsoftPlayerState.generated.h"

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftPlayerState : public APlayerState
{
	GENERATED_BODY()

public:
	AAirsoftPlayerState();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void CopyProperties(APlayerState* PlayerState) override;

	/** None during a free-for-all match (Gun Game); SavedTeam keeps the lobby team. */
	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftTeam Team = EAirsoftTeam::None;
	/** Stats for the whole match (all rounds of a round-based mode). */
	UPROPERTY(Replicated, BlueprintReadOnly) FAirsoftRoundStats Round;
	/** Career XP reported by the player's own profile when they join (friends game: trusted). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 CareerXP = 0;
	UPROPERTY(Replicated, BlueprintReadOnly) bool bOut = false;
	/** Server world time until which the player can't be tagged. */
	UPROPERTY(Replicated, BlueprintReadOnly) float ProtectedUntil = 0.f;
	/** Server world time at which a tagged player respawns (0 = not waiting, e.g. out for the round). */
	UPROPERTY(Replicated, BlueprintReadOnly) float RespawnAt = 0.f;
	/** Name of whoever tagged this player last. */
	UPROPERTY(Replicated, BlueprintReadOnly) FString LastTaggedBy;
	/** The player's own chosen loadout (modes may hand out a different one: see AAirsoftGameMode::GetEffectiveLoadout). */
	UPROPERTY(Replicated, BlueprintReadOnly) FAirsoftLoadout Loadout;
	UPROPERTY(Replicated, BlueprintReadOnly) bool bLoadoutReceived = false;
	/** Lobby votes: index into the mode list (AirsoftRules) and the match map list, -1 = none. */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 ModeVote = -1;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 MapVote = -1;
	/** Gun Game: ladder rung, 0 = the first weapon. */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 GunLevel = 0;

	// --- Server only (not replicated) ----------------------------------------
	/** Lobby team to go back to after a free-for-all match (carried over seamless travel). */
	EAirsoftTeam SavedTeam = EAirsoftTeam::None;
	/** Lobby: world time to post this player's vote in chat (0 = nothing pending; debounces F1/F2 cycling). */
	double VoteAnnounceAt = 0.0;
	/** "<name> joined" was posted (carried over seamless travel so it shows once per session). */
	bool bJoinAnnounced = false;
	/** VIP: rounds played as the VIP this match (the least-used candidate goes next). */
	int32 VIPTurns = 0;

	int32 RankIndex() const;
	bool IsProtected() const;
	/** New match: clears the match stats, votes and per-life state. */
	void ResetRound();
	/** New round of a round-based mode: per-life state only (the match stats carry on). */
	void ResetLife();
};
