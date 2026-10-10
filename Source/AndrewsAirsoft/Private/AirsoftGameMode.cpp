#include "AirsoftGameMode.h"

#include "AirsoftBotController.h"
#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftGrenade.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
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
	constexpr float DominationCaptureTime = 8.f;
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

namespace AirsoftBotNames
{
	/** Original call signs for bots (rain, sodium light and back alleys). */
	const TArray<FString>& CallSigns()
	{
		static const TArray<FString> Names = {
			TEXT("Sodium"), TEXT("Rainline"), TEXT("Coldwire"), TEXT("Neon Hush"), TEXT("Gutter Halo"),
			TEXT("Brass Lantern"), TEXT("Low Tide"), TEXT("Kerbside"), TEXT("Dusk Relay"), TEXT("Glasswork"),
			TEXT("Signal Nine"), TEXT("Overpass"), TEXT("Tin Saint"), TEXT("Velvet Fuse"), TEXT("Ember Docket"),
			TEXT("Rust Choir"), TEXT("Lamplight"), TEXT("Cinder Grid"), TEXT("Static Bloom"), TEXT("Fogbank"),
			TEXT("Sable Key"), TEXT("Graveshift"), TEXT("Halogen"), TEXT("Moth Signal"), TEXT("Downpour"),
			TEXT("Cobalt Nine"), TEXT("Red Ledger"), TEXT("Ash Meridian"), TEXT("Underpass"), TEXT("Quiet Meter"),
			TEXT("Wet Asphalt"), TEXT("Ninefold")
		};
		return Names;
	}

	/** Primary weapon weights for bot loadouts: open field vs. close quarters (Velvet Club). */
	struct FPrimaryWeight
	{
		const TCHAR* Id;
		int32 Field;
		int32 CloseQuarters;
	};

