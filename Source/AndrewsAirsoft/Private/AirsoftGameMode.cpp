#include "AirsoftGameMode.h"

#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameState.h"
#include "AirsoftGrenade.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSettings.h"
#include "AirsoftTeamStart.h"
#include "AirsoftWeaponData.h"
#include "Algo/Sort.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerStart.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/PackageName.h"
#include "TimerManager.h"

namespace
{
	constexpr float CaptureTime = 8.f;
	constexpr float MaxLoadWait = 25.f;

	int32 PickVote(const TArray<int32>& Votes)
	{
		int32 Best = -1;
		TArray<int32> Ties;
		for (int32 i = 0; i < Votes.Num(); ++i)
		{
			if (Votes[i] > Best)
			{
				Best = Votes[i];
				Ties = { i };
			}
			else if (Votes[i] == Best)
			{
				Ties.Add(i);
			}
		}
		return Ties.Num() > 0 ? Ties[FMath::RandRange(0, Ties.Num() - 1)] : 0;
	}

	bool IsFrozenPhase(EAirsoftPhase Phase)
	{
		return Phase == EAirsoftPhase::Waiting || Phase == EAirsoftPhase::Briefing || Phase == EAirsoftPhase::PostRound;
	}
}

AAirsoftGameMode::AAirsoftGameMode()
{
	PrimaryActorTick.bCanEverTick = true;
	DefaultPawnClass = AAirsoftCharacter::StaticClass();
	PlayerControllerClass = AAirsoftPlayerController::StaticClass();
	PlayerStateClass = AAirsoftPlayerState::StaticClass();
	GameStateClass = AAirsoftGameState::StaticClass();
	bUseSeamlessTravel = true;
	bStartPlayersAsSpectators = false;
}

AAirsoftGameState* AAirsoftGameMode::GetAirsoftGameState() const
{
	return GetGameState<AAirsoftGameState>();
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

void AAirsoftGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);

	const FString ModeOption = UGameplayStatics::ParseOption(Options, TEXT("Mode"));
	PendingMode = ModeOption.Equals(TEXT("Domination"), ESearchCase::IgnoreCase) ? EAirsoftMode::Domination : EAirsoftMode::TDM;

	const FString Current = FPackageName::GetShortName(UWorld::RemovePIEPrefix(MapName));
	bPendingMatchMap = false;
	PendingMapId = NAME_None;
	for (const TPair<FName, FString>& Pair : UAirsoftSettings::Get()->MatchMaps)
	{
		if (FPackageName::GetShortName(Pair.Value).Equals(Current, ESearchCase::IgnoreCase))
		{
			bPendingMatchMap = true;
			PendingMapId = Pair.Key;
		}
	}
}

void AAirsoftGameMode::InitGameState()
{
	Super::InitGameState();
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		const UAirsoftSettings* S = UAirsoftSettings::Get();
		GS->bIsMatchMap = bPendingMatchMap;
		GS->Mode = PendingMode;
		GS->MapId = PendingMapId;
		GS->ScoreLimit = PendingMode == EAirsoftMode::Domination ? S->DominationScoreLimit : S->TDMScoreLimit;
		GS->ModeVotes.Init(0, 2);
		GS->MapVotes.Init(0, AAirsoftGameState::MapIds().Num());
		GS->BlueScore = 0;
		GS->RedScore = 0;
	}
}

void AAirsoftGameMode::StartPlay()
{
	Super::StartPlay();
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	GS->Objectives.Reset();
	for (TActorIterator<AAirsoftObjective> It(GetWorld()); It; ++It)
	{
		GS->Objectives.Add(*It);
	}
	Algo::Sort(GS->Objectives, [](const TObjectPtr<AAirsoftObjective>& A, const TObjectPtr<AAirsoftObjective>& B) { return A->Letter < B->Letter; });
	const bool bDomination = GS->bIsMatchMap && GS->Mode == EAirsoftMode::Domination;
	for (AAirsoftObjective* Obj : GS->Objectives)
	{
		if (Obj)
		{
			Obj->ServerReset(bDomination);
		}
	}
	WaitingSince = GetWorld()->GetTimeSeconds();
	SetPhase(EAirsoftPhase::Waiting, 0.f);
}

