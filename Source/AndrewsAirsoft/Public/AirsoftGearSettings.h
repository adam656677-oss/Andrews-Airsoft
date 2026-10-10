// Andrew's Airsoft - third-person team gear settings (Project Settings > Game > Airsoft Team Gear).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "AirsoftGearSettings.generated.h"

UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Airsoft Team Gear"))
class ANDREWSAIRSOFT_API UAirsoftGearSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	/** Master switch for the gear worn by every third-person body (Content/Airsoft/Data/Gear.json, Gear meshes). */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear")
	bool bEnableTeamGear = true;

	/**
	 * Yaw (degrees) that turns character space (+X forward, the space the gear is modelled in) into the body
	 * mesh's component space. The UE5 mannequin (Manny) faces +Y in its asset, hence 90.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear")
	float MeshFacingYaw = 90.f;

	UPROPERTY(Config, EditAnywhere, Category = "Team Gear")
	bool bCastShadows = true;

	/** The owner sees first-person arms instead of the body but still sees the body's shadow; keep the gear in it. */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear")
	bool bOwnerSeesShadow = true;

	/**
	 * Also hide the gear (keeping its shadow) while its owner looks through this body's own camera. Belt and braces
	 * for OwnerNoSee, which Nanite meshes may ignore; the gear still shows when the view target is another camera (replays).
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear")
	bool bHideFromOwnerView = true;

	/** Pieces that follow a limb (armband, knee pads) are turned onto the skeleton's bone direction unless it differs from the modelled one by more than this. */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear", meta = (ClampMin = "0", ClampMax = "180"))
	float MaxAlignAngle = 60.f;

	/** Draw distance (cm) of translucent pieces (goggle lens). 0 = unlimited. */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear", meta = (ClampMin = "0"))
	float GlassCullDistance = 6000.f;

	/** Without the Third Person pack: put the head set (helmet/cap, goggles, mask) on the stand-in sphere head. */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear")
	bool bGearOnFallbackBody = true;

	/** Scale of the head set on the stand-in sphere head (the sphere is bigger than a real head). */
	UPROPERTY(Config, EditAnywhere, Category = "Team Gear", meta = (ClampMin = "0.1"))
	float FallbackHeadScale = 1.25f;

	static const UAirsoftGearSettings* Get() { return GetDefault<UAirsoftGearSettings>(); }
};
