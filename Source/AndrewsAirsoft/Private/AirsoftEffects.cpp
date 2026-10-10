#include "AirsoftEffects.h"

#include "AirsoftAssets.h"
#include "AirsoftCharacter.h"
#include "AirsoftGameInstance.h"
#include "AirsoftPracticeTarget.h"
#include "AirsoftSaveGame.h"
#include "AirsoftWeaponData.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/HitResult.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirsoftFX, Log, All);

// Helpers live in a named namespace: unity builds merge .cpp files, so anonymous-namespace names must not collide.
namespace AirsoftEffectsPrivate
{
	struct FSurfaceKey
	{
		const TCHAR* Key;
		EAirsoftSurface Surface;
	};

	// Piece suffixes first (a tree's leaves, a lamp's glass, a flag pole's cloth).
	const FSurfaceKey SuffixKeys[] = {
		{ TEXT("_Glass"), EAirsoftSurface::Glass },
		{ TEXT("_Emissive"), EAirsoftSurface::Glass },
		{ TEXT("_Leaves"), EAirsoftSurface::Foliage },
		{ TEXT("_Shrub"), EAirsoftSurface::Foliage },
		{ TEXT("_Flag"), EAirsoftSurface::Soft },
		{ TEXT("_Rope"), EAirsoftSurface::Soft },
	};

	// Whole-name keywords (asset ids from Content/Airsoft/Data, material ids from Materials.json), first match wins.
	const FSurfaceKey NameKeys[] = {
		{ TEXT("SteelTarget"), EAirsoftSurface::Steel },
		{ TEXT("Puddle"), EAirsoftSurface::Water },
		{ TEXT("Water"), EAirsoftSurface::Water },
		{ TEXT("Wet"), EAirsoftSurface::Water },
		{ TEXT("Glass"), EAirsoftSurface::Glass },
		{ TEXT("Neon"), EAirsoftSurface::Glass },
		{ TEXT("Chandelier"), EAirsoftSurface::Glass },
		{ TEXT("LightFluo"), EAirsoftSurface::Glass },
		{ TEXT("LightSodium"), EAirsoftSurface::Glass },
		{ TEXT("Emissive"), EAirsoftSurface::Glass },
		{ TEXT("Tire"), EAirsoftSurface::Rubber },
		{ TEXT("Rubber"), EAirsoftSurface::Rubber },
		{ TEXT("Cone"), EAirsoftSurface::Rubber },
		{ TEXT("WheelStop"), EAirsoftSurface::Rubber },
		// Names that would otherwise hit a broader keyword below.
		{ TEXT("Crate_Ammo"), EAirsoftSurface::Metal },
		{ TEXT("RopePost"), EAirsoftSurface::Metal },
		{ TEXT("StreetLamp"), EAirsoftSurface::Metal },
		{ TEXT("BlockPallet"), EAirsoftSurface::Stone },
		{ TEXT("JerseyBarrier"), EAirsoftSurface::Stone },
		{ TEXT("BarrierArm"), EAirsoftSurface::Metal },
		{ TEXT("DJBooth"), EAirsoftSurface::Wood },
		{ TEXT("BoothSofa"), EAirsoftSurface::Soft },
		{ TEXT("BoothTable"), EAirsoftSurface::Wood },
		// Soft: the BB just stops.
		{ TEXT("Sandbag"), EAirsoftSurface::Soft },
		{ TEXT("Netting"), EAirsoftSurface::Soft },
		{ TEXT("Tent"), EAirsoftSurface::Soft },
		{ TEXT("Canvas"), EAirsoftSurface::Soft },
		{ TEXT("Burlap"), EAirsoftSurface::Soft },
		{ TEXT("Velvet"), EAirsoftSurface::Soft },
		{ TEXT("Carpet"), EAirsoftSurface::Soft },
		{ TEXT("Rug"), EAirsoftSurface::Soft },
		{ TEXT("Leather"), EAirsoftSurface::Soft },
		{ TEXT("Sofa"), EAirsoftSurface::Soft },
		{ TEXT("Armchair"), EAirsoftSurface::Soft },
		{ TEXT("TrashBag"), EAirsoftSurface::Soft },
		{ TEXT("Speaker"), EAirsoftSurface::Soft },
		{ TEXT("Fabric"), EAirsoftSurface::Soft },
		{ TEXT("Cloth"), EAirsoftSurface::Soft },
		// Foliage and straw.
		{ TEXT("Leaves"), EAirsoftSurface::Foliage },
		{ TEXT("Bush"), EAirsoftSurface::Foliage },
		{ TEXT("Foliage"), EAirsoftSurface::Foliage },
		{ TEXT("Grass"), EAirsoftSurface::Foliage },
		{ TEXT("Shrub"), EAirsoftSurface::Foliage },
		{ TEXT("Straw"), EAirsoftSurface::Foliage },
		{ TEXT("Hay"), EAirsoftSurface::Foliage },
		// Loose ground.
		{ TEXT("Dirt"), EAirsoftSurface::Dirt },
		{ TEXT("Mud"), EAirsoftSurface::Dirt },
		{ TEXT("Gravel"), EAirsoftSurface::Dirt },
		{ TEXT("ForestFloor"), EAirsoftSurface::Dirt },
		{ TEXT("Soil"), EAirsoftSurface::Dirt },
		{ TEXT("Sand"), EAirsoftSurface::Dirt },
		// Wood.
		{ TEXT("Plywood"), EAirsoftSurface::Wood },
		{ TEXT("OSB"), EAirsoftSurface::Wood },
		{ TEXT("Timber"), EAirsoftSurface::Wood },
		{ TEXT("Wood"), EAirsoftSurface::Wood },
		{ TEXT("Walnut"), EAirsoftSurface::Wood },
		{ TEXT("Bark"), EAirsoftSurface::Wood },
		{ TEXT("Logs"), EAirsoftSurface::Wood },
		{ TEXT("Pallet"), EAirsoftSurface::Wood },
		{ TEXT("Crate"), EAirsoftSurface::Wood },
		{ TEXT("Barricade"), EAirsoftSurface::Wood },
		{ TEXT("Watchtower"), EAirsoftSurface::Wood },
		{ TEXT("CableSpool"), EAirsoftSurface::Wood },
		{ TEXT("Counter"), EAirsoftSurface::Wood },
		{ TEXT("BackBar"), EAirsoftSurface::Wood },
		{ TEXT("Table"), EAirsoftSurface::Wood },
		{ TEXT("Tree_"), EAirsoftSurface::Wood },
		// Stone.
		{ TEXT("Concrete"), EAirsoftSurface::Stone },
		{ TEXT("Asphalt"), EAirsoftSurface::Stone },
		{ TEXT("Brick"), EAirsoftSurface::Stone },
		{ TEXT("Granite"), EAirsoftSurface::Stone },
		{ TEXT("Marble"), EAirsoftSurface::Stone },
		{ TEXT("Rock"), EAirsoftSurface::Stone },
		{ TEXT("Stone"), EAirsoftSurface::Stone },
		{ TEXT("Pillar"), EAirsoftSurface::Stone },
		{ TEXT("Ramp"), EAirsoftSurface::Stone },
		{ TEXT("Planter"), EAirsoftSurface::Stone },
		{ TEXT("PaintLine"), EAirsoftSurface::Stone },
		{ TEXT("Curb"), EAirsoftSurface::Stone },
		// Metal.
		{ TEXT("Steel"), EAirsoftSurface::Metal },
		{ TEXT("Metal"), EAirsoftSurface::Metal },
		{ TEXT("DiamondPlate"), EAirsoftSurface::Metal },
		{ TEXT("Brass"), EAirsoftSurface::Metal },
		{ TEXT("Container"), EAirsoftSurface::Metal },
		{ TEXT("Drum"), EAirsoftSurface::Metal },
		{ TEXT("Car_"), EAirsoftSurface::Metal },
		{ TEXT("WreckedCar"), EAirsoftSurface::Metal },
		{ TEXT("Truck"), EAirsoftSurface::Metal },
		{ TEXT("Dumpster"), EAirsoftSurface::Metal },
		{ TEXT("Scaffold"), EAirsoftSurface::Metal },
		{ TEXT("Railing"), EAirsoftSurface::Metal },
		{ TEXT("Pipe"), EAirsoftSurface::Metal },
		{ TEXT("Ladder"), EAirsoftSurface::Metal },
		{ TEXT("Roof"), EAirsoftSurface::Metal },
		{ TEXT("Corrugated"), EAirsoftSurface::Metal },
		{ TEXT("Floodlight"), EAirsoftSurface::Metal },
		{ TEXT("FlagPole"), EAirsoftSurface::Metal },
		{ TEXT("Bollard"), EAirsoftSurface::Metal },
		{ TEXT("Lamp"), EAirsoftSurface::Metal },
		{ TEXT("Sconce"), EAirsoftSurface::Metal },
		{ TEXT("CeilingLight"), EAirsoftSurface::Metal },
		{ TEXT("MovingHead"), EAirsoftSurface::Metal },
		{ TEXT("GunDisplay"), EAirsoftSurface::Metal },
		{ TEXT("Stool"), EAirsoftSurface::Metal },
		{ TEXT("Kiosk"), EAirsoftSurface::Metal },
		{ TEXT("PayMachine"), EAirsoftSurface::Metal },
		{ TEXT("HVAC"), EAirsoftSurface::Metal },
		{ TEXT("Elevator"), EAirsoftSurface::Metal },
		{ TEXT("Cage"), EAirsoftSurface::Metal },
		{ TEXT("Drain"), EAirsoftSurface::Metal },
		{ TEXT("HeightBar"), EAirsoftSurface::Metal },
		{ TEXT("Booth"), EAirsoftSurface::Metal },
		{ TEXT("Sign"), EAirsoftSurface::Metal },
		{ TEXT("Post"), EAirsoftSurface::Metal },
		{ TEXT("Fence"), EAirsoftSurface::Metal },
	};

