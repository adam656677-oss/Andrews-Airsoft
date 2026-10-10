// Andrew's Airsoft - code-driven visual effects: muzzle puffs, BB impacts per
// surface, the tag pop, grenade bursts and footstep dust.
//
// Plastic BBs, not bullets: no blood, no bullet holes, no casings. Everything is
// cosmetic and local to each machine (never replicated, never touches gameplay),
// pooled with hard caps, and one world subsystem moves every live effect - no
// per-effect actors or ticks. Nothing exists on a dedicated server.
//
// Materials come from the editor setup script (materials.py: M_FXSmoke, M_FXGlow).
// If they are missing the glows fall back to the project's emissive material and
// the smoke puffs are skipped, so the game still runs.

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "Subsystems/WorldSubsystem.h"
#include "Tickable.h"
#include "UObject/ObjectKey.h"
#include "AirsoftEffects.generated.h"

class AActor;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UPointLightComponent;
class UStaticMeshComponent;
struct FHitResult;
struct FAirsoftWeaponDef;

/** What a BB hit, for the impact look and how far the BB bounces. */
enum class EAirsoftSurface : uint8
{
	Default,
	Metal,   // painted steel, containers, cars, scaffolding
	Steel,   // practice target plates: bright ping
	Wood,    // plywood, timber, OSB, crates
	Stone,   // concrete, asphalt, brick, rock, marble
	Dirt,    // dirt, mud, gravel, forest floor
	Foliage, // grass, leaves, bushes, straw
	Soft,    // fabric, sandbags, velvet, carpet, leather, netting
	Glass,
	Water,   // puddles, wet asphalt
	Rubber,  // tyres, cones
	Player
};

