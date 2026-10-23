// Andrew's Airsoft - steel plate on the practice range: rings and swings when hit.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AirsoftPracticeTarget.generated.h"

class UStaticMeshComponent;
class UTextRenderComponent;
class UMaterialInstanceDynamic;

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftPracticeTarget : public AActor
{
	GENERATED_BODY()

public:
	AAirsoftPracticeTarget();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Shown under the plate, e.g. "25 m". Empty = measured from the firing line at BeginPlay. */
	UPROPERTY(EditAnywhere, Category = "Airsoft")
	FString Caption;

	/** Plate diameter in cm. */
	UPROPERTY(EditAnywhere, Category = "Airsoft")
	float PlateSize = 40.f;

	/** Local feedback for the shooter (the plate is not replicated). */
	void Ding(const FVector& ImpactPoint);

	int32 GetHits() const { return Hits; }

protected:
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Stand;
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Hinge;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Plate;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UTextRenderComponent> Label;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> PlateMID;

	float Swing = 0.f;
	float SwingVelocity = 0.f;
	float Flash = 0.f;
	int32 Hits = 0;
	bool bUsingAsset = false;
	bool bCanSwing = true;
};
