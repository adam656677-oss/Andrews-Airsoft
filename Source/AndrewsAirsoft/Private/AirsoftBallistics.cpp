#include "AirsoftBallistics.h"

#include "AirsoftAssets.h"
#include "AirsoftEffects.h"
#include "AirsoftTypes.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

namespace AirsoftBallistics
{
	FVector Step(const FVector& Velocity, float MuzzleSpeed, float Hop, float Drag, float Dt)
	{
		const float Speed = Velocity.Size();
		// Drag proportional to speed squared.
		FVector Accel = -Drag * Speed * Velocity;
		// Hop-up lift scales with speed squared; at muzzle velocity it cancels gravity * Hop.
		const float SpeedRatio = MuzzleSpeed > 1.f ? Speed / MuzzleSpeed : 0.f;
		const float Lift = FMath::Min(Hop * SpeedRatio * SpeedRatio, 1.25f);
		Accel.Z += -980.f * (1.f - Lift);
		return Velocity + Accel * Dt;
	}

	FVector Spread(const FVector& Dir, float HalfAngleDeg, FRandomStream& Rng)
	{
		if (HalfAngleDeg <= 0.f)
		{
			return Dir.GetSafeNormal();
		}
		// Uniform within the cone (sqrt for even area distribution).
		const float Angle = FMath::DegreesToRadians(HalfAngleDeg) * FMath::Sqrt(Rng.GetFraction());
		const float Roll = Rng.GetFraction() * 2.f * UE_PI;
		const FVector Forward = Dir.GetSafeNormal();
		FVector Right, Up;
		Forward.FindBestAxisVectors(Right, Up);
		const FVector Offset = (Right * FMath::Cos(Roll) + Up * FMath::Sin(Roll)) * FMath::Tan(Angle);
		return (Forward + Offset).GetSafeNormal();
	}

	float MaxFlightTime(float Speed, float Range)
	{
		return Range / FMath::Max(Speed * 0.45f, 1000.f) + 0.6f;
	}
}

namespace AirsoftBallisticsPrivate
{
	constexpr float BBRicochetRestTime = 0.9f;  // a spent BB lies on the ground this long, fading
	constexpr float BBRicochetMaxAge = 3.f;
	constexpr float BBRicochetWidth = 0.6f;     // a 6 mm BB
	constexpr int32 BBVisualPoolSize = 256;
}

void UAirsoftBBSubsystem::Fire(FAirsoftBBParams&& Params)
{
	FActiveBB BB;
	BB.Position = Params.Origin;
	BB.Velocity = Params.Direction.GetSafeNormal() * Params.Speed;
	BB.Heading = Params.Direction.GetSafeNormal();
	BB.VisualOffset = Params.bHasVisualStart ? Params.VisualStart - Params.Origin : FVector::ZeroVector;
	BB.P = MoveTemp(Params);
	UWorld* World = GetWorld();
	if (BB.P.bVisible && World && World->GetNetMode() != NM_DedicatedServer)
	{
		// Shots fired on this machine always get a tracer; everyone else's share a budget, so twenty
		// guns on full auto stay cheap (the BBs still fly and land, just unseen).
		const bool bOwnShot = static_cast<bool>(BB.P.OnHit);
		if (bOwnShot || NumVisuals < UAirsoftEffectsSettings::Get()->MaxRemoteTracers)
		{
			BB.Visual = AcquireVisual(BB.P.Color);
			if (BB.Visual.IsValid())
			{
				BB.bCountedVisual = true;
				++NumVisuals;
				const UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this);
				UpdateVisual(BB, FX, FX && FX->IsNightMap());
			}
		}
	}
	Active.Add(MoveTemp(BB));
}

