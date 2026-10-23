#include "AirsoftPracticeTarget.h"

#include "AirsoftAssets.h"
#include "AirsoftGunVisual.h"
#include "AirsoftTypes.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Materials/MaterialInstanceDynamic.h"

AAirsoftPracticeTarget::AAirsoftPracticeTarget()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	Stand = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Stand"));
	Stand->SetupAttachment(Root);
	Stand->SetCollisionProfileName(TEXT("BlockAll"));

	Hinge = CreateDefaultSubobject<USceneComponent>(TEXT("Hinge"));
	Hinge->SetupAttachment(Root);
	Hinge->SetRelativeLocation(FVector(0.f, 0.f, 120.f));

	Plate = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Plate"));
	Plate->SetupAttachment(Hinge);
	Plate->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	Plate->SetCollisionResponseToAllChannels(ECR_Ignore);
	Plate->SetCollisionResponseToChannel(ECC_BB, ECR_Block);
	Plate->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);

	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(Root);
	Label->SetRelativeLocation(FVector(4.f, 0.f, 22.f));
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetWorldSize(16.f);
	Label->SetTextRenderColor(FColor(255, 170, 60));
	Label->SetCollisionEnabled(ECollisionEnabled::NoCollision);
}

void AAirsoftPracticeTarget::BeginPlay()
{
	Super::BeginPlay();

	// Prefer the 4K steel target from the asset kit; fall back to primitives.
	UStaticMesh* StandMesh = AirsoftAssets::FindMesh(TEXT("Props"), TEXT("SteelTarget"), TEXT("Body"));
	UStaticMesh* PlateMesh = AirsoftAssets::FindMesh(TEXT("Props"), TEXT("SteelTarget"), TEXT("Plate"));
	bUsingAsset = StandMesh && PlateMesh;
	if (bUsingAsset)
	{
		Stand->SetStaticMesh(StandMesh);
		Plate->SetStaticMesh(PlateMesh);
		// Pieces share the asset origin; swing about the "Hinge" point if the kit provides one.
		const FAirsoftAssetLayout& L = UAirsoftGunVisual::Layout(TEXT("Props"), TEXT("SteelTarget"));
		const FVector HingePoint = L.Point(TEXT("Hinge")) ? *L.Point(TEXT("Hinge")) : FVector::ZeroVector;
		Hinge->SetRelativeLocation(HingePoint);
		Plate->SetRelativeLocation(-HingePoint);
		bCanSwing = L.Point(TEXT("Hinge")) != nullptr;
	}
	else
	{
		Stand->SetStaticMesh(AirsoftAssets::Cylinder());
		Stand->SetRelativeLocation(FVector(-4.f, 0.f, 50.f));
		Stand->SetRelativeScale3D(FVector(0.05f, 0.05f, 1.f));
		Plate->SetStaticMesh(AirsoftAssets::Cylinder());
		// Disc facing +X, hanging below the hinge.
		Plate->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -PlateSize * 0.5f - 4.f), FRotator(90.f, 0.f, 0.f));
		Plate->SetRelativeScale3D(FVector(PlateSize / 100.f, PlateSize / 100.f, 0.015f));
	}
	if (UMaterialInterface* Base = Plate->GetMaterial(0))
	{
		PlateMID = UMaterialInstanceDynamic::Create(Base, this);
		Plate->SetMaterial(0, PlateMID);
		if (!bUsingAsset)
		{
			PlateMID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.85f, 0.32f, 0.05f));
		}
	}

	if (Caption.IsEmpty())
	{
		Label->SetText(FText::GetEmpty());
	}
	else
	{
		Label->SetText(FText::FromString(Caption));
	}
}

void AAirsoftPracticeTarget::Ding(const FVector& ImpactPoint)
{
	++Hits;
	SwingVelocity += 260.f; // plate faces +X, so it kicks away from the shooter
	Flash = 1.f;
	AirsoftAssets::Play3D(this, TEXT("SteelDing"), ImpactPoint, 0.9f, FMath::FRandRange(0.94f, 1.08f) * FMath::Clamp(40.f / PlateSize, 0.8f, 1.4f));
	SetActorTickEnabled(true);
}

void AAirsoftPracticeTarget::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// Damped pendulum about the top hinge.
	const float Stiffness = 90.f;
	const float Damping = 5.5f;
	SwingVelocity += (-Stiffness * Swing - Damping * SwingVelocity) * DeltaSeconds;
	Swing += SwingVelocity * DeltaSeconds;
	Swing = FMath::Clamp(Swing, -50.f, 50.f);
	Hinge->SetRelativeRotation(FRotator(bCanSwing ? -Swing : 0.f, 0.f, 0.f));

	Flash = FMath::Max(0.f, Flash - DeltaSeconds * 4.f);
	if (PlateMID)
	{
		PlateMID->SetScalarParameterValue(TEXT("HitFlash"), Flash);
		if (!bUsingAsset)
		{
			PlateMID->SetVectorParameterValue(TEXT("Color"), FMath::Lerp(FLinearColor(0.85f, 0.32f, 0.05f), FLinearColor::White, Flash));
		}
	}

	if (FMath::Abs(Swing) < 0.05f && FMath::Abs(SwingVelocity) < 0.05f && Flash <= 0.f)
	{
		Swing = 0.f;
		SwingVelocity = 0.f;
		Hinge->SetRelativeRotation(FRotator::ZeroRotator);
		SetActorTickEnabled(false);
	}
}