	EAirsoftSurface SurfaceFromName(const FString& Name)
	{
		for (const FSurfaceKey& Entry : SuffixKeys)
		{
			if (Name.EndsWith(Entry.Key))
			{
				return Entry.Surface;
			}
		}
		for (const FSurfaceKey& Entry : NameKeys)
		{
			if (Name.Contains(Entry.Key))
			{
				return Entry.Surface;
			}
		}
		return EAirsoftSurface::Default;
	}

	bool ProfileFlag(const UObject* WorldContext, FName Field, bool bDefault)
	{
		const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
		UAirsoftGameInstance* GI = World ? World->GetGameInstance<UAirsoftGameInstance>() : nullptr;
		if (!GI)
		{
			return bDefault;
		}
		// Looked up by name so this compiles before (and keeps working after) the profile gains the field.
		const FBoolProperty* Prop = FindFProperty<FBoolProperty>(FAirsoftUserSettings::StaticStruct(), Field);
		return Prop ? Prop->GetPropertyValue_InContainer(&GI->GetUserSettings()) : bDefault;
	}

	constexpr float FXBasicShapeSize = 100.f; // engine basic shapes are 100 cm across
}

// ---------------------------------------------------------------------------
// Free functions
// ---------------------------------------------------------------------------

namespace AirsoftEffects
{
	bool CinematicEnabled(const UObject* WorldContext)
	{
		return AirsoftEffectsPrivate::ProfileFlag(WorldContext, FName(TEXT("bCinematicEffects")), true);
	}

	bool ScreenShakeEnabled(const UObject* WorldContext)
	{
		return AirsoftEffectsPrivate::ProfileFlag(WorldContext, FName(TEXT("bScreenShake")), true);
	}

	EAirsoftSurface ClassifySurface(const FHitResult& Hit)
	{
		const AActor* HitActor = Hit.GetActor();
		if (Cast<APawn>(HitActor))
		{
			return EAirsoftSurface::Player;
		}
		if (Cast<AAirsoftPracticeTarget>(HitActor))
		{
			return EAirsoftSurface::Steel;
		}
		// Physical materials are optional; a named one (e.g. "PM_Wood") wins when present.
		if (const UPhysicalMaterial* PhysMat = Hit.PhysMaterial.Get())
		{
			const EAirsoftSurface FromPhys = AirsoftEffectsPrivate::SurfaceFromName(PhysMat->GetName());
			if (FromPhys != EAirsoftSurface::Default)
			{
				return FromPhys;
			}
		}
		const UPrimitiveComponent* Comp = Hit.GetComponent();
		if (!Comp)
		{
			return EAirsoftSurface::Default;
		}
		// Imported assets are SM_<AssetId>_<Piece>; engine shapes (Cube, Cylinder) fall through to the material.
		if (const UStaticMeshComponent* MeshComp = Cast<UStaticMeshComponent>(Comp))
		{
			if (const UStaticMesh* Mesh = MeshComp->GetStaticMesh())
			{
				const EAirsoftSurface FromMesh = AirsoftEffectsPrivate::SurfaceFromName(Mesh->GetName());
				if (FromMesh != EAirsoftSurface::Default)
				{
					return FromMesh;
				}
			}
		}
		// Simple collision does not say which section was hit: the first slot speaks for the mesh.
		// Setup-script instances are MI_<Material>[_Tint][_World] or MI_<AssetId>_<Piece>; runtime MIDs report their parent.
		const UMaterialInterface* Material = Comp->GetMaterial(0);
		for (int32 Guard = 0; Guard < 4 && Material; ++Guard)
		{
			const UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(Material);
			if (!MID || !MID->Parent)
			{
				break;
			}
			Material = MID->Parent.Get();
		}
		return Material ? AirsoftEffectsPrivate::SurfaceFromName(Material->GetName()) : EAirsoftSurface::Default;
	}

	float Restitution(EAirsoftSurface Surface)
	{
		switch (Surface)
		{
		case EAirsoftSurface::Steel: return 0.45f;
		case EAirsoftSurface::Metal: return 0.42f;
		case EAirsoftSurface::Glass: return 0.4f;
		case EAirsoftSurface::Stone: return 0.38f;
		case EAirsoftSurface::Rubber: return 0.5f;
		case EAirsoftSurface::Default: return 0.3f;
		case EAirsoftSurface::Wood: return 0.24f;
		case EAirsoftSurface::Player: return 0.18f;
		case EAirsoftSurface::Water: return 0.15f; // mostly wet concrete and asphalt: a short skip
		default: return 0.f; // dirt, grass and fabric swallow the BB
		}
	}
}

// ---------------------------------------------------------------------------
// Subsystem lifetime
// ---------------------------------------------------------------------------

UAirsoftEffectsSubsystem* UAirsoftEffectsSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	if (!World || World->GetNetMode() == NM_DedicatedServer)
	{
		return nullptr;
	}
	return World->GetSubsystem<UAirsoftEffectsSubsystem>();
}

bool UAirsoftEffectsSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (IsRunningDedicatedServer() || !Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}
	const UWorld* World = Cast<UWorld>(Outer);
	return World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE);
}

void UAirsoftEffectsSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	RefreshUserOptions();
	// Load the effect materials with the map rather than on the first shot (the BB tracers share M_FXGlow).
	MaterialFor(EAirsoftFXLayer::Glow);
}

void UAirsoftEffectsSubsystem::Deinitialize()
{
	Particles.Reset();
	LiveLights.Reset();
	FreeLights.Reset();
	SurfaceCache.Reset();
	SmokePool = FAirsoftFXPool();
	GlowPool = FAirsoftFXPool();
	DebrisPool = FAirsoftFXPool();
	Lights.Reset();
	EffectsOwner = nullptr;
	Super::Deinitialize();
}

TStatId UAirsoftEffectsSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(UAirsoftEffectsSubsystem, STATGROUP_Tickables);
}