void AAirsoftGameMode::PostSeamlessTravel()
{
	Super::PostSeamlessTravel();
	WaitingSince = GetWorld()->GetTimeSeconds();
}

void AAirsoftGameMode::PostLogin(APlayerController* NewPlayer)
{
	Super::PostLogin(NewPlayer);
	RecountVotes();
}

void AAirsoftGameMode::Logout(AController* Exiting)
{
	if (FTimerHandle* Handle = RespawnTimers.Find(Exiting))
	{
		GetWorldTimerManager().ClearTimer(*Handle);
		RespawnTimers.Remove(Exiting);
	}
	Super::Logout(Exiting);
	RecountVotes();
}

void AAirsoftGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
	if (AAirsoftPlayerState* PS = NewPlayer ? NewPlayer->GetPlayerState<AAirsoftPlayerState>() : nullptr)
	{
		PS->bOut = false;
		PS->RespawnAt = 0.f;
		if (PS->Team == EAirsoftTeam::None)
		{
			AssignTeam(PS);
		}
	}
	Super::HandleStartingNewPlayer_Implementation(NewPlayer);
}

// ---------------------------------------------------------------------------
// Spawning
// ---------------------------------------------------------------------------

AActor* AAirsoftGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	const AAirsoftPlayerState* PS = Player ? Player->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	const EAirsoftTeam Team = PS ? PS->Team : EAirsoftTeam::None;
	const bool bMatch = GS && GS->bIsMatchMap;

	TArray<APlayerStart*> TeamStarts;
	TArray<APlayerStart*> NeutralStarts;
	TArray<APlayerStart*> AllStarts;
	for (TActorIterator<APlayerStart> It(GetWorld()); It; ++It)
	{
		APlayerStart* Start = *It;
		AllStarts.Add(Start);
		const AAirsoftTeamStart* TS = Cast<AAirsoftTeamStart>(Start);
		const EAirsoftTeam StartTeam = TS ? TS->Team : EAirsoftTeam::None;
		if (StartTeam == EAirsoftTeam::None)
		{
			NeutralStarts.Add(Start);
		}
		else if (StartTeam == Team)
		{
			TeamStarts.Add(Start);
		}
	}
	const TArray<APlayerStart*>& Pool = bMatch
		? (TeamStarts.Num() > 0 ? TeamStarts : (NeutralStarts.Num() > 0 ? NeutralStarts : AllStarts))
		: (NeutralStarts.Num() > 0 ? NeutralStarts : AllStarts);
	if (Pool.Num() == 0)
	{
		return Super::ChoosePlayerStart_Implementation(Player);
	}

	// Furthest from live enemies, never on top of someone, with a little randomness.
	APlayerStart* Best = nullptr;
	float BestScore = -MAX_flt;
	for (APlayerStart* Start : Pool)
	{
		const FVector Loc = Start->GetActorLocation();
		float NearestEnemy = 6000.f;
		bool bOccupied = false;
		for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
		{
			const AAirsoftCharacter* Other = *It;
			if (!Other || Other->GetController() == Player)
			{
				continue;
			}
			const float Dist = FVector::Dist(Other->GetActorLocation(), Loc);
			if (Dist < 110.f)
			{
				bOccupied = true;
			}
			if (!Other->IsOut() && Other->GetTeam() != Team)
			{
				NearestEnemy = FMath::Min(NearestEnemy, Dist);
			}
		}
		const float Score = NearestEnemy + FMath::FRandRange(0.f, 500.f) - (bOccupied ? 100000.f : 0.f);
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = Start;
		}
	}
	return Best;
}

