#include "AirsoftBotController.h"

#include "AirsoftBallistics.h"
#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameState.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSettings.h"
#include "AirsoftTeamStart.h"
#include "AirsoftWeaponData.h"
#include "Camera/CameraComponent.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Navigation/PathFollowingComponent.h"
#include "NavigationSystem.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirsoftBot, Log, All);

// Named (not anonymous) so nothing here can collide with other files in a unity build.
namespace AirsoftBotLocal
{
	constexpr float ChestZ = 12.f;               // centre mass, above the capsule centre
	constexpr float PlayerHalfWidth = 30.f;      // for "is the aim on them" checks
	constexpr float CloseSenseRadius = 350.f;    // this close an enemy is noticed outside the view cone (footsteps)
	constexpr float CrouchEyeDrop = 62.f;        // standing eye 164 cm, crouched 102 cm
	constexpr float ThinkInterval = 0.45f;
	constexpr float StuckCheckInterval = 1.f;
	constexpr float StuckMinProgress = 60.f;
	constexpr float ADSDistance = 900.f;
	constexpr float CloseQuarters = 900.f;
	constexpr float WhizRadius = 300.f;          // BBs passing this close count as being shot at
	constexpr float GrenadeMinDistance = 700.f;
	constexpr float GrenadeMaxDistance = 2600.f;
	constexpr float GrenadeMaxFlight = 2.6f;     // fuse is 2.2 s: a little longer still bursts over the target
	constexpr float GrenadeArcCheck = 0.85f;     // clear-path check over this share of the flight (it lands by cover)
	constexpr double SightMemoryGap = 1.5;       // unseen this long = the next sighting is new (react again)
	constexpr double InvestigateMaxAge = 4.0;

	float AngleBetweenDeg(const FVector& A, const FVector& B)
	{
		const double Dot = FVector::DotProduct(A.GetSafeNormal(), B.GetSafeNormal());
		return static_cast<float>(FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(Dot, -1.0, 1.0))));
	}

	FVector RandomUnit2D(FRandomStream& Rng)
	{
		const float Angle = Rng.FRandRange(0.f, 2.f * UE_PI);
		return FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f);
	}

	/** Flies a level BB with the gun's real ballistics until it has covered Distance: flight time and drop below the bore line. */
	void PredictShot(const FAirsoftWeaponDef& W, float Distance, float& OutTime, float& OutDrop)
	{
		FVector Pos = FVector::ZeroVector;
		FVector Vel(W.MuzzleVelocity, 0.f, 0.f);
		constexpr float Dt = 1.f / 60.f;
		float Time = 0.f;
		for (int32 Step = 0; Step < 300 && Pos.X < Distance && Vel.X > 300.0; ++Step)
		{
			Vel = AirsoftBallistics::Step(Vel, W.MuzzleVelocity, W.Hop, W.Drag, Dt);
			Pos += Vel * Dt;
			Time += Dt;
		}
		OutTime = Time;
		OutDrop = static_cast<float>(-Pos.Z);
	}

	/** Launch direction for the grenade (fixed throw speed) to land on To; low or high arc. */
	bool SolveGrenadeArc(const FVector& From, const FVector& To, bool bHigh, double Gravity, FVector& OutDir, float& OutTime)
	{
		const double Speed = AirsoftWeapons::GrenadeThrowSpeed;
		const FVector Delta = To - From;
		const double Dx = Delta.Size2D();
		const double Dz = Delta.Z;
		if (Dx < 50.0 || Gravity <= 0.0)
		{
			return false;
		}
		const double S2 = Speed * Speed;
		const double Disc = S2 * S2 - Gravity * (Gravity * Dx * Dx + 2.0 * Dz * S2);
		if (Disc < 0.0)
		{
			return false;
		}
		const double Root = FMath::Sqrt(Disc);
		const double Angle = FMath::Atan((S2 + (bHigh ? Root : -Root)) / (Gravity * Dx));
		const FVector Flat = Delta.GetSafeNormal2D();
		OutDir = (Flat * FMath::Cos(Angle) + FVector::UpVector * FMath::Sin(Angle)).GetSafeNormal();
		OutTime = static_cast<float>(Dx / FMath::Max(Speed * FMath::Cos(Angle), 1.0));
		return true;
	}

	bool IsArcClear(const UWorld* World, const FVector& From, const FVector& Velocity, double Gravity, float Duration, const AActor* Ignore)
	{
		FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftBotGrenadeArc), false, Ignore);
		FVector Prev = From;
		constexpr int32 Steps = 10;
		for (int32 Step = 1; Step <= Steps; ++Step)
		{
			const double Time = static_cast<double>(Duration) * Step / Steps;
			const FVector Point = From + Velocity * Time + FVector(0.0, 0.0, -0.5 * Gravity * Time * Time);
			FHitResult Hit;
			if (World->LineTraceSingleByChannel(Hit, Prev, Point, ECC_Visibility, Query))
			{
				return false;
			}
			Prev = Point;
		}
		return true;
	}

	void WarnNoNavigationOnce(const UWorld* World)
	{
		static bool bWarned = false;
		if (!bWarned)
		{
			bWarned = true;
			UE_LOG(LogAirsoftBot, Warning, TEXT("Bots can't find a path on %s - is there a navmesh? Re-run Content/Python/airsoft_setup.py (it places a NavMeshBoundsVolume over each match map) or add one by hand."),
				World ? *World->GetMapName() : TEXT("this map"));
		}
	}
}

AAirsoftBotController::AAirsoftBotController(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// A PlayerState gives the bot a scoreboard row, a team and a loadout, exactly like a person.
	bWantsPlayerState = true;
	PrimaryActorTick.bCanEverTick = true;
	Rng.GenerateNewSeed();
	PersonalityReaction = Rng.FRandRange(0.88f, 1.15f);
	PersonalityAim = Rng.FRandRange(0.85f, 1.15f);
}

// ---------------------------------------------------------------------------
// Basics
// ---------------------------------------------------------------------------

AAirsoftCharacter* AAirsoftBotController::GetBotCharacter() const
{
	return Cast<AAirsoftCharacter>(GetPawn());
}

UAirsoftCombatComponent* AAirsoftBotController::GetBotCombat() const
{
	const AAirsoftCharacter* C = GetBotCharacter();
	return C ? C->GetCombat() : nullptr;
}

EAirsoftTeam AAirsoftBotController::GetBotTeam() const
{
	const AAirsoftPlayerState* PS = GetPlayerState<AAirsoftPlayerState>();
	return PS ? PS->Team : EAirsoftTeam::None;
}

FVector AAirsoftBotController::GetEyeLocation() const
{
	// The camera is where shots start (eye height, crouch and lean included).
	if (const AAirsoftCharacter* C = GetBotCharacter())
	{
		return C->GetCamera() ? C->GetCamera()->GetComponentLocation() : C->GetPawnViewLocation();
	}
	return GetActorLocation();
}

double AAirsoftBotController::WorldTime() const
{
	const UWorld* World = GetWorld();
	return World ? World->GetTimeSeconds() : 0.0;
}

void AAirsoftBotController::SetSkill(EAirsoftBotSkill InSkill)
{
	if (bSkillSet && InSkill == Skill)
	{
		return;
	}
	bSkillSet = true;
	Skill = InSkill;
	Tune = UAirsoftSettings::Get()->GetBotTuning(Skill);
}