void UAirsoftEffectsSubsystem::Tick(float DeltaTime)
{
	// DeltaTime is game time, so effects slow down with any time dilation along with everything else.
	UpdateView();
	OptionsRefreshIn -= DeltaTime;
	if (OptionsRefreshIn <= 0.f)
	{
		OptionsRefreshIn = 0.5f;
		RefreshUserOptions();
	}
	SpawnBudget = FMath::Max(1, FMath::RoundToInt(static_cast<float>(UAirsoftEffectsSettings::Get()->MaxSpawnsPerFrame) * QualityScale));
	UpdateParticles(DeltaTime);
	UpdateLights(DeltaTime);
	UpdateRain(DeltaTime);
}

void UAirsoftEffectsSubsystem::RefreshUserOptions()
{
	bCinematic = AirsoftEffects::CinematicEnabled(this);
	QualityScale = 1.f;
	UWorld* World = GetWorld();
	if (UAirsoftGameInstance* GI = World ? World->GetGameInstance<UAirsoftGameInstance>() : nullptr)
	{
		const int32 Quality = FMath::Clamp(GI->GetUserSettings().Quality, 0, 3);
		QualityScale = Quality <= 0 ? 0.5f : (Quality == 1 ? 0.75f : 1.f);
	}
	bNightMap = false;
	bRainMap = false;
	if (World)
	{
		const FString MapName = World->GetMapName();
		const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
		for (const FString& Keyword : S->NightMapKeywords)
		{
			bNightMap = bNightMap || (!Keyword.IsEmpty() && MapName.Contains(Keyword));
		}
		for (const FString& Keyword : S->RainMapKeywords)
		{
			bRainMap = bRainMap || (!Keyword.IsEmpty() && MapName.Contains(Keyword));
		}
	}
}

void UAirsoftEffectsSubsystem::UpdateRain(float DeltaTime)
{
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	UWorld* World = GetWorld();
	if (!bRainMap || !bHasView || !World || S->RainRipplesPerSecond <= 0.f || S->RainRippleRadius <= 0.f)
	{
		return;
	}
	RainAccumulator = FMath::Min(RainAccumulator + DeltaTime * S->RainRipplesPerSecond * QualityScale, 4.f);
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftFXRain), false);
	while (RainAccumulator >= 1.f)
	{
		RainAccumulator -= 1.f;
		// Drop from above a random spot around the camera; only wet ground and puddles show a ripple.
		const FVector2D Offset = FMath::RandPointInCircle(S->RainRippleRadius);
		const FVector Top = ViewLocation + FVector(Offset.X, Offset.Y, 600.0);
		FHitResult Hit;
		if (!World->LineTraceSingleByChannel(Hit, Top, Top - FVector(0.0, 0.0, 1400.0), ECC_Visibility, Query))
		{
			continue;
		}
		if (Hit.ImpactNormal.Z < 0.7 || SurfaceOf(Hit) != EAirsoftSurface::Water)
		{
			continue;
		}
		const float Size = FMath::FRandRange(7.f, 14.f);
		Ring(Hit.ImpactPoint + Hit.ImpactNormal * 0.4, Hit.ImpactNormal, DustColor(EAirsoftSurface::Water), 1.f, Size, 0.22f, FMath::FRandRange(0.4f, 0.6f));
	}
}

void UAirsoftEffectsSubsystem::UpdateView()
{
	bHasView = false;
	UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (!PC || !PC->PlayerCameraManager)
	{
		return;
	}
	ViewLocation = PC->PlayerCameraManager->GetCameraLocation();
	ViewDirection = PC->PlayerCameraManager->GetCameraRotation().Vector();
	float ScreenWidth = 1920.f;
	if (const UGameViewportClient* Viewport = World->GetGameViewport())
	{
		FVector2D Size(0.0, 0.0);
		Viewport->GetViewportSize(Size);
		if (Size.X > 1.0)
		{
			ScreenWidth = static_cast<float>(Size.X);
		}
	}
	const float HalfFov = FMath::DegreesToRadians(FMath::Clamp(PC->PlayerCameraManager->GetFOVAngle(), 5.f, 170.f) * 0.5f);
	PixelAngle = 2.f * FMath::Tan(HalfFov) / ScreenWidth;
	bHasView = true;
}

bool UAirsoftEffectsSubsystem::ShouldSpawnAt(const FVector& Location, float MaxDistance) const
{
	if (!bHasView)
	{
		return true;
	}
	const FVector ToLocation = Location - ViewLocation;
	const double DistSq = ToLocation.SizeSquared();
	if (DistSq > FMath::Square(static_cast<double>(MaxDistance)))
	{
		return false;
	}
	// Well behind the camera: nobody sees it in its short life.
	return DistSq < FMath::Square(400.0) || FVector::DotProduct(ToLocation, ViewDirection) > -200.0;
}

bool UAirsoftEffectsSubsystem::IsViewerPawn(const AActor* Actor) const
{
	const UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	return Actor && PC && PC->GetPawn() == Actor;
}

float UAirsoftEffectsSubsystem::ViewDistance(const FVector& Location) const
{
	return bHasView ? static_cast<float>(FVector::Dist(Location, ViewLocation)) : 0.f;
}

int32 UAirsoftEffectsSubsystem::Count(float Base) const
{
	return FMath::Max(0, FMath::RoundToInt(Base * QualityScale));
}

// ---------------------------------------------------------------------------
// Pools
// ---------------------------------------------------------------------------

FAirsoftFXPool& UAirsoftEffectsSubsystem::PoolFor(EAirsoftFXLayer Layer)
{
	switch (Layer)
	{
	case EAirsoftFXLayer::Smoke: return SmokePool;
	case EAirsoftFXLayer::Glow: return GlowPool;
	default: return DebrisPool;
	}
}

int32 UAirsoftEffectsSubsystem::CapFor(EAirsoftFXLayer Layer) const
{
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	const int32 Base = Layer == EAirsoftFXLayer::Smoke ? S->MaxSmoke : (Layer == EAirsoftFXLayer::Glow ? S->MaxGlow : S->MaxDebris);
	return FMath::Max(0, FMath::RoundToInt(static_cast<float>(Base) * QualityScale));
}

UMaterialInterface* UAirsoftEffectsSubsystem::MaterialFor(EAirsoftFXLayer Layer)
{
	if (!bMaterialsResolved)
	{
		bMaterialsResolved = true;
		const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
		SmokeMat = S->SmokeMaterial.IsNull() ? nullptr : S->SmokeMaterial.LoadSynchronous();
		GlowMat = S->GlowMaterial.IsNull() ? nullptr : S->GlowMaterial.LoadSynchronous();
		bGlowAdditive = GlowMat != nullptr;
		if (!GlowMat)
		{
			GlowMat = AirsoftAssets::EmissiveMaterial();
		}
		DebrisMat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"), nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!DebrisMat)
		{
			DebrisMat = UMaterial::GetDefaultMaterial(MD_Surface);
		}
		if (!SmokeMat || !bGlowAdditive)
		{
			UE_LOG(LogAirsoftFX, Warning, TEXT("Effects materials missing (%s, %s): run Content/Python/airsoft_setup.py. Dust and gas puffs are off until then."),
				*S->SmokeMaterial.ToString(), *S->GlowMaterial.ToString());
		}
	}
	switch (Layer)
	{
	case EAirsoftFXLayer::Smoke: return SmokeMat;
	case EAirsoftFXLayer::Glow: return GlowMat;
	default: return DebrisMat;
	}
}