void AAirsoftGameMode::SetPlayerDefaults(APawn* PlayerPawn)
{
	Super::SetPlayerDefaults(PlayerPawn);
	AAirsoftCharacter* C = Cast<AAirsoftCharacter>(PlayerPawn);
	AAirsoftPlayerState* PS = C ? C->GetAirsoftPlayerState() : nullptr;
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!C || !PS || !GS)
	{
		return;
	}
	PS->bOut = false;
	PS->RespawnAt = 0.f;
	C->GetCombat()->ServerInitLoadout(PS->Loadout);
	const bool bLive = GS->bIsMatchMap && GS->Phase == EAirsoftPhase::Live;
	PS->ProtectedUntil = bLive ? GS->GetServerWorldTimeSeconds() + UAirsoftSettings::Get()->SpawnProtection : 0.f;
	C->ServerSetFrozen(GS->bIsMatchMap && IsFrozenPhase(GS->Phase));
	C->ApplyTeamLook();
}

void AAirsoftGameMode::ScheduleRespawn(AController* Controller, float Delay)
{
	if (!Controller)
	{
		return;
	}
	FTimerHandle& Handle = RespawnTimers.FindOrAdd(Controller);
	TWeakObjectPtr<AController> Weak(Controller);
	GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, Weak]()
	{
		if (Weak.IsValid())
		{
			Respawn(Weak.Get());
		}
	}), FMath::Max(Delay, 0.1f), false);
}

void AAirsoftGameMode::Respawn(AController* Controller)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!Controller || !GS || bTravelling)
	{
		return;
	}
	if (GS->bIsMatchMap && GS->Phase == EAirsoftPhase::PostRound)
	{
		return;
	}
	if (APawn* Old = Controller->GetPawn())
	{
		Controller->UnPossess();
		Old->Destroy();
	}
	RestartPlayer(Controller);
}

// ---------------------------------------------------------------------------
// Teams and votes
// ---------------------------------------------------------------------------

EAirsoftTeam AAirsoftGameMode::SmallerTeam() const
{
	int32 Blue = 0;
	int32 Red = 0;
	if (const AAirsoftGameState* GS = GetAirsoftGameState())
	{
		for (APlayerState* P : GS->PlayerArray)
		{
			if (const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
			{
				Blue += PS->Team == EAirsoftTeam::Blue ? 1 : 0;
				Red += PS->Team == EAirsoftTeam::Red ? 1 : 0;
			}
		}
	}
	if (Blue != Red)
	{
		return Blue < Red ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
	}
	return FMath::RandBool() ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
}

void AAirsoftGameMode::AssignTeam(AAirsoftPlayerState* PS)
{
	if (PS)
	{
		PS->Team = EAirsoftTeam::None; // don't count ourselves
		PS->Team = SmallerTeam();
	}
}

void AAirsoftGameMode::BalanceTeams()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	TArray<AAirsoftPlayerState*> Blue;
	TArray<AAirsoftPlayerState*> Red;
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			if (PS->Team == EAirsoftTeam::None)
			{
				PS->Team = Blue.Num() <= Red.Num() ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
			}
			(PS->Team == EAirsoftTeam::Blue ? Blue : Red).Add(PS);
		}
	}
	while (FMath::Abs(Blue.Num() - Red.Num()) >= 2)
	{
		TArray<AAirsoftPlayerState*>& From = Blue.Num() > Red.Num() ? Blue : Red;
		TArray<AAirsoftPlayerState*>& To = Blue.Num() > Red.Num() ? Red : Blue;
		const int32 Index = FMath::RandRange(0, From.Num() - 1);
		AAirsoftPlayerState* Moved = From[Index];
		From.RemoveAt(Index);
		Moved->Team = (&To == &Blue) ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
		To.Add(Moved);
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(Moved->GetOwningController()))
		{
			PC->ClientAnnounce(TEXT("TEAMS BALANCED"), FString::Printf(TEXT("You're on %s"), *AirsoftColors::TeamName(Moved->Team)), AirsoftColors::Team(Moved->Team), 3.f);
		}
	}
}

