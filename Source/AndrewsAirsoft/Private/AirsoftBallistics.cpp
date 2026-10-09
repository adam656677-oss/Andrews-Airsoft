#include "AirsoftBallistics.h"

#include "AirsoftAssets.h"
#include "AirsoftTypes.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"

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
		const float Roll = Rng.GetFraction() * 2.f * PI;
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

void UAirsoftBBSubsystem::Fire(FAirsoftBBParams&& Params)
{
	FActiveBB BB;
	BB.Position = Params.Origin;
	BB.Velocity = Params.Direction.GetSafeNormal() * Params.Speed;
	BB.VisualOffset = Params.bHasVisualStart ? Params.VisualStart - Params.Origin : FVector::ZeroVector;
	BB.P = MoveTemp(Params);
	if (BB.P.bVisible && GetWorld() && GetWorld()->GetNetMode() != NM_DedicatedServer)
	{
		BB.Visual = AcquireVisual(BB.P.Color);
		if (BB.Visual.IsValid())
		{
			BB.Visual->SetWorldLocation(BB.Position + BB.VisualOffset);
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
	// Sub-step so fast BBs are swept accurately even at low frame rates.
	const int32 SubSteps = FMath::Clamp(FMath::CeilToInt(DeltaTime / (1.f / 120.f)), 1, 4);
	const float Dt = DeltaTime / SubSteps;

	// Hit callbacks run after the loop so they can safely fire new BBs.
	TArray<TPair<TFunction<void(const FHitResult&)>, FHitResult>> PendingHits;

	for (int32 i = Active.Num() - 1; i >= 0; --i)
	{
		FActiveBB& BB = Active[i];
		bool bDone = false;
		for (int32 Step = 0; Step < SubSteps && !bDone; ++Step)
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
				if (BB.Travelled >= BB.P.MaxRange || BB.Age > 4.f || BB.Velocity.SizeSquared() < 1500.f * 1500.f)
				{
					bDone = true;
				}
			}
		}

		if (UStaticMeshComponent* Visual = BB.Visual.Get())
		{
			// Converge the tracer from the muzzle onto the real flight line over ~2.5 m.
			const float Blend = FMath::Clamp(1.f - BB.Travelled / 250.f, 0.f, 1.f);
			const FVector Pos = BB.Position + BB.VisualOffset * Blend;
			const FVector Dir = BB.Velocity.GetSafeNormal();
			Visual->SetWorldLocationAndRotation(Pos - Dir * 12.f, Dir.Rotation());
		}

		if (bDone)
		{
			ReleaseVisual(BB.Visual.Get());
			Active.RemoveAtSwap(i);
		}
	}

	for (TPair<TFunction<void(const FHitResult&)>, FHitResult>& Pending : PendingHits)
	{
		Pending.Key(Pending.Value);
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
	Super::Deinitialize();
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
		Visual->SetStaticMesh(AirsoftAssets::Sphere());
		Visual->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Visual->SetCastShadow(false);
		Visual->bReceivesDecals = false;
		// A stretched sphere reads as a glowing BB streak.
		Visual->SetWorldScale3D(FVector(0.24f, 0.012f, 0.012f));
		Visual->RegisterComponent();
	}
	UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(Visual->GetMaterial(0));
	if (!MID)
	{
		MID = AirsoftAssets::MakeEmissive(Visual, Color, 6.f);
		Visual->SetMaterial(0, MID);
	}
	else
	{
		MID->SetVectorParameterValue(TEXT("Color"), Color);
	}
	Visual->SetVisibility(true);
	return Visual;
}

void UAirsoftBBSubsystem::ReleaseVisual(UStaticMeshComponent* Visual)
{
	if (Visual)
	{
		Visual->SetVisibility(false);
		if (Pool.Num() < 256)
		{
			Pool.Add(Visual);
		}
		else
		{
			Visual->DestroyComponent();
		}
	}
}
