#include "AirsoftGameMode.h"

#include "AirsoftBotController.h"
#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftGrenade.h"
#include "AirsoftModeRules.h"
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

// Named (not anonymous) so nothing here can collide with other files in a unity build.
namespace AirsoftGameModeLocal
{
	constexpr float DominationCaptureTime = 8.f;
	constexpr float MaxLoadWait = 25.f;
	/** Lobby: a vote is posted in chat once the player stops cycling for this long. */
	constexpr double VoteAnnounceDelay = 1.5;
	constexpr double BotChatterCooldown = 25.0;

	/** Index with the most votes (ties at random); negative entries are not candidates. INDEX_NONE if none. */
	int32 PickVote(const TArray<int32>& Votes)
	{
		int32 Best = -1;
		TArray<int32> Ties;
		for (int32 i = 0; i < Votes.Num(); ++i)
		{
			const int32 V = Votes[i];
			if (V < 0)
			{
				continue;
			}
			if (V > Best)
			{
				Best = V;
				Ties.Reset();
				Ties.Add(i);
			}
			else if (V == Best)
			{
				Ties.Add(i);
			}
		}
		return Ties.Num() > 0 ? Ties[FMath::RandRange(0, Ties.Num() - 1)] : INDEX_NONE;
	}

	bool IsFrozenPhase(EAirsoftPhase Phase)
	{
		return Phase == EAirsoftPhase::Waiting || Phase == EAirsoftPhase::Briefing || Phase == EAirsoftPhase::PostRound;
	}

	EAirsoftTeam OtherTeam(EAirsoftTeam Team)
	{
		return Team == EAirsoftTeam::Blue ? EAirsoftTeam::Red : (Team == EAirsoftTeam::Red ? EAirsoftTeam::Blue : EAirsoftTeam::None);
	}

	/** Grenade rule: none in Gun Game (the ladder decides the weapon), none for the VIP. */
	bool CarriesGrenade(const AAirsoftGameState* GS, const AAirsoftPlayerState* PS)
	{
		if (!GS || !GS->bIsMatchMap)
		{
			return true;
		}
		if (!AirsoftRules::AllowsGrenades(GS->Mode))
		{
			return false;
		}
		return !(GS->Mode == EAirsoftMode::VIP && PS && GS->VIPPlayer.Get() == PS);
	}

	FString WeaponDisplayName(FName WeaponId)
	{
		const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(WeaponId);
		return Def ? Def->Name : WeaponId.ToString();
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

	/** Primary weapon weights for bot loadouts: open field vs. close quarters (Velvet Club, Nightjar Garage). */
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

	/** Short, friendly chat lines. Situation 0: tagged someone (team), 1: got tagged (everyone), 2: round start (team). */
	const TArray<FString>& ChatterLines(int32 Situation)
	{
		static const TArray<FString> Tagged = {
			TEXT("Got one."), TEXT("One down, keep moving."), TEXT("Hit called on mine."), TEXT("Clear here."), TEXT("That lane is ours.")
		};
		static const TArray<FString> Out = {
			TEXT("Good shot."), TEXT("Hit. Fair one."), TEXT("Didn't even see that."), TEXT("Walking off, nice."), TEXT("Ouch. Well placed.")
		};
		static const TArray<FString> Start = {
			TEXT("Moving up."), TEXT("Watch the flanks."), TEXT("Stick together."), TEXT("I'll take the left."), TEXT("Quiet start, eyes open.")
		};
		return Situation == 0 ? Tagged : (Situation == 1 ? Out : Start);
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

	PendingMode = AirsoftRules::ModeFromOption(UGameplayStatics::ParseOption(Options, TEXT("Mode")));

	const FString Current = FPackageName::GetShortName(UWorld::RemovePIEPrefix(MapName));
	bPendingMatchMap = false;
	PendingMapId = NAME_None;
	for (const FAirsoftMapInfo& Info : AirsoftRules::Maps())
	{
		if (!Info.LevelPath.IsEmpty() && FPackageName::GetShortName(Info.LevelPath).Equals(Current, ESearchCase::IgnoreCase))
		{
			bPendingMatchMap = true;
			PendingMapId = Info.Key;
			// Opened directly (e.g. Play-In-Editor) with a mode this map doesn't list: use one it does.
			if (!Info.SupportsMode(PendingMode))
			{
				PendingMode = Info.Modes.Num() > 0 ? Info.Modes[0] : EAirsoftMode::TDM;
			}
			break;
		}
	}
}

void AAirsoftGameMode::InitGameState()
{
	Super::InitGameState();
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		GS->bIsMatchMap = bPendingMatchMap;
		GS->Mode = PendingMode;
		GS->MapId = PendingMapId;
		GS->ScoreLimit = AirsoftRules::ScoreLimit(PendingMode);
		GS->MaxRounds = bPendingMatchMap ? AirsoftRules::MaxRounds(PendingMode) : 0;
		GS->ModeVotes.Init(0, AirsoftRules::NumModes);
		GS->MapVotes.Init(0, AirsoftRules::NumMaps());
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
			Obj->ServerReset(bDomination && !Obj->IsExtractionOnly());
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
		const APlayerState* LeavingPS = Exiting->GetPlayerState<APlayerState>();
		if (LeavingPS && !bTravelling)
		{
			BroadcastSystem(FString::Printf(TEXT("%s left"), *LeavingPS->GetPlayerName()));
		}
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
		const AAirsoftGameState* GS = GetAirsoftGameState();
		if (GS && GS->IsFreeForAll())
		{
			// No teams in a free-for-all; remember the lobby team for the trip back.
			if (PS->Team != EAirsoftTeam::None)
			{
				PS->SavedTeam = PS->Team;
				PS->Team = EAirsoftTeam::None;
			}
		}
		else if (PS->Team == EAirsoftTeam::None)
		{
			AssignTeam(PS);
		}
	}
	Super::HandleStartingNewPlayer_Implementation(NewPlayer);
}

bool AAirsoftGameMode::PlayerCanRestart_Implementation(APlayerController* Player)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (GS && GS->bIsMatchMap && GS->Phase == EAirsoftPhase::Live && !AirsoftRules::HasRespawns(GS->Mode))
	{
		return false; // one life per round: someone joining mid-round watches until the next one
	}
	return Super::PlayerCanRestart_Implementation(Player);
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
	const bool bFreeForAll = GS && GS->IsFreeForAll();

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
	// Free-for-all uses every start on the map (both teams' and any neutral ones).
	const TArray<APlayerStart*>& Pool = bMatch
		? (bFreeForAll ? AllStarts : (TeamStarts.Num() > 0 ? TeamStarts : (NeutralStarts.Num() > 0 ? NeutralStarts : AllStarts)))
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
			const float Dist = static_cast<float>(FVector::Dist(Other->GetActorLocation(), Loc));
			if (Dist < 110.f)
			{
				bOccupied = true;
			}
			if (!Other->IsOut() && (bFreeForAll || Other->GetTeam() != Team))
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
	C->GetCombat()->ServerInitLoadout(GetEffectiveLoadout(PS));
	if (!AirsoftGameModeLocal::CarriesGrenade(GS, PS))
	{
		C->GetCombat()->Grenades = 0;
	}
	const bool bLive = GS->bIsMatchMap && GS->Phase == EAirsoftPhase::Live;
	PS->ProtectedUntil = bLive ? static_cast<float>(GS->GetServerWorldTimeSeconds()) + UAirsoftSettings::Get()->SpawnProtection : 0.f;
	C->ServerSetFrozen(GS->bIsMatchMap && AirsoftGameModeLocal::IsFrozenPhase(GS->Phase));
	C->ApplyTeamLook();
}