void AAirsoftGameMode::SwitchTeam(AAirsoftPlayerController* PC)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!GS || !PS || GS->bIsMatchMap)
	{
		return;
	}
	PS->Team = PS->Team == EAirsoftTeam::Blue ? EAirsoftTeam::Red : EAirsoftTeam::Blue;
	if (AAirsoftCharacter* C = Cast<AAirsoftCharacter>(PC->GetPawn()))
	{
		C->ApplyTeamLook();
	}
	PC->ClientAnnounce(AirsoftColors::TeamName(PS->Team).ToUpper(), TEXT("Team switched"), AirsoftColors::Team(PS->Team), 2.f);
}

void AAirsoftGameMode::OnVotesChanged()
{
	RecountVotes();
}

void AAirsoftGameMode::RecountVotes()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	TArray<int32> Modes;
	TArray<int32> Maps;
	Modes.Init(0, 2);
	Maps.Init(0, AAirsoftGameState::MapIds().Num());
	for (APlayerState* P : GS->PlayerArray)
	{
		const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (!PS || !IsValid(PS) || PS->IsActorBeingDestroyed() || PS->IsInactive())
		{
			continue;
		}
		if (Modes.IsValidIndex(PS->ModeVote))
		{
			++Modes[PS->ModeVote];
		}
		if (Maps.IsValidIndex(PS->MapVote))
		{
			++Maps[PS->MapVote];
		}
	}
	if (GS->ModeVotes != Modes)
	{
		GS->ModeVotes = Modes;
	}
	if (GS->MapVotes != Maps)
	{
		GS->MapVotes = Maps;
	}
}

void AAirsoftGameMode::OnLoadoutChanged(AAirsoftPlayerController* PC)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	AAirsoftCharacter* C = PC ? Cast<AAirsoftCharacter>(PC->GetPawn()) : nullptr;
	if (!GS || !PS || !C || C->IsOut())
	{
		return;
	}
	// In the staging area and before a round goes live the change is instant.
	if (!GS->bIsMatchMap || GS->Phase != EAirsoftPhase::Live)
	{
		C->GetCombat()->ServerInitLoadout(PS->Loadout);
	}
}

void AAirsoftGameMode::ForceStart(AAirsoftPlayerController* Requester)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || !Requester || !Requester->IsLocalController() || GS->bIsMatchMap || bTravelling)
	{
		return;
	}
	bForceStarted = true;
	SetPhase(EAirsoftPhase::Intermission, 5.f);
	AnnounceAll(TEXT("HOST IS STARTING"), TEXT("Deploying in 5 seconds"), AirsoftColors::Accent(), 3.f);
}

// ---------------------------------------------------------------------------
// Phases
// ---------------------------------------------------------------------------

void AAirsoftGameMode::SetPhase(EAirsoftPhase NewPhase, float Duration)
{
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		GS->Phase = NewPhase;
		GS->PhaseEndsAt = Duration > 0.f ? GS->GetServerWorldTimeSeconds() + Duration : 0.f;
	}
}

void AAirsoftGameMode::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || bTravelling)
	{
		return;
	}
	if (GS->bIsMatchMap)
	{
		TickMatch(DeltaSeconds);
	}
	else
	{
		TickStaging(DeltaSeconds);
	}
}

void AAirsoftGameMode::TickStaging(float DeltaSeconds)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	const UAirsoftSettings* S = UAirsoftSettings::Get();
	const int32 Players = CountPlayers();
	RecountVotes();

	if (GS->Phase == EAirsoftPhase::Waiting)
	{
		GS->StatusMessage = FString::Printf(TEXT("Waiting for players  %d / %d"), Players, S->MinPlayers);
		if (Players >= S->MinPlayers)
		{
			SetPhase(EAirsoftPhase::Intermission, S->IntermissionTime);
			AnnounceAll(TEXT("SQUAD UP"), TEXT("Vote for the next match. Deploying soon."), AirsoftColors::Accent(), 4.f);
		}
	}
	else if (GS->Phase == EAirsoftPhase::Intermission)
	{
		if (Players < S->MinPlayers && !bForceStarted)
		{
			SetPhase(EAirsoftPhase::Waiting, 0.f);
			return;
		}
		GS->StatusMessage = TEXT("Vote now  ·  F1 TDM  ·  F2 Domination  ·  F3 Ironwood Yard  ·  F4 Velvet Club");
		if (GS->GetTimeRemaining() <= 0.f)
		{
			TravelToMatch();
		}
	}
	else
	{
		SetPhase(EAirsoftPhase::Waiting, 0.f);
	}
}

