#include "AirsoftGameState.h"

#include "AirsoftObjective.h"
#include "Net/UnrealNetwork.h"

void AAirsoftGameState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AAirsoftGameState, Phase);
	DOREPLIFETIME(AAirsoftGameState, PhaseEndsAt);
	DOREPLIFETIME(AAirsoftGameState, bIsMatchMap);
	DOREPLIFETIME(AAirsoftGameState, Mode);
	DOREPLIFETIME(AAirsoftGameState, MapId);
	DOREPLIFETIME(AAirsoftGameState, BlueScore);
	DOREPLIFETIME(AAirsoftGameState, RedScore);
	DOREPLIFETIME(AAirsoftGameState, ScoreLimit);
	DOREPLIFETIME(AAirsoftGameState, StatusMessage);
	DOREPLIFETIME(AAirsoftGameState, ModeVotes);
	DOREPLIFETIME(AAirsoftGameState, MapVotes);
	DOREPLIFETIME(AAirsoftGameState, Winner);
	DOREPLIFETIME(AAirsoftGameState, Objectives);
}

float AAirsoftGameState::GetTimeRemaining() const
{
	if (PhaseEndsAt <= 0.f)
	{
		return -1.f;
	}
	return FMath::Max(0.f, PhaseEndsAt - static_cast<float>(GetServerWorldTimeSeconds()));
}

int32 AAirsoftGameState::GetScore(EAirsoftTeam Team) const
{
	return Team == EAirsoftTeam::Blue ? BlueScore : Team == EAirsoftTeam::Red ? RedScore : 0;
}

const TArray<FName>& AAirsoftGameState::MapIds()
{
	static const TArray<FName> Ids = { TEXT("Field"), TEXT("Club") };
	return Ids;
}

FString AAirsoftGameState::MapDisplayName(FName Id)
{
	if (Id == TEXT("Field")) return TEXT("Ironwood Yard");
	if (Id == TEXT("Club")) return TEXT("Velvet Club");
	return TEXT("Staging Area");
}

FString AAirsoftGameState::ModeDisplayName(EAirsoftMode InMode)
{
	return InMode == EAirsoftMode::Domination ? TEXT("Domination") : TEXT("Team Deathmatch");
}

FString AAirsoftGameState::ModeBlurb(EAirsoftMode InMode)
{
	return InMode == EAirsoftMode::Domination ? TEXT("Hold A, B and C. Every held point scores over time.")
		: TEXT("Tag the other team. First to the limit wins.");
}