AActor* UAirsoftEffectsSubsystem::EnsureOwner()
{
	if (IsValid(EffectsOwner.Get()))
	{
		return EffectsOwner.Get();
	}
	if (EffectsOwner)
	{
		// The owner died under us (world teardown): its components went with it.
		Particles.Reset();
		LiveLights.Reset();
		FreeLights.Reset();
		SmokePool = FAirsoftFXPool();
		GlowPool = FAirsoftFXPool();
		DebrisPool = FAirsoftFXPool();
		Lights.Reset();
		EffectsOwner = nullptr;
	}
	UWorld* World = GetWorld();
	if (!World)
	{
		return nullptr;
	}
	FActorSpawnParameters Params;
	Params.ObjectFlags |= RF_Transient;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	AActor* NewOwner = World->SpawnActor<AActor>(AActor::StaticClass(), FTransform::Identity, Params);
	if (!NewOwner)
	{
		return nullptr;
	}
	USceneComponent* Root = NewObject<USceneComponent>(NewOwner, TEXT("Root"));
	NewOwner->SetRootComponent(Root);
	Root->RegisterComponent();
	EffectsOwner = NewOwner;
	return NewOwner;
}

bool UAirsoftEffectsSubsystem::Spawn(const FAirsoftFXParticle& Particle, bool bForce)
{
	if (!bForce && SpawnBudget <= 0)
	{
		return false;
	}
	UMaterialInterface* Material = MaterialFor(Particle.Layer);
	if (!Material)
	{
		return false;
	}
	FAirsoftFXPool& Pool = PoolFor(Particle.Layer);
	int32 Slot = INDEX_NONE;
	while (Pool.Free.Num() > 0 && Slot == INDEX_NONE)
	{
		const int32 Candidate = Pool.Free.Pop();
		if (Pool.Components.IsValidIndex(Candidate) && Pool.Components[Candidate])
		{
			Slot = Candidate;
		}
	}
	if (Slot == INDEX_NONE)
	{
		if (Pool.Components.Num() >= CapFor(Particle.Layer))
		{
			return false;
		}
		AActor* Owner = EnsureOwner();
		if (!Owner)
		{
			return false;
		}
		UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(Owner, NAME_None, RF_Transient);
		Comp->SetMobility(EComponentMobility::Movable);
		Comp->SetStaticMesh(Particle.Layer == EAirsoftFXLayer::Debris ? AirsoftAssets::Cube() : AirsoftAssets::Sphere());
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetGenerateOverlapEvents(false);
		Comp->SetCanEverAffectNavigation(false);
		Comp->SetCastShadow(false);
		Comp->bReceivesDecals = false;
		Comp->bAffectDynamicIndirectLighting = false;
		Comp->bAffectDistanceFieldLighting = false;
		Comp->SetVisibility(false);
		Comp->RegisterComponent();
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(Material, Comp);
		if (MID)
		{
			Comp->SetMaterial(0, MID);
		}
		Slot = Pool.Components.Add(Comp);
		Pool.Materials.Add(MID);
	}

	if (UMaterialInstanceDynamic* MID = Pool.Materials.IsValidIndex(Slot) ? Pool.Materials[Slot].Get() : nullptr)
	{
		MID->SetVectorParameterValue(TEXT("Color"), Particle.Color);
		if (Particle.Layer == EAirsoftFXLayer::Smoke)
		{
			MID->SetScalarParameterValue(TEXT("Rim"), Particle.Rim);
			MID->SetScalarParameterValue(TEXT("Emissive"), Particle.Emissive);
		}
	}
	FAirsoftFXParticle& Added = Particles.Add_GetRef(Particle);
	Added.Slot = Slot;
	Added.LastParam = -1.f;
	ApplyParticle(Added);
	if (!bForce)
	{
		--SpawnBudget;
	}
	return true;
}

void UAirsoftEffectsSubsystem::ApplyParticle(FAirsoftFXParticle& P)
{
	FAirsoftFXPool& Pool = PoolFor(P.Layer);
	UStaticMeshComponent* Comp = Pool.Components.IsValidIndex(P.Slot) ? Pool.Components[P.Slot].Get() : nullptr;
	if (!Comp)
	{
		return;
	}
	if (P.Age < 0.f)
	{
		Comp->SetVisibility(false);
		return;
	}
	const float T = FMath::Clamp(P.Age / FMath::Max(P.Life, 0.001f), 0.f, 1.f);
	const float Grow = 1.f - FMath::Square(1.f - T); // fast out, slow settle
	FVector Size = FMath::Lerp(P.Size0, P.Size1, Grow);
	FVector Axis = P.Axis;
	FVector Center = P.Location;
	float Fade = FMath::Pow(1.f - T, P.FadePow);
	if (P.FadeIn > 0.f && T < P.FadeIn)
	{
		Fade *= T / P.FadeIn;
	}
	float Param = P.Alpha * Fade;

	if (P.bAlignToVelocity)
	{
		const double Speed = P.Velocity.Size();
		if (Speed > 1.0)
		{
			Axis = P.Velocity / Speed;
			Size.X = FMath::Max(Size.X, Speed * static_cast<double>(P.StretchSeconds));
		}
	}
	if (P.Layer == EAirsoftFXLayer::Glow && bHasView)
	{
		// Keep sparks and flashes at least ~1.5 px across (dimmed to match) so TSR does not swallow them.
		const double MinWidth = FVector::Dist(P.Location, ViewLocation) * static_cast<double>(PixelAngle) * 1.5;
		if (Size.Y < MinWidth)
		{
			Param *= FMath::Max(static_cast<float>(Size.Y / MinWidth), 0.3f);
			Size.X = FMath::Max(Size.X, MinWidth);
			Size.Y = MinWidth;
			Size.Z = MinWidth;
		}
	}
	if (P.bAlignToVelocity)
	{
		Center -= Axis * (Size.X * 0.5); // the streak trails behind its head
	}

	const FQuat Rotation = P.Layer == EAirsoftFXLayer::Debris ? P.Rotation.Quaternion() : FRotationMatrix::MakeFromX(Axis).ToQuat();
	Comp->SetWorldTransform(FTransform(Rotation, Center, Size / AirsoftEffectsPrivate::FXBasicShapeSize));

	if (P.Layer != EAirsoftFXLayer::Debris && FMath::Abs(Param - P.LastParam) > 0.002f + 0.04f * FMath::Max(P.LastParam, 0.f))
	{
		if (UMaterialInstanceDynamic* MID = Pool.Materials.IsValidIndex(P.Slot) ? Pool.Materials[P.Slot].Get() : nullptr)
		{
			MID->SetScalarParameterValue(P.Layer == EAirsoftFXLayer::Smoke ? FName(TEXT("Opacity")) : FName(TEXT("Intensity")), Param);
		}
		P.LastParam = Param;
	}
	Comp->SetVisibility(true);
}

void UAirsoftEffectsSubsystem::Release(const FAirsoftFXParticle& P)
{
	FAirsoftFXPool& Pool = PoolFor(P.Layer);
	if (!Pool.Components.IsValidIndex(P.Slot))
	{
		return;
	}
	if (UStaticMeshComponent* Comp = Pool.Components[P.Slot].Get())
	{
		Comp->SetVisibility(false);
		Pool.Free.Add(P.Slot);
	}
}

void UAirsoftEffectsSubsystem::UpdateParticles(float DeltaTime)
{
	for (int32 i = Particles.Num() - 1; i >= 0; --i)
	{
		FAirsoftFXParticle& P = Particles[i];
		P.Age += DeltaTime;
		if (P.Age >= P.Life)
		{
			Release(P);
			Particles.RemoveAtSwap(i);
			continue;
		}
		if (P.Age >= 0.f)
		{
			if (P.Drag > 0.f)
			{
				P.Velocity *= FMath::Max(0.f, 1.f - P.Drag * DeltaTime);
			}
			P.Velocity.Z -= P.Gravity * DeltaTime;
			P.Location += P.Velocity * DeltaTime;
			if (P.Layer == EAirsoftFXLayer::Debris)
			{
				P.Rotation += P.Spin * DeltaTime;
				if (P.Location.Z < P.FloorZ)
				{
					// One dull bounce, then it skids and shrinks away.
					P.Location.Z = P.FloorZ;
					P.Velocity.Z = FMath::Abs(P.Velocity.Z) * 0.25;
					P.Velocity.X *= 0.45;
					P.Velocity.Y *= 0.45;
					P.Spin *= 0.4f;
				}
			}
		}
		ApplyParticle(P);
	}
}