void AAirsoftGameMode::TravelToMatch()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	const UAirsoftSettings* S = UAirsoftSettings::Get();
	RecountVotes();
	const EAirsoftMode Mode = PickVote(GS->ModeVotes) == 1 ? EAirsoftMode::Domination : EAirsoftMode::TDM;
	const TArray<FName>& Ids = AAirsoftGameState::MapIds();
	const int32 MapIndex = PickVote(GS->MapVotes);
	const FName MapId = Ids.IsValidIndex(MapIndex) ? Ids[MapIndex] : Ids[0];
	const FString* Path = S->MatchMaps.Find(MapId);
	if (!Path || Path->IsEmpty())
	{
		GS->StatusMessage = TEXT("Match map missing - run the setup script");
		SetPhase(EAirsoftPhase::Waiting, 0.f);
		return;
	}
	bTravelling = true;
	BalanceTeams();
	GS->StatusMessage = TEXT("Deploying...");
	AnnounceAll(TEXT("DEPLOYING"), FString::Printf(TEXT("%s  ·  %s"), *AAirsoftGameState::ModeDisplayName(Mode), *AAirsoftGameState::MapDisplayName(MapId)), AirsoftColors::Accent(), 3.f);

	const FString URL = FString::Printf(TEXT("%s?Mode=%s"), **Path, Mode == EAirsoftMode::Domination ? TEXT("Domination") : TEXT("TDM"));
	FTimerHandle Handle;
	GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, URL]()
	{
		GetWorld()->ServerTravel(URL, false, false);
	}), 2.f, false);
}

void AAirsoftGameMode::TickMatch(float DeltaSeconds)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	switch (GS->Phase)
	{
	case EAirsoftPhase::Waiting:
	case EAirsoftPhase::Intermission:
		GS->StatusMessage = TEXT("Squad loading in...");
		if (NumTravellingPlayers <= 0 || GetWorld()->GetTimeSeconds() - WaitingSince > MaxLoadWait)
		{
			BeginBriefing();
		}
		break;

	case EAirsoftPhase::Briefing:
		if (GS->GetTimeRemaining() <= 0.f)
		{
			BeginLive();
		}
		break;

	case EAirsoftPhase::Live:
		if (GS->Mode == EAirsoftMode::Domination)
		{
			TickDomination(DeltaSeconds);
		}
		if (GS->Phase == EAirsoftPhase::Live && GS->GetTimeRemaining() <= 0.f)
		{
			const EAirsoftTeam Winner = GS->BlueScore == GS->RedScore ? EAirsoftTeam::None
				: (GS->BlueScore > GS->RedScore ? EAirsoftTeam::Blue : EAirsoftTeam::Red);
			EndRound(Winner);
		}
		break;

	case EAirsoftPhase::PostRound:
		if (GS->GetTimeRemaining() <= 0.f)
		{
			ReturnToStaging();
		}
		break;
	}
}

void AAirsoftGameMode::BeginBriefing()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	const UAirsoftSettings* S = UAirsoftSettings::Get();
	BalanceTeams();
	GS->BlueScore = 0;
	GS->RedScore = 0;
	GS->Winner = EAirsoftTeam::None;
	GS->StatusMessage = TEXT("Briefing");
	LastTag = FAirsoftFinalTag();
	DominationScoreClock = 0.f;
	for (AAirsoftObjective* Obj : GS->Objectives)
	{
		if (Obj)
		{
			Obj->ServerReset(GS->Mode == EAirsoftMode::Domination);
		}
	}
	SetPhase(EAirsoftPhase::Briefing, S->BriefingTime);

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get());
		AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
		if (!PC || !PS)
		{
			continue;
		}
		PS->ResetRound();
		PC->ClientResetForNewRound();
		Respawn(PC); // everyone starts at their own team's spawn, frozen
		PC->ClientAnnounce(AAirsoftGameState::ModeDisplayName(GS->Mode).ToUpper(),
			FString::Printf(TEXT("%s  ·  You're on %s  ·  %s"), *AAirsoftGameState::MapDisplayName(GS->MapId), *AirsoftColors::TeamName(PS->Team), *AAirsoftGameState::ModeBlurb(GS->Mode)),
			AirsoftColors::Team(PS->Team), S->BriefingTime);
	}
	FreezeAll(true);
}

