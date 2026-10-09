// Andrew's Airsoft - assembles a gun from its imported pieces + attachments,
// or a simple stand-in until the 4K assets have been imported.

#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "AirsoftTypes.h"
#include "AirsoftGunVisual.generated.h"

class UStaticMeshComponent;
class USpotLightComponent;
class UMaterialInstanceDynamic;

/** Named points on a gun or attachment, read from Content/Airsoft/Data/*.json. */
struct FAirsoftAssetLayout
{
	TMap<FName, FVector> Points;
	TArray<FName> Pieces;
	TArray<FName> Kinds;
	bool bLoaded = false;

	const FVector* Point(FName Name) const { return Points.Find(Name); }
};

UCLASS(ClassGroup = (Airsoft), meta = (BlueprintSpawnableComponent))
class ANDREWSAIRSOFT_API UAirsoftGunVisual : public USceneComponent
{
	GENERATED_BODY()

public:
	UAirsoftGunVisual();

	/** Rebuilds the gun. First-person guns are only visible to their owner and cast no shadows. */
	void Build(const FAirsoftCustomization& Custom, const FLinearColor& TeamAccent, bool bFirstPerson, bool bThirdPerson);
	void Clear();

	FName GetWeaponId() const { return Built.WeaponId; }
	const FAirsoftCustomization& GetCustomization() const { return Built; }

	/** Points in this component's local space (cm). */
	FVector AimPointLocal = FVector(-14.f, 0.f, 15.f);
	FVector MuzzleLocal = FVector(55.f, 0.f, 9.f);
	FVector LeftHandLocal = FVector(28.f, 0.f, 4.f);
	FVector MagWellLocal = FVector(12.f, 0.f, 2.f);
	FVector LaserLocal = FVector::ZeroVector;
	bool bHasLaser = false;

	FVector GetMuzzleWorld() const { return GetComponentTransform().TransformPosition(MuzzleLocal); }
	FVector GetLaserWorld() const { return GetComponentTransform().TransformPosition(LaserLocal); }

	/** Animation offsets for moving parts, applied about each part's pivot. */
	void SetPartOffsets(const FTransform& Mag, const FTransform& Slide, const FTransform& Bolt, const FTransform& Pump);

	void SetLightOn(bool bOn);
	bool IsLightOn() const { return bLightOn; }

	/** Fades optic housings when fully aimed so the sight picture is clear. */
	void SetOpticFade(float Alpha);

	static const FAirsoftAssetLayout& Layout(const FString& Category, FName Id);

private:
	UStaticMeshComponent* AddPart(UStaticMesh* Mesh, FName Kind, const FTransform& Relative, const FVector& Pivot);
	void BuildFallbackGun(const FAirsoftCustomization& Custom);
	void BuildFallbackAttachment(FName AttachmentId, FName Slot, const FVector& Mount);
	UStaticMeshComponent* AddBox(const FVector& Center, const FVector& Size, const FLinearColor& Color, FName Kind = TEXT("Body"));
	void ApplyMaterials(UStaticMeshComponent* Comp);

	struct FPartInfo
	{
		FName Kind;
		FTransform Base;
		FVector Pivot;
		bool bOptic = false;
	};

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> Parts;
	TArray<FPartInfo> PartInfo;

	UPROPERTY()
	TObjectPtr<USpotLightComponent> Light;

	FAirsoftCustomization Built;
	FLinearColor Accent = FLinearColor::White;
	bool bFP = false;
	bool bTP = true;
	bool bLightOn = false;
	float OpticFade = 0.f;
};