/** Tuning for the effects (Project Settings > Game > Airsoft Effects). User on/off switches live in the profile. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Airsoft Effects"))
class ANDREWSAIRSOFT_API UAirsoftEffectsSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	/** Lit translucent puff (Color, Opacity, Rim, Emissive) built by materials.py. */
	UPROPERTY(Config, EditAnywhere, Category = "Materials")
	TSoftObjectPtr<UMaterialInterface> SmokeMaterial = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/Game/Airsoft/Materials/M_FXSmoke.M_FXSmoke")));

	/** Additive unlit glow (Color, Intensity) built by materials.py; BB tracers, sparks, flashes. */
	UPROPERTY(Config, EditAnywhere, Category = "Materials")
	TSoftObjectPtr<UMaterialInterface> GlowMaterial = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/Game/Airsoft/Materials/M_FXGlow.M_FXGlow")));

	// --- Budgets (scaled down on Low/Medium graphics quality) ---------------------
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0")) int32 MaxSmoke = 64;
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0")) int32 MaxGlow = 64;
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0")) int32 MaxDebris = 48;
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0", ClampMax = "8")) int32 MaxLights = 4;
	/** Particles started per frame, all effects together (grenades and your own gun ignore it). */
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "1")) int32 MaxSpawnsPerFrame = 40;
	/** Visible tracers for other players' BBs (your own always get one); the rest fly unseen. */
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0")) int32 MaxRemoteTracers = 160;
	/** Bouncing spent BBs alive at once / started per frame. */
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0")) int32 MaxRicochets = 32;
	UPROPERTY(Config, EditAnywhere, Category = "Budget", meta = (ClampMin = "0")) int32 MaxRicochetsPerFrame = 6;

	// --- Distances (cm from the camera) -------------------------------------------
	UPROPERTY(Config, EditAnywhere, Category = "Distances") float ImpactCullDistance = 6000.f;
	UPROPERTY(Config, EditAnywhere, Category = "Distances") float DebrisCullDistance = 2500.f;
	UPROPERTY(Config, EditAnywhere, Category = "Distances") float MuzzleCullDistance = 7000.f;
	UPROPERTY(Config, EditAnywhere, Category = "Distances") float FootDustCullDistance = 2500.f;
	UPROPERTY(Config, EditAnywhere, Category = "Distances") float LightCullDistance = 3500.f;

	// --- BB tracers ---------------------------------------------------------------
	/** Streak length = speed x this (s): ~38 cm at 110 m/s, a round dot once the BB has slowed. */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float TracerLengthSeconds = 0.0035f;
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float TracerMaxLength = 60.f;
	/** Streak thickness up close (a 6 mm BB plus glow). */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float TracerWidth = 0.9f;
	/** Far streaks are kept at least this many screen pixels wide (dimmed to match) so TSR does not lose them. */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float TracerMinPixels = 1.6f;
	/** Lowest brightness a far, widened streak is dimmed to (fraction). */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float TracerFarDimFloor = 0.35f;
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float TracerIntensity = 9.f;
	/** "Tracer unit" glow on night maps. */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float NightTracerBoost = 2.f;
	/** Map name fragments that count as night maps. */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") TArray<FString> NightMapKeywords = { TEXT("VelvetClub"), TEXT("NightjarGarage") };
	/** Brightness of spent, bouncing BBs. */
	UPROPERTY(Config, EditAnywhere, Category = "Tracers") float RicochetIntensity = 2.5f;

	// --- Looks ----------------------------------------------------------------------
	/** Multiplies every muzzle puff's opacity (0 = off). */
	UPROPERTY(Config, EditAnywhere, Category = "Looks") float MuzzlePuffScale = 1.f;
	/** Brief cool light on gas guns' shots (cinematic only), candela. */
	UPROPERTY(Config, EditAnywhere, Category = "Looks") float GasMuzzleLightCandela = 2.5f;
	/** Multiplies every impact puff's opacity. */
	UPROPERTY(Config, EditAnywhere, Category = "Looks") float ImpactScale = 1.f;
	/** Grenade burst light peak, candela. */
	UPROPERTY(Config, EditAnywhere, Category = "Looks") float GrenadeLightCandela = 60.f;
	/** Players within this distance of a grenade burst get a camera shake that fades with distance. */
	UPROPERTY(Config, EditAnywhere, Category = "Looks") float GrenadeShakeRadius = 1500.f;
	/** Multiplies all camera shakes. */
	UPROPERTY(Config, EditAnywhere, Category = "Looks") float ShakeScale = 1.f;

	// --- Rain ---------------------------------------------------------------------
	/** Map name fragments where it rains: ripples appear on wet ground and puddles around the camera. */
	UPROPERTY(Config, EditAnywhere, Category = "Rain") TArray<FString> RainMapKeywords = { TEXT("NightjarGarage") };
	/** Ripples per second (0 = off); a short downward trace each. */
	UPROPERTY(Config, EditAnywhere, Category = "Rain", meta = (ClampMin = "0")) float RainRipplesPerSecond = 14.f;
	/** Ripples land within this distance of the camera (cm). */
	UPROPERTY(Config, EditAnywhere, Category = "Rain") float RainRippleRadius = 1200.f;

	static const UAirsoftEffectsSettings* Get() { return GetDefault<UAirsoftEffectsSettings>(); }
};

namespace AirsoftEffects
{
	/**
	 * User switches, read from the profile (FAirsoftUserSettings::bCinematicEffects / bScreenShake)
	 * when those fields exist; both default to on.
	 */
	ANDREWSAIRSOFT_API bool CinematicEnabled(const UObject* WorldContext);
	ANDREWSAIRSOFT_API bool ScreenShakeEnabled(const UObject* WorldContext);

	/** Surface from the hit actor / mesh / material names (no physical materials needed). Uncached. */
	ANDREWSAIRSOFT_API EAirsoftSurface ClassifySurface(const FHitResult& Hit);

	/** How much speed a BB keeps bouncing off this surface (0 = it stops dead). */
	ANDREWSAIRSOFT_API float Restitution(EAirsoftSurface Surface);
}

/** One live particle: a pooled sphere/cube moved and faded by the subsystem. */
enum class EAirsoftFXLayer : uint8
{
	Smoke,  // lit translucent puffs and rings
	Glow,   // additive flashes, sparks, streaks
	Debris  // small opaque chips and grit
};