void AAirsoftGameMode::BeginLive()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	SetPhase(EAirsoftPhase::Live, UAirsoftSettings::Get()->RoundTime);
	GS->StatusMessage.Reset();
	FreezeAll(false);
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			PS->ProtectedUntil = 0.f;
		}
	}
	AnnounceAll(TEXT("GAME ON"), GS->Mode == EAirsoftMode::Domination ? TEXT("Take the points") : TEXT("Call your hits"), AirsoftColors::Accent(), 2.5f);
}

void AAirsoftGameMode::TickDomination(float DeltaSeconds)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	TArray<AAirsoftCharacter*> Alive;
	for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
	{
		if (!It->IsOut() && It->GetTeam() != EAirsoftTeam::None)
		{
			Alive.Add(*It);
		}
	}

	for (AAirsoftObjective* Obj : GS->Objectives)
	{
		if (!Obj || !Obj->bActive)
		{
			continue;
		}
		int32 Blue = 0;
		int32 Red = 0;
		TArray<AAirsoftCharacter*> Inside;
		for (AAirsoftCharacter* C : Alive)
		{
			if (Obj->IsInside(C->GetActorLocation()))
			{
				Inside.Add(C);
				Blue += C->GetTeam() == EAirsoftTeam::Blue ? 1 : 0;
				Red += C->GetTeam() == EAirsoftTeam::Red ? 1 : 0;
			}
		}
		const EAirsoftTeam Taken = Obj->ServerUpdate(DeltaSeconds, Blue, Red, CaptureTime);
		if (Taken != EAirsoftTeam::None)
		{
			for (AAirsoftCharacter* C : Inside)
			{
				if (C->GetTeam() == Taken)
				{
					if (AAirsoftPlayerState* PS = C->GetAirsoftPlayerState())
					{
						PS->Round.Captures++;
					}
					GiveXP(C->GetController(), 150, FString::Printf(TEXT("CAPTURED %s"), *Obj->Letter));
				}
			}
			AnnounceAll(FString::Printf(TEXT("%s SECURED"), *Obj->Letter), AirsoftColors::TeamName(Taken), AirsoftColors::Team(Taken), 2.f);
		}
	}

	DominationScoreClock += DeltaSeconds;
	while (DominationScoreClock >= 1.f)
	{
		DominationScoreClock -= 1.f;
		for (const AAirsoftObjective* Obj : GS->Objectives)
		{
			if (Obj && Obj->bActive)
			{
				GS->BlueScore += Obj->OwnerTeam == EAirsoftTeam::Blue ? 1 : 0;
				GS->RedScore += Obj->OwnerTeam == EAirsoftTeam::Red ? 1 : 0;
			}
		}
	}
	if (GS->BlueScore >= GS->ScoreLimit || GS->RedScore >= GS->ScoreLimit)
	{
		EndRound(GS->BlueScore == GS->RedScore ? EAirsoftTeam::None : (GS->BlueScore > GS->RedScore ? EAirsoftTeam::Blue : EAirsoftTeam::Red));
	}
}