void UAirsoftEffectsSubsystem::Light(const FVector& Location, const FLinearColor& Color, float Candela, float Radius, float Life)
{
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	if (Candela <= 0.f || S->MaxLights <= 0 || !ShouldSpawnAt(Location, S->LightCullDistance))
	{
		return;
	}
	int32 Slot = INDEX_NONE;
	while (FreeLights.Num() > 0 && Slot == INDEX_NONE)
	{
		const int32 Candidate = FreeLights.Pop();
		if (Lights.IsValidIndex(Candidate) && Lights[Candidate])
		{
			Slot = Candidate;
		}
	}
	if (Slot == INDEX_NONE && Lights.Num() < S->MaxLights)
	{
		AActor* Owner = EnsureOwner();
		if (!Owner)
		{
			return;
		}
		UPointLightComponent* NewLight = NewObject<UPointLightComponent>(Owner, NAME_None, RF_Transient);
		NewLight->SetMobility(EComponentMobility::Movable);
		NewLight->SetCastShadows(false);
		NewLight->SetIntensityUnits(ELightUnits::Candelas);
		NewLight->SetIntensity(0.f);
		NewLight->SetSourceRadius(2.f);
		NewLight->SetVisibility(false);
		NewLight->RegisterComponent();
		Slot = Lights.Add(NewLight);
	}
	if (Slot == INDEX_NONE)
	{
		// All busy: take over the one closest to finishing.
		int32 Steal = INDEX_NONE;
		float MostDone = -1.f;
		for (int32 i = 0; i < LiveLights.Num(); ++i)
		{
			const float Done = LiveLights[i].Age / FMath::Max(LiveLights[i].Life, 0.001f);
			if (Done > MostDone)
			{
				MostDone = Done;
				Steal = i;
			}
		}
		if (Steal == INDEX_NONE)
		{
			return;
		}
		Slot = LiveLights[Steal].Slot;
		LiveLights.RemoveAtSwap(Steal);
	}
	UPointLightComponent* Comp = Lights.IsValidIndex(Slot) ? Lights[Slot].Get() : nullptr;
	if (!Comp)
	{
		return;
	}
	Comp->SetWorldLocation(Location);
	Comp->SetLightColor(Color);
	Comp->SetAttenuationRadius(Radius);
	Comp->SetIntensity(Candela);
	Comp->SetVisibility(true);
	FLiveLight& Live = LiveLights.AddDefaulted_GetRef();
	Live.Slot = Slot;
	Live.Age = 0.f;
	Live.Life = FMath::Max(Life, 0.01f);
	Live.Peak = Candela;
}

void UAirsoftEffectsSubsystem::UpdateLights(float DeltaTime)
{
	for (int32 i = LiveLights.Num() - 1; i >= 0; --i)
	{
		FLiveLight& Live = LiveLights[i];
		Live.Age += DeltaTime;
		UPointLightComponent* Comp = Lights.IsValidIndex(Live.Slot) ? Lights[Live.Slot].Get() : nullptr;
		if (!Comp || Live.Age >= Live.Life)
		{
			if (Comp)
			{
				Comp->SetIntensity(0.f);
				Comp->SetVisibility(false);
				FreeLights.Add(Live.Slot);
			}
			LiveLights.RemoveAtSwap(i);
			continue;
		}
		const float K = 1.f - Live.Age / Live.Life;
		Comp->SetIntensity(Live.Peak * K * K);
	}
}

// ---------------------------------------------------------------------------
// Building blocks
// ---------------------------------------------------------------------------

void UAirsoftEffectsSubsystem::Puff(const FVector& Location, const FVector& Direction, const FLinearColor& Color, float Size0, float Size1, float Opacity, float Life, float Speed, float Rise, bool bForce)
{
	if (Opacity <= 0.005f)
	{
		return;
	}
	const FVector Dir = Direction.IsNearlyZero() ? FVector::UpVector : Direction.GetSafeNormal();
	FAirsoftFXParticle P;
	P.Layer = EAirsoftFXLayer::Smoke;
	P.Location = Location;
	P.Velocity = Dir * static_cast<double>(Speed) + FVector(0.0, 0.0, static_cast<double>(Rise));
	P.Drag = 4.f;
	P.Axis = Dir;
	P.Size0 = FVector(Size0);
	P.Size1 = FVector(Size1);
	P.Color = Color;
	P.Alpha = Opacity;
	P.Emissive = bNightMap ? 0.05f : 0.02f; // a touch of self-light so dust never reads as a black blob
	P.Life = Life;
	P.FadeIn = 0.12f;
	P.FadePow = 1.5f;
	Spawn(P, bForce);
}

void UAirsoftEffectsSubsystem::Ring(const FVector& Location, const FVector& Normal, const FLinearColor& Color, float Size0, float Size1, float Opacity, float Life, float Delay, bool bForce)
{
	if (Opacity <= 0.005f)
	{
		return;
	}
	FAirsoftFXParticle P;
	P.Layer = EAirsoftFXLayer::Smoke;
	P.Location = Location;
	P.Axis = Normal.IsNearlyZero() ? FVector::UpVector : Normal.GetSafeNormal();
	// A flattened sphere drawn rim-only reads as an expanding ring.
	P.Size0 = FVector(FMath::Max(0.8f, Size0 * 0.06f), Size0, Size0);
	P.Size1 = FVector(FMath::Max(1.f, Size1 * 0.06f), Size1, Size1);
	P.Color = Color;
	P.Alpha = Opacity;
	P.Rim = 1.f;
	P.Emissive = bNightMap ? 0.05f : 0.02f;
	P.Age = -FMath::Max(Delay, 0.f);
	P.Life = Life;
	P.FadePow = 1.3f;
	Spawn(P, bForce);
}

void UAirsoftEffectsSubsystem::Flash(const FVector& Location, const FLinearColor& Color, float Size0, float Size1, float Intensity, float Life, bool bForce)
{
	// A solid emissive ball is no flash: needs the additive glow material.
	if (!bMaterialsResolved)
	{
		MaterialFor(EAirsoftFXLayer::Glow);
	}
	if (!bGlowAdditive || Intensity <= 0.f)
	{
		return;
	}
	FAirsoftFXParticle P;
	P.Layer = EAirsoftFXLayer::Glow;
	P.Location = Location;
	P.Size0 = FVector(Size0);
	P.Size1 = FVector(Size1);
	P.Color = Color;
	P.Alpha = Intensity;
	P.Life = Life;
	P.FadePow = 2.f;
	Spawn(P, bForce);
}

void UAirsoftEffectsSubsystem::Sparks(const FVector& Location, const FVector& Direction, int32 Num, const FLinearColor& Color, float SpeedMin, float SpeedMax, float ConeDeg, float Intensity, float Life, float Gravity, bool bForce)
{
	const FVector Dir = Direction.IsNearlyZero() ? FVector::UpVector : Direction.GetSafeNormal();
	const float Cone = FMath::DegreesToRadians(ConeDeg);
	for (int32 i = 0; i < Num; ++i)
	{
		FAirsoftFXParticle P;
		P.Layer = EAirsoftFXLayer::Glow;
		P.Location = Location;
		P.Velocity = FMath::VRandCone(Dir, Cone) * static_cast<double>(FMath::FRandRange(SpeedMin, FMath::Max(SpeedMin, SpeedMax)));
		P.bAlignToVelocity = true;
		P.StretchSeconds = 0.012f;
		P.Size0 = FVector(0.6f, 0.35f, 0.35f);
		P.Size1 = FVector(0.6f, 0.2f, 0.2f);
		P.Color = Color;
		P.Alpha = Intensity;
		P.Life = Life * FMath::FRandRange(0.6f, 1.25f);
		P.Gravity = Gravity;
		P.Drag = 3.f;
		P.FadePow = 1.2f;
		if (!Spawn(P, bForce))
		{
			break;
		}
	}
}

