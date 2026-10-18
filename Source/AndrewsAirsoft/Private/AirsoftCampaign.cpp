#include "AirsoftCampaign.h"

#include "AirsoftBotController.h"
#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "AirsoftTeamStart.h"
#include "AirsoftWeaponData.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerStart.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/PackageName.h"
#include "TimerManager.h"

// ---------------------------------------------------------------------------
// The story
// ---------------------------------------------------------------------------

namespace AirsoftCampaign
{
	FString GameTitle()
	{
		return TEXT("Last Contract");
	}

	const TArray<FMission>& Missions()
	{
		static const TArray<FMission> List = []()
		{
			TArray<FMission> Out;
			{
				FMission M;
				M.Title = TEXT("Closing Time");
				M.MapPath = TEXT("/Game/Maps/L_Staging");
				M.Intro = {
					TEXT("Five years ago Andrew walked away from the Ledger, the syndicate that paid him to settle its debts."),
					TEXT("Now he runs a quiet armory on the edge of the city. Tonight the Ledger has come to settle one with him."),
				};
				M.Objective = TEXT("Survive the hit team");
				M.Enemies = 8;
				M.MaxAlive = 4;
				M.EnemyWeapons = { TEXT("MP5"), TEXT("MP7"), TEXT("M870"), TEXT("VECTOR") };
				M.Outro = TEXT("Every one of them carried a matchbook from the Velvet Club.");
				Out.Add(M);
			}
			{
				FMission M;
				M.Title = TEXT("Velvet");
				M.MapPath = TEXT("/Game/Maps/L_VelvetClub");
				M.Intro = {
					TEXT("The Velvet Club belongs to Silas Varga, the Ledger's new underboss."),
					TEXT("He put the price on Andrew's head. Andrew goes in through the front door."),
				};
				M.Objective = TEXT("Clear the club");
				M.Enemies = 14;
				M.MaxAlive = 6;
				M.EnemyWeapons = { TEXT("MP5"), TEXT("VECTOR"), TEXT("P90"), TEXT("M870"), TEXT("SG4") };
				M.Outro = TEXT("Varga's books name a meeting tonight: the roof of the Nightjar Garage.");
				Out.Add(M);
			}
			{
				FMission M;
				M.Title = TEXT("Nightjar");
				M.MapPath = TEXT("/Game/Maps/L_NightjarGarage");
				M.Intro = {
					TEXT("Three levels of concrete between Andrew and the roof."),
					TEXT("Varga's lieutenants are moving the money tonight. Every floor is watched."),
				};
				M.Objective = TEXT("Fight through the garage");
				M.Enemies = 16;
				M.MaxAlive = 6;
				M.EnemyWeapons = { TEXT("M4"), TEXT("TR1"), TEXT("AK74"), TEXT("MP7"), TEXT("SG4") };
				M.Outro = TEXT("The money is gone, and so is Varga. The trail ends at Ironwood Yard.");
				Out.Add(M);
			}
			{
				FMission M;
				M.Title = TEXT("Ironwood");
				M.MapPath = TEXT("/Game/Maps/L_IronwoodYard");
				M.Intro = {
					TEXT("Ironwood Yard is the Ledger's freight depot, and Varga's last fortress."),
					TEXT("He is waiting with everyone he has left. So is Andrew."),
				};
				M.Objective = TEXT("Break Varga's crew");
				M.Enemies = 20;
				M.MaxAlive = 7;
				M.EnemyWeapons = { TEXT("M4"), TEXT("TR1"), TEXT("AK74"), TEXT("SR25"), TEXT("M249") };
				M.Outro = TEXT("The Ledger's debt is paid in full. Andrew goes home. For now.");
				Out.Add(M);
			}
			return Out;
		}();
		return List;
	}

	const FMission* FindMission(int32 Number)
	{
		const TArray<FMission>& List = Missions();
		return List.IsValidIndex(Number - 1) ? &List[Number - 1] : nullptr;
	}