struct FAirsoftFXParticle
{
	EAirsoftFXLayer Layer = EAirsoftFXLayer::Smoke;
	int32 Slot = INDEX_NONE;
	FVector Location = FVector::ZeroVector;
	FVector Velocity = FVector::ZeroVector;
	/** Stretch axis (the mesh X axis); ignored when AlignToVelocity. */
	FVector Axis = FVector::UpVector;
	/** Size in cm at birth and death: X along Axis, Y/Z across. */
	FVector Size0 = FVector(10.f);
	FVector Size1 = FVector(20.f);
	FLinearColor Color = FLinearColor::White;
	/** Peak opacity (smoke) or emissive intensity (glow). */
	float Alpha = 1.f;
	float Emissive = 0.f;
	float Rim = 0.f;
	/** Negative = delayed start (hidden until 0). */
	float Age = 0.f;
	float Life = 0.3f;
	/** cm/s^2 downward. */
	float Gravity = 0.f;
	/** 1/s velocity damping. */
	float Drag = 0.f;
	/** Fraction of life spent fading in. */
	float FadeIn = 0.f;
	float FadePow = 1.f;
	/** Debris: bounces once off this height. */
	double FloorZ = -UE_BIG_NUMBER;
	/** Glow streaks: X follows the velocity and stretches with speed. */
	bool bAlignToVelocity = false;
	float StretchSeconds = 0.f;
	/** Debris: tumbling rotation. */
	FRotator Rotation = FRotator::ZeroRotator;
	FRotator Spin = FRotator::ZeroRotator;
	float LastParam = -1.f;
};

USTRUCT()
struct FAirsoftFXPool
{
	GENERATED_BODY()

	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> Components;
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;
	TArray<int32> Free;
};

UCLASS()
class ANDREWSAIRSOFT_API UAirsoftEffectsSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	/** Null on a dedicated server or a non-game world. */
	static UAirsoftEffectsSubsystem* Get(const UObject* WorldContext);

	/** Gas puff / barrel breath at the muzzle (Direction = barrel forward). */
	void MuzzlePuff(const FVector& Muzzle, const FVector& Direction, const FAirsoftWeaponDef& Weapon, bool bQuiet, bool bFirstPerson, float AimAlpha = 0.f);

	/** A BB hit something (any BB this machine draws, local or remote). */
	void BBImpact(const FHitResult& Hit, const FVector& Velocity, EAirsoftSurface Surface);

	/** Surface for a hit, cached per component. */
	EAirsoftSurface SurfaceOf(const FHitResult& Hit);

	/** The moment a player is called out: orange pop where the last BB struck them. */
	void TagPop(const AActor* Victim);

	/** The same pop at a known spot (e.g. the slow-motion final-tag replay's impact). */
	void TagPopAt(const FVector& Location);

	/** Shooter-only: a small white pop on the confirmed hit. */
	void HitConfirmPop(const FVector& Location);

	/** Gas BB grenade: flash, expanding gas puff, ground dust ring, BB spray, nearby camera shake. */
	void GrenadeBurst(const FVector& Location, float Radius);

	/** Kicked-up dust under a running player on dusty ground. Strength 0..1. */
	void FootDust(const AActor* Walker, const FVector& FootLocation, float Strength);

	/** Landing puff. Strength 0..1 from the fall speed. */
	void LandingDust(const FHitResult& FloorHit, float Strength);

	/** Shakes the local player's view if they are within Radius of Origin. */
	void ShakeNear(const FVector& Origin, float Radius, float Strength);

	/** Camera of the local viewer, refreshed each frame (false before the first camera exists). */
	bool HasView() const { return bHasView; }
	const FVector& GetViewLocation() const { return ViewLocation; }
	/** Radians covered by one screen pixel at the current FOV. */
	float GetPixelAngle() const { return PixelAngle; }
	bool IsNightMap() const { return bNightMap; }
	bool IsCinematic() const { return bCinematic; }
	/** 0.5 .. 1 from the user's graphics quality. */
	float GetQualityScale() const { return QualityScale; }
	/** The pawn this machine views from (BBs striking it would burst right in front of the camera). */
	bool IsViewerPawn(const AActor* Actor) const;

	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;