void AAirsoftBotController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);
	ResetBrain();
	if (AAirsoftCharacter* Me = Cast<AAirsoftCharacter>(InPawn))
	{
		// Never step off a roof, platform or the catwalk: bots only go where the navmesh connects.
		if (UCharacterMovementComponent* Move = Me->GetCharacterMovement())
		{
			Move->bCanWalkOffLedges = false;
		}
		CacheSpawns(Me);
	}
	bDefender = Rng.FRand() < 0.25f;
	for (float& Bias : ObjectiveBias)
	{
		Bias = Rng.FRandRange(-120.f, 120.f);
	}
}

void AAirsoftBotController::OnUnPossess()
{
	ReleaseTrigger();
	Super::OnUnPossess();
	ResetBrain();
}

void AAirsoftBotController::ResetBrain()
{
	const double T = WorldTime();
	State = EAirsoftBotState::Idle;
	Memory.Reset();
	Target.Reset();
	GoalObjective.Reset();
	bHasDesiredRotation = false;
	TurnScale = 1.f;
	AimError = 0.f;
	bTriggerHeld = false;
	BurstLength = 0;
	NextTriggerAt = 0.0;
	bHasMoveGoal = false;
	bWantSprint = false;
	bSprinting = false;
	bWalkingOff = false;
	bHoldCrouch = false;
	StuckStrikes = 0;
	MoveFailures = 0;
	CombatMove = EAirsoftBotCombatMove::Stand;
	LastLandmark = INDEX_NONE;
	NextSightAt = T + Rng.FRandRange(0.f, 0.2f);
	NextThinkAt = T + Rng.FRandRange(0.f, 0.4f);
	NextGoalAt = 0.0;
	NextCombatMoveAt = 0.0;
	NextGrenadeAt = T + Rng.FRandRange(8.f, 16.f); // no grenade straight off the spawn
	NextScanAt = 0.0;
	HoldUntil = 0.0;
	GoalExpiresAt = 0.0;
	InvestigateUntil = 0.0;
	InvestigatedStamp = -1.0;
	LastCombatAt = -100.0;
	UnderFireUntil = 0.0;
}

void AAirsoftBotController::CacheSpawns(const AAirsoftCharacter* Me)
{
	const EAirsoftTeam MyTeam = GetBotTeam();
	FVector Home = FVector::ZeroVector;
	FVector Enemy = FVector::ZeroVector;
	int32 NumHome = 0;
	int32 NumEnemy = 0;
	for (TActorIterator<AAirsoftTeamStart> It(GetWorld()); It; ++It)
	{
		const AAirsoftTeamStart* Start = *It;
		if (!Start || Start->Team == EAirsoftTeam::None)
		{
			continue;
		}
		if (Start->Team == MyTeam)
		{
			Home += Start->GetActorLocation();
			++NumHome;
		}
		else
		{
			Enemy += Start->GetActorLocation();
			++NumEnemy;
		}
	}
	bHaveSpawns = NumHome > 0 && NumEnemy > 0;
	HomeSpawn = NumHome > 0 ? Home / static_cast<double>(NumHome) : Me->GetActorLocation();
	EnemySpawn = NumEnemy > 0 ? Enemy / static_cast<double>(NumEnemy) : Me->GetActorLocation() + Me->GetActorForwardVector() * 5000.f;
}

// ---------------------------------------------------------------------------
// Tick
// ---------------------------------------------------------------------------

void AAirsoftBotController::Tick(float DeltaSeconds)
{
	// Decide first, then Super::Tick turns the view (UpdateControlRotation) toward what we decided.
	if (HasAuthority())
	{
		UpdateBrain(DeltaSeconds);
	}
	Super::Tick(DeltaSeconds);
}

void AAirsoftBotController::UpdateBrain(float DeltaSeconds)
{
	AAirsoftCharacter* Me = GetBotCharacter();
	const UWorld* World = GetWorld();
	const AAirsoftGameState* GS = World ? World->GetGameState<AAirsoftGameState>() : nullptr;
	if (!Me || !GS || !Me->GetCombat())
	{
		return;
	}
	if (!bHasDesiredRotation)
	{
		// First tick on a fresh pawn: start from the spawn point's facing.
		DesiredRotation = GetControlRotation();
		DesiredRotation.Pitch = 0.f;
		DesiredRotation.Roll = 0.f;
		HomeYaw = static_cast<float>(DesiredRotation.Yaw);
		bHasDesiredRotation = true;
	}
	if (Me->IsOut())
	{
		TickWalkOff(Me);
		return;
	}
	bWalkingOff = false;
	if (!GS->bIsMatchMap || GS->Phase != EAirsoftPhase::Live || Me->IsFrozen())
	{
		TickIdle(Me);
		return;
	}
	TickLive(Me, DeltaSeconds);
}

void AAirsoftBotController::TickIdle(AAirsoftCharacter* Me)
{
	ReleaseTrigger();
	Me->GetCombat()->BotSetAim(false);
	if (bSprinting)
	{
		Me->SetSprintHeld(false);
		bSprinting = false;
	}
	if (IsMoving())
	{
		StopMovement();
	}
	bHasMoveGoal = false;
	Target.Reset();
	State = EAirsoftBotState::Idle;
	TurnScale = 0.35f;
	// Glance around while frozen for the briefing.
	const double T = WorldTime();
	if (T >= NextScanAt)
	{
		NextScanAt = T + Rng.FRandRange(1.5f, 3.5f);
		DesiredRotation = FRotator(Rng.FRandRange(-6.f, 3.f), HomeYaw + Rng.FRandRange(-35.f, 35.f), 0.f);
	}
}

void AAirsoftBotController::TickWalkOff(AAirsoftCharacter* Me)
{
	if (!bWalkingOff)
	{
		// Tagged, like a person: stop fighting, rag up (the character shows it), walk back toward our spawn.
		bWalkingOff = true;
		State = EAirsoftBotState::WalkOff;
		ReleaseTrigger();
		Me->GetCombat()->BotSetAim(false);
		Target.Reset();
		if (bSprinting)
		{
			Me->SetSprintHeld(false);
			bSprinting = false;
		}
		if (Me->bIsCrouched)
		{
			Me->UnCrouch();
		}
		FVector Home;
		if (RandomPointNear(HomeSpawn, 600.f, Home))
		{
			MoveToPoint(Home, 150.f, false);
		}
		else
		{
			StopMovement();
		}
	}
	TurnScale = 0.5f;
	const FVector Vel = Me->GetVelocity();
	if (Vel.SizeSquared2D() > FMath::Square(100.f))
	{
		DesiredRotation = FRotator(-10.f, static_cast<float>(Vel.Rotation().Yaw), 0.f);
	}
}

void AAirsoftBotController::TickLive(AAirsoftCharacter* Me, float DeltaSeconds)
{
	const double T = WorldTime();
	if (T >= NextSightAt)
	{
		NextSightAt = T + Tune.SightInterval * Rng.FRandRange(0.8f, 1.2f);
		UpdateSight(Me);
		ChooseTarget(Me);
	}

	if (Target.IsValid())
	{
		Engage(Me, DeltaSeconds);
	}
	else
	{
		ReleaseTrigger();
		Me->GetCombat()->BotSetAim(false);
		if (State == EAirsoftBotState::Engage)
		{
			State = EAirsoftBotState::Advance;
		}
		CombatMove = EAirsoftBotCombatMove::Stand;
		if (Me->bIsCrouched && !bHoldCrouch)
		{
			Me->UnCrouch();
		}
		if (T >= NextThinkAt)
		{
			NextThinkAt = T + AirsoftBotLocal::ThinkInterval * Rng.FRandRange(0.8f, 1.2f);
			Think(Me);
		}
		UpdateLook(Me);
	}
	UpdateMovement(Me);
}

