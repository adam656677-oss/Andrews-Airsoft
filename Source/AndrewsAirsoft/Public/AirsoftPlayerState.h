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

	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftTeam Team = EAirsoftTeam::None;
	UPROPERTY(Replicated, BlueprintReadOnly) FAirsoftRoundStats Round;
	/** Career XP reported by the player's own profile when they join (friends game: trusted). */
	UPROPERTY(Replicated, BlueprintReadOnly) int32 CareerXP = 0;
	UPROPERTY(Replicated, BlueprintReadOnly) bool bOut = false;
	/** Server world time until which the player can't be tagged. */
	UPROPERTY(Replicated, BlueprintReadOnly) float ProtectedUntil = 0.f;
	/** Server world time at which a tagged player respawns (0 = not waiting). */
	UPROPERTY(Replicated, BlueprintReadOnly) float RespawnAt = 0.f;
	/** Name of whoever tagged this player last. */
	UPROPERTY(Replicated, BlueprintReadOnly) FString LastTaggedBy;
	UPROPERTY(Replicated, BlueprintReadOnly) FAirsoftLoadout Loadout;
	UPROPERTY(Replicated, BlueprintReadOnly) bool bLoadoutReceived = false;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 ModeVote = -1;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 MapVote = -1;

	int32 RankIndex() const;
	bool IsProtected() const;
	void ResetRound();
};
