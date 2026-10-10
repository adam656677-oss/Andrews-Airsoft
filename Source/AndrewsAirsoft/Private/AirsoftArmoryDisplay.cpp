#include "AirsoftArmoryDisplay.h"

#include "AirsoftGunVisual.h"
#include "AirsoftTypes.h"
#include "AirsoftWeaponData.h"
#include "Components/BoxComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/TextRenderComponent.h"

AAirsoftArmoryDisplay::AAirsoftArmoryDisplay()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;

	InteractBox = CreateDefaultSubobject<UBoxComponent>(TEXT("InteractBox"));
	InteractBox->InitBoxExtent(FVector(15.f, 60.f, 35.f));
	InteractBox->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	InteractBox->SetCollisionResponseToAllChannels(ECR_Ignore);
	InteractBox->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
	SetRootComponent(InteractBox);

	Pivot = CreateDefaultSubobject<USceneComponent>(TEXT("Pivot"));
	Pivot->SetupAttachment(InteractBox);

	// Gun lies side-on to the viewer: its barrel (+X) runs along the bay's width (+Y).
	Gun = CreateDefaultSubobject<UAirsoftGunVisual>(TEXT("Gun"));
	Gun->SetupAttachment(Pivot);
	Gun->SetRelativeRotation(FRotator(0.f, 90.f, 0.f));

	Label = CreateDefaultSubobject<UTextRenderComponent>(TEXT("Label"));
	Label->SetupAttachment(InteractBox);
	Label->SetRelativeLocation(FVector(14.f, 0.f, -46.f));
	Label->SetHorizontalAlignment(EHTA_Center);
	Label->SetVerticalAlignment(EVRTA_TextCenter);
	Label->SetWorldSize(7.f);
	Label->SetTextRenderColor(FColor(232, 176, 92));
	Label->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	SubLabel = CreateDefaultSubobject<UTextRenderComponent>(TEXT("SubLabel"));
	SubLabel->SetupAttachment(InteractBox);
	SubLabel->SetRelativeLocation(FVector(14.f, 0.f, -54.f));
	SubLabel->SetHorizontalAlignment(EHTA_Center);
	SubLabel->SetVerticalAlignment(EVRTA_TextCenter);
	SubLabel->SetWorldSize(4.f);
	SubLabel->SetTextRenderColor(FColor(180, 160, 130));
	SubLabel->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	KeyLight = CreateDefaultSubobject<USpotLightComponent>(TEXT("KeyLight"));
	KeyLight->SetupAttachment(InteractBox);
	KeyLight->SetRelativeLocationAndRotation(FVector(90.f, 0.f, 70.f), FRotator(-38.f, 180.f, 0.f));
	KeyLight->SetIntensity(2400.f);
	KeyLight->SetAttenuationRadius(260.f);
	KeyLight->SetInnerConeAngle(18.f);
	KeyLight->SetOuterConeAngle(38.f);
	KeyLight->SetLightColor(FLinearColor(1.f, 0.86f, 0.68f));
	KeyLight->SetCastShadows(true);
}

void AAirsoftArmoryDisplay::BeginPlay()
{
	Super::BeginPlay();
	Rebuild();
	SetActorTickEnabled(bRotate);
}

#if WITH_EDITOR
void AAirsoftArmoryDisplay::PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent)
{
	Super::PostEditChangeProperty(PropertyChangedEvent);
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(WeaponId);
	Label->SetText(FText::FromString(Def ? Def->Name.ToUpper() : WeaponId.ToString()));
}
#endif

void AAirsoftArmoryDisplay::Rebuild()
{
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(WeaponId);
	if (!Def)
	{
		Gun->Clear();
		Label->SetText(FText::FromString(WeaponId.ToString()));
		SubLabel->SetText(FText::GetEmpty());
		return;
	}
	FAirsoftCustomization Custom;
	Custom.WeaponId = WeaponId;
	Custom = AirsoftWeapons::Clean(Custom);
	// Display guns are built for everyone (not first person), with a brass accent.
	Gun->Build(Custom, FLinearColor(0.85f, 0.6f, 0.25f), false, true);

	// Centre the gun on the bay using its muzzle/stock span.
	const float Length = Gun->MuzzleLocal.X + 30.f;
	Gun->SetRelativeLocation(FVector(0.f, -(Gun->MuzzleLocal.X - Length * 0.5f), -6.f));

	Label->SetVisibility(bShowLabel);
	SubLabel->SetVisibility(bShowLabel);
	Label->SetText(FText::FromString(Def->Name.ToUpper()));
	SubLabel->SetText(FText::FromString(FString::Printf(TEXT("%s  ·  %s"), *Def->Kind, *Def->Class)));
}

void AAirsoftArmoryDisplay::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Pivot->AddLocalRotation(FRotator(0.f, 18.f * DeltaSeconds, 0.f));
}

FString AAirsoftArmoryDisplay::GetPrompt() const
{
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(WeaponId);
	return FString::Printf(TEXT("[F]  Customize %s"), Def ? *Def->Name : *WeaponId.ToString());
}
