#include "AirsoftAssets.h"

#include "AirsoftSettings.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

namespace AirsoftAssets
{
	namespace
	{
		template <typename T>
		T* LoadCached(const TCHAR* Path)
		{
			// Weak cache: avoids static strong references outliving the UObject system at exit.
			static TMap<FString, TWeakObjectPtr<UObject>> Cache;
			static TSet<FString> Missing;
			if (TWeakObjectPtr<UObject>* Found = Cache.Find(Path))
			{
				if (Found->IsValid())
				{
					return Cast<T>(Found->Get());
				}
			}
			if (Missing.Contains(Path))
			{
				return nullptr;
			}
			T* Loaded = LoadObject<T>(nullptr, Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
			if (Loaded)
			{
				Cache.Add(Path, Loaded);
			}
			else
			{
				Missing.Add(Path);
			}
			return Loaded;
		}

		USoundAttenuation* Attenuation()
		{
			static TWeakObjectPtr<USoundAttenuation> Att;
			if (!Att.IsValid())
			{
				USoundAttenuation* A = NewObject<USoundAttenuation>(GetTransientPackage());
				A->Attenuation.bAttenuate = true;
				A->Attenuation.bSpatialize = true;
				A->Attenuation.AttenuationShape = EAttenuationShape::Sphere;
				A->Attenuation.AttenuationShapeExtents = FVector(400.f, 0.f, 0.f);
				A->Attenuation.FalloffDistance = 9000.f;
				A->Attenuation.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
				A->Attenuation.bAttenuateWithLPF = true;
				A->Attenuation.LPFRadiusMin = 1500.f;
				A->Attenuation.LPFRadiusMax = 8000.f;
				A->AddToRoot(); // lives for the whole session
				Att = A;
			}
			return Att.Get();
		}
	}

	UStaticMesh* Cube() { return LoadCached<UStaticMesh>(TEXT("/Engine/BasicShapes/Cube.Cube")); }
	UStaticMesh* Cylinder() { return LoadCached<UStaticMesh>(TEXT("/Engine/BasicShapes/Cylinder.Cylinder")); }
	UStaticMesh* Sphere() { return LoadCached<UStaticMesh>(TEXT("/Engine/BasicShapes/Sphere.Sphere")); }
	UStaticMesh* Plane() { return LoadCached<UStaticMesh>(TEXT("/Engine/BasicShapes/Plane.Plane")); }

	UStaticMesh* FindMesh(const FString& Category, FName AssetId, const FString& Piece)
	{
		const FString Id = AssetId.ToString();
		const FString Path = FString::Printf(TEXT("/Game/Airsoft/Meshes/%s/%s/SM_%s_%s.SM_%s_%s"), *Category, *Id, *Id, *Piece, *Id, *Piece);
		return LoadCached<UStaticMesh>(*Path);
	}

	UMaterialInterface* EmissiveMaterial()
	{
		static TWeakObjectPtr<UMaterialInterface> Mat;
		if (!Mat.IsValid())
		{
			UMaterialInterface* Found = UAirsoftSettings::Get()->BBMaterial.LoadSynchronous();
			if (!Found)
			{
				Found = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/EngineMaterials/EmissiveMeshMaterial.EmissiveMeshMaterial"), nullptr, LOAD_NoWarn | LOAD_Quiet);
			}
			if (!Found)
			{
				Found = UMaterial::GetDefaultMaterial(MD_Surface);
			}
			Mat = Found;
		}
		return Mat.Get();
	}

	UMaterialInstanceDynamic* MakeEmissive(UObject* Outer, const FLinearColor& Color, float Intensity)
	{
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(EmissiveMaterial(), Outer);
		if (MID)
		{
			MID->SetVectorParameterValue(TEXT("Color"), Color);
			MID->SetScalarParameterValue(TEXT("Intensity"), Intensity);
		}
		return MID;
	}

	USoundBase* Sound(FName Key)
	{
		const FString Name = Key.ToString();
		const FString Path = FString::Printf(TEXT("/Game/Airsoft/Audio/%s.%s"), *Name, *Name);
		return LoadCached<USoundBase>(*Path);
	}

	void Play2D(const UObject* WorldContext, FName Key, float Volume, float Pitch)
	{
		if (USoundBase* S = Sound(Key))
		{
			UGameplayStatics::PlaySound2D(WorldContext, S, Volume, Pitch);
		}
	}

	void Play3D(const UObject* WorldContext, FName Key, const FVector& Location, float Volume, float Pitch)
	{
		if (USoundBase* S = Sound(Key))
		{
			UGameplayStatics::PlaySoundAtLocation(WorldContext, S, Location, Volume, Pitch, 0.f, Attenuation());
		}
	}

	TSharedPtr<FJsonObject> LoadData(const FString& FileName)
	{
		static TMap<FString, TSharedPtr<FJsonObject>> Cache;
		if (TSharedPtr<FJsonObject>* Found = Cache.Find(FileName))
		{
			return *Found;
		}
		FString Text;
		TSharedPtr<FJsonObject> Root;
		const FString Path = FPaths::ProjectContentDir() / TEXT("Airsoft/Data") / FileName;
		if (FFileHelper::LoadFileToString(Text, *Path))
		{
			TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
			FJsonSerializer::Deserialize(Reader, Root);
		}
		Cache.Add(FileName, Root);
		return Root;
	}
}