void UAirsoftBBSubsystem::Burst(const FVector& Location, float Radius, int32 Count)
{
	FRandomStream Rng(FMath::Rand());
	for (int32 i = 0; i < Count; ++i)
	{
		FAirsoftBBParams P;
		P.Origin = Location + FVector(0.f, 0.f, 10.f);
		P.Direction = FVector(Rng.FRandRange(-1.f, 1.f), Rng.FRandRange(-1.f, 1.f), Rng.FRandRange(-0.1f, 0.8f)).GetSafeNormal();
		P.Speed = 4500.f;
		P.Hop = 0.f;
		P.Drag = 0.0004f;
		P.MaxRange = Radius;
		P.Color = FLinearColor(1.f, 0.85f, 0.6f);
		Fire(MoveTemp(P));
	}
}

void UAirsoftBBSubsystem::Tick(float DeltaTime)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this);
	const bool bNight = FX && FX->IsNightMap();
	RicochetsThisFrame = 0;

	// Sub-step so fast BBs are swept accurately even at low frame rates.
	const int32 SubSteps = FMath::Clamp(FMath::CeilToInt(DeltaTime / (1.f / 120.f)), 1, 4);
	const float Dt = DeltaTime / SubSteps;

	// Impacts and hit callbacks run after the loop so they can safely add BBs.
	struct FPendingImpact
	{
		FHitResult Hit;
		FVector Velocity = FVector::ZeroVector;
		FLinearColor Color = FLinearColor::White;
		float Drag = 0.f;
	};
	TArray<FPendingImpact> PendingImpacts;
	TArray<TPair<TFunction<void(const FHitResult&)>, FHitResult>> PendingHits;

	for (int32 i = Active.Num() - 1; i >= 0; --i)
	{
		FActiveBB& BB = Active[i];
		bool bDone = false;
		if (BB.bRicochet)
		{
			bDone = TickRicochet(BB, DeltaTime, World);
		}
		for (int32 Step = 0; Step < SubSteps && !bDone && !BB.bRicochet; ++Step)
		{
			const FVector NewVelocity = AirsoftBallistics::Step(BB.Velocity, BB.P.Speed, BB.P.Hop, BB.P.Drag, Dt);
			const FVector Delta = (BB.Velocity + NewVelocity) * 0.5f * Dt;
			BB.Velocity = NewVelocity;

			FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftBB), false);
			Query.bReturnPhysicalMaterial = true;
			for (const TWeakObjectPtr<AActor>& Ignore : BB.P.IgnoreActors)
			{
				if (Ignore.IsValid())
				{
					Query.AddIgnoredActor(Ignore.Get());
				}
			}
			FHitResult Hit;
			if (World->LineTraceSingleByChannel(Hit, BB.Position, BB.Position + Delta, ECC_BB, Query))
			{
				BB.Position = Hit.ImpactPoint;
				bDone = true;
				if (BB.P.bVisible && FX)
				{
					FPendingImpact& Impact = PendingImpacts.AddDefaulted_GetRef();
					Impact.Hit = Hit;
					Impact.Velocity = BB.Velocity;
					Impact.Color = BB.P.Color;
					Impact.Drag = BB.P.Drag;
				}
				if (BB.P.OnHit)
				{
					PendingHits.Emplace(MoveTemp(BB.P.OnHit), Hit);
				}
			}
			else
			{
				BB.Position += Delta;
				BB.Travelled += Delta.Size();
				BB.Age += Dt;
				if (BB.Travelled >= BB.P.MaxRange || BB.Age > 6.f || BB.Velocity.SizeSquared() < FMath::Square(FMath::Min(1500.f, BB.P.Speed * 0.15f)))
				{
					bDone = true;
				}
			}
		}

		UpdateVisual(BB, FX, bNight);

		if (bDone)
		{
			if (BB.bRicochet)
			{
				NumRicochets = FMath::Max(0, NumRicochets - 1);
			}
			ReleaseVisual(BB);
			Active.RemoveAtSwap(i);
		}
	}

	// Cosmetic only: the surface's impact look, and the BB skipping off hard surfaces.
	if (FX)
	{
		for (const FPendingImpact& Impact : PendingImpacts)
		{
			const EAirsoftSurface Surface = FX->SurfaceOf(Impact.Hit);
			FX->BBImpact(Impact.Hit, Impact.Velocity, Surface);
			SpawnRicochet(Impact.Hit, Impact.Velocity, Impact.Color, AirsoftEffects::Restitution(Surface), Impact.Drag);
		}
	}

	for (TPair<TFunction<void(const FHitResult&)>, FHitResult>& Pending : PendingHits)
	{
		Pending.Key(Pending.Value);
	}
}