	float WeaponDamage(FName WeaponId, bool bHeadshot)
	{
		float Damage = 30.f;
		if (WeaponId == TEXT("Grenade"))
		{
			return 110.f;
		}
		if (const FAirsoftWeaponDef* W = AirsoftWeapons::Find(WeaponId))
		{
			if (W->Class == TEXT("Sniper")) Damage = 140.f;
			else if (W->Class == TEXT("DMR")) Damage = 60.f;
			else if (W->Class == TEXT("LMG")) Damage = 28.f;
			else if (W->Class == TEXT("SMG")) Damage = 22.f;
			else if (W->Class == TEXT("Shotgun")) Damage = 34.f;  // per pellet, three pellets a shell
			else if (W->Class == TEXT("Pistol")) Damage = WeaponId == TEXT("DEAGLE") ? 55.f : 28.f;
			else Damage = 30.f;                                   // rifles
		}
		return bHeadshot ? Damage * 2.2f : Damage;
	}

	float EnemyDamageScale(EAirsoftBotSkill Skill)
	{
		switch (Skill)
		{
		case EAirsoftBotSkill::Easy: return 0.3f;
		case EAirsoftBotSkill::Hard: return 0.65f;
		case EAirsoftBotSkill::Expert: return 0.9f;
		default: return 0.45f;
		}
	}

	FString MissionOptions(int32 Number)
	{
		return FString::Printf(TEXT("game=/Script/AndrewsAirsoft.AirsoftCampaignGameMode?Mission=%d"), Number);
	}
}

namespace AirsoftCampaignLocal
{
	const TArray<FString>& EnemyNames()
	{
		static const TArray<FString> Names = {
			TEXT("Ledger Enforcer"), TEXT("Ledger Gunman"), TEXT("Varga's Crew"), TEXT("Ledger Cleaner"),
			TEXT("Ledger Soldier"), TEXT("Hired Gun"), TEXT("Varga's Bodyguard"), TEXT("Ledger Collector")
		};
		return Names;
	}

	const FLinearColor StoryColor(0.9f, 0.88f, 0.85f);
	const FLinearColor DangerColor(1.f, 0.16f, 0.1f);
}

// ---------------------------------------------------------------------------
// Referee
// ---------------------------------------------------------------------------

AAirsoftCampaignGameMode::AAirsoftCampaignGameMode()
{
	// Story missions load straight in: no seamless lobby travel.
	bUseSeamlessTravel = false;
}

void AAirsoftCampaignGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);
	MissionNumber = FMath::Max(1, UGameplayStatics::GetIntOption(Options, TEXT("Mission"), 1));
	if (!AirsoftCampaign::FindMission(MissionNumber))
	{
		MissionNumber = 1;
	}
	// Every story map is fought like a match map (team-vs-team rules), whatever the airsoft map list says.
	bPendingMatchMap = true;
	PendingMode = EAirsoftMode::TDM;
}

void AAirsoftCampaignGameMode::InitGameState()
{
	Super::InitGameState();
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
		GS->bCampaign = true;
		GS->bIsMatchMap = true;
		GS->Mode = EAirsoftMode::TDM;
		GS->MaxRounds = 0;
		GS->MissionNumber = MissionNumber;
		GS->MissionTitle = Mission ? Mission->Title : FString();
		GS->Objective = Mission ? Mission->Objective : FString();
	}
}

void AAirsoftCampaignGameMode::StartPlay()
{
	// Skip the airsoft referee's lobby/match flow: a mission is live from the first frame.
	AGameModeBase::StartPlay();
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	GS->Objectives.Reset();
	for (TActorIterator<AAirsoftObjective> It(GetWorld()); It; ++It)
	{
		It->ServerReset(false);
	}
	GS->Phase = EAirsoftPhase::Live;
	GS->PhaseEndsAt = 0.f;
	UpdateObjectiveText();

	// Story cards first; the first wave arrives as the objective comes up (PlayIntroCard).
	PlayIntroCard(0);

#if !UE_BUILD_SHIPPING
	// Testing aid: ?DebugAutoWin=N kills whatever enemies are up every N seconds (plays the mission chain unattended).
	const int32 AutoWin = UGameplayStatics::GetIntOption(OptionsString, TEXT("DebugAutoWin"), 0);
	if (AutoWin > 0)
	{
		FTimerHandle AutoWinTimer;
		GetWorldTimerManager().SetTimer(AutoWinTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { DebugKillEnemies(); }), static_cast<float>(AutoWin), true);
	}
#endif
}