FAirsoftLoadout AAirsoftGameMode::GetEffectiveLoadout(const AAirsoftPlayerState* PS) const
{
	if (!PS)
	{
		return AirsoftWeapons::DefaultLoadout();
	}
	FAirsoftLoadout Out = PS->Loadout;
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || !GS->bIsMatchMap)
	{
		return Out;
	}
	// The same gun in both slots, so swapping can't get around the rule.
	auto Single = [](const FAirsoftCustomization& Custom)
	{
		FAirsoftLoadout L;
		L.Primary = AirsoftWeapons::Clean(Custom);
		L.Secondary = L.Primary;
		return L;
	};
	if (GS->Mode == EAirsoftMode::GunGame)
	{
		const TArray<FName> Ladder = AirsoftRules::GunGameLadder();
		if (Ladder.Num() > 0)
		{
			const FName WeaponId = Ladder[FMath::Clamp(PS->GunLevel, 0, Ladder.Num() - 1)];
			// The player's own attachments when the rung is a gun they carry, the gun's defaults otherwise.
			if (PS->Loadout.Primary.WeaponId == WeaponId)
			{
				return Single(PS->Loadout.Primary);
			}
			if (PS->Loadout.Secondary.WeaponId == WeaponId)
			{
				return Single(PS->Loadout.Secondary);
			}
			FAirsoftCustomization Custom;
			Custom.WeaponId = WeaponId;
			Custom.Skin = PS->Loadout.Primary.Skin;
			return Single(Custom);
		}
	}
	else if (GS->Mode == EAirsoftMode::VIP && GS->VIPPlayer.Get() == PS)
	{
		// Pistol only: their own sidearm, or a G17.
		const FAirsoftWeaponDef* Sidearm = AirsoftWeapons::Find(PS->Loadout.Secondary.WeaponId);
		if (Sidearm && Sidearm->Class == TEXT("Pistol"))
		{
			return Single(PS->Loadout.Secondary);
		}
		FAirsoftCustomization Custom;
		Custom.WeaponId = TEXT("G17");
		Custom.Skin = PS->Loadout.Secondary.Skin;
		return Single(Custom);
	}
	return Out;
}

void AAirsoftGameMode::ApplyModeLoadout(AController* Controller)
{
	AAirsoftCharacter* C = Controller ? Cast<AAirsoftCharacter>(Controller->GetPawn()) : nullptr;
	AAirsoftPlayerState* PS = Controller ? Controller->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!C || !PS || C->IsOut() || !C->GetCombat())
	{
		return;
	}
	C->GetCombat()->ServerInitLoadout(GetEffectiveLoadout(PS));
	if (!AirsoftGameModeLocal::CarriesGrenade(GetAirsoftGameState(), PS))
	{
		C->GetCombat()->Grenades = 0;
	}
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
				// Back from a free-for-all (or new): the lobby team if we kept one.
				PS->Team = PS->SavedTeam != EAirsoftTeam::None ? PS->SavedTeam : (Blue.Num() <= Red.Num() ? EAirsoftTeam::Blue : EAirsoftTeam::Red);
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

void AAirsoftGameMode::ClearTeamsForFreeForAll()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	for (APlayerState* P : GS->PlayerArray)
	{
		AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (PS && PS->Team != EAirsoftTeam::None)
		{
			if (!PS->IsABot())
			{
				PS->SavedTeam = PS->Team;
			}
			PS->Team = EAirsoftTeam::None; // pawns pick up the neutral look on their next tick
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

void AAirsoftGameMode::OnVotesChanged(AAirsoftPlayerController* VoteFrom)
{
	RecountVotes();
	AAirsoftPlayerState* PS = VoteFrom ? VoteFrom->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (PS && GetWorld())
	{
		PS->VoteAnnounceAt = GetWorld()->GetTimeSeconds() + AirsoftGameModeLocal::VoteAnnounceDelay;
	}
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
	Modes.Init(0, AirsoftRules::NumModes);
	Maps.Init(0, AirsoftRules::NumMaps());
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

void AAirsoftGameMode::PostPendingVotes()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || !GetWorld())
	{
		return;
	}
	const double Now = GetWorld()->GetTimeSeconds();
	const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
	for (APlayerState* P : GS->PlayerArray)
	{
		AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (!IsValid(PS) || PS->VoteAnnounceAt <= 0.0 || Now < PS->VoteAnnounceAt)
		{
			continue;
		}
		PS->VoteAnnounceAt = 0.0;
		TArray<FString> Parts;
		if (PS->ModeVote >= 0 && PS->ModeVote < AirsoftRules::NumModes)
		{
			Parts.Add(AirsoftRules::ModeName(AirsoftRules::ModeFromIndex(PS->ModeVote)));
		}
		if (Maps.IsValidIndex(PS->MapVote))
		{
			Parts.Add(AirsoftRules::MapDisplayName(Maps[PS->MapVote].Key));
		}
		if (Parts.Num() > 0)
		{
			BroadcastSystem(FString::Printf(TEXT("%s votes %s"), *PS->GetPlayerName(), *FString::Join(Parts, TEXT(" · "))));
		}
	}
}

bool AAirsoftGameMode::PickNextMatch(EAirsoftMode& OutMode, int32& OutMapIndex)
{
	using namespace AirsoftGameModeLocal;
	AAirsoftGameState* GS = GetAirsoftGameState();
	const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
	RecountVotes();

	const int32 ModePick = GS ? PickVote(GS->ModeVotes) : INDEX_NONE;
	OutMode = AirsoftRules::ModeFromIndex(ModePick == INDEX_NONE ? 0 : ModePick);
	OutMapIndex = INDEX_NONE;

	TArray<int32> Votes;
	Votes.Init(0, Maps.Num());
	for (int32 i = 0; GS && i < Maps.Num() && i < GS->MapVotes.Num(); ++i)
	{
		Votes[i] = GS->MapVotes[i];
	}
	auto Usable = [&Maps](int32 Index, EAirsoftMode InMode)
	{
		// A map the setup script hasn't built yet is skipped instead of failing the travel.
		return Maps.IsValidIndex(Index) && !Maps[Index].LevelPath.IsEmpty() && Maps[Index].SupportsMode(InMode)
			&& FPackageName::DoesPackageExist(Maps[Index].LevelPath);
	};
	for (int32 Attempt = 0; Attempt < 2; ++Attempt)
	{
		// The mode won the vote: take the best-voted map that runs it.
		TArray<int32> Allowed = Votes;
		for (int32 i = 0; i < Allowed.Num(); ++i)
		{
			if (!Usable(i, OutMode))
			{
				Allowed[i] = -1;
			}
		}
		const int32 MapPick = PickVote(Allowed);
		if (MapPick != INDEX_NONE)
		{
			OutMapIndex = MapPick;
			return true;
		}
		OutMode = EAirsoftMode::TDM; // no built map runs the voted mode: fall back to the plainest one
	}
	return false;
}

void AAirsoftGameMode::OnLoadoutChanged(AAirsoftPlayerController* PC)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || !PC)
	{
		return;
	}
	// In the staging area and before a round goes live the change is instant (Gun Game: the ladder decides).
	if (!GS->bIsMatchMap || GS->Phase != EAirsoftPhase::Live)
	{
		if (GS->bIsMatchMap && GS->Mode == EAirsoftMode::GunGame)
		{
			return;
		}
		ApplyModeLoadout(PC);
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
	AnnounceAll(TEXT("HOST IS STARTING"), bAloneWithoutBots ? TEXT("Deploying in 5 seconds  ·  bots are off (Menu > Bots)") : TEXT("Deploying in 5 seconds  ·  leading vote wins"),
		AirsoftColors::Accent(), 3.f);
}