private:
	bool Spawn(const FAirsoftFXParticle& Particle, bool bForce = false);
	void ApplyParticle(FAirsoftFXParticle& Particle);
	void Release(const FAirsoftFXParticle& Particle);
	void UpdateParticles(float DeltaTime);
	void UpdateLights(float DeltaTime);
	void UpdateView();
	void UpdateRain(float DeltaTime);
	void RefreshUserOptions();
	bool ShouldSpawnAt(const FVector& Location, float MaxDistance) const;
	float ViewDistance(const FVector& Location) const;
	int32 Count(float Base) const;

	// Building blocks.
	void Puff(const FVector& Location, const FVector& Direction, const FLinearColor& Color, float Size0, float Size1, float Opacity, float Life, float Speed, float Rise = 0.f, bool bForce = false);
	void Ring(const FVector& Location, const FVector& Normal, const FLinearColor& Color, float Size0, float Size1, float Opacity, float Life, float Delay = 0.f, bool bForce = false);
	void Flash(const FVector& Location, const FLinearColor& Color, float Size0, float Size1, float Intensity, float Life, bool bForce = false);
	void Sparks(const FVector& Location, const FVector& Direction, int32 Num, const FLinearColor& Color, float SpeedMin, float SpeedMax, float ConeDeg, float Intensity, float Life, float Gravity, bool bForce = false);
	void Debris(const FVector& Location, const FVector& Direction, int32 Num, const FLinearColor& Color, float SizeMin, float SizeMax, float SpeedMin, float SpeedMax, float ConeDeg, float Life, bool bForce = false);
	void Light(const FVector& Location, const FLinearColor& Color, float Candela, float Radius, float Life);
	double FloorBelow(const FVector& Location, float MaxDrop) const;
	void RememberPlayerHit(const AActor* Player, const FVector& Location);
	FLinearColor DustColor(EAirsoftSurface Surface) const;

	FAirsoftFXPool& PoolFor(EAirsoftFXLayer Layer);
	int32 CapFor(EAirsoftFXLayer Layer) const;
	UMaterialInterface* MaterialFor(EAirsoftFXLayer Layer);
	AActor* EnsureOwner();

	UPROPERTY() FAirsoftFXPool SmokePool;
	UPROPERTY() FAirsoftFXPool GlowPool;
	UPROPERTY() FAirsoftFXPool DebrisPool;
	UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> Lights;
	UPROPERTY() TObjectPtr<AActor> EffectsOwner;
	UPROPERTY() TObjectPtr<UMaterialInterface> SmokeMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> DebrisMat;

	struct FLiveLight
	{
		int32 Slot = INDEX_NONE;
		float Age = 0.f;
		float Life = 0.05f;
		float Peak = 1.f;
	};

	struct FPlayerHitMemo
	{
		TWeakObjectPtr<const AActor> Player;
		FVector Location = FVector::ZeroVector;
		double Time = -100.0;
	};

	TArray<FAirsoftFXParticle> Particles;
	TArray<FLiveLight> LiveLights;
	TArray<int32> FreeLights;
	TMap<FObjectKey, EAirsoftSurface> SurfaceCache;
	FPlayerHitMemo PlayerHits[8];
	int32 NextPlayerHit = 0;

	FVector ViewLocation = FVector::ZeroVector;
	FVector ViewDirection = FVector::ForwardVector;
	float PixelAngle = 0.0008f;
	bool bHasView = false;
	bool bNightMap = false;
	bool bRainMap = false;
	float RainAccumulator = 0.f;
	bool bCinematic = true;
	bool bMaterialsResolved = false;
	/** The glow material is the additive one (not the opaque emissive fallback): flash spheres are allowed. */
	bool bGlowAdditive = false;
	float QualityScale = 1.f;
	int32 SpawnBudget = 0;
	float OptionsRefreshIn = 0.f;
};