void AAirsoftCampaignGameMode::PlayIntroCard(int32 Index)
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!Mission || bMissionOver)
	{
		return;
	}
	const FString Title = FString::Printf(TEXT("MISSION %d · %s"), MissionNumber, *Mission->Title.ToUpper());
	if (Mission->Intro.IsValidIndex(Index))
	{
		AnnounceAll(Title, Mission->Intro[Index], AirsoftCampaignLocal::StoryColor, 6.f);
		GetWorldTimerManager().SetTimer(IntroTimer, FTimerDelegate::CreateWeakLambda(this, [this, Index]() { PlayIntroCard(Index + 1); }), 6.2f, false);
	}
	else
	{
		AnnounceAll(Mission->Objective.ToUpper(), FString::Printf(TEXT("%d hostiles · they're coming"), Mission->Enemies), AirsoftColors::Accent(), 3.5f);
		// A breath to get into cover, then the first wave.
		FTimerHandle Start;
		GetWorldTimerManager().SetTimer(Start, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			bEnemiesStarted = true;
			TopUpEnemies();
		}), 3.f, false);
	}
}

void AAirsoftCampaignGameMode::DebugKillEnemies()
{
	APlayerController* Andrew = GetWorld()->GetFirstPlayerController();
	const TArray<TObjectPtr<AAirsoftBotController>> Current = Enemies;
	for (AAirsoftBotController* Bot : Current)
	{
		if (Bot && Bot->GetPawn() && !bMissionOver)
		{
			ApplyCampaignDamage(Andrew, Bot, TEXT("M4"), 10000.f, false);
		}
	}
}

void AAirsoftCampaignGameMode::DebugCompleteMission()
{
	CompleteMission();
}

namespace AirsoftCampaignLocal
{
	// Developer shortcuts for testing the mission flow (console: ~).
	static FAutoConsoleCommandWithWorld GKillEnemies(TEXT("airsoft.campaign.killenemies"),
		TEXT("Story campaign: kills every enemy that is up right now (counts as your kills)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (AAirsoftCampaignGameMode* GM = World ? World->GetAuthGameMode<AAirsoftCampaignGameMode>() : nullptr)
			{
				GM->DebugKillEnemies();
			}
		}));
	static FAutoConsoleCommandWithWorld GComplete(TEXT("airsoft.campaign.complete"),
		TEXT("Story campaign: wins the current mission (unlocks the next one)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (AAirsoftCampaignGameMode* GM = World ? World->GetAuthGameMode<AAirsoftCampaignGameMode>() : nullptr)
			{
				GM->DebugCompleteMission();
			}
		}));
}

void AAirsoftCampaignGameMode::Tick(float DeltaSeconds)
{
	// Not the airsoft referee's tick (no lobby, votes, rounds or bot fill).
	AGameModeBase::Tick(DeltaSeconds);
}

void AAirsoftCampaignGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
	if (AAirsoftPlayerState* PS = NewPlayer ? NewPlayer->GetPlayerState<AAirsoftPlayerState>() : nullptr)
	{
		PS->Team = EAirsoftTeam::Blue; // Andrew; every enemy is Red
	}
	Super::HandleStartingNewPlayer_Implementation(NewPlayer);
}

APawn* AAirsoftCampaignGameMode::FindPlayerPawn() const
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (const APlayerController* PC = It->Get())
		{
			if (APawn* P = PC->GetPawn())
			{
				return P;
			}
		}
	}
	return nullptr;
}

