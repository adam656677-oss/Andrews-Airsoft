// Andrew's Airsoft - BB flight model and the per-world simulator.
//
// BBs are real projectiles: they leave at muzzle velocity, lose speed to drag,
// and hop-up backspin holds them level until they slow down, at which point
// they drop away - the classic airsoft trajectory.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Tickable.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "AirsoftBallistics.generated.h"

class AActor;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
struct FHitResult;

struct FAirsoftBBParams
{
	FVector Origin = FVector::ZeroVector;
	FVector Direction = FVector::ForwardVector;
	float Speed = 11000.f;
	float Hop = 1.f;
	float Drag = 0.000121f;
	float MaxRange = 6000.f;
	/** Where the visible tracer starts (muzzle); it converges onto the true path over the first few metres. */
	FVector VisualStart = FVector::ZeroVector;
	bool bHasVisualStart = false;
	FLinearColor Color = FLinearColor(1.f, 0.6f, 0.1f);
	bool bVisible = true;
	TArray<TWeakObjectPtr<AActor>> IgnoreActors;
	/** Called once on impact (game thread). */
	TFunction<void(const FHitResult&)> OnHit;
};

namespace AirsoftBallistics
{
	/** Advances one BB by Dt. Returns the new velocity. */
	ANDREWSAIRSOFT_API FVector Step(const FVector& Velocity, float MuzzleSpeed, float Hop, float Drag, float Dt);

	/** Random direction inside a cone of HalfAngleDeg around Dir. */
	ANDREWSAIRSOFT_API FVector Spread(const FVector& Dir, float HalfAngleDeg, FRandomStream& Rng);

	/** Upper bound on flight time, used by the server to expire shot records. */
	ANDREWSAIRSOFT_API float MaxFlightTime(float Speed, float Range);
}

UCLASS()
class ANDREWSAIRSOFT_API UAirsoftBBSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	void Fire(FAirsoftBBParams&& Params);

	/** Visual-only burst of BBs (grenades). */
	void Burst(const FVector& Location, float Radius, int32 Count);

	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual void Deinitialize() override;

private:
	struct FActiveBB
	{
		FAirsoftBBParams P;
		FVector Position;
		FVector Velocity;
		FVector VisualOffset;
		float Travelled = 0.f;
		float Age = 0.f;
		TWeakObjectPtr<UStaticMeshComponent> Visual;
	};

	UStaticMeshComponent* AcquireVisual(const FLinearColor& Color);
	void ReleaseVisual(UStaticMeshComponent* Visual);

	TArray<FActiveBB> Active;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Pool;

	UPROPERTY()
	TObjectPtr<AActor> VisualOwner;
};