void AAirsoftBotController::UpdateControlRotation(float DeltaTime, bool bUpdatePawn)
{
	APawn* const MyPawn = GetPawn();
	if (!MyPawn || !bHasDesiredRotation)
	{
		Super::UpdateControlRotation(DeltaTime, bUpdatePawn);
		return;
	}
	FRotator Current = GetControlRotation();
	Current.Pitch = FRotator::NormalizeAxis(Current.Pitch);
	Current.Yaw = FRotator::NormalizeAxis(Current.Yaw);
	Current.Roll = 0.f;
	const FRotator Delta = (DesiredRotation - Current).GetNormalized();
	// Proportional tracking (quick flick, gentle settle) capped by the bot's turn speed. Recoil from
	// the combat component kicks the control rotation; this pulls it back like a person would.
	const float MaxStep = Tune.TurnRate * TurnScale * DeltaTime;
	const float Gain = FMath::Clamp(DeltaTime * 14.f, 0.f, 1.f);
	const float StepYaw = FMath::Clamp(static_cast<float>(Delta.Yaw) * Gain, -MaxStep, MaxStep);
	const float StepPitch = FMath::Clamp(static_cast<float>(Delta.Pitch) * Gain, -MaxStep, MaxStep);
	Current.Yaw = FRotator::NormalizeAxis(Current.Yaw + StepYaw);
	Current.Pitch = FMath::Clamp(static_cast<float>(Current.Pitch) + StepPitch, -85.f, 85.f);
	SetControlRotation(Current);
	if (bUpdatePawn && !MyPawn->GetActorRotation().Equals(Current, 1e-3f))
	{
		MyPawn->FaceRotation(Current, DeltaTime);
	}
}

// ---------------------------------------------------------------------------
// Perception
// ---------------------------------------------------------------------------

AAirsoftBotController::FBotMemory& AAirsoftBotController::Remember(AAirsoftCharacter* Enemy)
{
	for (FBotMemory& M : Memory)
	{
		if (M.Enemy.Get() == Enemy)
		{
			return M;
		}
	}
	FBotMemory& M = Memory.AddDefaulted_GetRef();
	M.Enemy = Enemy;
	return M;
}

AAirsoftBotController::FBotMemory* AAirsoftBotController::FindMemory(const AAirsoftCharacter* Enemy)
{
	if (!Enemy)
	{
		return nullptr;
	}
	for (FBotMemory& M : Memory)
	{
		if (M.Enemy.Get() == Enemy)
		{
			return &M;
		}
	}
	return nullptr;
}

void AAirsoftBotController::ForgetStale()
{
	const double T = WorldTime();
	const double Keep = Tune.MemoryTime;
	Memory.RemoveAll([T, Keep](const FBotMemory& M)
	{
		const AAirsoftCharacter* Enemy = M.Enemy.Get();
		return !Enemy || Enemy->IsOut() || (!M.bVisible && T - FMath::Max(M.LastSeen, M.LastHeard) > Keep);
	});
}

const AAirsoftBotController::FBotMemory* AAirsoftBotController::FreshestUnseen(const FVector& From, float MaxDistance) const
{
	const FBotMemory* Best = nullptr;
	double BestTime = -1.0;
	for (const FBotMemory& M : Memory)
	{
		if (M.bVisible || !M.Enemy.IsValid())
		{
			continue;
		}
		const double When = FMath::Max(M.LastSeen, M.LastHeard);
		if (When > BestTime && FVector::Dist(From, M.LastKnown) <= MaxDistance)
		{
			Best = &M;
			BestTime = When;
		}
	}
	return Best;
}

bool AAirsoftBotController::CanSee(const FVector& Eye, const AAirsoftCharacter* Other, float& OutAimZ) const
{
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftBotSight), false, GetPawn());
	Query.AddIgnoredActor(Other);
	FHitResult Hit;
	const FVector Base = Other->GetActorLocation();
	// Centre mass first, then the head (peeking over cover). Same channel the server's hit check uses.
	if (!GetWorld()->LineTraceSingleByChannel(Hit, Eye, Base + FVector(0.f, 0.f, AirsoftBotLocal::ChestZ), ECC_Visibility, Query))
	{
		OutAimZ = AirsoftBotLocal::ChestZ;
		return true;
	}
	const float HeadZ = static_cast<float>(Other->GetPawnViewLocation().Z - Base.Z) - 4.f;
	if (!GetWorld()->LineTraceSingleByChannel(Hit, Eye, Base + FVector(0.f, 0.f, HeadZ), ECC_Visibility, Query))
	{
		OutAimZ = HeadZ;
		return true;
	}
	return false;
}

bool AAirsoftBotController::CanSeeFrom(const FVector& Eye, const AAirsoftCharacter* Other) const
{
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftBotSight), false, GetPawn());
	Query.AddIgnoredActor(Other);
	FHitResult Hit;
	return !GetWorld()->LineTraceSingleByChannel(Hit, Eye, Other->GetActorLocation() + FVector(0.f, 0.f, AirsoftBotLocal::ChestZ), ECC_Visibility, Query);
}

void AAirsoftBotController::UpdateSight(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	const EAirsoftTeam MyTeam = Me->GetTeam();
	const FVector Eye = GetEyeLocation();
	const FVector Forward = GetControlRotation().Vector();
	const float CosHalf = FMath::Cos(FMath::DegreesToRadians(Tune.ViewHalfAngle));
	for (FBotMemory& M : Memory)
	{
		M.bVisible = false;
	}
	for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
	{
		AAirsoftCharacter* Other = *It;
		if (!IsValid(Other) || Other == Me || Other->IsOut())
		{
			continue;
		}
		const EAirsoftTeam OtherTeam = Other->GetTeam();
		if (OtherTeam == EAirsoftTeam::None || OtherTeam == MyTeam)
		{
			continue;
		}
		const FVector To = Other->GetActorLocation() - Eye;
		const float Dist = static_cast<float>(To.Size());
		if (Dist < 1.f || Dist > Tune.SightRange)
		{
			continue;
		}
		const float Facing = static_cast<float>(FVector::DotProduct(To / Dist, Forward));
		const bool bTracked = Other == Target.Get();
		if (!bTracked && Dist > AirsoftBotLocal::CloseSenseRadius && Facing < CosHalf)
		{
			continue;
		}
		float AimZ = AirsoftBotLocal::ChestZ;
		if (!CanSee(Eye, Other, AimZ))
		{
			continue;
		}
		FBotMemory& M = Remember(Other);
		if (T - M.LastSeen > AirsoftBotLocal::SightMemoryGap)
		{
			// A new sighting: notice, then react. Slower for far, crouched-and-still or peripheral
			// targets; quicker when we already heard them.
			float React = (Tune.ReactionTime + Tune.ReactionPer10m * Dist / 1000.f) * PersonalityReaction;
			if (Other->bIsCrouched && Other->GetVelocity().SizeSquared2D() < FMath::Square(50.f))
			{
				React += 0.25f;
			}
			if (Facing < 0.9f)
			{
				React += 0.15f;
			}
			if (T - M.LastHeard < 2.0)
			{
				React *= 0.7f;
			}
			M.NoticeAt = T + React * 0.4f;
			M.FireReadyAt = T + React;
		}
		M.bVisible = true;
		M.LastSeen = T;
		M.LastKnown = Other->GetActorLocation();
		M.Velocity = Other->GetVelocity();
		M.AimZ = AimZ;
	}
	ForgetStale();
}

