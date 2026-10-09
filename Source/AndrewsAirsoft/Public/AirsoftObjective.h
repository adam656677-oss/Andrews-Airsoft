// Andrew's Airsoft - Domination capture point (A/B/C).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AirsoftTypes.h"
#include "AirsoftObjective.generated.h"

class UStaticMeshComponent;
class UPointLightComponent;
class UMaterialInstanceDynamic;
class UTextRenderComponent;

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftObjective : public AActor
{
	GENERATED_BODY()

public:
	AAirsoftObjective();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airsoft")
	FString Letter = TEXT("A");

	/** Capture radius in cm. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airsoft")
	float Radius = 500.f;

	/** Vertical tolerance in cm (keeps a point upstairs from being captured from below). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Airsoft")
	float HalfHeight = 250.f;

	UPROPERTY(ReplicatedUsing = OnRep_State, BlueprintReadOnly) EAirsoftTeam OwnerTeam = EAirsoftTeam::None;
	/** -1 = fully Blue, +1 = fully Red. */
	UPROPERTY(ReplicatedUsing = OnRep_State, BlueprintReadOnly) float Progress = 0.f;
	UPROPERTY(ReplicatedUsing = OnRep_State, BlueprintReadOnly) EAirsoftTeam CapturingTeam = EAirsoftTeam::None;
	UPROPERTY(ReplicatedUsing = OnRep_State, BlueprintReadOnly) bool bContested = false;
	UPROPERTY(ReplicatedUsing = OnRep_State, BlueprintReadOnly) bool bActive = false;

	bool IsInside(const FVector& Location) const;

	/** Server: advance capture. Returns the team that just took the point, or None. */
	EAirsoftTeam ServerUpdate(float DeltaSeconds, int32 BlueCount, int32 RedCount, float CaptureTime);
	void ServerReset(bool bEnable);

	FLinearColor CurrentColor() const;

protected:
	UFUNCTION() void OnRep_State();
	void RefreshVisuals();

	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> Root;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Ring;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Pole;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> Flag;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPointLightComponent> Glow;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UTextRenderComponent> Label;

	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> RingMID;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> FlagMID;

	float FlagWave = 0.f;
	bool bAssetFlag = false;
};
