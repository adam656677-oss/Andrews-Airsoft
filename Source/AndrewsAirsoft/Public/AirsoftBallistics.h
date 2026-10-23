// Andrew's Airsoft - BB flight model and the per-world simulator.
//
// BBs are real projectiles: they leave at muzzle velocity, lose speed to drag,
// and hop-up backspin holds them level until they slow down, at which point
// they drop away - the classic airsoft trajectory.
//
// On machines that draw (not a dedicated server) every visible BB is a pooled,
// speed-stretched tracer streak; when it hits something the effects subsystem
// plays the surface's impact and a cosmetic spent BB skips off hard surfaces.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Tickable.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "AirsoftBallistics.generated.h"

class AActor;
class UWorld;
class UStaticMeshComponent;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UAirsoftEffectsSubsystem;
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
	/** Drawn as a tracer, with an impact effect where it lands (purely cosmetic either way). */
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
		/** Last flight direction (a resting spent BB keeps its streak orientation). */
		FVector Heading = FVector::ForwardVector;
		float Travelled = 0.f;
		float Age = 0.f;
		TWeakObjectPtr<UStaticMeshComponent> Visual;
		bool bCountedVisual = false;
		float LastIntensity = -1.f;
		/** Cosmetic spent BB skipping off a hard surface (never reports hits). */
		bool bRicochet = false;
		/** Ricochets: bounces left; below zero it lies still and fades. */
		int32 BouncesLeft = 0;
		float RestTime = 0.f;
	};

	UStaticMeshComponent* AcquireVisual(const FLinearColor& Color);
	void ReleaseVisual(FActiveBB& BB);
	void UpdateVisual(FActiveBB& BB, const UAirsoftEffectsSubsystem* FX, bool bNight);
	bool TickRicochet(FActiveBB& BB, float DeltaTime, UWorld* World);
	void SpawnRicochet(const FHitResult& Hit, const FVector& Velocity, const FLinearColor& Color, float Restitution, float Drag);
	UMaterialInterface* GetTracerMaterial();

	TArray<FActiveBB> Active;
	int32 NumVisuals = 0;
	int32 NumRicochets = 0;
	int32 RicochetsThisFrame = 0;
	bool bTracerMaterialResolved = false;
	/** Tracers use the additive glow material (else the opaque emissive fallback). */
	bool bGlowTracers = false;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Pool;

	UPROPERTY()
	TObjectPtr<AActor> VisualOwner;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> TracerMaterial;
};