void AAirsoftGameMode::OnPlayerProfileReady(AAirsoftPlayerController* PC)
{
	AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!PS || PS->bJoinAnnounced)
	{
		return;
	}
	PS->bJoinAnnounced = true;
	BroadcastSystem(FString::Printf(TEXT("%s joined"), *PS->GetPlayerName()));
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

void AAirsoftGameMode::BroadcastChat(APlayerState* From, const FString& Text, bool bTeamOnly)
{
	if (!From || Text.IsEmpty())
	{
		return;
	}
	const AAirsoftPlayerState* FromPS = Cast<AAirsoftPlayerState>(From);
	const AAirsoftGameState* GS = GetAirsoftGameState();
	const EAirsoftTeam Team = FromPS ? FromPS->Team : EAirsoftTeam::None;
	// Free-for-all has no teams: "team" chat goes to everyone.
	const bool bTeam = bTeamOnly && Team != EAirsoftTeam::None && !(GS && GS->IsFreeForAll());
	const FString Name = From->GetPlayerName();
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get());
		if (!PC)
		{
			continue;
		}
		const AAirsoftPlayerState* PS = PC->GetPlayerState<AAirsoftPlayerState>();
		if (bTeam && (!PS || PS->Team != Team))
		{
			continue;
		}
		PC->ClientReceiveChat(Name, Team, Text, bTeam ? EAirsoftChatKind::Team : EAirsoftChatKind::All);
	}
	UE_LOG(LogTemp, Log, TEXT("Airsoft chat%s %s: %s"), bTeam ? TEXT(" [team]") : TEXT(""), *Name, *Text);
}

void AAirsoftGameMode::BroadcastSystem(const FString& Text)
{
	if (Text.IsEmpty() || !GetWorld())
	{
		return;
	}
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientReceiveChat(FString(), EAirsoftTeam::None, Text, EAirsoftChatKind::System);
		}
	}
}

void AAirsoftGameMode::BotChatter(AController* Speaker, int32 Situation)
{
	UWorld* World = GetWorld();
	if (!Speaker || !World || !UAirsoftSettings::Get()->bBotChatter)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	if (Now < NextBotChatterAt)
	{
		return;
	}
	const float Chance = Situation == 0 ? 0.12f : (Situation == 1 ? 0.1f : 0.35f);
	if (FMath::FRand() > Chance)
	{
		return;
	}
	const TArray<FString>& Lines = AirsoftBotNames::ChatterLines(Situation);
	APlayerState* PS = Speaker->GetPlayerState<APlayerState>();
	if (!PS || Lines.Num() == 0)
	{
		return;
	}
	NextBotChatterAt = Now + AirsoftGameModeLocal::BotChatterCooldown * FMath::FRandRange(0.8f, 1.5f);
	const FString Line = Lines[FMath::RandRange(0, Lines.Num() - 1)];
	const bool bTeamOnly = Situation != 1; // a good-sport "nice shot" goes to everyone
	TWeakObjectPtr<APlayerState> WeakPS(PS);
	FTimerHandle Handle;
	// A moment's delay: nobody types that fast.
	GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, WeakPS, Line, bTeamOnly]()
	{
		if (WeakPS.IsValid())
		{
			BroadcastChat(WeakPS.Get(), Line, bTeamOnly);
		}
	}), FMath::FRandRange(0.8f, 2.2f), false);
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
	PostPendingVotes();
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
			AnnounceAll(TEXT("SQUAD UP"), TEXT("Vote for the next match: F1 mode, F2 map. Deploying soon."), AirsoftColors::Accent(), 4.f);
			BroadcastSystem(TEXT("Vote is open: F1 cycles the mode, F2 the map (or Menu > Next match)."));
		}
	}
	else if (GS->Phase == EAirsoftPhase::Intermission)
	{
		if (Players < S->MinPlayers && !bForceStarted)
		{
			SetPhase(EAirsoftPhase::Waiting, 0.f);
			return;
		}
		GS->StatusMessage = TEXT("Vote now  ·  F1 mode  ·  F2 map  ·  Enter chat");
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
	EAirsoftMode Mode = EAirsoftMode::TDM;
	int32 MapIndex = INDEX_NONE;
	const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
	if (!PickNextMatch(Mode, MapIndex) || !Maps.IsValidIndex(MapIndex))
	{
		GS->StatusMessage = TEXT("Match map missing - run the setup script");
		bForceStarted = false;
		SetPhase(EAirsoftPhase::Waiting, 0.f);
		return;
	}
	const FAirsoftMapInfo& Map = Maps[MapIndex];
	bTravelling = true;
	BalanceTeams();
	GS->StatusMessage = TEXT("Deploying...");
	const FString MapName = AirsoftRules::MapDisplayName(Map.Key);
	AnnounceAll(TEXT("DEPLOYING"), FString::Printf(TEXT("%s  ·  %s"), *AirsoftRules::ModeName(Mode), *MapName), AirsoftColors::Accent(), 3.f);
	BroadcastSystem(FString::Printf(TEXT("Next match: %s on %s"), *AirsoftRules::ModeName(Mode), *MapName));

	const FString URL = FString::Printf(TEXT("%s?Mode=%s"), *Map.LevelPath, *AirsoftRules::ModeOption(Mode));
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
		if (NumTravellingPlayers <= 0 || GetWorld()->GetTimeSeconds() - WaitingSince > AirsoftGameModeLocal::MaxLoadWait)
		{
			BeginMatch();
		}
		break;

	case EAirsoftPhase::Briefing:
		if (GS->GetTimeRemaining() <= 0.f)
		{
			BeginLive();
		}
		break;

	case EAirsoftPhase::Live:
		UpdateAliveCounts();
		switch (GS->Mode)
		{
		case EAirsoftMode::Domination: TickDomination(DeltaSeconds); break;
		case EAirsoftMode::Elimination: TickElimination(DeltaSeconds); break;
		case EAirsoftMode::VIP: TickVIP(DeltaSeconds); break;
		default: break; // TDM and Gun Game score in HandleTag
		}
		if (GS->Phase == EAirsoftPhase::Live && GS->GetTimeRemaining() <= 0.f)
		{
			HandleTimeUp();
		}
		break;

	case EAirsoftPhase::PostRound:
		if (GS->GetTimeRemaining() <= 0.f)
		{
			if (GS->bMatchOver)
			{
				ReturnToStaging();
			}
			else
			{
				BeginRound();
			}
		}
		break;
	}
}

