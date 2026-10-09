// Andrew's Airsoft - replicated match state read by every HUD.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameStateBase.h"
#include "AirsoftTypes.h"
#include "AirsoftGameState.generated.h"

class AAirsoftObjective;

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
	UPROPERTY(Replicated, BlueprintReadOnly) int32 BlueScore = 0;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 RedScore = 0;
	UPROPERTY(Replicated, BlueprintReadOnly) int32 ScoreLimit = 40;
	UPROPERTY(Replicated, BlueprintReadOnly) FString StatusMessage;
	UPROPERTY(Replicated, BlueprintReadOnly) TArray<int32> ModeVotes;
	UPROPERTY(Replicated, BlueprintReadOnly) TArray<int32> MapVotes;
	UPROPERTY(Replicated, BlueprintReadOnly) EAirsoftTeam Winner = EAirsoftTeam::None;
	UPROPERTY(Replicated, BlueprintReadOnly) TArray<TObjectPtr<AAirsoftObjective>> Objectives;

	float GetTimeRemaining() const;
	int32 GetScore(EAirsoftTeam Team) const;

	static const TArray<FName>& MapIds();
	static FString MapDisplayName(FName Id);
	static FString ModeDisplayName(EAirsoftMode InMode);
	static FString ModeBlurb(EAirsoftMode InMode);
};