void AAirsoftBotController::HearShot(AAirsoftCharacter* Shooter, const FVector& Origin, const FVector& Direction, bool bQuiet)
{
	AAirsoftCharacter* Me = GetBotCharacter();
	if (!Me || !Shooter || Shooter == Me || Me->IsOut())
	{
		return;
	}
	const EAirsoftTeam ShooterTeam = Shooter->GetTeam();
	if (ShooterTeam == EAirsoftTeam::None || ShooterTeam == Me->GetTeam())
	{
		return;
	}
	const FVector Head = GetEyeLocation();
	const float Dist = static_cast<float>(FVector::Dist(Origin, Head));
	// Did it come our way? BBs cracking past within a few metres.
	const FVector Dir = Direction.GetSafeNormal();
	const double Along = FVector::DotProduct(Head - Origin, Dir);
	const bool bAtMe = Along > 0.0 && FVector::Dist(Origin + Dir * Along, Head) < AirsoftBotLocal::WhizRadius;
	const UAirsoftSettings* S = UAirsoftSettings::Get();
	const float Range = (bQuiet ? S->BotQuietHearingRange : S->BotHearingRange) * Tune.HearingScale;
	if (!bAtMe && Dist > Range)
	{
		return;
	}
	const double T = WorldTime();
	FBotMemory& M = Remember(Shooter);
	if (!M.bVisible)
	{
		// A heard position is only roughly right - better the closer it is.
		const float Fuzz = bAtMe ? 150.f : Dist * 0.1f;
		M.LastKnown = Origin - FVector(0.f, 0.f, 70.f) + FVector(Rng.FRandRange(-Fuzz, Fuzz), Rng.FRandRange(-Fuzz, Fuzz), 0.f);
	}
	M.LastHeard = T;
	if (bAtMe || (!Target.IsValid() && Dist < Range * 0.5f))
	{
		ThreatPoint = Origin;
		UnderFireUntil = T + (bAtMe ? 1.5 : 0.7);
	}
}

// ---------------------------------------------------------------------------
// Combat
// ---------------------------------------------------------------------------

void AAirsoftBotController::ChooseTarget(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	const FVector Eye = GetEyeLocation();
	const FVector Forward = GetControlRotation().Vector();
	AAirsoftCharacter* Best = nullptr;
	float BestScore = TNumericLimits<float>::Max();
	for (const FBotMemory& M : Memory)
	{
		AAirsoftCharacter* Enemy = M.Enemy.Get();
		if (!Enemy || !M.bVisible || Enemy->IsOut() || T < M.NoticeAt)
		{
			continue;
		}
		// Spawn-protected players can't be tagged: no point wasting BBs (it ends when they shoot).
		const AAirsoftPlayerState* EnemyPS = Enemy->GetAirsoftPlayerState();
		if (EnemyPS && EnemyPS->IsProtected())
		{
			continue;
		}
		const FVector To = Enemy->GetActorLocation() - Eye;
		float Score = static_cast<float>(To.Size()) * (1.f + AirsoftBotLocal::AngleBetweenDeg(Forward, To) / 120.f);
		if (Enemy == Target.Get())
		{
			Score *= 0.6f; // stay on the current fight
		}
		if (Score < BestScore)
		{
			BestScore = Score;
			Best = Enemy;
		}
	}
	if (Best == Target.Get())
	{
		return;
	}
	const bool bWasFighting = Target.IsValid();
	ReleaseTrigger();
	Target = Best;
	if (Best)
	{
		// A fresh target starts with a wide aim error; switching mid-fight is a bit tighter.
		AimError = Tune.AimErrorStart * PersonalityAim * (bWasFighting ? 0.6f : 1.f);
		AimErrorAngle = Rng.FRandRange(0.f, 2.f * UE_PI);
		State = EAirsoftBotState::Engage;
		NextCombatMoveAt = T + Rng.FRandRange(0.2f, 0.6f);
		if (bSprinting)
		{
			Me->SetSprintHeld(false);
			bSprinting = false;
		}
	}
}

void AAirsoftBotController::Engage(AAirsoftCharacter* Me, float DeltaSeconds)
{
	const double T = WorldTime();
	AAirsoftCharacter* Enemy = Target.Get();
	FBotMemory* M = FindMemory(Enemy);
	UAirsoftCombatComponent* Combat = Me->GetCombat();
	if (!Enemy || !M || Enemy->IsOut() || !M->bVisible)
	{
		// Lost them: go and look where they were heading.
		const bool bKnown = Enemy && M && !Enemy->IsOut();
		const FVector Last = bKnown ? M->LastKnown + M->Velocity * 0.6f : FVector::ZeroVector;
		if (bKnown)
		{
			InvestigatedStamp = FMath::Max(M->LastSeen, M->LastHeard);
		}
		Target.Reset();
		ReleaseTrigger();
		if (bKnown)
		{
			StartInvestigate(Last);
		}
		return;
	}
	State = EAirsoftBotState::Engage;
	LastCombatAt = T;
	TurnScale = 1.f;
	bHoldCrouch = false;
	if (bSprinting)
	{
		Me->SetSprintHeld(false);
		bSprinting = false;
	}
	ManageWeapon(Me);

	const FAirsoftWeaponDef& W = Combat->Current();
	const FVector Eye = GetEyeLocation();
	const FVector EnemyLoc = Enemy->GetActorLocation();
	FVector AimPoint = EnemyLoc + FVector(0.f, 0.f, M->AimZ);
	const float Dist = static_cast<float>(FVector::Dist(Eye, AimPoint));
	const bool bNoticed = T >= M->NoticeAt;
	const bool bReactionDone = T >= M->FireReadyAt;

	// Lead and holdover from the gun's real BB flight, as well as this bot can judge it.
	float Flight = 0.f;
	float Drop = 0.f;
	AirsoftBotLocal::PredictShot(W, Dist, Flight, Drop);
	const FVector EnemyVel = Enemy->GetVelocity();
	AimPoint += EnemyVel * (Flight * Tune.LeadSkill);
	AimPoint.Z += Drop * Tune.LeadSkill;

	// Aim error: wide at first, settling toward a floor that rises when the target or the bot moves,
	// and wandering around the target rather than sitting on one side of it.
	const FVector ToDir = (EnemyLoc - Eye).GetSafeNormal();
	const float Lateral = static_cast<float>((EnemyVel - ToDir * FVector::DotProduct(EnemyVel, ToDir)).Size());
	const float MySpeed = static_cast<float>(Me->GetVelocity().Size2D());
	const float Floor = Tune.AimErrorMin * PersonalityAim + Tune.TargetMoveError * Lateral / 100.f
		+ Tune.SelfMoveError * FMath::Min(MySpeed / 430.f, 1.5f);
	if (bNoticed)
	{
		AimError = Floor + (AimError - Floor) * FMath::Exp(-Tune.AimSettleRate * DeltaSeconds);
		AimErrorAngle += Rng.FRandRange(-4.f, 4.f) * DeltaSeconds;
		FRotator Want = (AimPoint - Eye).Rotation();
		Want.Yaw += AimError * FMath::Cos(AimErrorAngle);
		Want.Pitch += AimError * FMath::Sin(AimErrorAngle) * 0.6f; // people miss wide more than high
		Want.Roll = 0.f;
		DesiredRotation = Want;
	}

	// Pull the trigger once the view has caught up with where the bot means to aim.
	const float SizeDeg = FMath::RadiansToDegrees(FMath::Atan2(AirsoftBotLocal::PlayerHalfWidth, FMath::Max(Dist, 1.f)));
	const float Lag = AirsoftBotLocal::AngleBetweenDeg(GetControlRotation().Vector(), DesiredRotation.Vector());
	const float Allowed = SizeDeg * Tune.TriggerDiscipline + 0.3f;
	const bool bInRange = Dist <= W.MaxRange * 0.92f;

	// Aim down sights at range (marksman guns always), hip-fire up close.
	const bool bLongGun = W.Class == TEXT("Sniper") || W.Class == TEXT("DMR");
	const bool bShotgun = W.Class == TEXT("Shotgun");
	const bool bWantADS = bNoticed && !Combat->IsReloading() && (bLongGun ? Dist > 400.f : (!bShotgun && Dist > AirsoftBotLocal::ADSDistance));
	Combat->BotSetAim(bWantADS);
	// Like a person, wait for the sights to come up before the first shot.
	const bool bSightsUp = !bWantADS || Combat->GetAimAlpha() >= (bLongGun ? 0.9f : 0.6f);

	const bool bReady = bNoticed && bReactionDone && bInRange && !Combat->IsReloading() && !Combat->IsThrowing();
	const bool bCanStart = bReady && bSightsUp && Lag <= Allowed && AimError <= Allowed * 3.f + 1.5f;
	const bool bCanContinue = bReady && Lag <= Allowed * 3.f;

	// Stance and movement while fighting.
	if (!bInRange)
	{
		// Out of reach for this gun: close the distance.
		if (!IsMoving() || T >= NextCombatMoveAt)
		{
			NextCombatMoveAt = T + 2.0;
			FVector Point;
			if (RandomPointNear(EnemyLoc, 800.f, Point))
			{
				MoveToPoint(Point, 300.f, false);
			}
		}
	}
	else if (bNoticed && T >= NextCombatMoveAt)
	{
		PickCombatMove(Me, Enemy, Dist);
	}
	else if (Combat->IsReloading() && !Me->bIsCrouched
		&& !CanSeeFrom(Eye - FVector(0.f, 0.f, AirsoftBotLocal::CrouchEyeDrop), Enemy))
	{
		// Duck behind cover to reload when crouching hides us.
		StopMovement();
		Me->Crouch();
		CombatMove = EAirsoftBotCombatMove::Crouch;
	}

	// Now and then, lob the grenade at a bunch of them.
	if (T >= NextGrenadeAt && TryGrenade(Me))
	{
		return;
	}
	SelectFireMode(Combat, Dist);
	UpdateTrigger(Combat, Dist, bCanStart, bCanContinue);
}