	const TArray<FPrimaryWeight>& PrimaryWeights()
	{
		static const TArray<FPrimaryWeight> Weights = {
			{ TEXT("M4"), 4, 2 }, { TEXT("AK74"), 4, 2 }, { TEXT("SR25"), 2, 1 }, { TEXT("VSR"), 1, 0 },
			{ TEXT("M249"), 1, 1 }, { TEXT("MP5"), 2, 3 }, { TEXT("VECTOR"), 2, 3 }, { TEXT("MP7"), 2, 3 },
			{ TEXT("P90"), 2, 3 }, { TEXT("M870"), 1, 2 }
		};
		return Weights;
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
	bBotsDirty = true; // a bot on the newcomer's team makes room
}

void AAirsoftGameMode::Logout(AController* Exiting)
{
	if (FTimerHandle* Handle = RespawnTimers.Find(Exiting))
	{
		GetWorldTimerManager().ClearTimer(*Handle);
		RespawnTimers.Remove(Exiting);
	}
	if (AAirsoftBotController* Bot = Cast<AAirsoftBotController>(Exiting))
	{
		Bots.Remove(Bot);
	}
	else if (Cast<APlayerController>(Exiting))
	{
		bBotsDirty = true; // a person left: top the bots back up (next tick, not from inside Logout)
	}
	Super::Logout(Exiting);
	RecountVotes();
}

void AAirsoftGameMode::GetSeamlessTravelActorList(bool bToTransition, TArray<AActor*>& ActorList)
{
	Super::GetSeamlessTravelActorList(bToTransition, ActorList);
	// The base class keeps every PlayerState so people stay on their teams. Bots are rebuilt on every
	// match map, so their PlayerStates (whose controllers don't travel) must not tag along.
	ActorList.RemoveAll([](const AActor* Actor)
	{
		const APlayerState* PS = Cast<APlayerState>(Actor);
		return (PS && PS->IsABot()) || Cast<AAirsoftBotController>(Actor) != nullptr;
	});
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
	float BestScore = -TNumericLimits<float>::Max();
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
	PS->ProtectedUntil = bLive ? static_cast<float>(GS->GetServerWorldTimeSeconds()) + UAirsoftSettings::Get()->SpawnProtection : 0.f;
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
	int32 BlueHumans = 0;
	int32 RedHumans = 0;
	if (const AAirsoftGameState* GS = GetAirsoftGameState())
	{
		for (APlayerState* P : GS->PlayerArray)
		{
			if (const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
			{
				Blue += PS->Team == EAirsoftTeam::Blue ? 1 : 0;
				Red += PS->Team == EAirsoftTeam::Red ? 1 : 0;
				if (!PS->IsABot())
				{
					BlueHumans += PS->Team == EAirsoftTeam::Blue ? 1 : 0;
					RedHumans += PS->Team == EAirsoftTeam::Red ? 1 : 0;
				}
			}
		}
	}
	// People are spread evenly first (bots fill in around them), then by head count.
	if (BlueHumans != RedHumans)
	{
		return BlueHumans < RedHumans ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
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
			if (PS->IsABot())
			{
				continue; // only people are balanced; UpdateBots refills the bots around them
			}
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
	// Practising alone with bots off would be an empty field: point at the switch.
	int32 BotTeamSize = 0;
	EAirsoftBotSkill BotSkill = EAirsoftBotSkill::Normal;
	GetBotSettings(BotTeamSize, BotSkill);
	const bool bAloneWithoutBots = BotTeamSize == 0 && CountPlayers() <= 1;
	AnnounceAll(TEXT("HOST IS STARTING"), bAloneWithoutBots ? TEXT("Deploying in 5 seconds  ·  bots are off (Menu > Bots)") : TEXT("Deploying in 5 seconds"),
		AirsoftColors::Accent(), 3.f);
}

// ---------------------------------------------------------------------------
// Phases
// ---------------------------------------------------------------------------

void AAirsoftGameMode::SetPhase(EAirsoftPhase NewPhase, float Duration)
{
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		GS->Phase = NewPhase;
		GS->PhaseEndsAt = Duration > 0.f ? static_cast<float>(GS->GetServerWorldTimeSeconds()) + Duration : 0.f;
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
	// People only: bots never count toward starting the vote (and only exist on match maps).
	const int32 Players = CountPlayers();
	RecountVotes();
	if (Bots.Num() > 0)
	{
		RemoveAllBots();
	}

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
	if (GS->Phase == EAirsoftPhase::Briefing || GS->Phase == EAirsoftPhase::Live)
	{
		// Keep the bot count right as people join, leave or the host changes the setting.
		BotClock += DeltaSeconds;
		if (bBotsDirty || BotClock >= 1.f)
		{
			BotClock = 0.f;
			bBotsDirty = false;
			UpdateBots();
		}
	}
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
	// Bots already here start over too; then fill both sides up around the people (new bots spawn frozen).
	const TArray<TObjectPtr<AAirsoftBotController>> ExistingBots = Bots;
	for (AAirsoftBotController* Bot : ExistingBots)
	{
		if (AAirsoftPlayerState* BotPS = IsValid(Bot) ? Bot->GetPlayerState<AAirsoftPlayerState>() : nullptr)
		{
			BotPS->ResetRound();
			Respawn(Bot);
		}
	}
	bBotsDirty = false;
	BotClock = 0.f;
	UpdateBots();
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
		const EAirsoftTeam Taken = Obj->ServerUpdate(DeltaSeconds, Blue, Red, DominationCaptureTime);
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
			Row.bBot = PS->IsABot();
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
	// Bots are server-only and made fresh on each match map: never carry them (or their PlayerStates) over.
	RemoveAllBots();
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
	VictimPS->RespawnAt = static_cast<float>(GS->GetServerWorldTimeSeconds()) + S->RespawnTime;

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

int32 AAirsoftGameMode::CountPlayers()
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
// Bots
// ---------------------------------------------------------------------------

void AAirsoftGameMode::NotifyShotFired(AAirsoftCharacter* Shooter, const FVector& Origin, const FVector& Direction, bool bQuiet)
{
	for (AAirsoftBotController* Bot : Bots)
	{
		if (IsValid(Bot))
		{
			Bot->HearShot(Shooter, Origin, Direction, bQuiet);
		}
	}
}

void AAirsoftGameMode::GetBotSettings(int32& OutTeamSize, EAirsoftBotSkill& OutSkill) const
{
	// Listen server: the host's own saved settings decide (clients' settings never reach here).
	OutTeamSize = 0;
	OutSkill = EAirsoftBotSkill::Normal;
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		const FAirsoftUserSettings& Settings = GI->GetUserSettings();
		OutTeamSize = AirsoftBots::TeamSize(Settings.BotFill);
		OutSkill = AirsoftBots::SkillFromIndex(Settings.BotSkill);
	}
}

void AAirsoftGameMode::UpdateBots()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || bTravelling)
	{
		return;
	}
	Bots.RemoveAll([](const TObjectPtr<AAirsoftBotController>& Bot) { return !IsValid(Bot); });
	int32 TeamSize = 0;
	EAirsoftBotSkill Skill = EAirsoftBotSkill::Normal;
	GetBotSettings(TeamSize, Skill);
	if (!GS->bIsMatchMap)
	{
		TeamSize = 0;
	}

	// People per side, and the bots we already have per side.
	int32 Humans[2] = { 0, 0 };
	TArray<AAirsoftBotController*> TeamBots[2];
	for (APlayerState* P : GS->PlayerArray)
	{
		const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (!IsValid(PS) || PS->IsABot() || PS->IsInactive())
		{
			continue;
		}
		Humans[0] += PS->Team == EAirsoftTeam::Blue ? 1 : 0;
		Humans[1] += PS->Team == EAirsoftTeam::Red ? 1 : 0;
	}
	for (AAirsoftBotController* Bot : Bots)
	{
		const AAirsoftPlayerState* BotPS = Bot->GetPlayerState<AAirsoftPlayerState>();
		TeamBots[(BotPS && BotPS->Team == EAirsoftTeam::Red) ? 1 : 0].Add(Bot);
	}

	// Both sides end up with max(fill size, people on the bigger side): even teams, bots make up the gap.
	const int32 Side = TeamSize > 0 ? FMath::Max3(TeamSize, Humans[0], Humans[1]) : 0;
	for (int32 Index = 0; Index < 2; ++Index)
	{
		const EAirsoftTeam Team = Index == 0 ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
		const int32 Want = FMath::Max(0, Side - Humans[Index]);
		TArray<AAirsoftBotController*>& Have = TeamBots[Index];
		while (Have.Num() > Want)
		{
			// Remove a tagged-out (or pawnless) bot first so nobody vanishes mid-fight.
			int32 Pick = Have.Num() - 1;
			for (int32 i = 0; i < Have.Num(); ++i)
			{
				const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(Have[i]->GetPawn());
				if (!C || C->IsOut())
				{
					Pick = i;
					break;
				}
			}
			AAirsoftBotController* Leaving = Have[Pick];
			Have.RemoveAt(Pick);
			RemoveBot(Leaving);
		}
		while (Have.Num() < Want)
		{
			AAirsoftBotController* Added = AddBot(Team, Skill);
			if (!Added)
			{
				break;
			}
			Have.Add(Added);
		}
	}

	// Difficulty changes apply straight away; keep call signs clear of people's names.
	TSet<FString> HumanNames;
	for (APlayerState* P : GS->PlayerArray)
	{
		if (IsValid(P) && !P->IsABot())
		{
			HumanNames.Add(P->GetPlayerName().ToLower());
		}
	}
	for (AAirsoftBotController* Bot : Bots)
	{
		if (!IsValid(Bot))
		{
			continue;
		}
		Bot->SetSkill(Skill);
		APlayerState* BotPS = Bot->GetPlayerState<APlayerState>();
		if (BotPS && HumanNames.Contains(BotPS->GetPlayerName().ToLower()))
		{
			BotPS->SetPlayerName(MakeBotName());
		}
	}
}

AAirsoftBotController* AAirsoftGameMode::AddBot(EAirsoftTeam Team, EAirsoftBotSkill Skill)
{
	UWorld* World = GetWorld();
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!World || !GS || Team == EAirsoftTeam::None)
	{
		return nullptr;
	}
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Params.ObjectFlags |= RF_Transient; // never saved into a map
	AAirsoftBotController* Bot = World->SpawnActor<AAirsoftBotController>(AAirsoftBotController::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Params);
	if (!Bot)
	{
		return nullptr;
	}
	AAirsoftPlayerState* PS = Bot->GetPlayerState<AAirsoftPlayerState>();
	if (!PS)
	{
		Bot->Destroy();
		return nullptr;
	}
	// IsABot() is already true: APlayerState flags itself as a bot when its owner isn't a PlayerController.
	PS->SetPlayerName(MakeBotName());
	PS->Team = Team;
	PS->Loadout = MakeBotLoadout();
	PS->bLoadoutReceived = true;
	PS->CareerXP = 0;
	Bot->SetSkill(Skill);
	Bots.Add(Bot);
	if (GS->bIsMatchMap && (GS->Phase == EAirsoftPhase::Briefing || GS->Phase == EAirsoftPhase::Live))
	{
		RestartPlayer(Bot); // SetPlayerDefaults hands out the loadout, spawn protection and the freeze
	}
	return Bot;
}