void AAirsoftGameMode::BeginMatch()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (GS->IsFreeForAll())
	{
		ClearTeamsForFreeForAll();
	}
	else
	{
		BalanceTeams();
	}
	GS->BlueScore = 0;
	GS->RedScore = 0;
	GS->Winner = EAirsoftTeam::None;
	GS->WinnerName.Reset();
	GS->bMatchOver = false;
	GS->RoundNumber = 0;
	GS->RoundWinner = EAirsoftTeam::None;
	GS->ScoreLimit = AirsoftRules::ScoreLimit(GS->Mode);
	GS->MaxRounds = AirsoftRules::MaxRounds(GS->Mode);
	GS->VIPPlayer = nullptr;
	GS->ExtractionPoint = nullptr;
	GS->ExtractProgress = 0.f;
	GS->AttackingTeam = GS->Mode == EAirsoftMode::VIP ? (FMath::RandBool() ? EAirsoftTeam::Blue : EAirsoftTeam::Red) : EAirsoftTeam::None;
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			PS->ResetRound();
		}
	}
	BeginRound();
}

void AAirsoftGameMode::BeginRound()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	const bool bRounds = GS->IsRoundBased();
	const bool bFreeForAll = GS->IsFreeForAll();
	const float Freeze = AirsoftRules::FreezeTime(GS->Mode);

	GS->RoundNumber++;
	GS->RoundWinner = EAirsoftTeam::None;
	GS->VIPPlayer = nullptr; // last round's VIP gets a normal loadout on respawn
	GS->ExtractProgress = 0.f;
	ExtractClock = 0.f;
	LastTag = FAirsoftFinalTag();
	DominationScoreClock = 0.f;
	bLastStandAnnounced[0] = false;
	bLastStandAnnounced[1] = false;

	// VIP: sides swap at half time.
	const int32 PerHalf = AirsoftRules::RoundsPerHalf(GS->Mode);
	const bool bHalfTime = PerHalf > 0 && GS->RoundNumber == PerHalf + 1;
	if (bHalfTime)
	{
		GS->AttackingTeam = AirsoftGameModeLocal::OtherTeam(GS->AttackingTeam);
		BroadcastSystem(TEXT("Half time: sides switched."));
	}

	for (AAirsoftObjective* Obj : GS->Objectives)
	{
		if (Obj)
		{
			Obj->ServerReset(GS->Mode == EAirsoftMode::Domination && !Obj->IsExtractionOnly());
		}
	}
	if (GS->Mode == EAirsoftMode::VIP)
	{
		ChooseExtraction();
	}

	SetPhase(EAirsoftPhase::Briefing, Freeze); // before the respawns: Respawn() refuses during PostRound
	GS->StatusMessage = bRounds ? FString::Printf(TEXT("Round %d  ·  frozen: pick your loadout (L)"), GS->RoundNumber) : FString(TEXT("Briefing"));

	const FString MapName = AirsoftRules::MapDisplayName(GS->MapId);
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get());
		AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
		if (!PC || !PS)
		{
			continue;
		}
		PS->ResetLife();
		PC->ClientResetForNewRound();
		Respawn(PC); // everyone starts at their own team's spawn, frozen

		FString Title = AirsoftRules::ModeName(GS->Mode).ToUpper();
		FString Sub;
		if (bFreeForAll)
		{
			Sub = FString::Printf(TEXT("%s  ·  Everyone for themselves  ·  %d guns to climb"), *MapName, GS->ScoreLimit);
		}
		else if (GS->Mode == EAirsoftMode::VIP)
		{
			Title = FString::Printf(TEXT("ROUND %d / %d"), GS->RoundNumber, GS->MaxRounds);
			const bool bAttack = PS->Team == GS->AttackingTeam;
			Sub = FString::Printf(TEXT("%s%s  ·  %s"), bHalfTime ? TEXT("Sides switched  ·  ") : TEXT(""),
				bAttack ? TEXT("ATTACK: walk the VIP to EXTRACT") : TEXT("DEFEND: tag the VIP or hold out"), *AirsoftColors::TeamName(PS->Team));
		}
		else if (bRounds)
		{
			Title = FString::Printf(TEXT("ROUND %d"), GS->RoundNumber);
			Sub = FString::Printf(TEXT("Blue %d – %d Red  ·  You're on %s  ·  One life  ·  first to %d"),
				GS->BlueScore, GS->RedScore, *AirsoftColors::TeamName(PS->Team), GS->ScoreLimit);
		}
		else
		{
			Sub = FString::Printf(TEXT("%s  ·  You're on %s  ·  %s"), *MapName, *AirsoftColors::TeamName(PS->Team), *AirsoftRules::ModeBlurb(GS->Mode));
		}
		PC->ClientAnnounce(Title, Sub, AirsoftColors::Team(PS->Team), Freeze);
	}
	// Bots already here start over too; then fill both sides up around the people (new bots spawn frozen).
	const TArray<TObjectPtr<AAirsoftBotController>> ExistingBots = Bots;
	for (AAirsoftBotController* Bot : ExistingBots)
	{
		if (AAirsoftPlayerState* BotPS = IsValid(Bot) ? Bot->GetPlayerState<AAirsoftPlayerState>() : nullptr)
		{
			BotPS->ResetLife();
			Respawn(Bot);
		}
	}
	bBotsDirty = false;
	BotClock = 0.f;
	UpdateBots();
	if (GS->Mode == EAirsoftMode::VIP)
	{
		ChooseVIP(); // after the bots: a side of only bots still gets a VIP
	}
	FreezeAll(true);
}