void AAirsoftBotController::PickCombatMove(AAirsoftCharacter* Me, const AAirsoftCharacter* Enemy, float Distance)
{
	const double T = WorldTime();
	NextCombatMoveAt = T + Rng.FRandRange(1.f, 2.4f);
	const bool bClose = Distance < AirsoftBotLocal::CloseQuarters;
	const float StrafeChance = FMath::Clamp(Tune.StrafeChance + (bClose ? 0.25f : 0.f), 0.f, 0.95f);
	const float CrouchChance = bClose ? Tune.CrouchChance * 0.3f : Tune.CrouchChance;
	const float Roll = Rng.FRand();
	const FVector MyLoc = Me->GetActorLocation();
	const FVector EnemyLoc = Enemy->GetActorLocation();

	if (Roll < StrafeChance)
	{
		// Side-step a few metres (staying on the point when taking or holding one).
		if (Me->bIsCrouched)
		{
			Me->UnCrouch();
		}
		const FVector ToEnemy = (EnemyLoc - MyLoc).GetSafeNormal2D();
		const FVector Side = FVector::CrossProduct(FVector::UpVector, ToEnemy) * (Rng.FRand() < 0.5f ? -1.f : 1.f);
		FVector Wanted = MyLoc + Side * Rng.FRandRange(200.f, 450.f) + ToEnemy * Rng.FRandRange(-150.f, 100.f);
		if (const AAirsoftObjective* Obj = GoalObjective.Get())
		{
			if (Obj->bActive && Obj->IsInside(MyLoc))
			{
				const FVector Center = Obj->GetActorLocation();
				FVector Offset = Wanted - Center;
				Offset.Z = 0.f;
				const float MaxRadius = Obj->Radius * 0.8f;
				if (Offset.Size2D() > MaxRadius)
				{
					Wanted = Center + Offset.GetSafeNormal2D() * MaxRadius + FVector(0.f, 0.f, Wanted.Z - Center.Z);
				}
			}
		}
		FVector Point;
		if (ProjectToNav(Wanted, Point))
		{
			MoveToPoint(Point, 40.f, false);
		}
		CombatMove = EAirsoftBotCombatMove::Strafe;
		return;
	}

	StopMovement();
	bHasMoveGoal = false;
	const FVector CrouchEye = GetEyeLocation() - FVector(0.f, 0.f, AirsoftBotLocal::CrouchEyeDrop);
	if (Roll < StrafeChance + CrouchChance && (Me->bIsCrouched || CanSeeFrom(CrouchEye, Enemy)))
	{
		// Crouch only where we can still see them (steadier aim, smaller target).
		Me->Crouch();
		CombatMove = EAirsoftBotCombatMove::Crouch;
	}
	else
	{
		if (Me->bIsCrouched)
		{
			Me->UnCrouch();
		}
		CombatMove = EAirsoftBotCombatMove::Stand;
	}
}

void AAirsoftBotController::SelectFireMode(UAirsoftCombatComponent* Combat, float Distance)
{
	if (bTriggerHeld)
	{
		return; // never mid-burst
	}
	EAirsoftFireMode Wanted = Combat->GetFireMode();
	if (Combat->HasFireMode(EAirsoftFireMode::Auto) && Distance < 1800.f)
	{
		Wanted = EAirsoftFireMode::Auto;
	}
	else if (Combat->HasFireMode(EAirsoftFireMode::Burst) && Distance < 3200.f)
	{
		Wanted = EAirsoftFireMode::Burst;
	}
	else if (Combat->HasFireMode(EAirsoftFireMode::Semi))
	{
		Wanted = EAirsoftFireMode::Semi;
	}
	if (Wanted != Combat->GetFireMode())
	{
		Combat->BotSetFireMode(Wanted);
	}
}

void AAirsoftBotController::UpdateTrigger(UAirsoftCombatComponent* Combat, float Distance, bool bCanStart, bool bCanContinue)
{
	const double T = WorldTime();
	const FAirsoftWeaponDef& W = Combat->Current();
	const EAirsoftFireMode Mode = Combat->GetFireMode();
	if (Mode == EAirsoftFireMode::Auto)
	{
		if (bTriggerHeld)
		{
			const int32 Fired = BurstStartMag - Combat->GetLocalMag();
			if (!bCanContinue || Fired >= BurstLength || Combat->GetLocalMag() <= 0)
			{
				ReleaseTrigger();
				NextTriggerAt = T + Tune.BurstPause * Rng.FRandRange(0.7f, 1.3f) * FMath::Clamp(Distance / 1500.f, 0.6f, 2.f);
			}
			return;
		}
		if (bCanStart && T >= NextTriggerAt && Combat->GetLocalMag() > 0)
		{
			// Long bursts up close, short controlled ones at range.
			const float Close = FMath::Clamp(1.f - Distance / 2500.f, 0.f, 1.f);
			const int32 MaxShots = FMath::Max(Tune.BurstMin, FMath::RoundToInt(FMath::Lerp(static_cast<float>(Tune.BurstMin), static_cast<float>(Tune.BurstMax), Close)));
			BurstLength = Rng.RandRange(FMath::Max(Tune.BurstMin, 1), FMath::Max(MaxShots, 1));
			BurstStartMag = Combat->GetLocalMag();
			Combat->BotPullTrigger();
			bTriggerHeld = true;
		}
		return;
	}

	// Semi, burst, bolt, pump: one press per shot at a human cadence.
	ReleaseTrigger();
	if (!bCanStart || T < NextTriggerAt || T - Combat->GetLastShotTime() < W.FireInterval || Combat->GetLocalMag() <= 0)
	{
		return;
	}
	Combat->BotPullTrigger();
	Combat->BotReleaseTrigger();
	const float Gap = Mode == EAirsoftFireMode::Burst
		? W.FireInterval * 3.f + Tune.BurstPause * Rng.FRandRange(0.7f, 1.3f)
		: FMath::Max(W.FireInterval, Tune.TapInterval * Rng.FRandRange(0.8f, 1.3f) * (1.f + Distance / 4000.f));
	NextTriggerAt = T + Gap;
}

