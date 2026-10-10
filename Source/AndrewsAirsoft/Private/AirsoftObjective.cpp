#include "AirsoftObjective.h"

#include "AirsoftAssets.h"
#include "AirsoftGunVisual.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"
#include "UObject/ConstructorHelpers.h"

AAirsoftObjective::AAirsoftObjective()
{
	bReplicates = true;
	bAlwaysRelevant = true;
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.f;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));

	Ring = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Ring"));
	Ring->SetupAttachment(Root);
	Ring->SetStaticMesh(CylinderMesh.Object);
	Ring->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Ring->SetCastShadow(false);
	Ring->SetRelativeLocation(FVector(0.f, 0.f, 2.f));

	Pole = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Pole"));
	Pole->SetupAttachment(Root);
	Pole->SetStaticMesh(CylinderMesh.Object);
	Pole->SetRelativeScale3D(FVector(0.08f, 0.08f, 4.5f));
	Pole->SetRelativeLocation(FVector(0.f, 0.f, 225.f));
	Pole->SetCollisionProfileName(TEXT("BlockAll"));

	Flag = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Flag"));
	Flag->SetupAttachment(Root);
	Flag->SetStaticMesh(CubeMesh.Object);
	Flag->SetRelativeScale3D(FVector(1.3f, 0.02f, 0.85f));
	Flag->SetRelativeLocation(FVector(68.f, 0.f, 400.f));
	Flag->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	Glow = CreateDefaultSubobject<UPointLightComponent>(TEXT("Glow"));
	Glow->SetupAttachment(Root);
	Glow->SetRelativeLocation(FVector(0.f, 0.f, 380.f));
	Glow->SetIntensity(2500.f);
	Glow->SetAttenuationRadius(900.f);
	Glow->SetCastShadows(false);

	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(Root);
	Label->SetRelativeLocation(FVector(0.f, 0.f, 520.f));
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetWorldSize(90.f);
	Label->SetText(FText::FromString(TEXT("A")));
}

void AAirsoftObjective::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AAirsoftObjective, OwnerTeam);
	DOREPLIFETIME(AAirsoftObjective, Progress);
	DOREPLIFETIME(AAirsoftObjective, CapturingTeam);
	DOREPLIFETIME(AAirsoftObjective, bContested);
	DOREPLIFETIME(AAirsoftObjective, bActive);
}

void AAirsoftObjective::BeginPlay()
{
	Super::BeginPlay();
	Ring->SetRelativeScale3D(FVector(Radius * 2.f / 100.f, Radius * 2.f / 100.f, 0.02f));
	RingMID = AirsoftAssets::MakeEmissive(this, FLinearColor::White, 1.5f);
	Ring->SetMaterial(0, RingMID);

	// Use the 4K flag pole from the asset kit when it has been imported.
	UStaticMesh* PoleMesh = AirsoftAssets::FindMesh(TEXT("Props"), TEXT("FlagPole_Objective"), TEXT("Body"));
	UStaticMesh* FlagMesh = AirsoftAssets::FindMesh(TEXT("Props"), TEXT("FlagPole_Objective"), TEXT("Flag"));
	if (PoleMesh && FlagMesh)
	{
		bAssetFlag = true;
		Pole->SetStaticMesh(PoleMesh);
		Pole->SetRelativeTransform(FTransform::Identity);
		Flag->SetStaticMesh(FlagMesh);
		Flag->SetRelativeTransform(FTransform::Identity);
		FlagMID = Flag->CreateDynamicMaterialInstance(0);
		const FAirsoftAssetLayout& L = UAirsoftGunVisual::Layout(TEXT("Props"), TEXT("FlagPole_Objective"));
		const FVector* Top = L.Point(TEXT("FlagTop"));
		const float TopZ = Top ? Top->Z : 600.f;
		Label->SetRelativeLocation(FVector(0.f, 0.f, TopZ + 110.f));
		Glow->SetRelativeLocation(FVector(0.f, 0.f, TopZ - 40.f));
	}
	else
	{
		FlagMID = AirsoftAssets::MakeEmissive(this, FLinearColor::White, 0.6f);
		Flag->SetMaterial(0, FlagMID);
	}
	Label->SetText(FText::FromString(Letter));
	RefreshVisuals();
}