void AAirsoftGameMode::BeginLive()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	SetPhase(EAirsoftPhase::Live, AirsoftRules::RoundTime(GS->Mode));
	GS->StatusMessage.Reset();
	FreezeAll(false);
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			PS->ProtectedUntil = 0.f;
		}
	}
	// Who is in this round (an empty side never "loses" by elimination: practice runs on the clock).
	CountAlive(RoundStartBlue, RoundStartRed);
	UpdateAliveCounts();

	if (GS->Mode == EAirsoftMode::VIP)
	{
		for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
		{
			AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get());
			const AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
			if (PC && PS)
			{
				const bool bVIP = GS->VIPPlayer.Get() == PS;
				const bool bAttack = PS->Team == GS->AttackingTeam;
				PC->ClientAnnounce(TEXT("GAME ON"), bVIP ? TEXT("Get to EXTRACT") : (bAttack ? TEXT("Get the VIP out") : TEXT("Find the VIP")), AirsoftColors::Accent(), 2.5f);
			}
		}
	}
	else
	{
		FString Go = TEXT("Call your hits");
		switch (GS->Mode)
		{
		case EAirsoftMode::Domination: Go = TEXT("Take the points"); break;
		case EAirsoftMode::Elimination: Go = TEXT("One life - make it count"); break;
		case EAirsoftMode::GunGame: Go = TEXT("Climb the ladder"); break;
		default: break;
		}
		AnnounceAll(TEXT("GAME ON"), Go, AirsoftColors::Accent(), 2.5f);
	}
	if (Bots.Num() > 0)
	{
		AAirsoftBotController* Speaker = Bots[FMath::RandRange(0, Bots.Num() - 1)];
		if (IsValid(Speaker))
		{
			BotChatter(Speaker, 2);
		}
	}
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
		const EAirsoftTeam Taken = Obj->ServerUpdate(DeltaSeconds, Blue, Red, AirsoftGameModeLocal::DominationCaptureTime);
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
		FinishMatch(GS->BlueScore == GS->RedScore ? EAirsoftTeam::None : (GS->BlueScore > GS->RedScore ? EAirsoftTeam::Blue : EAirsoftTeam::Red), nullptr);
	}
}

void AAirsoftGameMode::TickElimination(float DeltaSeconds)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->Phase != EAirsoftPhase::Live || RoundStartBlue <= 0 || RoundStartRed <= 0)
	{
		return; // a side with nobody on it: the clock decides (practice)
	}
	int32 Blue = 0;
	int32 Red = 0;
	CountAlive(Blue, Red);

	// The last player standing on a side hears about it once.
	for (int32 Index = 0; Index < 2; ++Index)
	{
		const EAirsoftTeam Team = Index == 0 ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
		const int32 Standing = Index == 0 ? Blue : Red;
		const int32 Started = Index == 0 ? RoundStartBlue : RoundStartRed;
		if (Standing != 1 || Started < 2 || bLastStandAnnounced[Index])
		{
			continue;
		}
		bLastStandAnnounced[Index] = true;
		for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
		{
			if (!It->IsOut() && It->GetTeam() == Team)
			{
				if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->GetController()))
				{
					const int32 Facing = Index == 0 ? Red : Blue;
					PC->ClientAnnounce(TEXT("LAST ONE STANDING"), FString::Printf(TEXT("%d against you"), Facing), AirsoftColors::Team(Team), 2.5f);
				}
				break;
			}
		}
	}

	if (Blue == 0 || Red == 0)
	{
		const EAirsoftTeam Winner = Blue == Red ? EAirsoftTeam::None : (Blue > 0 ? EAirsoftTeam::Blue : EAirsoftTeam::Red);
		EndRound(Winner, Winner == EAirsoftTeam::None ? TEXT("both sides out") : TEXT("last side standing"));
	}
}

void AAirsoftGameMode::TickVIP(float DeltaSeconds)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->Phase != EAirsoftPhase::Live)
	{
		return;
	}
	const EAirsoftTeam Attackers = GS->AttackingTeam;
	const EAirsoftTeam Defenders = GS->DefendingTeam();
	int32 Blue = 0;
	int32 Red = 0;
	CountAlive(Blue, Red);
	const int32 DefendersUp = Defenders == EAirsoftTeam::Blue ? Blue : Red;
	const int32 DefendersStarted = Defenders == EAirsoftTeam::Blue ? RoundStartBlue : RoundStartRed;

	AAirsoftPlayerState* VIPPS = GS->VIPPlayer.Get();
	if (!VIPPS)
	{
		// Nobody to escort (the attacking side is empty): defenders hold on for the clock.
		if (DefendersStarted > 0 && DefendersUp == 0)
		{
			EndRound(Attackers, TEXT("defenders wiped out"));
		}
		return;
	}
	if (!IsValid(VIPPS))
	{
		EndRound(EAirsoftTeam::None, TEXT("the VIP left"));
		return;
	}
	AAirsoftCharacter* VIPChar = FindCharacterFor(VIPPS);
	if (!VIPChar || VIPChar->IsOut())
	{
		EndRound(Defenders, TEXT("VIP tagged"));
		return;
	}
	if (DefendersStarted > 0 && DefendersUp == 0)
	{
		EndRound(Attackers, TEXT("defenders wiped out"));
		return;
	}

	// Extraction: the VIP has to stand in the zone for a few seconds (stepping out bleeds it back).
	const AAirsoftObjective* Extract = GS->ExtractionPoint.Get();
	if (Extract && Extract->IsInside(VIPChar->GetActorLocation()))
	{
		ExtractClock += DeltaSeconds;
	}
	else
	{
		ExtractClock = FMath::Max(0.f, ExtractClock - DeltaSeconds * 2.f);
	}
	const float Needed = FMath::Max(UAirsoftSettings::Get()->VIPExtractTime, 0.5f);
	const float Progress = FMath::Clamp(ExtractClock / Needed, 0.f, 1.f);
	if (!FMath::IsNearlyEqual(GS->ExtractProgress, Progress, 0.01f) || (Progress <= 0.f && GS->ExtractProgress > 0.f))
	{
		GS->ExtractProgress = Progress;
	}
	if (ExtractClock >= Needed)
	{
		VIPPS->Round.Captures++;
		GiveXP(VIPPS->GetOwningController(), 300, TEXT("VIP EXTRACTED"));
		for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
		{
			if (*It != VIPChar && !It->IsOut() && It->GetTeam() == Attackers)
			{
				GiveXP(It->GetController(), 100, TEXT("ESCORT"));
			}
		}
		EndRound(Attackers, TEXT("VIP extracted"));
	}
}

void AAirsoftGameMode::HandleTimeUp()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	switch (GS->Mode)
	{
	case EAirsoftMode::Elimination:
	{
		int32 Blue = 0;
		int32 Red = 0;
		CountAlive(Blue, Red);
		EndRound(Blue == Red ? EAirsoftTeam::None : (Blue > Red ? EAirsoftTeam::Blue : EAirsoftTeam::Red), TEXT("time: most players standing"));
		break;
	}
	case EAirsoftMode::VIP:
		EndRound(GS->DefendingTeam(), TEXT("time: the VIP never made it"));
		break;
	case EAirsoftMode::GunGame:
	{
		// Highest level wins; a tie on level and tags is a draw.
		AAirsoftPlayerState* Leader = GS->GetGunGameLeader();
		for (APlayerState* P : GS->PlayerArray)
		{
			const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
			if (Leader && PS && PS != Leader && !PS->IsInactive() && PS->GunLevel == Leader->GunLevel && PS->Round.Tags == Leader->Round.Tags)
			{
				Leader = nullptr;
				break;
			}
		}
		FinishMatch(EAirsoftTeam::None, Leader);
		break;
	}
	default:
		FinishMatch(GS->BlueScore == GS->RedScore ? EAirsoftTeam::None : (GS->BlueScore > GS->RedScore ? EAirsoftTeam::Blue : EAirsoftTeam::Red), nullptr);
		break;
	}
}