void AAirsoftBotController::ReleaseTrigger()
{
	if (!bTriggerHeld)
	{
		return;
	}
	bTriggerHeld = false;
	if (UAirsoftCombatComponent* Combat = GetBotCombat())
	{
		Combat->BotReleaseTrigger();
	}
}

void AAirsoftBotController::ManageWeapon(AAirsoftCharacter* Me)
{
	UAirsoftCombatComponent* Combat = Me->GetCombat();
	if (Combat->IsReloading() || Combat->IsThrowing())
	{
		return;
	}
	const EAirsoftSlot Slot = Combat->GetActiveSlot();
	const EAirsoftSlot Other = Slot == EAirsoftSlot::Primary ? EAirsoftSlot::Secondary : EAirsoftSlot::Primary;
	const int32 Mag = Combat->GetLocalMag();
	const int32 Reserve = Combat->GetLocalReserve();
	if (Mag <= 0 && Reserve <= 0)
	{
		// Dry: go to the other gun if it has anything left.
		if (Combat->GetLocalMagFor(Other) + Combat->GetLocalReserveFor(Other) > 0)
		{
			ReleaseTrigger();
			Combat->BotEquip(Other);
		}
		return;
	}
	if (Mag <= 0)
	{
		ReleaseTrigger();
		Combat->BotReload();
		return;
	}
	const bool bQuiet = !Target.IsValid() && WorldTime() - LastCombatAt > 2.0;
	if (!bQuiet)
	{
		return;
	}
	// Things calmed down: back to the main gun, and top up a half-empty mag.
	if (Slot == EAirsoftSlot::Secondary && Combat->GetLocalMagFor(EAirsoftSlot::Primary) + Combat->GetLocalReserveFor(EAirsoftSlot::Primary) > 0)
	{
		Combat->BotEquip(EAirsoftSlot::Primary);
		return;
	}
	if (Reserve > 0 && Mag < FMath::CeilToInt(Combat->Current().MagSize * 0.6f))
	{
		Combat->BotReload();
	}
}

bool AAirsoftBotController::TryGrenade(AAirsoftCharacter* Me)
{
	UAirsoftCombatComponent* Combat = Me->GetCombat();
	const double T = WorldTime();
	if (T < NextGrenadeAt || Combat->GetGrenades() <= 0 || Combat->IsThrowing() || Combat->IsReloading())
	{
		return false;
	}
	NextGrenadeAt = T + Rng.FRandRange(2.f, 4.f);

	// Enemies seen in the last few seconds, bunched within the burst radius.
	const float Radius = AirsoftWeapons::GrenadeRadius * 0.8f;
	const FVector MyLoc = Me->GetActorLocation();
	FVector Center = FVector::ZeroVector;
	int32 BestCount = 0;
	bool bHidden = false;
	for (const FBotMemory& A : Memory)
	{
		const AAirsoftCharacter* EnemyA = A.Enemy.Get();
		if (!EnemyA || EnemyA->IsOut() || T - A.LastSeen > 3.0)
		{
			continue;
		}
		const float Dist = static_cast<float>(FVector::Dist(MyLoc, A.LastKnown));
		if (Dist < AirsoftBotLocal::GrenadeMinDistance || Dist > AirsoftBotLocal::GrenadeMaxDistance)
		{
			continue;
		}
		int32 Count = 0;
		FVector Sum = FVector::ZeroVector;
		bool bAllHidden = true;
		for (const FBotMemory& B : Memory)
		{
			const AAirsoftCharacter* EnemyB = B.Enemy.Get();
			if (!EnemyB || EnemyB->IsOut() || T - B.LastSeen > 3.0)
			{
				continue;
			}
			if (FVector::Dist(A.LastKnown, B.LastKnown) <= Radius)
			{
				++Count;
				Sum += B.LastKnown;
				bAllHidden = bAllHidden && !B.bVisible;
			}
		}
		if (Count > BestCount)
		{
			BestCount = Count;
			Center = Sum / static_cast<double>(Count);
			bHidden = bAllHidden;
		}
	}
	// Two or more bunched up - or, for the sharper bots, one dug in out of sight.
	const bool bWorth = BestCount >= 2 || (BestCount == 1 && bHidden && Skill >= EAirsoftBotSkill::Hard);
	if (!bWorth || Rng.FRand() > Tune.GrenadeChance)
	{
		return false;
	}
	if (UAirsoftSettings::Get()->bFriendlyFire)
	{
		for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
		{
			if (*It != Me && !It->IsOut() && It->GetTeam() == Me->GetTeam()
				&& FVector::Dist(It->GetActorLocation(), Center) < AirsoftWeapons::GrenadeRadius)
			{
				return false;
			}
		}
	}

	const FVector Eye = GetEyeLocation();
	const FVector Aim = Center - FVector(0.f, 0.f, 60.f); // around their feet
	const double Gravity = -static_cast<double>(GetWorld()->GetGravityZ());
	// Lob it over cover when we can't see them, throw it flat when we can.
	for (const bool bHigh : { bHidden, !bHidden })
	{
		FVector Dir = FVector::ForwardVector;
		float Flight = 0.f;
		if (!AirsoftBotLocal::SolveGrenadeArc(Eye, Aim, bHigh, Gravity, Dir, Flight) || Flight > AirsoftBotLocal::GrenadeMaxFlight)
		{
			continue;
		}
		const FVector Start = Eye + Dir * 45.f; // where the game mode spawns it
		if (!AirsoftBotLocal::IsArcClear(GetWorld(), Start, Dir * AirsoftWeapons::GrenadeThrowSpeed, Gravity, Flight * AirsoftBotLocal::GrenadeArcCheck, Me))
		{
			continue;
		}
		ReleaseTrigger();
		StopMovement(); // a thrown grenade inherits half the thrower's velocity: stand still for it
		if (Combat->BotThrowGrenade(Dir))
		{
			NextGrenadeAt = T + Rng.FRandRange(18.f, 30.f);
			NextCombatMoveAt = T + 0.8;
			DesiredRotation = Dir.Rotation();
			return true;
		}
		return false;
	}
	return false;
}

// ---------------------------------------------------------------------------
// Goals
// ---------------------------------------------------------------------------

