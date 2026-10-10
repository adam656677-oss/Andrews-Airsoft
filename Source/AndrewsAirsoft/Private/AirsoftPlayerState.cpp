#include "AirsoftPlayerState.h"

#include "AirsoftWeaponData.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "Net/UnrealNetwork.h"

AAirsoftPlayerState::AAirsoftPlayerState()
{
	Loadout = AirsoftWeapons::DefaultLoadout();
	SetNetUpdateFrequency(20.f);
}

void AAirsoftPlayerState::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AAirsoftPlayerState, Team);
	DOREPLIFETIME(AAirsoftPlayerState, Round);
	DOREPLIFETIME(AAirsoftPlayerState, CareerXP);
	DOREPLIFETIME(AAirsoftPlayerState, bOut);
	DOREPLIFETIME(AAirsoftPlayerState, ProtectedUntil);
	DOREPLIFETIME(AAirsoftPlayerState, RespawnAt);
	DOREPLIFETIME(AAirsoftPlayerState, LastTaggedBy);
	DOREPLIFETIME(AAirsoftPlayerState, Loadout);
	DOREPLIFETIME(AAirsoftPlayerState, bLoadoutReceived);
	DOREPLIFETIME(AAirsoftPlayerState, ModeVote);
	DOREPLIFETIME(AAirsoftPlayerState, MapVote);
	DOREPLIFETIME(AAirsoftPlayerState, GunLevel);
}

void AAirsoftPlayerState::CopyProperties(APlayerState* PlayerState)
{
	Super::CopyProperties(PlayerState);
	// Carried across seamless travel between the staging area and match maps.
	if (AAirsoftPlayerState* Next = Cast<AAirsoftPlayerState>(PlayerState))
	{
		Next->CareerXP = CareerXP;
		Next->Loadout = Loadout;
		Next->bLoadoutReceived = bLoadoutReceived;
		Next->Team = Team;
		Next->SavedTeam = SavedTeam;
		Next->bJoinAnnounced = bJoinAnnounced;
	}
}

int32 AAirsoftPlayerState::RankIndex() const
{
	return AirsoftWeapons::RankIndexForXP(CareerXP + Round.XP);
}

bool AAirsoftPlayerState::IsProtected() const
{
	const UWorld* World = GetWorld();
	const AGameStateBase* GS = World ? World->GetGameState() : nullptr;
	return GS && GS->GetServerWorldTimeSeconds() < ProtectedUntil;
}

void AAirsoftPlayerState::ResetRound()
{
	Round = FAirsoftRoundStats();
	ResetLife();
	ModeVote = -1;
	MapVote = -1;
	VoteAnnounceAt = 0.0;
	GunLevel = 0;
	VIPTurns = 0;
}

void AAirsoftPlayerState::ResetLife()
{
	bOut = false;
	ProtectedUntil = 0.f;
	RespawnAt = 0.f;
	LastTaggedBy.Reset();
}