void AAirsoftObjective::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// Flag flutter and a label that always faces the local camera.
	FlagWave += DeltaSeconds;
	Flag->SetRelativeRotation(FRotator(0.f, FMath::Sin(FlagWave * 1.7f) * 12.f, bAssetFlag ? 0.f : FMath::Sin(FlagWave * 3.1f) * 3.f));
	if (const UWorld* World = GetWorld())
	{
		if (APlayerController* PC = World->GetFirstPlayerController())
		{
			if (PC->PlayerCameraManager)
			{
				const FVector CamLoc = PC->PlayerCameraManager->GetCameraLocation();
				const FVector To = CamLoc - Label->GetComponentLocation();
				Label->SetWorldRotation(FRotator(0.f, To.Rotation().Yaw, 0.f));
			}
		}
	}
}

bool AAirsoftObjective::IsInside(const FVector& Location) const
{
	const FVector Delta = Location - GetActorLocation();
	return FVector2D(Delta.X, Delta.Y).Size() <= Radius && FMath::Abs(Delta.Z) <= HalfHeight;
}

EAirsoftTeam AAirsoftObjective::ServerUpdate(float DeltaSeconds, int32 BlueCount, int32 RedCount, float CaptureTime)
{
	if (!bActive)
	{
		return EAirsoftTeam::None;
	}
	bContested = BlueCount > 0 && RedCount > 0;
	CapturingTeam = EAirsoftTeam::None;
	if (bContested || (BlueCount == 0 && RedCount == 0))
	{
		return EAirsoftTeam::None;
	}
	const EAirsoftTeam Team = BlueCount > 0 ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
	if (Team == OwnerTeam)
	{
		return EAirsoftTeam::None;
	}
	CapturingTeam = Team;
	const int32 Count = FMath::Max(BlueCount, RedCount);
	const float Rate = DeltaSeconds / CaptureTime * FMath::Min(1.f + (Count - 1) * 0.5f, 2.5f);
	const float Dir = Team == EAirsoftTeam::Blue ? -1.f : 1.f;
	const float Before = Progress;
	Progress = FMath::Clamp(Progress + Dir * Rate, -1.f, 1.f);

	// Crossing the midpoint neutralises the previous owner.
	if (OwnerTeam != EAirsoftTeam::None && FMath::Sign(Before) != FMath::Sign(Progress))
	{
		OwnerTeam = EAirsoftTeam::None;
	}
	EAirsoftTeam Captured = EAirsoftTeam::None;
	if (FMath::Abs(Progress) >= 1.f && OwnerTeam != Team)
	{
		OwnerTeam = Team;
		Captured = Team;
	}
	RefreshVisuals();
	return Captured;
}

void AAirsoftObjective::ServerReset(bool bEnable)
{
	OwnerTeam = EAirsoftTeam::None;
	Progress = 0.f;
	CapturingTeam = EAirsoftTeam::None;
	bContested = false;
	bActive = bEnable;
	RefreshVisuals();
}

FLinearColor AAirsoftObjective::CurrentColor() const
{
	const FLinearColor Neutral(0.8f, 0.8f, 0.8f);
	if (OwnerTeam != EAirsoftTeam::None)
	{
		return AirsoftColors::Team(OwnerTeam);
	}
	if (Progress < 0.f)
	{
		return FLinearColor::LerpUsingHSV(Neutral, AirsoftColors::Team(EAirsoftTeam::Blue), -Progress);
	}
	if (Progress > 0.f)
	{
		return FLinearColor::LerpUsingHSV(Neutral, AirsoftColors::Team(EAirsoftTeam::Red), Progress);
	}
	return Neutral;
}

void AAirsoftObjective::OnRep_State()
{
	RefreshVisuals();
}

void AAirsoftObjective::RefreshVisuals()
{
	const FLinearColor Color = CurrentColor();
	if (RingMID)
	{
		RingMID->SetVectorParameterValue(TEXT("Color"), Color);
		RingMID->SetScalarParameterValue(TEXT("Intensity"), bActive ? 1.5f : 0.f);
	}
	if (FlagMID)
	{
		FlagMID->SetVectorParameterValue(bAssetFlag ? TEXT("PrimaryTint") : TEXT("Color"), Color);
	}
	Ring->SetVisibility(bActive);
	Flag->SetVisibility(bActive);
	Pole->SetVisibility(bActive);
	Pole->SetCollisionEnabled(bActive ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	Label->SetVisibility(bActive);
	Label->SetTextRenderColor(Color.ToFColor(true));
	Glow->SetLightColor(Color);
	Glow->SetVisibility(bActive);
}