void UAirsoftEffectsSubsystem::Debris(const FVector& Location, const FVector& Direction, int32 Num, const FLinearColor& Color, float SizeMin, float SizeMax, float SpeedMin, float SpeedMax, float ConeDeg, float Life, bool bForce)
{
	if (Num <= 0)
	{
		return;
	}
	const FVector Dir = Direction.IsNearlyZero() ? FVector::UpVector : Direction.GetSafeNormal();
	const float Cone = FMath::DegreesToRadians(ConeDeg);
	const double Floor = FloorBelow(Location, 300.f);
	for (int32 i = 0; i < Num; ++i)
	{
		FAirsoftFXParticle P;
		P.Layer = EAirsoftFXLayer::Debris;
		P.Location = Location;
		P.Velocity = FMath::VRandCone(Dir, Cone) * static_cast<double>(FMath::FRandRange(SpeedMin, FMath::Max(SpeedMin, SpeedMax)));
		const float Size = FMath::FRandRange(SizeMin, FMath::Max(SizeMin, SizeMax));
		P.Size0 = FVector(Size, Size * FMath::FRandRange(0.5f, 1.f), Size * FMath::FRandRange(0.3f, 0.7f));
		P.Size1 = P.Size0 * 0.3;
		P.Color = Color * FMath::FRandRange(0.8f, 1.15f);
		P.Rotation = FRotator(FMath::FRandRange(0.f, 360.f), FMath::FRandRange(0.f, 360.f), FMath::FRandRange(0.f, 360.f));
		P.Spin = FRotator(FMath::FRandRange(-900.f, 900.f), FMath::FRandRange(-900.f, 900.f), FMath::FRandRange(-900.f, 900.f));
		P.Gravity = 980.f;
		P.Drag = 1.5f;
		P.FloorZ = Floor;
		P.Life = Life * FMath::FRandRange(0.7f, 1.3f);
		if (!Spawn(P, bForce))
		{
			break;
		}
	}
}

double UAirsoftEffectsSubsystem::FloorBelow(const FVector& Location, float MaxDrop) const
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return Location.Z - MaxDrop;
	}
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftFXFloor), false);
	FHitResult Hit;
	const FVector Start = Location + FVector(0.0, 0.0, 2.0);
	if (World->LineTraceSingleByChannel(Hit, Start, Start - FVector(0.0, 0.0, static_cast<double>(MaxDrop)), ECC_Visibility, Query))
	{
		return Hit.ImpactPoint.Z + 0.3;
	}
	return Location.Z - MaxDrop;
}

void UAirsoftEffectsSubsystem::RememberPlayerHit(const AActor* Player, const FVector& Location)
{
	const UWorld* World = GetWorld();
	if (!Player || !World)
	{
		return;
	}
	FPlayerHitMemo& Memo = PlayerHits[NextPlayerHit];
	Memo.Player = Player;
	Memo.Location = Location;
	Memo.Time = World->GetTimeSeconds();
	NextPlayerHit = (NextPlayerHit + 1) % static_cast<int32>(UE_ARRAY_COUNT(PlayerHits));
}

FLinearColor UAirsoftEffectsSubsystem::DustColor(EAirsoftSurface Surface) const
{
	switch (Surface)
	{
	case EAirsoftSurface::Wood: return FLinearColor(0.45f, 0.34f, 0.22f);
	case EAirsoftSurface::Stone: return FLinearColor(0.42f, 0.41f, 0.39f);
	case EAirsoftSurface::Dirt: return FLinearColor(0.3f, 0.24f, 0.17f);
	case EAirsoftSurface::Foliage: return FLinearColor(0.3f, 0.28f, 0.18f);
	case EAirsoftSurface::Soft: return FLinearColor(0.4f, 0.38f, 0.36f);
	case EAirsoftSurface::Metal:
	case EAirsoftSurface::Steel: return FLinearColor(0.32f, 0.32f, 0.32f);
	case EAirsoftSurface::Water: return FLinearColor(0.7f, 0.75f, 0.8f);
	default: return FLinearColor(0.38f, 0.37f, 0.35f);
	}
}

// ---------------------------------------------------------------------------
// Effects
// ---------------------------------------------------------------------------

EAirsoftSurface UAirsoftEffectsSubsystem::SurfaceOf(const FHitResult& Hit)
{
	const UPrimitiveComponent* Comp = Hit.GetComponent();
	if (!Comp)
	{
		return AirsoftEffects::ClassifySurface(Hit);
	}
	const FObjectKey Key(Comp);
	if (const EAirsoftSurface* Found = SurfaceCache.Find(Key))
	{
		return *Found;
	}
	const EAirsoftSurface Surface = AirsoftEffects::ClassifySurface(Hit);
	if (SurfaceCache.Num() < 8192)
	{
		SurfaceCache.Add(Key, Surface);
	}
	return Surface;
}

void UAirsoftEffectsSubsystem::MuzzlePuff(const FVector& Muzzle, const FVector& Direction, const FAirsoftWeaponDef& Weapon, bool bQuiet, bool bFirstPerson, float AimAlpha)
{
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	if (S->MuzzlePuffScale <= 0.f || !ShouldSpawnAt(Muzzle, S->MuzzleCullDistance))
	{
		return;
	}
	const bool bGas = Weapon.Kind == TEXT("Gas");
	const bool bSpring = Weapon.Kind == TEXT("Spring");
	const bool bShotgun = Weapon.Class == TEXT("Shotgun");
	const bool bMagnum = bShotgun || Weapon.Id == FName(TEXT("DEAGLE"));
	// Airsoft guns have no flash. Authentic mode keeps only the real thing: a gas gun's breath of propellant.
	if (!bCinematic && !bGas)
	{
		return;
	}
	float Opacity = bGas ? 0.2f : (bSpring ? 0.05f : 0.08f);
	if (!bCinematic)
	{
		Opacity *= 0.6f;
	}
	if (bQuiet)
	{
		Opacity *= 0.25f; // suppressors and integrally quiet guns trap almost all of it
	}
	if (bFirstPerson)
	{
		Opacity *= FMath::Lerp(0.75f, 0.3f, FMath::Clamp(AimAlpha, 0.f, 1.f)); // keep the sight picture clean
	}
	Opacity *= S->MuzzlePuffScale;
	if (Opacity < 0.01f)
	{
		return;
	}
	const FVector Dir = Direction.IsNearlyZero() ? FVector::ForwardVector : Direction.GetSafeNormal();
	const float Scale = bShotgun ? 1.8f : (bMagnum ? 1.4f : (bGas ? 1.15f : 1.f));

	FAirsoftFXParticle P;
	P.Layer = EAirsoftFXLayer::Smoke;
	P.Location = Muzzle + Dir * 1.5;
	P.Velocity = Dir * (bGas ? 300.0 : 180.0);
	P.Drag = 8.f;
	P.Axis = Dir;
	P.Size0 = FVector(3.f, 2.f, 2.f) * Scale;
	P.Size1 = FVector(13.f, 9.f, 9.f) * Scale;
	P.Color = bGas ? FLinearColor(0.8f, 0.84f, 0.9f) : FLinearColor(0.6f, 0.58f, 0.55f);
	P.Alpha = Opacity;
	P.Emissive = 0.03f;
	P.Life = bGas ? 0.3f : 0.18f;
	P.FadeIn = 0.06f;
	P.FadePow = 1.6f;
	Spawn(P, bFirstPerson);

	if (bGas && !bQuiet)
	{
		// The lazy curl of vapour that hangs after a gas shot.
		P.Location = Muzzle + Dir * 4.0;
		P.Velocity = Dir * 60.0 + FVector(0.0, 0.0, 18.0);
		P.Drag = 3.f;
		P.Size0 = FVector(5.f) * Scale;
		P.Size1 = FVector(20.f) * Scale;
		P.Alpha = Opacity * 0.45f;
		P.Life = 0.7f;
		P.FadeIn = 0.2f;
		P.FadePow = 1.3f;
		Spawn(P, bFirstPerson);
		if (bCinematic)
		{
			Light(Muzzle + Dir * 6.0, FLinearColor(0.85f, 0.9f, 1.f), S->GasMuzzleLightCandela * (bMagnum ? 1.6f : 1.f), 250.f, 0.045f);
		}
	}
}