void AAirsoftBotController::Think(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	ManageWeapon(Me);
	if (T >= NextGrenadeAt && TryGrenade(Me))
	{
		return;
	}

	const FVector MyLoc = Me->GetActorLocation();
	if (State == EAirsoftBotState::Investigate)
	{
		const bool bArrived = FVector::Dist2D(MyLoc, InvestigatePoint) < 400.f;
		if (T < InvestigateUntil && !bArrived)
		{
			if (!IsMoving())
			{
				FVector Point;
				if (ProjectToNav(InvestigatePoint, Point))
				{
					MoveToPoint(Point, 250.f, false);
				}
			}
			return;
		}
		// Nothing there: have a look around, then carry on.
		State = EAirsoftBotState::Hold;
		bHasMoveGoal = false;
		HoldUntil = T + Rng.FRandRange(1.5f, 3.f);
		NextScanAt = 0.0;
		return;
	}

	// Something worth checking? Domination bots stay on task unless it is close.
	const bool bDomination = GS && GS->Mode == EAirsoftMode::Domination;
	if (const FBotMemory* M = FreshestUnseen(MyLoc, bDomination ? 1800.f : 4000.f))
	{
		const double When = FMath::Max(M->LastSeen, M->LastHeard);
		if (When > InvestigatedStamp && T - When < AirsoftBotLocal::InvestigateMaxAge)
		{
			InvestigatedStamp = When;
			StartInvestigate(M->LastKnown);
			return;
		}
	}

	if (bDomination)
	{
		ThinkDomination(Me);
	}
	else
	{
		ThinkTDM(Me);
	}
}

void AAirsoftBotController::ThinkTDM(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	const bool bMoving = IsMoving();
	if (bMoving && T < GoalExpiresAt)
	{
		return;
	}
	if (!bMoving && bHasMoveGoal)
	{
		// Arrived (or the move ended): hold here a moment, watching.
		bHasMoveGoal = false;
		State = EAirsoftBotState::Hold;
		HoldUntil = T + Rng.FRandRange(2.f, 5.f);
		NextScanAt = 0.0;
		bHoldCrouch = Rng.FRand() < Tune.CrouchChance;
		if (bHoldCrouch)
		{
			Me->Crouch();
		}
		return;
	}
	if (!bMoving && T < HoldUntil)
	{
		State = EAirsoftBotState::Hold;
		return;
	}
	bHoldCrouch = false;

	// Next push: one of the A/B/C sites (they exist in TDM too), somewhere toward the enemy
	// spawn (never into it), or around where enemies were last known.
	const FVector MyLoc = Me->GetActorLocation();
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	const int32 NumObjectives = GS ? GS->Objectives.Num() : 0;
	FVector Landmark = MyLoc;
	const float Roll = Rng.FRand();
	const FBotMemory* Known = FreshestUnseen(MyLoc, 1.0e7f);
	if (Roll < 0.55f && NumObjectives > 0)
	{
		int32 Pick = Rng.RandRange(0, NumObjectives - 1);
		if (Pick == LastLandmark && NumObjectives > 1)
		{
			Pick = (Pick + 1) % NumObjectives;
		}
		LastLandmark = Pick;
		if (const AAirsoftObjective* Obj = GS->Objectives[Pick])
		{
			Landmark = Obj->GetActorLocation();
		}
	}
	else if (Roll < 0.85f && bHaveSpawns)
	{
		Landmark = FMath::Lerp(MyLoc, EnemySpawn, Rng.FRandRange(0.35f, 0.75f));
	}
	else if (Known)
	{
		Landmark = Known->LastKnown;
	}
	else
	{
		Landmark = MyLoc + AirsoftBotLocal::RandomUnit2D(Rng) * Rng.FRandRange(1500.f, 3000.f);
	}

	FVector Dest;
	if ((RandomPointNear(Landmark, 900.f, Dest) || RandomPointNear(MyLoc, 2500.f, Dest)) && MoveToPoint(Dest, 150.f, true))
	{
		State = EAirsoftBotState::Advance;
		GoalExpiresAt = T + 40.0;
	}
}

void AAirsoftBotController::ThinkDomination(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	if (!GS)
	{
		return;
	}
	if (T >= NextGoalAt || !GoalObjective.IsValid() || !GoalObjective->bActive)
	{
		// Re-pick the point to take or defend (with some hysteresis so bots don't dither).
		NextGoalAt = T + Rng.FRandRange(1.2f, 2.f);
		AAirsoftObjective* Best = nullptr;
		float BestScore = -TNumericLimits<float>::Max();
		for (AAirsoftObjective* Obj : GS->Objectives)
		{
			if (!Obj || !Obj->bActive)
			{
				continue;
			}
			const float Score = ScoreObjective(Me, Obj);
			if (Score > BestScore)
			{
				BestScore = Score;
				Best = Obj;
			}
		}
		const AAirsoftObjective* Current = GoalObjective.Get();
		const float CurrentScore = (Current && Current->bActive) ? ScoreObjective(Me, Current) : -TNumericLimits<float>::Max();
		if (Best && Best != Current && BestScore > CurrentScore + 120.f)
		{
			GoalObjective = Best;
			bHasMoveGoal = false;
			HoldUntil = 0.0;
		}
	}

	AAirsoftObjective* Obj = GoalObjective.Get();
	if (!Obj)
	{
		ThinkTDM(Me);
		return;
	}
	const FVector MyLoc = Me->GetActorLocation();
	const bool bMoving = IsMoving();
	if (Obj->IsInside(MyLoc))
	{
		// On the point: shuffle around inside the circle, sometimes crouched, watching outward.
		if (State != EAirsoftBotState::Hold)
		{
			State = EAirsoftBotState::Hold;
			HoldUntil = T + Rng.FRandRange(1.f, 3.f);
			NextScanAt = 0.0;
		}
		if (!bMoving && T >= HoldUntil)
		{
			HoldUntil = T + Rng.FRandRange(2.5f, 5.f);
			FVector Point;
			if (RandomPointNear(Obj->GetActorLocation(), Obj->Radius * 0.7f, Point))
			{
				bHoldCrouch = false;
				MoveToPoint(Point, 60.f, false);
			}
		}
		else if (!bMoving && !Me->bIsCrouched && Rng.FRand() < Tune.CrouchChance * 0.5f)
		{
			bHoldCrouch = true;
			Me->Crouch();
		}
		return;
	}
	bHoldCrouch = false;
	if (!bMoving || !bHasMoveGoal)
	{
		FVector Point;
		if (RandomPointNear(Obj->GetActorLocation(), Obj->Radius * 0.6f, Point) || ProjectToNav(Obj->GetActorLocation(), Point))
		{
			if (MoveToPoint(Point, 80.f, true))
			{
				State = EAirsoftBotState::Advance;
			}
		}
	}
}

float AAirsoftBotController::ScoreObjective(const AAirsoftCharacter* Me, const AAirsoftObjective* Obj) const
{
	const EAirsoftTeam Mine = GetBotTeam();
	const bool bOurs = Obj->OwnerTeam == Mine;
	const bool bThreatened = bOurs && (Obj->bContested || (Obj->CapturingTeam != EAirsoftTeam::None && Obj->CapturingTeam != Mine));
	float Score = bThreatened ? 1300.f : (bOurs ? 250.f : (Obj->OwnerTeam == EAirsoftTeam::None ? 1100.f : 950.f));
	if (bOurs && bDefender)
	{
		Score += 500.f;
	}
	// Closer is better (120 m away costs about as much as the gap between "ours" and "theirs").
	Score -= static_cast<float>(FVector::Dist(Me->GetActorLocation(), Obj->GetActorLocation())) / 12.f;
	// Spread out: a point teammates already cover is worth less (one defender on a safe point is plenty).
	int32 Mates = 0;
	for (TActorIterator<AAirsoftBotController> It(GetWorld()); It; ++It)
	{
		const AAirsoftBotController* Other = *It;
		if (Other && Other != this && Other->GetGoalObjective() == Obj && Other->GetBotTeam() == Mine)
		{
			++Mates;
		}
	}
	const int32 Comfortable = (bOurs && !bThreatened) ? 1 : 3;
	Score -= 260.f * static_cast<float>(FMath::Max(0, Mates + 1 - Comfortable));
	const int32 Index = Obj->Letter.IsEmpty() ? 0 : FMath::Clamp(static_cast<int32>(Obj->Letter[0]) - static_cast<int32>(TEXT('A')), 0, 2);
	return Score + ObjectiveBias[Index];
}