void AAirsoftGameMode::RemoveBot(AAirsoftBotController* Bot)
{
	if (!IsValid(Bot))
	{
		return;
	}
	Bots.Remove(Bot);
	if (APawn* BotPawn = Bot->GetPawn())
	{
		Bot->UnPossess();
		BotPawn->Destroy();
	}
	// AController::Destroyed logs the bot out (clears its respawn timer) and destroys its PlayerState.
	Bot->Destroy();
}

void AAirsoftGameMode::RemoveAllBots()
{
	const TArray<TObjectPtr<AAirsoftBotController>> Leaving = Bots;
	for (AAirsoftBotController* Bot : Leaving)
	{
		RemoveBot(Bot);
	}
	Bots.Reset();
}

FString AAirsoftGameMode::MakeBotName() const
{
	TSet<FString> Taken;
	if (const AAirsoftGameState* GS = GetAirsoftGameState())
	{
		for (APlayerState* P : GS->PlayerArray)
		{
			if (IsValid(P))
			{
				Taken.Add(P->GetPlayerName().ToLower());
			}
		}
	}
	const TArray<FString>& Names = AirsoftBotNames::CallSigns();
	const int32 First = FMath::RandRange(0, Names.Num() - 1);
	for (int32 i = 0; i < Names.Num(); ++i)
	{
		const FString& Name = Names[(First + i) % Names.Num()];
		if (!Taken.Contains(Name.ToLower()))
		{
			return Name;
		}
	}
	for (int32 Suffix = 2; Suffix < 100; ++Suffix)
	{
		const FString Name = FString::Printf(TEXT("%s %d"), *Names[First], Suffix);
		if (!Taken.Contains(Name.ToLower()))
		{
			return Name;
		}
	}
	return FString(TEXT("Bot"));
}