void AAirsoftGameMode::EndRound(EAirsoftTeam RoundWinnerTeam, const FString& Reason)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->Phase != EAirsoftPhase::Live)
	{
		return; // once per round, and only from a live round
	}
	if (!GS->IsRoundBased())
	{
		FinishMatch(RoundWinnerTeam, nullptr);
		return;
	}
	GS->RoundWinner = RoundWinnerTeam;
	GS->BlueScore += RoundWinnerTeam == EAirsoftTeam::Blue ? 1 : 0;
	GS->RedScore += RoundWinnerTeam == EAirsoftTeam::Red ? 1 : 0;
	GS->ExtractProgress = 0.f;
	ExtractClock = 0.f;
	UpdateAliveCounts();

	if (RoundWinnerTeam != EAirsoftTeam::None)
	{
		for (APlayerState* P : GS->PlayerArray)
		{
			const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
			if (PS && PS->Team == RoundWinnerTeam)
			{
				GiveXP(PS->GetOwningController(), 100, TEXT("ROUND WON"));
			}
		}
	}
	const FString TeamLine = RoundWinnerTeam == EAirsoftTeam::None ? FString(TEXT("Round drawn"))
		: FString::Printf(TEXT("%s takes the round"), *AirsoftColors::TeamName(RoundWinnerTeam));
	BroadcastSystem(FString::Printf(TEXT("Round %d: %s, %s (Blue %d – %d Red)"), GS->RoundNumber, *TeamLine, *Reason, GS->BlueScore, GS->RedScore));

	// Match over? A side reached the target, or the rounds ran out.
	const bool bClinched = GS->BlueScore >= GS->ScoreLimit || GS->RedScore >= GS->ScoreLimit;
	const bool bOutOfRounds = GS->MaxRounds > 0 && GS->RoundNumber >= GS->MaxRounds;
	if (bClinched || bOutOfRounds)
	{
		FinishMatch(GS->BlueScore == GS->RedScore ? EAirsoftTeam::None : (GS->BlueScore > GS->RedScore ? EAirsoftTeam::Blue : EAirsoftTeam::Red), nullptr);
		return;
	}

	// Between rounds: frozen, the round's last tag replays, then the next round's freeze.
	SetPhase(EAirsoftPhase::PostRound, FMath::Max(UAirsoftSettings::Get()->RoundOverTime, 3.f));
	GS->bMatchOver = false;
	GS->StatusMessage = FString::Printf(TEXT("Round %d  ·  %s"), GS->RoundNumber, *TeamLine);
	FreezeAll(true);
	for (TPair<TWeakObjectPtr<AController>, FTimerHandle>& Pair : RespawnTimers)
	{
		GetWorldTimerManager().ClearTimer(Pair.Value);
	}
	RespawnTimers.Reset();
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientRoundEnded(RoundWinnerTeam, Reason, LastTag);
		}
	}
}

void AAirsoftGameMode::FinishMatch(EAirsoftTeam WinnerTeam, AAirsoftPlayerState* WinnerPlayer)
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->Phase == EAirsoftPhase::PostRound)
	{
		return;
	}
	const bool bFreeForAll = GS->IsFreeForAll();
	SetPhase(EAirsoftPhase::PostRound, UAirsoftSettings::Get()->PostRoundTime);
	GS->bMatchOver = true;
	GS->Winner = bFreeForAll ? EAirsoftTeam::None : WinnerTeam;
	GS->WinnerName = WinnerPlayer ? WinnerPlayer->GetPlayerName() : FString();
	GS->ExtractProgress = 0.f;
	const bool bDraw = bFreeForAll ? WinnerPlayer == nullptr : WinnerTeam == EAirsoftTeam::None;
	GS->StatusMessage = bDraw ? FString(TEXT("Draw"))
		: FString::Printf(TEXT("%s wins"), bFreeForAll ? *GS->WinnerName : *AirsoftColors::TeamName(WinnerTeam));
	FreezeAll(true);
	for (TPair<TWeakObjectPtr<AController>, FTimerHandle>& Pair : RespawnTimers)
	{
		GetWorldTimerManager().ClearTimer(Pair.Value);
	}
	RespawnTimers.Reset();

	auto IsWinner = [bFreeForAll, WinnerTeam, WinnerPlayer](const AAirsoftPlayerState* PS)
	{
		return PS && (bFreeForAll ? PS == WinnerPlayer : (WinnerTeam != EAirsoftTeam::None && PS->Team == WinnerTeam));
	};

	// Match bonus XP first so the report includes it.
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			const bool bWon = IsWinner(PS);
			const int32 Bonus = bDraw ? 250 : (bWon ? 500 : 200);
			GiveXP(PS->GetOwningController(), Bonus, bDraw ? TEXT("DRAW") : (bWon ? TEXT("VICTORY") : TEXT("MATCH COMPLETE")));
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
			Row.Level = GS->Mode == EAirsoftMode::GunGame ? PS->GunLevel + 1 : 0;
			Rows.Add(Row);
		}
	}
	Rows.Sort([](const FAirsoftSummaryRow& A, const FAirsoftSummaryRow& B)
	{
		if (A.Level != B.Level)
		{
			return A.Level > B.Level;
		}
		return A.Stats.XP > B.Stats.XP;
	});

	if (bDraw)
	{
		BroadcastSystem(TEXT("Match over: a draw."));
	}
	else
	{
		BroadcastSystem(FString::Printf(TEXT("Match over: %s wins%s"), bFreeForAll ? *GS->WinnerName : *AirsoftColors::TeamName(WinnerTeam),
			GS->IsRoundBased() ? *FString::Printf(TEXT(" (Blue %d – %d Red)"), GS->BlueScore, GS->RedScore) : TEXT("")));
	}

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get());
		const AAirsoftPlayerState* PS = PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
		if (PC && PS)
		{
			PC->ClientMatchEnded(GS->Winner, GS->WinnerName, IsWinner(PS), Rows, LastTag, PS->Round.XP, PS->Round.Captures);
		}
	}
}