void AAirsoftBotController::StartInvestigate(const FVector& Point)
{
	State = EAirsoftBotState::Investigate;
	InvestigatePoint = Point;
	InvestigateUntil = WorldTime() + Rng.FRandRange(5.f, 9.f);
	bHoldCrouch = false;
	FVector NavPoint;
	if (ProjectToNav(Point, NavPoint) || RandomPointNear(Point, 600.f, NavPoint))
	{
		MoveToPoint(NavPoint, 250.f, false);
	}
}

// ---------------------------------------------------------------------------
// Movement and looking
// ---------------------------------------------------------------------------

bool AAirsoftBotController::IsMoving() const
{
	return GetMoveStatus() == EPathFollowingStatus::Moving;
}

bool AAirsoftBotController::MoveToPoint(const FVector& Dest, float Acceptance, bool bSprint)
{
	// Navmesh pathfinding, destination projected onto the navmesh, partial paths allowed, and
	// strafing (the bot's view is ours to control, not the path's).
	const EPathFollowingRequestResult::Type Result = MoveToLocation(Dest, Acceptance, true, true, true, true);
	if (Result == EPathFollowingRequestResult::Failed)
	{
		bHasMoveGoal = false;
		if (++MoveFailures == 10)
		{
			AirsoftBotLocal::WarnNoNavigationOnce(GetWorld());
		}
		return false;
	}
	MoveFailures = 0;
	MoveGoal = Dest;
	bHasMoveGoal = true;
	bWantSprint = bSprint;
	ProgressFrom = GetPawn() ? GetPawn()->GetActorLocation() : Dest;
	ProgressCheckAt = WorldTime() + AirsoftBotLocal::StuckCheckInterval;
	return true;
}

void AAirsoftBotController::OnMoveCompleted(FAIRequestID RequestID, const FPathFollowingResult& Result)
{
	Super::OnMoveCompleted(RequestID, Result);
	if (Result.Code == EPathFollowingResult::Aborted)
	{
		return; // replaced by a newer move (or stopped on purpose)
	}
	if (!Result.IsSuccess())
	{
		// Blocked / off the path: pick something else soon.
		GoalExpiresAt = 0.0;
		HoldUntil = 0.0;
	}
}

bool AAirsoftBotController::RandomPointNear(const FVector& Origin, float Radius, FVector& Out) const
{
	UNavigationSystemV1* Nav = UNavigationSystemV1::GetCurrent<UNavigationSystemV1>(GetWorld());
	if (!Nav)
	{
		return false;
	}
	FNavLocation Location;
	if (Nav->GetRandomReachablePointInRadius(Origin, Radius, Location))
	{
		Out = Location.Location;
		return true;
	}
	return ProjectToNav(Origin, Out);
}

bool AAirsoftBotController::ProjectToNav(const FVector& Point, FVector& Out) const
{
	UNavigationSystemV1* Nav = UNavigationSystemV1::GetCurrent<UNavigationSystemV1>(GetWorld());
	if (!Nav)
	{
		return false;
	}
	FNavLocation Location;
	if (Nav->ProjectPointToNavigation(Point, Location, FVector(150.f, 150.f, 250.f)))
	{
		Out = Location.Location;
		return true;
	}
	return false;
}

void AAirsoftBotController::UpdateMovement(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	const bool bMoving = IsMoving();
	const FVector MyLoc = Me->GetActorLocation();

	// Sprint on long moves with nothing to shoot at.
	const bool bSprintNow = bMoving && bWantSprint && !Target.IsValid() && State != EAirsoftBotState::Investigate
		&& FVector::DistSquared2D(MyLoc, MoveGoal) > FMath::Square(800.f);
	if (bSprintNow != bSprinting)
	{
		Me->SetSprintHeld(bSprintNow);
		bSprinting = bSprintNow;
	}

	// Stuck detection: moving but not getting anywhere.
	if (!bMoving)
	{
		StuckStrikes = 0;
		ProgressFrom = MyLoc;
		ProgressCheckAt = T + AirsoftBotLocal::StuckCheckInterval;
		return;
	}
	if (T < ProgressCheckAt)
	{
		return;
	}
	const float Moved = static_cast<float>(FVector::Dist2D(MyLoc, ProgressFrom));
	ProgressFrom = MyLoc;
	ProgressCheckAt = T + AirsoftBotLocal::StuckCheckInterval;
	const float Expected = (Me->bIsCrouched || Me->GetCombat()->IsAiming()) ? 30.f : AirsoftBotLocal::StuckMinProgress;
	if (Moved >= Expected)
	{
		StuckStrikes = 0;
		return;
	}
	++StuckStrikes;
	if (StuckStrikes == 2)
	{
		// Wedged on something: step to a random nearby spot on the navmesh.
		FVector Unstick;
		if (RandomPointNear(MyLoc, 500.f, Unstick))
		{
			MoveToPoint(Unstick, 50.f, false);
		}
	}
	else if (StuckStrikes >= 4)
	{
		// Still stuck: hop, drop the goal and re-plan.
		Me->JumpInput();
		StopMovement();
		bHasMoveGoal = false;
		GoalExpiresAt = 0.0;
		HoldUntil = 0.0;
		NextGoalAt = 0.0;
		StuckStrikes = 0;
	}
}

void AAirsoftBotController::LookAtPoint(const FVector& Point)
{
	FRotator Look = (Point - GetEyeLocation()).Rotation();
	Look.Pitch = FMath::Clamp(static_cast<float>(FRotator::NormalizeAxis(Look.Pitch)), -30.f, 30.f);
	Look.Roll = 0.f;
	DesiredRotation = Look;
}

FVector AAirsoftBotController::ThreatPointFor(const AAirsoftCharacter* Me) const
{
	const FVector MyLoc = Me->GetActorLocation();
	if (const FBotMemory* M = FreshestUnseen(MyLoc, 1.0e7f))
	{
		return M->LastKnown;
	}
	if (bHaveSpawns)
	{
		return EnemySpawn;
	}
	return MyLoc + Me->GetActorForwardVector() * 1000.f;
}

void AAirsoftBotController::UpdateLook(AAirsoftCharacter* Me)
{
	const double T = WorldTime();
	if (T < UnderFireUntil)
	{
		// Shot at (or heard a shot close by): snap toward it.
		TurnScale = 1.f;
		LookAtPoint(ThreatPoint);
		return;
	}
	if (State == EAirsoftBotState::Investigate)
	{
		TurnScale = 0.7f;
		LookAtPoint(InvestigatePoint + FVector(0.f, 0.f, 90.f));
		return;
	}
	const FVector Vel = Me->GetVelocity();
	if (Vel.SizeSquared2D() > FMath::Square(120.f))
	{
		// Walking: look where we're going (which is also what lets the movement sprint).
		TurnScale = 0.6f;
		DesiredRotation = FRotator(-3.f, static_cast<float>(Vel.Rotation().Yaw), 0.f);
		return;
	}
	// Holding: sweep around where trouble is likely to come from.
	TurnScale = 0.4f;
	if (T >= NextScanAt)
	{
		NextScanAt = T + Rng.FRandRange(1.2f, 2.8f);
		FRotator Look = (ThreatPointFor(Me) - GetEyeLocation()).Rotation();
		Look.Yaw += Rng.FRandRange(-40.f, 40.f);
		Look.Pitch = Rng.FRandRange(-5.f, 3.f);
		Look.Roll = 0.f;
		DesiredRotation = Look;
	}
}
