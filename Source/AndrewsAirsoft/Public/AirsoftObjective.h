// Andrew's Airsoft - Domination capture point (A/B/C), also the VIP extraction
// zone. A map may place a dedicated extraction point with Letter "X": it is
// never a Domination point. Under a low ceiling (the garage's lower decks) the
// pole, flag and label shrink to fit so nothing pokes through the deck above.

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
	/** VIP extraction zone this round (shown in the attackers' colour, labelled EXTRACT). */
	UPROPERTY(ReplicatedUsing = OnRep_State, BlueprintReadOnly) bool bExtraction = false;

	bool IsInside(const FVector& Location) const;
	/** Placed only as a VIP extraction point (Letter "X"): never a Domination point. */
	bool IsExtractionOnly() const;

	/** Server: advance capture. Returns the team that just took the point, or None. */
	EAirsoftTeam ServerUpdate(float DeltaSeconds, int32 BlueCount, int32 RedCount, float CaptureTime);
	void ServerReset(bool bEnable);
	/** Server: show this point as the VIP extraction zone for AttackingTeam. */
	void ServerSetExtraction(EAirsoftTeam AttackingTeam);

	FLinearColor CurrentColor() const;

protected:
	UFUNCTION() void OnRep_State();
	void RefreshVisuals();
	/** Shrinks the pole, flag, label and light under a ceiling lower than the full-height pole. */
	void FitUnderCeiling();

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