AActor* AAirsoftCampaignGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	const AAirsoftPlayerState* PS = Player ? Player->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	const bool bEnemy = PS && PS->Team == EAirsoftTeam::Red;

	TArray<APlayerStart*> Mine, Neutral, All;
	for (TActorIterator<APlayerStart> It(GetWorld()); It; ++It)
	{
		APlayerStart* Start = *It;
		All.Add(Start);
		const AAirsoftTeamStart* TS = Cast<AAirsoftTeamStart>(Start);
		const EAirsoftTeam StartTeam = TS ? TS->Team : EAirsoftTeam::None;
		if (StartTeam == EAirsoftTeam::None)
		{
			Neutral.Add(Start);
		}
		else if (StartTeam == (bEnemy ? EAirsoftTeam::Red : EAirsoftTeam::Blue))
		{
			Mine.Add(Start);
		}
	}
	const TArray<APlayerStart*>& Pool = Mine.Num() > 0 ? Mine : (Neutral.Num() > 0 ? Neutral : All);
	if (Pool.Num() == 0)
	{
		return Super::ChoosePlayerStart_Implementation(Player);
	}
	if (!bEnemy)
	{
		// Andrew always starts at the same spot so a restart replays the same fight.
		return Pool[0];
	}
	// Enemies: well away from Andrew (never in his face), not on top of each other, a little random.
	const APawn* Andrew = FindPlayerPawn();
	APlayerStart* Best = nullptr;
	float BestScore = -TNumericLimits<float>::Max();
	for (APlayerStart* Start : Pool)
	{
		const FVector Loc = Start->GetActorLocation();
		bool bOccupied = false;
		for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
		{
			if (!It->IsOut() && FVector::Dist(It->GetActorLocation(), Loc) < 110.f)
			{
				bOccupied = true;
			}
		}
		const float Dist = Andrew ? static_cast<float>(FVector::Dist(Andrew->GetActorLocation(), Loc)) : 3000.f;
		// Far is good up to ~25 m; beyond that distance stops mattering so they don't all queue at one end.
		const float Score = FMath::Min(Dist, 2500.f) - (Dist < 1200.f ? 5000.f : 0.f) + FMath::FRandRange(0.f, 900.f) - (bOccupied ? 100000.f : 0.f);
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = Start;
		}
	}
	return Best;
}

void AAirsoftCampaignGameMode::SetPlayerDefaults(APawn* PlayerPawn)
{
	Super::SetPlayerDefaults(PlayerPawn);
	AAirsoftCharacter* C = Cast<AAirsoftCharacter>(PlayerPawn);
	if (!C)
	{
		return;
	}
	C->Health = C->MaxHealth;
	C->ServerSetFrozen(false);
	if (AAirsoftPlayerState* PS = C->GetAirsoftPlayerState())
	{
		PS->ProtectedUntil = 0.f; // no airsoft spawn protection in the story
	}
}

EAirsoftBotSkill AAirsoftCampaignGameMode::Difficulty() const
{
	UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance());
	return AirsoftBots::SkillFromIndex(GI ? GI->GetUserSettings().BotSkill : 1);
}

FAirsoftLoadout AAirsoftCampaignGameMode::MakeEnemyLoadout() const
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	FAirsoftLoadout L = MakeBotLoadout();
	if (Mission && Mission->EnemyWeapons.Num() > 0)
	{
		FAirsoftCustomization Primary;
		Primary.WeaponId = Mission->EnemyWeapons[FMath::RandRange(0, Mission->EnemyWeapons.Num() - 1)];
		if (const FAirsoftWeaponDef* W = AirsoftWeapons::Find(Primary.WeaponId))
		{
			// Iron sights or a red dot: enemies don't need magnified glass.
			if (const TArray<FName>* Optics = W->Options.Find(AirsoftWeapons::SlotOptic))
			{
				Primary.Optic = Optics->Contains(TEXT("RedDot")) && FMath::RandBool() ? FName(TEXT("RedDot")) : AirsoftWeapons::AttachOff;
			}
		}
		L.Primary = AirsoftWeapons::Clean(Primary);
	}
	return L;
}

AAirsoftBotController* AAirsoftCampaignGameMode::SpawnEnemy()
{
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Params.ObjectFlags |= RF_Transient;
	AAirsoftBotController* Bot = GetWorld()->SpawnActor<AAirsoftBotController>(AAirsoftBotController::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Params);
	AAirsoftPlayerState* PS = Bot ? Bot->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!PS)
	{
		if (Bot)
		{
			Bot->Destroy();
		}
		return nullptr;
	}
	const TArray<FString>& Names = AirsoftCampaignLocal::EnemyNames();
	PS->SetPlayerName(Names[FMath::RandRange(0, Names.Num() - 1)]);
	PS->Team = EAirsoftTeam::Red;
	PS->Loadout = MakeEnemyLoadout();
	PS->bLoadoutReceived = true;
	PS->CareerXP = 0;
	Bot->SetSkill(Difficulty());
	Enemies.Add(Bot);
	return Bot;
}