void AAirsoftGameMode::ReturnToStaging()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	bTravelling = true;
	const bool bFreeForAll = GS->IsFreeForAll();
	for (APlayerState* P : GS->PlayerArray)
	{
		if (AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P))
		{
			PS->CareerXP += PS->Round.XP;
			PS->ResetRound();
			// Back to the lobby team after a free-for-all (None = the lobby assigns one).
			if (bFreeForAll && !PS->IsABot() && PS->Team == EAirsoftTeam::None)
			{
				PS->Team = PS->SavedTeam;
			}
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
// VIP
// ---------------------------------------------------------------------------

AAirsoftCharacter* AAirsoftGameMode::FindCharacterFor(const APlayerState* PS) const
{
	if (!PS)
	{
		return nullptr;
	}
	for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
	{
		if (It->GetPlayerState() == PS)
		{
			return *It;
		}
	}
	return nullptr;
}

void AAirsoftGameMode::ChooseExtraction()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	GS->ExtractionPoint = nullptr;
	if (GS->Mode != EAirsoftMode::VIP)
	{
		return;
	}
	// A dedicated extraction point (Letter "X") if the map has one...
	AAirsoftObjective* Best = nullptr;
	for (AAirsoftObjective* Obj : GS->Objectives)
	{
		if (Obj && Obj->IsExtractionOnly())
		{
			Best = Obj;
			break;
		}
	}
	// ...otherwise the objective furthest from the attackers' spawn: C when Blue attacks on the stock maps,
	// A when Red attacks after the swap, so both halves walk the same distance.
	if (!Best)
	{
		FVector Home = FVector::ZeroVector;
		int32 NumHome = 0;
		for (TActorIterator<AAirsoftTeamStart> It(GetWorld()); It; ++It)
		{
			if (It->Team == GS->AttackingTeam)
			{
				Home += It->GetActorLocation();
				++NumHome;
			}
		}
		if (NumHome > 0)
		{
			Home /= static_cast<double>(NumHome);
		}
		double BestDist = -1.0;
		for (AAirsoftObjective* Obj : GS->Objectives)
		{
			if (!Obj)
			{
				continue;
			}
			const double Dist = NumHome > 0 ? FVector::Dist(Obj->GetActorLocation(), Home) : static_cast<double>(Obj->Letter.Compare(TEXT("A")));
			if (Dist > BestDist)
			{
				BestDist = Dist;
				Best = Obj;
			}
		}
	}
	if (Best)
	{
		Best->ServerSetExtraction(GS->AttackingTeam);
		GS->ExtractionPoint = Best;
	}
}

void AAirsoftGameMode::ChooseVIP()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->Mode != EAirsoftMode::VIP)
	{
		return;
	}
	// A person on the attacking side who has been VIP the least; a bot only if the side has no people.
	TArray<AAirsoftPlayerState*> Humans;
	TArray<AAirsoftPlayerState*> BotCandidates;
	for (APlayerState* P : GS->PlayerArray)
	{
		AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (!IsValid(PS) || PS->IsInactive() || PS->Team != GS->AttackingTeam || !FindCharacterFor(PS))
		{
			continue;
		}
		(PS->IsABot() ? BotCandidates : Humans).Add(PS);
	}
	TArray<AAirsoftPlayerState*>& Pool = Humans.Num() > 0 ? Humans : BotCandidates;
	if (Pool.Num() == 0)
	{
		GS->VIPPlayer = nullptr;
		return;
	}
	int32 Fewest = MAX_int32;
	for (const AAirsoftPlayerState* PS : Pool)
	{
		Fewest = FMath::Min(Fewest, PS->VIPTurns);
	}
	Pool.RemoveAll([Fewest](const AAirsoftPlayerState* PS) { return PS->VIPTurns > Fewest; });
	AAirsoftPlayerState* Pick = Pool[FMath::RandRange(0, Pool.Num() - 1)];
	Pick->VIPTurns++;
	GS->VIPPlayer = Pick;
	ApplyModeLoadout(Pick->GetOwningController()); // pistol only, no grenade
	if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(Pick->GetOwningController()))
	{
		PC->ClientAnnounce(TEXT("YOU ARE THE VIP"), TEXT("Pistol only. Your squad walks you to EXTRACT."), AirsoftColors::Accent(), AirsoftRules::FreezeTime(GS->Mode));
	}
	BroadcastSystem(FString::Printf(TEXT("%s is the VIP for %s"), *Pick->GetPlayerName(), *AirsoftColors::TeamName(GS->AttackingTeam)));
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
	const UAirsoftSettings* S = UAirsoftSettings::Get();
	const bool bFreeForAll = GS->IsFreeForAll();
	const bool bSameTeam = ShooterPS && !bFreeForAll && ShooterPS->Team == VictimPS->Team;
	if (bSameTeam && !S->bFriendlyFire)
	{
		return false;
	}

	const bool bRespawns = AirsoftRules::HasRespawns(GS->Mode);
	const float RespawnDelay = AirsoftRules::RespawnTime(GS->Mode);
	const FString ShooterName = ShooterPS ? ShooterPS->GetPlayerName() : FString(TEXT("Grenade"));
	const int32 VictimStreak = VictimPS->Round.Streak;
	const bool bVictimWasVIP = GS->Mode == EAirsoftMode::VIP && GS->VIPPlayer.Get() == VictimPS;

	VictimChar->ServerMarkOut(ShooterName);
	VictimPS->LastTaggedBy = ShooterName;
	VictimPS->Round.Outs++;
	VictimPS->Round.Streak = 0;
	VictimPS->RespawnAt = bRespawns ? static_cast<float>(GS->GetServerWorldTimeSeconds()) + RespawnDelay : 0.f;

	// The replay needs this tag before anything below can end the round.
	const APawn* ShooterPawn = Shooter ? Shooter->GetPawn() : nullptr;
	LastTag.bValid = true;
	LastTag.Shooter = ShooterName;
	LastTag.Victim = VictimPS->GetPlayerName();
	LastTag.ShooterTeam = ShooterPS ? ShooterPS->Team : EAirsoftTeam::None;
	LastTag.VictimTeam = VictimPS->Team;
	LastTag.To = VictimChar->GetActorLocation() + FVector(0.f, 0.f, 40.f);
	LastTag.From = ShooterPawn ? ShooterPawn->GetPawnViewLocation() : LastTag.To + FVector(-300.f, 0.f, 100.f);
	LastTag.WeaponId = WeaponId;

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
		if (bVictimWasVIP)
		{
			GiveXP(Shooter, 250, TEXT("VIP TAGGED"));
		}
		if (GS->Mode == EAirsoftMode::TDM)
		{
			GS->BlueScore += ShooterPS->Team == EAirsoftTeam::Blue ? 1 : 0;
			GS->RedScore += ShooterPS->Team == EAirsoftTeam::Red ? 1 : 0;
		}
	}

	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientKillFeed(ShooterName, LastTag.ShooterTeam, LastTag.Victim, LastTag.VictimTeam, WeaponId);
		}
	}

	if (bRespawns)
	{
		ScheduleRespawn(Victim, RespawnDelay);
	}

	if (ShooterPS && !bSameTeam && ShooterPS->IsABot())
	{
		BotChatter(Shooter, 0);
	}
	else if (VictimPS->IsABot())
	{
		BotChatter(Victim, 1);
	}

	// What the tag means for the match.
	switch (GS->Mode)
	{
	case EAirsoftMode::TDM:
		if (GS->BlueScore >= GS->ScoreLimit || GS->RedScore >= GS->ScoreLimit)
		{
			FinishMatch(GS->BlueScore >= GS->ScoreLimit ? EAirsoftTeam::Blue : EAirsoftTeam::Red, nullptr);
		}
		break;
	case EAirsoftMode::GunGame:
		if (ShooterPS && !bSameTeam && WeaponId != TEXT("Grenade"))
		{
			AdvanceGunGame(Shooter, ShooterPS);
		}
		break;
	case EAirsoftMode::VIP:
		if (bVictimWasVIP)
		{
			EndRound(GS->DefendingTeam(), FString::Printf(TEXT("VIP tagged by %s"), *ShooterName));
		}
		break;
	case EAirsoftMode::Elimination:
		TickElimination(0.f); // end the round straight away when a side is out
		break;
	default:
		break;
	}
	return true;
}

