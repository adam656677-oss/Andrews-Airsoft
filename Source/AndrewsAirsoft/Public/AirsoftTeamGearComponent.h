// Andrew's Airsoft - third-person airsoft team gear: plate carrier, helmet or soft cap, goggles,
// mesh lower-face mask, team armband and (sometimes) knee pads, attached to the body's bones and
// coloured for the team. Data: Content/Airsoft/Data/Gear.json (Tools/Blender/gear/build_teamgear.py).
//
// Placement never depends on bone local axes: every piece is modelled in character space
// (+X forward, +Z up) with its origin at its anchor bone's pivot, and the attach transform is
// computed from the skeleton's reference pose. Console (non-shipping):
//   airsoft.gear.tune <AssetId[/Piece]> <x> <y> <z> [pitch yaw roll [scale]]   live offset (cm, character space), logs the JSON
//   airsoft.gear.show 0|1   airsoft.gear.reload   airsoft.gear.bones   airsoft.gear.list   airsoft.gear.reroll

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AirsoftTypes.h"
#include "AirsoftTeamGearComponent.generated.h"

class USceneComponent;
class USkinnedMeshComponent;
class UStaticMeshComponent;

UCLASS(ClassGroup = (Airsoft), meta = (BlueprintSpawnableComponent))
class ANDREWSAIRSOFT_API UAirsoftTeamGearComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UAirsoftTeamGearComponent();

	/**
	 * Dresses Body (the visible third-person skinned mesh) in the team gear. VariantSeed picks the look
	 * deterministically on every machine (pass the PlayerState's player id). Calling again with the same
	 * body and seed only recolours. Pieces whose mesh is not imported are skipped.
	 * Returns true if at least one piece is attached.
	 */
	bool ApplyTo(USkinnedMeshComponent* Body, EAirsoftTeam Team, int32 VariantSeed);

	/** Head set only (helmet or cap, goggles, mask) on the stand-in sphere head used when the mannequin is missing. */
	bool ApplyToFallbackHead(USceneComponent* Head, EAirsoftTeam Team, int32 VariantSeed);

	/** Recolours the team-coloured parts (patches, helmet band, armband). */
	void SetTeam(EAirsoftTeam Team);

	/** Removes every gear piece. */
	void Clear();

	/** Shows or hides this player's gear (airsoft.gear.show 0 hides all gear on top of this). */
	void SetGearVisible(bool bVisible);

	/** True when the team armband is worn (the old stand-in TeamBand can then be hidden). */
	bool HasArmband() const;
	bool HasGear() const { return Components.Num() > 0; }

	/** Rebuilds with the last body/team/seed (after airsoft.gear.reload / reroll). */
	void Rebuild();
	/** Re-applies the anchors (after airsoft.gear.tune). */
	void RefreshPlacement();
	/** Logs the body's reference-pose anchor bones next to the generator's assumed positions. */
	void LogBones() const;
	/** Applies the global show flag. */
	void RefreshVisibility();

protected:
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	struct FPart
	{
		FName AssetId;
		FName Piece;
		FName Kind;
		FName Slot;
		/** Tuning key: "Asset", or "Asset/Piece" for pieces with their own anchor (knee pads). */
		FName AnchorKey;
		FName Bone;
		FLinearColor Primary = FLinearColor::Black;
		FLinearColor Secondary = FLinearColor::Black;
	};

	bool Build(USceneComponent* InParent, bool bInFallback, EAirsoftTeam Team, int32 VariantSeed);
	bool ComputeRelative(const FPart& Part, FTransform& OutRelative) const;
	void ApplyMaterials(UStaticMeshComponent* Comp, const FPart& Part, EAirsoftTeam Team) const;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Components;

	/** Parallel to Components. */
	TArray<FPart> Parts;

	TWeakObjectPtr<USceneComponent> Parent;
	TWeakObjectPtr<UObject> ParentAsset;
	int32 AppliedSeed = 0;
	EAirsoftTeam AppliedTeam = EAirsoftTeam::None;
	bool bApplied = false;
	bool bFallback = false;
	bool bWantVisible = true;
};