void AAirsoftCampaignGameMode::TopUpEnemies()
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!Mission || bMissionOver || !bEnemiesStarted)
	{
		return;
	}
	int32 Alive = 0;
	for (const AAirsoftBotController* Bot : Enemies)
	{
		const AAirsoftCharacter* C = Bot ? Cast<AAirsoftCharacter>(Bot->GetPawn()) : nullptr;
		Alive += (C && !C->IsOut()) ? 1 : 0;
	}
	while (Alive < Mission->MaxAlive && EnemiesSpawned < Mission->Enemies)
	{
		// Reuse a controller whose last body fell, otherwise hire a new one.
		AAirsoftBotController* Bot = nullptr;
		for (AAirsoftBotController* Candidate : Enemies)
		{
			if (Candidate && !Candidate->GetPawn())
			{
				Bot = Candidate;
				break;
			}
		}
		if (!Bot)
		{
			Bot = SpawnEnemy();
		}
		if (!Bot)
		{
			break;
		}
		if (AAirsoftPlayerState* PS = Bot->GetPlayerState<AAirsoftPlayerState>())
		{
			PS->Loadout = MakeEnemyLoadout();
			PS->bOut = false;
		}
		RestartPlayer(Bot);
		++EnemiesSpawned;
		++Alive;
	}
	UpdateObjectiveText();
}

void AAirsoftCampaignGameMode::UpdateObjectiveText()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!GS || !Mission)
	{
		return;
	}
	GS->EnemiesLeft = FMath::Max(0, Mission->Enemies - EnemiesKilled);
	GS->RedAlive = GS->EnemiesLeft;
	GS->StatusMessage = bMissionOver ? FString() : FString::Printf(TEXT("%s · %d hostiles left"), *Mission->Objective, GS->EnemiesLeft);
}

// ---------------------------------------------------------------------------
// Damage
// ---------------------------------------------------------------------------

bool AAirsoftCampaignGameMode::HandleTag(AController* Shooter, AController* Victim, FName WeaponId)
{
	// Only grenades come through here in the campaign (shots use HandleHit).
	return ApplyCampaignDamage(Shooter, Victim, WeaponId, AirsoftCampaign::WeaponDamage(WeaponId, false), false);
}

bool AAirsoftCampaignGameMode::HandleHit(AController* Shooter, AController* Victim, FName WeaponId, const FVector& HitLocation)
{
	const APawn* VictimPawn = Victim ? Victim->GetPawn() : nullptr;
	// Head: the top ~22 cm of a standing (or crouched) body.
	const bool bHeadshot = VictimPawn && HitLocation.Z > VictimPawn->GetPawnViewLocation().Z - 22.f;
	return ApplyCampaignDamage(Shooter, Victim, WeaponId, AirsoftCampaign::WeaponDamage(WeaponId, bHeadshot), bHeadshot);
}

bool AAirsoftCampaignGameMode::ApplyCampaignDamage(AController* Shooter, AController* Victim, FName WeaponId, float Damage, bool bHeadshot)
{
	if (bMissionOver || !Victim || Shooter == Victim)
	{
		return false;
	}
	AAirsoftCharacter* VictimChar = Cast<AAirsoftCharacter>(Victim->GetPawn());
	const AAirsoftPlayerState* VictimPS = Victim->GetPlayerState<AAirsoftPlayerState>();
	const AAirsoftPlayerState* ShooterPS = Shooter ? Shooter->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!VictimChar || !VictimPS || VictimChar->IsOut())
	{
		return false;
	}
	if (ShooterPS && ShooterPS->Team == VictimPS->Team)
	{
		return false; // enemies don't shoot each other, and nobody else is on Andrew's side
	}
	const bool bVictimIsPlayer = Victim->IsPlayerController();
	if (bVictimIsPlayer)
	{
		Damage *= AirsoftCampaign::EnemyDamageScale(Difficulty());
	}
	const APawn* ShooterPawn = Shooter ? Shooter->GetPawn() : nullptr;
	const FString ShooterName = ShooterPS ? ShooterPS->GetPlayerName() : FString(TEXT("a grenade"));
	const bool bKilled = VictimChar->ServerApplyDamage(Damage, ShooterName, ShooterPawn ? ShooterPawn->GetActorLocation() : VictimChar->GetActorLocation());
	if (bKilled)
	{
		if (bVictimIsPlayer)
		{
			OnPlayerKilled(Victim, ShooterName);
		}
		else
		{
			OnEnemyKilled(Shooter, Victim, WeaponId, bHeadshot);
		}
	}
	return true;
}