void AAirsoftGameMode::AdvanceGunGame(AController* Shooter, AAirsoftPlayerState* ShooterPS)
{
	const TArray<FName> Ladder = AirsoftRules::GunGameLadder();
	const int32 Last = Ladder.Num() - 1;
	if (!ShooterPS || Last < 0)
	{
		return;
	}
	if (ShooterPS->GunLevel >= Last)
	{
		// A tag with the final gun wins the match.
		GiveXP(Shooter, 300, TEXT("GUN GAME WIN"));
		FinishMatch(EAirsoftTeam::None, ShooterPS);
		return;
	}
	ShooterPS->GunLevel = FMath::Clamp(ShooterPS->GunLevel + 1, 0, Last);
	GiveXP(Shooter, 50, TEXT("LEVEL UP"));
	const FName Next = Ladder[ShooterPS->GunLevel];
	const bool bFinal = ShooterPS->GunLevel == Last;
	if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(Shooter))
	{
		PC->ClientAnnounce(FString::Printf(TEXT("LEVEL %d / %d"), ShooterPS->GunLevel + 1, Ladder.Num()),
			bFinal ? FString::Printf(TEXT("%s  ·  FINAL WEAPON: one tag wins"), *AirsoftGameModeLocal::WeaponDisplayName(Next)) : AirsoftGameModeLocal::WeaponDisplayName(Next),
			AirsoftColors::Accent(), 1.6f);
	}
	if (bFinal)
	{
		BroadcastSystem(FString::Printf(TEXT("%s is on the final weapon"), *ShooterPS->GetPlayerName()));
	}
	// Hand the next gun over once this hit has finished processing (we are inside the shooter's hit check).
	TWeakObjectPtr<AController> WeakShooter(Shooter);
	GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this, [this, WeakShooter]()
	{
		if (WeakShooter.IsValid())
		{
			ApplyModeLoadout(WeakShooter.Get());
		}
	}));
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

void AAirsoftGameMode::CountAlive(int32& OutBlue, int32& OutRed) const
{
	OutBlue = 0;
	OutRed = 0;
	for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
	{
		const AAirsoftCharacter* C = *It;
		if (!IsValid(C) || C->IsOut() || !C->GetController())
		{
			continue;
		}
		const EAirsoftTeam Team = C->GetTeam();
		OutBlue += Team == EAirsoftTeam::Blue ? 1 : 0;
		OutRed += Team == EAirsoftTeam::Red ? 1 : 0;
	}
}

void AAirsoftGameMode::UpdateAliveCounts()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	int32 Blue = 0;
	int32 Red = 0;
	CountAlive(Blue, Red);
	if (GS->BlueAlive != Blue)
	{
		GS->BlueAlive = Blue;
	}
	if (GS->RedAlive != Red)
	{
		GS->RedAlive = Red;
	}
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
	const bool bFreeForAll = GS->IsFreeForAll();

	// Removes bots past Want (a tagged-out or pawnless one first, so nobody vanishes mid-fight), adds up to Want.
	auto TrimAndFill = [this, Skill](TArray<AAirsoftBotController*>& Have, int32 Want, EAirsoftTeam Team)
	{
		while (Have.Num() > Want)
		{
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
	};

	// People per side, and the bots we already have per side.
	int32 Humans[2] = { 0, 0 };
	int32 HumansTotal = 0;
	for (APlayerState* P : GS->PlayerArray)
	{
		const AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(P);
		if (!IsValid(PS) || PS->IsABot() || PS->IsInactive())
		{
			continue;
		}
		++HumansTotal;
		Humans[0] += PS->Team == EAirsoftTeam::Blue ? 1 : 0;
		Humans[1] += PS->Team == EAirsoftTeam::Red ? 1 : 0;
	}

	if (bFreeForAll)
	{
		// Free-for-all: the same head count a team fill would give (2 x team size), nobody on a team.
		TArray<AAirsoftBotController*> Have;
		for (AAirsoftBotController* Bot : Bots)
		{
			Have.Add(Bot);
			if (AAirsoftPlayerState* BotPS = Bot->GetPlayerState<AAirsoftPlayerState>())
			{
				BotPS->Team = EAirsoftTeam::None;
			}
		}
		TrimAndFill(Have, TeamSize > 0 ? FMath::Max(0, TeamSize * 2 - HumansTotal) : 0, EAirsoftTeam::None);
	}
	else
	{
		TArray<AAirsoftBotController*> TeamBots[2];
		for (AAirsoftBotController* Bot : Bots)
		{
			const AAirsoftPlayerState* BotPS = Bot->GetPlayerState<AAirsoftPlayerState>();
			TeamBots[(BotPS && BotPS->Team == EAirsoftTeam::Red) ? 1 : 0].Add(Bot);
		}
		// Both sides end up with max(fill size, people on the bigger side): even teams, bots make up the gap.
		const int32 Side = TeamSize > 0 ? FMath::Max3(TeamSize, Humans[0], Humans[1]) : 0;
		for (int32 Index = 0; Index < 2; ++Index)
		{
			TrimAndFill(TeamBots[Index], FMath::Max(0, Side - Humans[Index]), Index == 0 ? EAirsoftTeam::Blue : EAirsoftTeam::Red);
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
	if (!World || !GS || (Team == EAirsoftTeam::None && !GS->IsFreeForAll()))
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
	// Mid-round in a one-life mode the newcomer waits for the next round like everyone else.
	const bool bCanSpawnNow = GS->Phase == EAirsoftPhase::Briefing || (GS->Phase == EAirsoftPhase::Live && AirsoftRules::HasRespawns(GS->Mode));
	if (GS->bIsMatchMap && bCanSpawnNow)
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
	const FAirsoftMapInfo* MapInfo = GS ? AirsoftRules::FindMap(GS->MapId) : nullptr;
	const bool bCloseQuarters = MapInfo && MapInfo->bCloseQuarters;
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