void AAirsoftGameMode::EndRound(EAirsoftTeam Winner)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->Phase == EAirsoftPhase::PostRound)
	{
		return;
	}
	SetPhase(EAirsoftPhase::PostRound, UAirsoftSettings::Get()->PostRoundTime);
	GS->Winner = Winner;
	GS->StatusMessage = Winner == EAirsoftTeam::None ? TEXT("Draw") : FString::Printf(TEXT("%s wins"), *AirsoftColors::TeamName(Winner));
	FreezeAll(true);
	for (TPair<TWeakObjectPtr<AController>, FTimerHandle>& Pair : RespawnTimers)
	{
		GetWorldTimerManager().ClearTimer(Pair.Value);
	}
	RespawnTimers.Reset();

	// Match bonus XP first so the report includes it.
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			const int32 Bonus = Winner == EAirsoftTeam::None ? 250 : (PS->Team == Winner ? 500 : 200);
			GiveXP(PS->GetOwningController(), Bonus, Winner == EAirsoftTeam::None ? TEXT("DRAW") : (PS->Team == Winner ? TEXT("VICTORY") : TEXT("MATCH COMPLETE")));
		}
	}

	TArray<FAirsoftSummaryRow> Rows;
	for (APlayerState* P : GS->PlayerArray)
	{
		if (const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			FAirsoftSummaryRow Row;
			Row.Name = PS->GetPlayerName();
			Row.Team = PS->Team;
			Row.Stats = PS->Round;
			Rows.Add(Row);
		}
	}
	Rows.Sort([](const FAirsoftSummaryRow& A, const FAirsoftSummaryRow& B) { return A.Stats.XP > B.Stats.XP; });

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get());
		const AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
		if (PC && PS)
		{
			PC->ClientMatchEnded(Winner, Rows, LastTag, PS->Round.XP, PS->Round.Captures);
		}
	}
}

void AAirsoftGameMode::ReturnToStaging()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	bTravelling = true;
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			PS->CareerXP += PS->Round.XP;
			PS->ResetRound();
		}
	}
	GS->StatusMessage = TEXT("Returning to staging...");
	GetWorld()->ServerTravel(UAirsoftSettings::Get()->StagingMap, false, false);
}

void AAirsoftGameMode::FreezeAll(bool bFreeze)
{
	for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
	{
		It->ServerSetFrozen(bFreeze);
	}
}

// ---------------------------------------------------------------------------
// Tags and grenades
// ---------------------------------------------------------------------------

bool AAirsoftGameMode::HandleTag(AController* Shooter, AController* Victim, FName WeaponId)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || !GS->bIsMatchMap || GS->Phase != EAirsoftPhase::Live || !Victim || Shooter == Victim)
	{
		return false;
	}
	AAirsoftCharacter* VictimChar = Cast<AAirsoftCharacter>(Victim->GetPawn());
	AAirsoftPlayerState* VictimPS = Victim->GetPlayerState<AAirsoftPlayerState>();
	AAirsoftPlayerState* ShooterPS = Shooter ? Shooter->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!VictimChar || !VictimPS || VictimChar->IsOut() || VictimPS->IsProtected())
	{
		return false;
	}
	const bool bSameTeam = ShooterPS && ShooterPS->Team == VictimPS->Team;
	if (bSameTeam && !UAirsoftSettings::Get()->bFriendlyFire)
	{
		return false;
	}

	const UAirsoftSettings* S = UAirsoftSettings::Get();
	const FString ShooterName = ShooterPS ? ShooterPS->GetPlayerName() : FString(TEXT("Grenade"));
	const int32 VictimStreak = VictimPS->Round.Streak;

	VictimChar->ServerMarkOut(ShooterName);
	VictimPS->LastTaggedBy = ShooterName;
	VictimPS->Round.Outs++;
	VictimPS->Round.Streak = 0;
	VictimPS->RespawnAt = GS->GetServerWorldTimeSeconds() + S->RespawnTime;

	const APawn* ShooterPawn = Shooter ? Shooter->GetPawn() : nullptr;
	if (ShooterPS && !bSameTeam)
	{
		ShooterPS->Round.Tags++;
		ShooterPS->Round.Streak++;
		const bool bGrenade = WeaponId == TEXT("Grenade");
		GiveXP(Shooter, bGrenade ? 125 : 100, bGrenade ? TEXT("GRENADE TAG") : TEXT("TAG"));
		if (ShooterPawn && FVector::Dist(ShooterPawn->GetActorLocation(), VictimChar->GetActorLocation()) > 4000.f)
		{
			GiveXP(Shooter, 50, TEXT("LONG SHOT"));
		}
		const int32 Streak = ShooterPS->Round.Streak;
		if (Streak == 3 || Streak == 5 || Streak == 8 || Streak == 12)
		{
			GiveXP(Shooter, Streak * 20, FString::Printf(TEXT("STREAK x%d"), Streak));
		}
		if (VictimStreak >= 3)
		{
			GiveXP(Shooter, 75, TEXT("STREAK ENDED"));
		}
		if (GS->Mode == EAirsoftMode::TDM)
		{
			GS->BlueScore += ShooterPS->Team == EAirsoftTeam::Blue ? 1 : 0;
			GS->RedScore += ShooterPS->Team == EAirsoftTeam::Red ? 1 : 0;
		}
	}

	LastTag.bValid = true;
	LastTag.Shooter = ShooterName;
	LastTag.Victim = VictimPS->GetPlayerName();
	LastTag.ShooterTeam = ShooterPS ? ShooterPS->Team : EAirsoftTeam::None;
	LastTag.VictimTeam = VictimPS->Team;
	LastTag.To = VictimChar->GetActorLocation() + FVector(0.f, 0.f, 40.f);
	LastTag.From = ShooterPawn ? ShooterPawn->GetPawnViewLocation() : LastTag.To + FVector(-300.f, 0.f, 100.f);
	LastTag.WeaponId = WeaponId;

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientKillFeed(ShooterName, LastTag.ShooterTeam, LastTag.Victim, LastTag.VictimTeam, WeaponId);
		}
	}

	ScheduleRespawn(Victim, S->RespawnTime);

	if (GS->Mode == EAirsoftMode::TDM && (GS->BlueScore >= GS->ScoreLimit || GS->RedScore >= GS->ScoreLimit))
	{
		EndRound(GS->BlueScore >= GS->ScoreLimit ? EAirsoftTeam::Blue : EAirsoftTeam::Red);
	}
	return true;
}

