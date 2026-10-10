// Andrew's Airsoft - project settings (Project Settings > Game > Airsoft).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "AirsoftSettings.generated.h"

class UAnimInstance;
class USkeletalMesh;
class UMaterialInterface;

UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Airsoft"))
class ANDREWSAIRSOFT_API UAirsoftSettings : public UDeveloperSettings
{
	GENERATED_BODY()

public:
	/** Body mesh for other players (UE mannequin from the Third Person feature pack). */
	UPROPERTY(Config, EditAnywhere, Category = "Characters")
	TSoftObjectPtr<USkeletalMesh> ThirdPersonMesh;

	UPROPERTY(Config, EditAnywhere, Category = "Characters")
	TSoftClassPtr<UAnimInstance> ThirdPersonAnimClass;

	/** Bone or socket that holds the third-person gun. Empty = the gun follows the player's aim at chest height (works with any animation set). */
	UPROPERTY(Config, EditAnywhere, Category = "Characters")
	FName ThirdPersonGunSocket;

	/** Offset from ThirdPersonGunSocket to the gun's grip. */
	UPROPERTY(Config, EditAnywhere, Category = "Characters")
	FTransform ThirdPersonGunOffset;

	/** Optional first-person arms. If empty the gun floats in view with gloved hands built from the gun data. */
	UPROPERTY(Config, EditAnywhere, Category = "Characters")
	TSoftObjectPtr<USkeletalMesh> FirstPersonArmsMesh;

	/** Unlit emissive material with a "Color" vector parameter, used for BB tracers and glows. */
	UPROPERTY(Config, EditAnywhere, Category = "Materials")
	TSoftObjectPtr<UMaterialInterface> BBMaterial;

	/** Master PBR material for guns: BaseColor/Normal/ORM/Mask textures + PrimaryTint/SecondaryTint/AccentTint. */
	UPROPERTY(Config, EditAnywhere, Category = "Materials")
	TSoftObjectPtr<UMaterialInterface> GunMaterial;

	UPROPERTY(Config, EditAnywhere, Category = "Maps")
	FString StagingMap = TEXT("/Game/Maps/L_Staging");

	UPROPERTY(Config, EditAnywhere, Category = "Maps")
	FString MainMenuMap = TEXT("/Game/Maps/L_MainMenu");

	UPROPERTY(Config, EditAnywhere, Category = "Maps")
	TMap<FName, FString> MatchMaps = { { TEXT("Field"), TEXT("/Game/Maps/L_IronwoodYard") }, { TEXT("Club"), TEXT("/Game/Maps/L_VelvetClub") } };

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	int32 MinPlayers = 2;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	float IntermissionTime = 25.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	float BriefingTime = 6.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	float RoundTime = 420.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	float PostRoundTime = 16.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	float RespawnTime = 5.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	float SpawnProtection = 3.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	int32 TDMScoreLimit = 40;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	int32 DominationScoreLimit = 250;

	UPROPERTY(Config, EditAnywhere, Category = "Rules")
	bool bFriendlyFire = false;

	static const UAirsoftSettings* Get() { return GetDefault<UAirsoftSettings>(); }
};
