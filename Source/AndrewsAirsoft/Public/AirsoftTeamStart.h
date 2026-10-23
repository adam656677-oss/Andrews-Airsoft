// Andrew's Airsoft - team spawn point. Team None = staging area spawn.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerStart.h"
#include "AirsoftTypes.h"
#include "AirsoftTeamStart.generated.h"

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftTeamStart : public APlayerStart
{
	GENERATED_BODY()

public:
	AAirsoftTeamStart(const FObjectInitializer& ObjectInitializer);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Airsoft")
	EAirsoftTeam Team = EAirsoftTeam::None;
};
