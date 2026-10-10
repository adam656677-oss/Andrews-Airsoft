#include "AirsoftGameState.h"

#include "AirsoftModeRules.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSettings.h"
#include "Engine/World.h"
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
	DOREPLIFETIME(AAirsoftGameState, RoundNumber);
	DOREPLIFETIME(AAirsoftGameState, MaxRounds);
	DOREPLIFETIME(AAirsoftGameState, bMatchOver);
	DOREPLIFETIME(AAirsoftGameState, RoundWinner);
	DOREPLIFETIME(AAirsoftGameState, BlueAlive);
	DOREPLIFETIME(AAirsoftGameState, RedAlive);
	DOREPLIFETIME(AAirsoftGameState, VIPPlayer);
	DOREPLIFETIME(AAirsoftGameState, AttackingTeam);
	DOREPLIFETIME(AAirsoftGameState, ExtractionPoint);
	DOREPLIFETIME(AAirsoftGameState, ExtractProgress);
	DOREPLIFETIME(AAirsoftGameState, WinnerName);
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

int32 AAirsoftGameState::GetAlive(EAirsoftTeam Team) const
{
	return Team == EAirsoftTeam::Blue ? BlueAlive : Team == EAirsoftTeam::Red ? RedAlive : 0;
}

bool AAirsoftGameState::IsFreeForAll() const
{
	return bIsMatchMap && AirsoftRules::IsFreeForAll(Mode);
}

bool AAirsoftGameState::IsRoundBased() const
{
	return bIsMatchMap && AirsoftRules::IsRoundBased(Mode);
}

EAirsoftTeam AAirsoftGameState::DefendingTeam() const
{
	switch (AttackingTeam)
	{
	case EAirsoftTeam::Blue: return EAirsoftTeam::Red;
	case EAirsoftTeam::Red: return EAirsoftTeam::Blue;
	default: return EAirsoftTeam::None;
	}
}

AAirsoftPlayerState* AAirsoftGameState::GetGunGameLeader() const
{
	AAirsoftPlayerState* Best = nullptr;
	for (APlayerState* P : PlayerArray)
	{
		AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (!IsValid(PS) || PS->IsInactive())
		{
			continue;
		}
		if (!Best || PS->GunLevel > Best->GunLevel || (PS->GunLevel == Best->GunLevel && PS->Round.Tags > Best->Round.Tags))
		{
			Best = PS;
		}
	}
	return Best;
}

bool AAirsoftGameState::AreHostile(const UObject* WorldContext, EAirsoftTeam A, EAirsoftTeam B)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	const AAirsoftGameState* GS = World ? World->GetGameState<AAirsoftGameState>() : nullptr;
	const EAirsoftMode RulesMode = (GS && GS->bIsMatchMap) ? GS->Mode : EAirsoftMode::TDM;
	return AirsoftRules::AreHostile(RulesMode, A, B);
}

bool AAirsoftGameState::CanTag(const UObject* WorldContext, EAirsoftTeam ShooterTeam, EAirsoftTeam VictimTeam)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	const AAirsoftGameState* GS = World ? World->GetGameState<AAirsoftGameState>() : nullptr;
	if (GS && GS->IsFreeForAll())
	{
		return true;
	}
	return ShooterTeam != VictimTeam || UAirsoftSettings::Get()->bFriendlyFire;
}

TArray<FName> AAirsoftGameState::MapIds()
{
	TArray<FName> Ids;
	for (const FAirsoftMapInfo& Info : AirsoftRules::Maps())
	{
		Ids.Add(Info.Key);
	}
	return Ids;
}

FString AAirsoftGameState::MapDisplayName(FName Id)
{
	return AirsoftRules::MapDisplayName(Id);
}

FString AAirsoftGameState::ModeDisplayName(EAirsoftMode InMode)
{
	return AirsoftRules::ModeName(InMode);
}

FString AAirsoftGameState::ModeBlurb(EAirsoftMode InMode)
{
	return AirsoftRules::ModeBlurb(InMode);
}
