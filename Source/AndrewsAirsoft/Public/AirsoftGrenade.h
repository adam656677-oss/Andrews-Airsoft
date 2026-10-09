// Andrew's Airsoft - BB grenade: bounces, then bursts and tags everyone in the
// blast radius with line of sight.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/NetSerialization.h"
#include "AirsoftTypes.h"
#include "AirsoftGrenade.generated.h"

class USphereComponent;
class UStaticMeshComponent;
class UProjectileMovementComponent;
class UPointLightComponent;

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftGrenade : public AActor
{
	GENERATED_BODY()

public:
	AAirsoftGrenade();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Server: set before FinishSpawning. */
	void Init(AController* InThrower, EAirsoftTeam InTeam, const FVector& Velocity);

	UFUNCTION(NetMulticast, Reliable)
	void MulticastBurst(FVector_NetQuantize Location);

protected:
	void Detonate();
	UFUNCTION() void OnBounce(const FHitResult& ImpactResult, const FVector& ImpactVelocity);

	UPROPERTY(VisibleAnywhere) TObjectPtr<USphereComponent> Collision;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Body;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UProjectileMovementComponent> Movement;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Flash;

	TWeakObjectPtr<AController> Thrower;
	EAirsoftTeam Team = EAirsoftTeam::None;
	FTimerHandle FuseTimer;
	float FlashLeft = 0.f;
	bool bDetonated = false;
	double LastBounceSound = 0.0;
};
