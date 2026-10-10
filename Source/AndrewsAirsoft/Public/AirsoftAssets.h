// Andrew's Airsoft - runtime asset lookup helpers. Imported content lives under /Game/Airsoft.

#pragma once

#include "CoreMinimal.h"

class UStaticMesh;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class USoundBase;
class UObject;
class FJsonObject;

namespace AirsoftAssets
{
	ANDREWSAIRSOFT_API UStaticMesh* Cube();
	ANDREWSAIRSOFT_API UStaticMesh* Cylinder();
	ANDREWSAIRSOFT_API UStaticMesh* Sphere();
	ANDREWSAIRSOFT_API UStaticMesh* Plane();

	/** /Game/Airsoft/Meshes/<Category>/<AssetId>/SM_<AssetId>_<Piece> or nullptr. */
	ANDREWSAIRSOFT_API UStaticMesh* FindMesh(const FString& Category, FName AssetId, const FString& Piece);

	/** Unlit emissive material (Color + Intensity parameters). */
	ANDREWSAIRSOFT_API UMaterialInterface* EmissiveMaterial();
	ANDREWSAIRSOFT_API UMaterialInstanceDynamic* MakeEmissive(UObject* Outer, const FLinearColor& Color, float Intensity = 8.f);

	/** /Game/Airsoft/Audio/<Key> (imported from Tools/Audio). */
	ANDREWSAIRSOFT_API USoundBase* Sound(FName Key);

	/** Plays a 2D UI/first-person sound. */
	ANDREWSAIRSOFT_API void Play2D(const UObject* WorldContext, FName Key, float Volume = 1.f, float Pitch = 1.f);

	/** Plays a positional sound with airsoft-scale attenuation. */
	ANDREWSAIRSOFT_API void Play3D(const UObject* WorldContext, FName Key, const FVector& Location, float Volume = 1.f, float Pitch = 1.f);

	/** Loads a JSON file under Content/Airsoft/Data. */
	ANDREWSAIRSOFT_API TSharedPtr<FJsonObject> LoadData(const FString& FileName);
}