bool UAirsoftBBSubsystem::TickRicochet(FActiveBB& BB, float DeltaTime, UWorld* World)
{
	BB.Age += DeltaTime;
	if (BB.Age > AirsoftBallisticsPrivate::BBRicochetMaxAge)
	{
		return true;
	}
	if (BB.BouncesLeft < 0)
	{
		// Lying still on the ground, fading out.
		BB.RestTime += DeltaTime;
		return BB.RestTime >= AirsoftBallisticsPrivate::BBRicochetRestTime;
	}
	// Gravity and drag, no hop-up: the backspin is gone after the impact.
	const FVector NewVelocity = AirsoftBallistics::Step(BB.Velocity, 1.f, 0.f, BB.P.Drag, DeltaTime);
	const FVector Delta = (BB.Velocity + NewVelocity) * 0.5f * DeltaTime;
	BB.Velocity = NewVelocity;
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftBBRicochet), false);
	FHitResult Hit;
	if (!World->LineTraceSingleByChannel(Hit, BB.Position, BB.Position + Delta, ECC_BB, Query))
	{
		BB.Position += Delta;
		return false;
	}
	if (Cast<APawn>(Hit.GetActor()))
	{
		return true; // bounced into someone: gone
	}
	FVector N = Hit.ImpactNormal;
	if (!N.Normalize())
	{
		return true;
	}
	// Lose most of the normal speed, keep some of the sliding speed.
	const double Normal = FVector::DotProduct(BB.Velocity, N);
	const FVector Tangent = BB.Velocity - N * Normal;
	BB.Velocity = Tangent * 0.7 - N * (Normal * 0.35);
	BB.Position = Hit.ImpactPoint + N * 0.4;
	--BB.BouncesLeft;
	if (BB.BouncesLeft < 0 || BB.Velocity.SizeSquared() < FMath::Square(80.0))
	{
		BB.Velocity = FVector::ZeroVector;
		BB.BouncesLeft = -1;
	}
	return false;
}

void UAirsoftBBSubsystem::SpawnRicochet(const FHitResult& Hit, const FVector& Velocity, const FLinearColor& Color, float Restitution, float Drag)
{
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	if (Restitution <= 0.f || NumRicochets >= S->MaxRicochets || RicochetsThisFrame >= S->MaxRicochetsPerFrame)
	{
		return;
	}
	const UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this);
	if (!FX || FX->IsViewerPawn(Hit.GetActor()))
	{
		return;
	}
	if (FX->HasView() && FVector::DistSquared(FX->GetViewLocation(), Hit.ImpactPoint) > FMath::Square(static_cast<double>(S->DebrisCullDistance)))
	{
		return;
	}
	const double Speed = Velocity.Size();
	FVector N = Hit.ImpactNormal;
	if (Speed < 1200.0 || !N.Normalize())
	{
		return;
	}
	const FVector In = Velocity / Speed;
	const float Cos = static_cast<float>(FMath::Abs(FVector::DotProduct(In, N)));
	// Square-on hits lose most of their speed; glancing hits skip off fast. Rough surfaces scatter.
	const float Keep = Restitution * FMath::Lerp(1.2f, 0.5f, Cos);
	FVector Out = FMath::VRandCone(In.MirrorByVector(N), FMath::DegreesToRadians(20.f));
	if (FVector::DotProduct(Out, N) < 0.1)
	{
		Out = (Out + N * 0.5).GetSafeNormal();
	}

	FActiveBB BB;
	BB.bRicochet = true;
	BB.BouncesLeft = 2;
	BB.Position = Hit.ImpactPoint + N * 0.5;
	BB.Velocity = Out * (Speed * static_cast<double>(Keep));
	BB.VisualOffset = FVector::ZeroVector;
	BB.Heading = Out;
	BB.P.Speed = static_cast<float>(Speed) * Keep;
	BB.P.Hop = 0.f;
	BB.P.Drag = Drag;
	BB.P.OnHit = nullptr;
	// A spent BB: off-white, keeping a little of a tracer BB's glow.
	BB.P.Color = FMath::Lerp(Color, FLinearColor(0.95f, 0.93f, 0.86f), 0.6f);
	BB.Visual = AcquireVisual(BB.P.Color);
	if (!BB.Visual.IsValid())
	{
		return; // nothing to show: a cosmetic BB is not worth simulating
	}
	BB.bCountedVisual = true;
	++NumVisuals;
	++NumRicochets;
	++RicochetsThisFrame;
	UpdateVisual(BB, FX, FX->IsNightMap());
	Active.Add(MoveTemp(BB));
}

