#include "AirsoftGrenade.h"

#include "AirsoftAssets.h"
#include "AirsoftBallistics.h"
#include "AirsoftCharacter.h"
#include "AirsoftGameMode.h"
#include "AirsoftSettings.h"
#include "AirsoftWeaponData.h"
#include "Components/PointLightComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "TimerManager.h"

AAirsoftGrenade::AAirsoftGrenade()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	SetReplicateMovement(true);
	InitialLifeSpan = 10.f;

	Collision = CreateDefaultSubobject<USphereComponent>(TEXT("Collision"));
	Collision->InitSphereRadius(5.f);
	Collision->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Collision->SetCollisionObjectType(ECC_WorldDynamic);
	Collision->SetCollisionResponseToAllChannels(ECR_Block);
	Collision->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	Collision->SetCollisionResponseToChannel(ECC_BB, ECR_Ignore);
	Collision->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
	SetRootComponent(Collision);

	Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
	Body->SetupAttachment(Collision);
	Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	Flash = CreateDefaultSubobject<UPointLightComponent>(TEXT("Flash"));
	Flash->SetupAttachment(Collision);
	Flash->SetIntensity(0.f);
	Flash->SetAttenuationRadius(900.f);
	Flash->SetLightColor(FLinearColor(1.f, 0.8f, 0.55f));
	Flash->SetCastShadows(false);

	Movement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("Movement"));
	Movement->UpdatedComponent = Collision;
	Movement->bShouldBounce = true;
	Movement->Bounciness = 0.32f;
	Movement->Friction = 0.45f;
	Movement->BounceVelocityStopSimulatingThreshold = 40.f;
	Movement->ProjectileGravityScale = 1.f;
	Movement->bRotationFollowsVelocity = false;
	Movement->InitialSpeed = 0.f;
	Movement->MaxSpeed = 4000.f;
}

void AAirsoftGrenade::Init(AController* InThrower, EAirsoftTeam InTeam, const FVector& Velocity)
{
	Thrower = InThrower;
	Team = InTeam;
	Movement->Velocity = Velocity;
}

void AAirsoftGrenade::BeginPlay()
{
	Super::BeginPlay();
	if (UStaticMesh* Mesh = AirsoftAssets::FindMesh(TEXT("Weapons"), TEXT("Grenade"), TEXT("Body")))
	{
		Body->SetStaticMesh(Mesh);
	}
	else
	{
		Body->SetStaticMesh(AirsoftAssets::Cylinder());
		Body->SetRelativeScale3D(FVector(0.065f, 0.065f, 0.12f));
		if (UMaterialInterface* Base = Body->GetMaterial(0))
		{
			UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(Base, this);
			MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.08f, 0.11f, 0.06f));
			Body->SetMaterial(0, MID);
		}
	}
	Movement->OnProjectileBounce.AddDynamic(this, &AAirsoftGrenade::OnBounce);
	if (HasAuthority())
	{
		GetWorldTimerManager().SetTimer(FuseTimer, this, &AAirsoftGrenade::Detonate, AirsoftWeapons::GrenadeFuse, false);
	}
}

void AAirsoftGrenade::OnBounce(const FHitResult& ImpactResult, const FVector& ImpactVelocity)
{
	const double Now = GetWorld()->GetTimeSeconds();
	if (ImpactVelocity.Size() > 120.f && Now - LastBounceSound > 0.12)
	{
		LastBounceSound = Now;
		AirsoftAssets::Play3D(this, TEXT("GrenadeBounce"), ImpactResult.ImpactPoint, FMath::Clamp(static_cast<float>(ImpactVelocity.Size()) / 900.f, 0.15f, 0.7f), FMath::FRandRange(0.9f, 1.15f));
	}
}

void AAirsoftGrenade::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bDetonated && Movement->Velocity.SizeSquared() > 100.f)
	{
		Body->AddLocalRotation(FRotator(-720.f * DeltaSeconds, 0.f, 260.f * DeltaSeconds));
	}
	if (FlashLeft > 0.f)
	{
		FlashLeft = FMath::Max(0.f, FlashLeft - DeltaSeconds);
		Flash->SetIntensity(FMath::Square(FlashLeft / 0.25f) * 60000.f);
	}
}

void AAirsoftGrenade::Detonate()
{
	if (bDetonated)
	{
		return;
	}
	bDetonated = true;
	const FVector Center = GetActorLocation() + FVector(0.f, 0.f, 10.f);
	MulticastBurst(Center);

	AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>();
	const bool bFriendlyFire = UAirsoftSettings::Get()->bFriendlyFire;
	for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
	{
		AAirsoftCharacter* Victim = *It;
		if (!Victim || Victim->IsOut() || !GM)
		{
			continue;
		}
		const bool bSelf = Victim->GetController() == Thrower.Get();
		if (!bSelf && !bFriendlyFire && Victim->GetTeam() == Team)
		{
			continue;
		}
		if (bSelf)
		{
			continue; // the thrower has the sense to duck
		}
		// Chest and head checks so a crouched player behind low cover is safe.
		const FVector Chest = Victim->GetActorLocation() + FVector(0.f, 0.f, 20.f);
		const FVector Head = Victim->GetPawnViewLocation();
		bool bExposed = false;
		for (const FVector& P : { Chest, Head })
		{
			if (FVector::Dist(Center, P) > AirsoftWeapons::GrenadeRadius)
			{
				continue;
			}
			FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftGrenade), false, this);
			Query.AddIgnoredActor(Victim);
			FHitResult Block;
			if (!GetWorld()->LineTraceSingleByChannel(Block, Center, P, ECC_Visibility, Query) || Cast<APawn>(Block.GetActor()))
			{
				bExposed = true;
				break;
			}
		}
		if (bExposed)
		{
			GM->HandleTag(Thrower.Get(), Victim->GetController(), TEXT("Grenade"));
		}
	}
	SetLifeSpan(1.5f);
}

void AAirsoftGrenade::MulticastBurst_Implementation(FVector_NetQuantize Location)
{
	bDetonated = true;
	Movement->StopMovementImmediately();
	Body->SetVisibility(false);
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	AirsoftAssets::Play3D(this, TEXT("GrenadeBurst"), Location, 1.f, FMath::FRandRange(0.95f, 1.05f));
	if (UAirsoftBBSubsystem* BBs = GetWorld()->GetSubsystem<UAirsoftBBSubsystem>())
	{
		BBs->Burst(Location, AirsoftWeapons::GrenadeRadius, 90);
	}
	FlashLeft = 0.25f;
	Flash->SetIntensity(60000.f);
}
