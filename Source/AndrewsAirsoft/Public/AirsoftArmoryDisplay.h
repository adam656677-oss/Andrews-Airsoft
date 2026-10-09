// Andrew's Airsoft - a gun on show in the staging armory. Look at it and
// press Interact to customize that weapon.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AirsoftArmoryDisplay.generated.h"

class UBoxComponent;
class UAirsoftGunVisual;
class UTextRenderComponent;
class USpotLightComponent;

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftArmoryDisplay : public AActor
{
	GENERATED_BODY()

public:
	AAirsoftArmoryDisplay();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
#if WITH_EDITOR
	virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
#endif

	/** Weapon id from AirsoftWeaponData (M4, AK74, SR25, ...). */
	UPROPERTY(EditAnywhere, Category = "Airsoft")
	FName WeaponId = TEXT("M4");

	/** Slowly turn on the stand (false = hang flat in a wall bay). */
	UPROPERTY(EditAnywhere, Category = "Airsoft")
	bool bRotate = false;

	/** Show the brass plaque text. */
	UPROPERTY(EditAnywhere, Category = "Airsoft")
	bool bShowLabel = true;

	FString GetPrompt() const;

protected:
	void Rebuild();

	UPROPERTY(VisibleAnywhere) TObjectPtr<UBoxComponent> InteractBox;
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Pivot;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UAirsoftGunVisual> Gun;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UTextRenderComponent> Label;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UTextRenderComponent> SubLabel;
	UPROPERTY(VisibleAnywhere) TObjectPtr<USpotLightComponent> KeyLight;
};