void UAirsoftBBSubsystem::UpdateVisual(FActiveBB& BB, const UAirsoftEffectsSubsystem* FX, bool bNight)
{
	UStaticMeshComponent* Visual = BB.Visual.Get();
	if (!Visual)
	{
		return;
	}
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	const float Speed = static_cast<float>(BB.Velocity.Size());
	if (Speed > 1.f)
	{
		BB.Heading = BB.Velocity / Speed;
	}
	const FVector Dir = BB.Heading;
	FVector Head = BB.Position;
	float Width = S->TracerWidth;
	float Length = 0.f;
	float Intensity = 0.f;
	if (BB.bRicochet)
	{
		Width = AirsoftBallisticsPrivate::BBRicochetWidth;
		const float Rest = BB.BouncesLeft < 0 ? FMath::Clamp(1.f - BB.RestTime / AirsoftBallisticsPrivate::BBRicochetRestTime, 0.f, 1.f) : 1.f;
		Intensity = S->RicochetIntensity * Rest;
		Length = FMath::Clamp(Speed * S->TracerLengthSeconds, Width, S->TracerMaxLength * 0.5f);
	}
	else
	{
		// Converge the tracer from the muzzle onto the real flight line over ~2.5 m.
		const float Blend = FMath::Clamp(1.f - BB.Travelled / 250.f, 0.f, 1.f);
		Head = BB.Position + BB.VisualOffset * Blend;
		// Streak length follows speed (a round dot once drag has slowed it); brightest leaving the barrel,
		// and never a streak poking out behind the muzzle.
		const float SpeedFraction = BB.P.Speed > 1.f ? FMath::Clamp(Speed / BB.P.Speed, 0.f, 1.f) : 1.f;
		Intensity = S->TracerIntensity * (0.45f + 0.55f * SpeedFraction);
		Length = FMath::Clamp(Speed * S->TracerLengthSeconds, Width, S->TracerMaxLength);
		Length = FMath::Min(Length, BB.Travelled + Width);
	}
	if (FX && FX->HasView())
	{
		// Far streaks stay at least a pixel or two wide (dimmed to match) so TSR does not lose them.
		const float Dist = static_cast<float>(FVector::Dist(FX->GetViewLocation(), Head));
		const float MinWidth = Dist * FX->GetPixelAngle() * S->TracerMinPixels;
		if (MinWidth > Width)
		{
			Intensity *= FMath::Max(Width / MinWidth, S->TracerFarDimFloor);
			Length = FMath::Max(Length, MinWidth);
			Width = MinWidth;
		}
	}
	if (bNight)
	{
		Intensity *= S->NightTracerBoost; // tracer-unit glow
	}
	if (!bGlowTracers)
	{
		Intensity *= 0.65f; // the opaque emissive fallback has no soft edge, so it reads brighter
	}
	Visual->SetWorldTransform(FTransform(Dir.Rotation(), Head - Dir * (Length * 0.5f), FVector(Length, Width, Width) / 100.f));
	if (FMath::Abs(Intensity - BB.LastIntensity) > 0.05f * FMath::Max(BB.LastIntensity, 0.2f))
	{
		if (UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(Visual->GetMaterial(0)))
		{
			MID->SetScalarParameterValue(TEXT("Intensity"), Intensity);
		}
		BB.LastIntensity = Intensity;
	}
}