void UAirsoftEffectsSubsystem::BBImpact(const FHitResult& Hit, const FVector& Velocity, EAirsoftSurface Surface)
{
	const FVector Loc = Hit.ImpactPoint;
	if (Surface == EAirsoftSurface::Player)
	{
		RememberPlayerHit(Hit.GetActor(), Loc);
		if (IsViewerPawn(Hit.GetActor()))
		{
			return; // your own body is not drawn; the tagged pulse is your feedback
		}
	}
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	if (!ShouldSpawnAt(Loc, S->ImpactCullDistance))
	{
		return;
	}
	const double Speed = Velocity.Size();
	const FVector In = Speed > 1.0 ? Velocity / Speed : FVector::ForwardVector;
	FVector N = Hit.ImpactNormal;
	if (!N.Normalize())
	{
		N = -In;
	}
	const FVector Bounce = In.MirrorByVector(N);
	const FVector Out = (Bounce + N).GetSafeNormal(); // chips fly between the bounce and the normal
	const float Energy = FMath::Clamp(static_cast<float>(Speed) / 11000.f, 0.3f, 1.2f);
	const bool bNear = ViewDistance(Loc) < S->DebrisCullDistance;
	const float K = S->ImpactScale;
	const FVector P0 = Loc + N * 1.0;
	const FVector UpOut = (N + FVector::UpVector * 0.6).GetSafeNormal();

	switch (Surface)
	{
	case EAirsoftSurface::Steel:
		// Practice plate: bright pings and a short "ting" flash.
		Sparks(P0, Bounce, Count(4.f), FLinearColor(1.f, 0.86f, 0.62f), 500.f, 1100.f * Energy, 50.f, 22.f, 0.13f, 900.f);
		Flash(P0, FLinearColor(1.f, 0.95f, 0.85f), 2.f, 9.f, 18.f, 0.06f);
		if (bCinematic)
		{
			Light(P0 + N * 6.0, FLinearColor(1.f, 0.9f, 0.75f), 1.2f, 160.f, 0.06f);
		}
		Puff(P0, N, DustColor(Surface), 1.5f, 7.f, 0.1f * K, 0.25f, 60.f);
		break;
	case EAirsoftSurface::Metal:
		Sparks(P0, Bounce, Count(2.f), FLinearColor(1.f, 0.9f, 0.75f), 400.f, 900.f * Energy, 45.f, 12.f, 0.08f, 900.f);
		if (bCinematic)
		{
			Flash(P0, FLinearColor(1.f, 0.95f, 0.9f), 1.5f, 5.f, 8.f, 0.04f);
		}
		Puff(P0, N, DustColor(Surface), 1.5f, 8.f, 0.14f * K, 0.3f, 60.f);
		break;
	case EAirsoftSurface::Wood:
		// Splinter dust and a couple of chips.
		Puff(P0, N, DustColor(Surface), 2.5f, 15.f * Energy, 0.32f * K, 0.45f, 110.f, 10.f);
		if (bNear)
		{
			Debris(P0, Out, Count(3.f), FLinearColor(0.36f, 0.25f, 0.14f), 0.4f, 1.1f, 200.f, 450.f * Energy, 55.f, 0.6f);
		}
		break;
	case EAirsoftSurface::Stone:
		Puff(P0, N, DustColor(Surface), 2.5f, 16.f * Energy, 0.34f * K, 0.5f, 120.f, 12.f);
		if (bNear)
		{
			Debris(P0, Out, Count(2.f), FLinearColor(0.28f, 0.28f, 0.27f), 0.3f, 0.7f, 250.f, 500.f * Energy, 50.f, 0.5f);
		}
		break;
	case EAirsoftSurface::Dirt:
		// Dust kick that rises and hangs.
		Puff(P0, UpOut, DustColor(Surface), 3.f, 22.f * Energy, 0.4f * K, 0.65f, 140.f, 25.f);
		if (bNear)
		{
			Debris(P0, UpOut, Count(3.f), FLinearColor(0.17f, 0.12f, 0.08f), 0.4f, 1.f, 150.f, 380.f, 35.f, 0.55f);
		}
		break;
	case EAirsoftSurface::Foliage:
		Puff(P0, N, DustColor(Surface), 2.f, 12.f, 0.18f * K, 0.45f, 80.f, 10.f);
		if (bNear)
		{
			Debris(P0, Out, Count(2.f), FLinearColor(0.1f, 0.17f, 0.05f), 0.4f, 1.f, 100.f, 250.f, 60.f, 0.5f);
		}
		break;
	case EAirsoftSurface::Soft:
		// Fabric, velvet, sandbags: the BB just stops.
		Puff(P0, N, DustColor(Surface), 1.5f, 7.f, 0.08f * K, 0.3f, 40.f);
		break;
	case EAirsoftSurface::Glass:
		Flash(P0, FLinearColor(0.9f, 0.95f, 1.f), 1.f, 4.f, 10.f, 0.05f);
		Sparks(P0, Bounce, Count(2.f), FLinearColor(0.85f, 0.9f, 1.f), 300.f, 600.f, 40.f, 6.f, 0.08f, 980.f);
		break;
	case EAirsoftSurface::Water:
		// Two ripples and a little splash.
		Ring(Loc + N * 0.5, N, DustColor(Surface), 2.f, 24.f, 0.35f * K, 0.55f);
		Ring(Loc + N * 0.5, N, DustColor(Surface), 1.f, 14.f, 0.25f * K, 0.45f, 0.12f);
		Puff(P0, N, FLinearColor(0.8f, 0.85f, 0.9f), 1.5f, 8.f, 0.18f * K, 0.25f, 120.f);
		if (bNear)
		{
			Debris(P0, N, Count(3.f), FLinearColor(0.55f, 0.6f, 0.65f), 0.3f, 0.5f, 150.f, 300.f, 25.f, 0.35f);
		}
		break;
	case EAirsoftSurface::Rubber:
		Puff(P0, N, FLinearColor(0.12f, 0.12f, 0.12f), 1.5f, 6.f, 0.08f * K, 0.25f, 40.f);
		break;
	case EAirsoftSurface::Player:
		// A BB smacking into kit: small hot-white/orange flash and a puff of dust off the clothes.
		Flash(P0, FLinearColor(1.f, 0.7f, 0.4f), 1.5f, 8.f, 9.f, 0.07f);
		Puff(P0, N, FLinearColor(0.78f, 0.76f, 0.72f), 1.5f, 9.f, 0.18f * K, 0.3f, 60.f);
		break;
	default:
		Puff(P0, N, DustColor(Surface), 2.f, 10.f, 0.22f * K, 0.4f, 90.f, 8.f);
		if (bNear)
		{
			Debris(P0, Out, Count(1.f), FLinearColor(0.3f, 0.3f, 0.3f), 0.3f, 0.6f, 200.f, 400.f, 50.f, 0.45f);
		}
		break;
	}
}

void UAirsoftEffectsSubsystem::TagPop(const AActor* Victim)
{
	const UWorld* World = GetWorld();
	if (!Victim || !World)
	{
		return;
	}
	// Where the last BB struck them, if this machine saw it; else the chest.
	FVector Loc = Victim->GetActorLocation() + FVector(0.0, 0.0, 30.0);
	const double Now = World->GetTimeSeconds();
	double Best = -1.0;
	for (const FPlayerHitMemo& Memo : PlayerHits)
	{
		if (Memo.Player.Get() == Victim && Now - Memo.Time < 1.0 && Memo.Time > Best)
		{
			Best = Memo.Time;
			Loc = Memo.Location;
		}
	}
	TagPopAt(Loc);
}