FAirsoftLoadout AAirsoftGameMode::MakeBotLoadout() const
{
	// Any legal attachment for each slot the gun has (Clean() then tidies it like a player's loadout).
	auto Kit = [](FName WeaponId)
	{
		FAirsoftCustomization Custom;
		Custom.WeaponId = WeaponId;
		if (const FAirsoftWeaponDef* W = AirsoftWeapons::Find(WeaponId))
		{
			for (const TPair<FName, TArray<FName>>& Option : W->Options)
			{
				if (Option.Value.Num() == 0)
				{
					continue;
				}
				const FName Pick = Option.Value[FMath::RandRange(0, Option.Value.Num() - 1)];
				if (Option.Key == AirsoftWeapons::SlotOptic) { Custom.Optic = Pick; }
				else if (Option.Key == AirsoftWeapons::SlotMuzzle) { Custom.Muzzle = Pick; }
				else if (Option.Key == AirsoftWeapons::SlotGrip) { Custom.Grip = Pick; }
				else if (Option.Key == AirsoftWeapons::SlotLaser) { Custom.Laser = Pick; }
				else if (Option.Key == AirsoftWeapons::SlotMag) { Custom.Mag = Pick; }
			}
		}
		// The plain, early finishes: bots have no rank to unlock the fancy ones.
		const TArray<FAirsoftSkinDef>& Skins = AirsoftWeapons::Skins();
		if (Skins.Num() > 0)
		{
			Custom.Skin = Skins[FMath::RandRange(0, FMath::Min(3, Skins.Num() - 1))].Id;
		}
		return AirsoftWeapons::Clean(Custom);
	};

	const AAirsoftGameState* GS = GetAirsoftGameState();
	const bool bCloseQuarters = GS && GS->MapId == TEXT("Club");
	const TArray<AirsoftBotNames::FPrimaryWeight>& Weights = AirsoftBotNames::PrimaryWeights();
	int32 Total = 0;
	for (const AirsoftBotNames::FPrimaryWeight& Entry : Weights)
	{
		Total += bCloseQuarters ? Entry.CloseQuarters : Entry.Field;
	}
	FName PrimaryId = TEXT("M4");
	int32 Roll = FMath::RandRange(0, FMath::Max(Total - 1, 0));
	for (const AirsoftBotNames::FPrimaryWeight& Entry : Weights)
	{
		Roll -= bCloseQuarters ? Entry.CloseQuarters : Entry.Field;
		if (Roll < 0)
		{
			PrimaryId = Entry.Id;
			break;
		}
	}
	const TArray<FName>& Secondaries = AirsoftWeapons::Secondaries();

	FAirsoftLoadout Loadout;
	Loadout.Primary = Kit(PrimaryId);
	Loadout.Secondary = Kit(Secondaries.Num() > 0 ? Secondaries[FMath::RandRange(0, Secondaries.Num() - 1)] : FName(TEXT("G17")));
	return Loadout;
}

// ---------------------------------------------------------------------------

AAirsoftMenuGameMode::AAirsoftMenuGameMode()
{
	DefaultPawnClass = nullptr;
	PlayerControllerClass = AAirsoftPlayerController::StaticClass();
	PlayerStateClass = AAirsoftPlayerState::StaticClass();
	GameStateClass = AAirsoftGameState::StaticClass();
}