void AAirsoftGameMode::SpawnGrenade(AController* Thrower, const FVector& Origin, const FVector& Direction)
{
	APawn* Pawn = Thrower ? Thrower->GetPawn() : nullptr;
	const AAirsoftPlayerState* PS = Thrower ? Thrower->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	const FVector Dir = Direction.GetSafeNormal();
	const FTransform SpawnTransform(Dir.Rotation(), Origin + Dir * 45.f);
	AAirsoftGrenade* Grenade = GetWorld()->SpawnActorDeferred<AAirsoftGrenade>(AAirsoftGrenade::StaticClass(), SpawnTransform, Thrower, Pawn, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (Grenade)
	{
		const FVector Inherit = Pawn ? Pawn->GetVelocity() * 0.5f : FVector::ZeroVector;
		Grenade->Init(Thrower, PS ? PS->Team : EAirsoftTeam::None, Dir * AirsoftWeapons::GrenadeThrowSpeed + Inherit);
		Grenade->FinishSpawning(SpawnTransform);
	}
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

int32 AAirsoftGameMode::CountPlayers() const
{
	return GetNumPlayers();
}

void AAirsoftGameMode::AnnounceAll(const FString& Title, const FString& Sub, const FLinearColor& Color, float Duration)
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientAnnounce(Title, Sub, Color, Duration);
		}
	}
}

void AAirsoftGameMode::GiveXP(AController* Controller, int32 Amount, const FString& Reason)
{
	AAirsoftPlayerState* PS = Controller ? Controller->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!PS || Amount <= 0)
	{
		return;
	}
	PS->Round.XP += Amount;
	if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(Controller))
	{
		PC->ClientXP(Amount, Reason);
	}
}

// ---------------------------------------------------------------------------

AAirsoftMenuGameMode::AAirsoftMenuGameMode()
{
	DefaultPawnClass = nullptr;
	PlayerControllerClass = AAirsoftPlayerController::StaticClass();
	PlayerStateClass = AAirsoftPlayerState::StaticClass();
	GameStateClass = AAirsoftGameState::StaticClass();
}