void AAirsoftCampaignGameMode::OnEnemyKilled(AController* Shooter, AController* Victim, FName WeaponId, bool bHeadshot)
{
	++EnemiesKilled;
	AAirsoftPlayerState* ShooterPS = Shooter ? Shooter->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	const AAirsoftPlayerState* VictimPS = Victim->GetPlayerState<AAirsoftPlayerState>();
	if (ShooterPS)
	{
		ShooterPS->Round.Tags++;
		ShooterPS->Round.Streak++;
		GiveXP(Shooter, 100, TEXT("ELIMINATED"));
		if (bHeadshot)
		{
			GiveXP(Shooter, 50, TEXT("HEADSHOT"));
		}
		const int32 Streak = ShooterPS->Round.Streak;
		if (Streak == 3 || Streak == 5 || Streak == 8 || Streak == 12)
		{
			GiveXP(Shooter, Streak * 20, FString::Printf(TEXT("STREAK x%d"), Streak));
		}
		// Scavenged ammunition off the body.
		if (AAirsoftCharacter* ShooterChar = Cast<AAirsoftCharacter>(Shooter->GetPawn()))
		{
			ShooterChar->GetCombat()->ServerGiveAmmo(0.5f);
		}
	}
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientKillFeed(ShooterPS ? ShooterPS->GetPlayerName() : FString(TEXT("Grenade")), EAirsoftTeam::Blue,
				VictimPS ? VictimPS->GetPlayerName() : FString(TEXT("Hostile")), EAirsoftTeam::Red, WeaponId);
		}
	}
	// The body stays where it fell (for a while); the controller is free to come back as reinforcements.
	if (APawn* Body = Victim->GetPawn())
	{
		Victim->UnPossess();
		Body->SetLifeSpan(60.f);
	}
	UpdateObjectiveText();

	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (Mission && EnemiesKilled >= Mission->Enemies)
	{
		CompleteMission();
		return;
	}
	// Reinforcements after a short pause, so there's a breath between waves.
	FTimerHandle Refill;
	GetWorldTimerManager().SetTimer(Refill, FTimerDelegate::CreateWeakLambda(this, [this]() { TopUpEnemies(); }), 2.5f, false);
}

void AAirsoftCampaignGameMode::OnPlayerKilled(AController* Victim, const FString& KilledBy)
{
	if (bMissionOver)
	{
		return;
	}
	bMissionOver = true;
	if (AAirsoftPlayerState* PS = Victim->GetPlayerState<AAirsoftPlayerState>())
	{
		PS->LastTaggedBy = KilledBy;
	}
	// The HUD's "DOWN · Killed by ..." overlay says it; no second banner on top.
	UpdateObjectiveText();
	const int32 Number = MissionNumber;
	const FString Map = AirsoftCampaign::FindMission(Number) ? AirsoftCampaign::FindMission(Number)->MapPath : FString();
	GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this, Number, Map]()
	{
		UGameplayStatics::OpenLevel(this, FName(*Map), true, AirsoftCampaign::MissionOptions(Number));
	}), 5.f, false);
}

void AAirsoftCampaignGameMode::CompleteMission()
{
	if (bMissionOver)
	{
		return;
	}
	bMissionOver = true;
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	const int32 Next = MissionNumber + 1;
	const bool bLast = AirsoftCampaign::FindMission(Next) == nullptr;
	if (UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance()))
	{
		if (UAirsoftSaveGame* Profile = GI->GetProfile())
		{
			Profile->CampaignReached = FMath::Max(Profile->CampaignReached, bLast ? MissionNumber : Next);
			Profile->bCampaignFinished = Profile->bCampaignFinished || bLast;
		}
		GI->SaveProfile();
	}
	AnnounceAll(bLast ? TEXT("CONTRACT CLOSED") : TEXT("MISSION COMPLETE"), Mission ? Mission->Outro : FString(), AirsoftColors::Accent(), 7.f);
	UpdateObjectiveText();
	GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this, Next, bLast]()
	{
		UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance());
		if (bLast || !GI)
		{
			if (GI)
			{
				GI->ReturnToMainMenu(FString::Printf(TEXT("%s complete. Thanks for playing."), *AirsoftCampaign::GameTitle()));
			}
			return;
		}
		GI->StartMission(Next);
	}), 8.f, false);
}
