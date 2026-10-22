// Andrew's Airsoft - third-person airsoft team gear: plate carrier, helmet or soft cap, goggles,
// mesh lower-face mask, team armband and (sometimes) knee pads, attached to the body's bones and
// coloured for the team. Data: Content/Airsoft/Data/Gear.json (Tools/Blender/gear/build_teamgear.py).
// The same component also dresses a body in the tailored suit outfit (ApplySuit: jacket, shirt and tie,
// trousers, belt, shoes and a slicked-back haircut as rigid per-bone pieces; Tools/Blender/gear/build_suit.py).
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
class UStaticMesh;
class UStaticMeshComponent;

/** What a third-person body wears. */
UENUM(BlueprintType)
enum class EAirsoftOutfit : uint8
{
	/** Plate carrier, helmet or cap, goggles, mask, armband (ApplyTo). */
	TeamGear,
	/** Tailored suit; in multiplayer the tie and pocket square carry the team colour (ApplySuit). */
	Suit
};

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

	/**
	 * Dresses Body in the tailored suit instead of the team gear (removes any team gear first). InSuitColor tints the
	 * cloth (see SuitColor() for the Gear.json colourways); VariantSeed picks the shirt (unless Shirt names one of
	 * Gear.json Suit.Colorways.Shirt, e.g. "Black" / "White"), the dark tie and the hair colour deterministically.
	 * Only owns the pieces it attaches (hides nothing on the body). Pieces whose mesh is not imported are skipped;
	 * returns true if at least one piece is attached (false: keep whatever fallback look the caller uses).
	 */
	bool ApplySuit(USkinnedMeshComponent* Body, FLinearColor InSuitColor, int32 VariantSeed, FName Shirt = NAME_None);

	/** TeamGear: ApplyTo. Suit: a multiplayer suit (colourway from Gear.json Suit.MultiplayerSuits by seed), tie in the team colour. */
	bool ApplyOutfit(USkinnedMeshComponent* Body, EAirsoftOutfit Outfit, EAirsoftTeam Team, int32 VariantSeed);

	/**
	 * Puts an original character head (GearHeads.json, Tools/Blender/heads) on Body's head bone, on top of the suit or team gear
	 * already applied. Character: a story name ("Andrew", or a boss by its Campaign.json name, "Name, the Title" works);
	 * NAME_None picks one of the Ledger crew heads from VariantSeed. Removes the suit's own haircut. Changes nothing and
	 * returns false when that head is not in the data or not imported.
	 */
	bool ApplyHead(USkinnedMeshComponent* Body, FName Character, int32 VariantSeed);

	/** The head asset ApplyHead would use (NAME_None when the character has none). */
	static FName HeadFor(FName Character, int32 VariantSeed);

	/** True while a character head is worn. */
	bool HasHead() const;

	/** A suit colourway from Gear.json Suit.Colorways.Suit: "Charcoal", "MidnightNavy", "Oxblood", "Black". Unknown names give Charcoal. */
	static FLinearColor SuitColor(FName Colorway);

	/** True while the suit (rather than team gear) is worn. */
	bool IsWearingSuit() const { return bSuit && Components.Num() > 0; }

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

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

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
		/** Mask B colour when bTeamAccent is false (the suit's tie). */
		FLinearColor Accent = FLinearColor::Black;
		/** Mask B takes the team colour (team gear patches, the multiplayer suit's tie). */
		bool bTeamAccent = true;
	};

	bool Build(USceneComponent* InParent, bool bInFallback, EAirsoftTeam Team, int32 VariantSeed);
	bool BuildSuit(USkinnedMeshComponent* Body, FLinearColor InSuitColor, int32 VariantSeed, FName Shirt, bool bTeamTie, EAirsoftTeam Team);
	/** Creates, attaches and registers one piece's mesh component. */
	bool AddPart(const FPart& Part, UStaticMesh* Mesh, USceneComponent* InParent, bool bInFallback, EAirsoftTeam Team);
	/** True while the owning player views the world through this body's own camera. */
	bool IsOwnerViewing() const;
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
	/** The suit outfit is applied (else team gear); with its inputs, for Rebuild. */
	bool bSuit = false;
	bool bSuitTeamTie = false;
	FLinearColor AppliedSuitColor = FLinearColor::Black;
	FName AppliedShirt;
	/** ApplyHead: the worn head asset and its inputs (for Rebuild); bHeadOnly when no suit / team gear is under it. */
	FName AppliedHead;
	FName AppliedHeadCharacter;
	int32 AppliedHeadSeed = 0;
	bool bHeadOnly = false;
	bool bWantVisible = true;
	bool bOwnerViewHidden = false;
};