TStatId UAirsoftBBSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UAirsoftBBSubsystem, STATGROUP_Tickables);
}

void UAirsoftBBSubsystem::Deinitialize()
{
	Active.Empty();
	Pool.Empty();
	VisualOwner = nullptr;
	TracerMaterial = nullptr;
	NumVisuals = 0;
	NumRicochets = 0;
	Super::Deinitialize();
}

UMaterialInterface* UAirsoftBBSubsystem::GetTracerMaterial()
{
	if (!bTracerMaterialResolved)
	{
		bTracerMaterialResolved = true;
		const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
		TracerMaterial = S->GlowMaterial.IsNull() ? nullptr : S->GlowMaterial.LoadSynchronous();
		bGlowTracers = TracerMaterial != nullptr;
		if (!TracerMaterial)
		{
			TracerMaterial = AirsoftAssets::EmissiveMaterial();
		}
	}
	return TracerMaterial;
}

UStaticMeshComponent* UAirsoftBBSubsystem::AcquireVisual(const FLinearColor& Color)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}
	if (!VisualOwner)
	{
		FActorSpawnParameters Params;
		Params.ObjectFlags |= RF_Transient;
		VisualOwner = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, Params);
		if (!VisualOwner)
		{
			return nullptr;
		}
		USceneComponent* Root = NewObject<USceneComponent>(VisualOwner, TEXT("Root"));
		VisualOwner->SetRootComponent(Root);
		Root->RegisterComponent();
	}

	UStaticMeshComponent* Visual = nullptr;
	while (Pool.Num() > 0 && !Visual)
	{
		Visual = Pool.Pop();
	}
	if (!Visual)
	{
		Visual = NewObject<UStaticMeshComponent>(VisualOwner);
		Visual->SetMobility(EComponentMobility::Movable);
		Visual->SetStaticMesh(AirsoftAssets::Sphere());
		Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Visual->SetGenerateOverlapEvents(false);
		Visual->SetCanEverAffectNavigation(false);
		Visual->SetCastShadow(false);
		Visual->bReceivesDecals = false;
		Visual->bAffectDynamicIndirectLighting = false;
		Visual->bAffectDistanceFieldLighting = false;
		// A sphere stretched along the flight path (scale set every frame) reads as a glowing BB streak.
		Visual->SetWorldScale3D(FVector(0.01f));
		Visual->RegisterComponent();
	}
	UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(Visual->GetMaterial(0));
	if (!MID)
	{
		MID = UMaterialInstanceDynamic::Create(GetTracerMaterial(), Visual);
		if (MID)
		{
			Visual->SetMaterial(0, MID);
		}
	}
	if (MID)
	{
		MID->SetVectorParameterValue(TEXT("Color"), Color);
	}
	Visual->SetVisibility(true);
	return Visual;
}

void UAirsoftBBSubsystem::ReleaseVisual(FActiveBB& BB)
{
	if (BB.bCountedVisual)
	{
		BB.bCountedVisual = false;
		NumVisuals = FMath::Max(0, NumVisuals - 1);
	}
	UStaticMeshComponent* Visual = BB.Visual.Get();
	BB.Visual = nullptr;
	if (!Visual)
	{
		return;
	}
	Visual->SetVisibility(false);
	if (Pool.Num() < AirsoftBallisticsPrivate::BBVisualPoolSize)
	{
		Pool.Add(Visual);
	}
	else
	{
		Visual->DestroyComponent();
	}
}