void UAirsoftEffectsSubsystem::TagPopAt(const FVector& Loc)
{
	if (!ShouldSpawnAt(Loc, UAirsoftEffectsSettings::Get()->ImpactCullDistance))
	{
		return;
	}
	Flash(Loc, FLinearColor(1.f, 0.45f, 0.1f), 4.f, 22.f, bCinematic ? 10.f : 6.f, 0.16f, true);
	Puff(Loc, FVector::UpVector, FLinearColor(0.82f, 0.8f, 0.76f), 4.f, 26.f, 0.22f, 0.55f, 20.f, 30.f, true);
	if (bCinematic)
	{
		Light(Loc + FVector(0.0, 0.0, 10.0), FLinearColor(1.f, 0.55f, 0.2f), 2.5f, 300.f, 0.15f);
	}
}

void UAirsoftEffectsSubsystem::HitConfirmPop(const FVector& Location)
{
	const FVector Facing = bHasView ? (ViewLocation - Location).GetSafeNormal() : FVector::UpVector;
	const FVector Loc = Location + Facing * 5.0;
	Flash(Loc, FLinearColor(1.f, 0.97f, 0.92f), 1.5f, 7.f, 7.f, 0.08f, true);
	if (bCinematic)
	{
		Sparks(Loc, Facing, 3, FLinearColor(1.f, 0.95f, 0.85f), 150.f, 300.f, 75.f, 6.f, 0.1f, 0.f, true);
	}
}

void UAirsoftEffectsSubsystem::GrenadeBurst(const FVector& Location, float Radius)
{
	const UAirsoftEffectsSettings* S = UAirsoftEffectsSettings::Get();
	ShakeNear(Location, S->GrenadeShakeRadius, 1.f);
	UWorld* World = GetWorld();
	if (!World || !ShouldSpawnAt(Location, S->ImpactCullDistance * 1.5f))
	{
		return;
	}
	const FVector Up = FVector::UpVector;
	FHitResult Ground;
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftFXGrenadeGround), false);
	const bool bGround = World->LineTraceSingleByChannel(Ground, Location + Up * 5.0, Location - Up * 120.0, ECC_Visibility, Query);
	const EAirsoftSurface GroundSurface = bGround ? SurfaceOf(Ground) : EAirsoftSurface::Default;

	// The gas charge letting go: a hard flash, a fast expanding puff, then a slow haze that drifts up.
	Flash(Location, FLinearColor(1.f, 0.9f, 0.75f), 15.f, bCinematic ? 110.f : 60.f, bCinematic ? 12.f : 6.f, 0.09f, true);
	Puff(Location, Up, FLinearColor(0.78f, 0.78f, 0.76f), 25.f, Radius * 0.5f, 0.34f, 0.5f, 0.f, 40.f, true);
	Puff(Location + Up * 20.0, Up, FLinearColor(0.62f, 0.62f, 0.6f), 60.f, Radius * 0.8f, 0.14f, 1.9f, 0.f, 35.f, true);

	// Dust (or a splash ring) racing out along the ground.
	if (bGround)
	{
		const FVector GroundN = Ground.ImpactNormal.GetSafeNormal();
		const FVector GroundP = Ground.ImpactPoint + GroundN * 3.0;
		const bool bDusty = GroundSurface == EAirsoftSurface::Dirt || GroundSurface == EAirsoftSurface::Foliage || GroundSurface == EAirsoftSurface::Stone || GroundSurface == EAirsoftSurface::Wood || GroundSurface == EAirsoftSurface::Default;
		if (GroundSurface == EAirsoftSurface::Water || bDusty)
		{
			Ring(GroundP, GroundN, DustColor(GroundSurface), 30.f, Radius * 0.9f, GroundSurface == EAirsoftSurface::Water ? 0.4f : 0.3f, 0.6f, 0.f, true);
		}
		if (bDusty)
		{
			const int32 Kicks = Count(5.f);
			for (int32 i = 0; i < Kicks; ++i)
			{
				const FVector Side = FVector::VectorPlaneProject(FMath::VRand(), GroundN).GetSafeNormal();
				Puff(GroundP + Side * static_cast<double>(Radius * 0.25f), (Side + GroundN * 0.5).GetSafeNormal(), DustColor(GroundSurface), 15.f, Radius * 0.3f, 0.22f, 0.9f, 220.f, 20.f, true);
			}
		}
	}

	// BB spray streaks (the BBs themselves fly in UAirsoftBBSubsystem::Burst).
	Sparks(Location, Up, Count(10.f), FLinearColor(1.f, 0.92f, 0.8f), 1800.f, 3200.f, 80.f, 7.f, 0.1f, 0.f, true);
}

void UAirsoftEffectsSubsystem::FootDust(const AActor* Walker, const FVector& FootLocation, float Strength)
{
	UWorld* World = GetWorld();
	if (!World || Strength <= 0.f || !ShouldSpawnAt(FootLocation, UAirsoftEffectsSettings::Get()->FootDustCullDistance))
	{
		return;
	}
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftFXFoot), false, Walker);
	FHitResult Hit;
	if (!World->LineTraceSingleByChannel(Hit, FootLocation + FVector(0.0, 0.0, 10.0), FootLocation - FVector(0.0, 0.0, 40.0), ECC_Visibility, Query))
	{
		return;
	}
	const EAirsoftSurface Surface = SurfaceOf(Hit);
	float Opacity = 0.f;
	switch (Surface)
	{
	case EAirsoftSurface::Dirt: Opacity = 0.16f; break;
	case EAirsoftSurface::Foliage: Opacity = 0.05f; break;
	case EAirsoftSurface::Stone: Opacity = 0.035f; break;
	default: return;
	}
	Puff(Hit.ImpactPoint + FVector(0.0, 0.0, 4.0), FVector::UpVector, DustColor(Surface), 6.f, 30.f, Opacity * Strength, 0.8f, 0.f, 25.f);
}

void UAirsoftEffectsSubsystem::LandingDust(const FHitResult& FloorHit, float Strength)
{
	if (Strength <= 0.f || !FloorHit.bBlockingHit)
	{
		return;
	}
	const FVector Loc = FloorHit.ImpactPoint;
	if (!ShouldSpawnAt(Loc, UAirsoftEffectsSettings::Get()->FootDustCullDistance))
	{
		return;
	}
	const EAirsoftSurface Surface = SurfaceOf(FloorHit);
	const FVector N = FloorHit.ImpactNormal.IsNearlyZero() ? FVector::UpVector : FloorHit.ImpactNormal.GetSafeNormal();
	float Opacity = 0.f;
	switch (Surface)
	{
	case EAirsoftSurface::Dirt: Opacity = 0.25f; break;
	case EAirsoftSurface::Foliage: Opacity = 0.1f; break;
	case EAirsoftSurface::Stone: Opacity = 0.08f; break;
	case EAirsoftSurface::Wood: Opacity = 0.06f; break;
	case EAirsoftSurface::Water:
		Ring(Loc + N * 0.5, N, DustColor(Surface), 10.f, 60.f, 0.35f * Strength, 0.6f);
		return;
	default: return;
	}
	Ring(Loc + N * 2.0, N, DustColor(Surface), 15.f, 40.f + 50.f * Strength, Opacity * Strength * 1.2f, 0.5f);
	Puff(Loc + N * 5.0, N, DustColor(Surface), 10.f, 45.f, Opacity * Strength, 0.9f, 60.f, 20.f);
}

void UAirsoftEffectsSubsystem::ShakeNear(const FVector& Origin, float Radius, float Strength)
{
	const UWorld* World = GetWorld();
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	AAirsoftCharacter* Viewer = PC ? Cast<AAirsoftCharacter>(PC->GetPawn()) : nullptr;
	if (!Viewer || !Viewer->IsLocalHuman() || Radius <= 0.f)
	{
		return;
	}
	const float Dist = static_cast<float>(FVector::Dist(Viewer->GetActorLocation(), Origin));
	if (Dist >= Radius)
	{
		return;
	}
	const float Falloff = 1.f - Dist / Radius;
	Viewer->AddViewShake(Strength * Falloff * Falloff, 1.5f * Falloff);
}
