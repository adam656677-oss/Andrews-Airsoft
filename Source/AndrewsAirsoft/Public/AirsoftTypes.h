// Andrew's Airsoft - shared enums and structs.

#pragma once

#include "CoreMinimal.h"
#include "AirsoftTypes.generated.h"

/** Trace channel used by BBs (DefaultEngine.ini: GameTraceChannel1 = "BB"). */
#define ECC_BB ECC_GameTraceChannel1

UENUM(BlueprintType)
enum class EAirsoftTeam : uint8
{
	None,
	Blue,
	Red
};

UENUM(BlueprintType)
enum class EAirsoftPhase : uint8
{
	Waiting,
	Intermission,
	Briefing,
	Live,
	PostRound
};

UENUM(BlueprintType)
enum class EAirsoftMode : uint8
{
	TDM,
	Domination
};

UENUM(BlueprintType)
enum class EAirsoftFireMode : uint8
{
	Auto,
	Semi,
	Burst,
	Bolt,
	Pump
};

UENUM(BlueprintType)
enum class EAirsoftSlot : uint8
{
	Primary,
	Secondary,
	Grenade
};

/** Attachments and finish chosen for one weapon. */
USTRUCT(BlueprintType)
struct FAirsoftCustomization
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName WeaponId;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Optic = NAME_None;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Muzzle = NAME_None;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Grip = NAME_None;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Laser = NAME_None;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Mag = NAME_None;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FName Skin = TEXT("Black");

	bool operator==(const FAirsoftCustomization& Other) const
	{
		return WeaponId == Other.WeaponId && Optic == Other.Optic && Muzzle == Other.Muzzle && Grip == Other.Grip
			&& Laser == Other.Laser && Mag == Other.Mag && Skin == Other.Skin;
	}
};

/** What a player carries into the field. */
USTRUCT(BlueprintType)
struct FAirsoftLoadout
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite) FAirsoftCustomization Primary;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FAirsoftCustomization Secondary;
};

/** Per-round stats shown on the scoreboard and after-action report. */
USTRUCT(BlueprintType)
struct FAirsoftRoundStats
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly) int32 Tags = 0;
	UPROPERTY(BlueprintReadOnly) int32 Outs = 0;
	UPROPERTY(BlueprintReadOnly) int32 Captures = 0;
	UPROPERTY(BlueprintReadOnly) int32 XP = 0;
	UPROPERTY(BlueprintReadOnly) int32 Streak = 0;
};

/** The last tag of a round, replayed in slow motion. */
USTRUCT(BlueprintType)
struct FAirsoftFinalTag
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly) bool bValid = false;
	UPROPERTY(BlueprintReadOnly) FString Shooter;
	UPROPERTY(BlueprintReadOnly) FString Victim;
	UPROPERTY(BlueprintReadOnly) EAirsoftTeam ShooterTeam = EAirsoftTeam::None;
	UPROPERTY(BlueprintReadOnly) EAirsoftTeam VictimTeam = EAirsoftTeam::None;
	UPROPERTY(BlueprintReadOnly) FVector From = FVector::ZeroVector;
	UPROPERTY(BlueprintReadOnly) FVector To = FVector::ZeroVector;
	UPROPERTY(BlueprintReadOnly) FName WeaponId;
};

/** One row of the after-action report. */
USTRUCT(BlueprintType)
struct FAirsoftSummaryRow
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly) FString Name;
	UPROPERTY(BlueprintReadOnly) EAirsoftTeam Team = EAirsoftTeam::None;
	UPROPERTY(BlueprintReadOnly) FAirsoftRoundStats Stats;
};

namespace AirsoftColors
{
	inline FLinearColor Team(EAirsoftTeam Team)
	{
		switch (Team)
		{
		case EAirsoftTeam::Blue: return FLinearColor(0.08f, 0.30f, 1.0f);
		case EAirsoftTeam::Red: return FLinearColor(1.0f, 0.09f, 0.07f);
		default: return FLinearColor(1.0f, 0.55f, 0.05f);
		}
	}

	inline FLinearColor Accent() { return FLinearColor(1.0f, 0.55f, 0.05f); }

	inline FString TeamName(EAirsoftTeam Team)
	{
		switch (Team)
		{
		case EAirsoftTeam::Blue: return TEXT("Blue Squad");
		case EAirsoftTeam::Red: return TEXT("Red Squad");
		default: return TEXT("Unassigned");
		}
	}
}
