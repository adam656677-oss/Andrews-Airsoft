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
	/** Computer-controlled player (shown with a BOT tag, never matched to a human profile). */
	UPROPERTY(BlueprintReadOnly) bool bBot = false;
};

UENUM(BlueprintType)
enum class EAirsoftBotSkill : uint8
{
	Easy,
	Normal,
	Hard,
	Expert
};

/**
 * How a bot plays at one difficulty (Project Settings > Game > Airsoft > Bots).
 * Angles in degrees, times in seconds, distances in centimetres.
 */
USTRUCT(BlueprintType)
struct FAirsoftBotTuning
{
	GENERATED_BODY()

	/** Seconds from first seeing an enemy to the first shot... */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float ReactionTime = 0.5f;
	/** ...plus this much for every 10 m of distance. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float ReactionPer10m = 0.07f;
	/** Furthest an enemy can be spotted. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float SightRange = 5000.f;
	/** Half-angle of the view cone (enemies very close are sensed outside it). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float ViewHalfAngle = 65.f;
	/** Seconds between line-of-sight checks. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float SightInterval = 0.22f;
	/** Aim error when a target is first acquired... */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float AimErrorStart = 6.f;
	/** ...the floor it settles to on a still target... */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float AimErrorMin = 0.9f;
	/** ...and how fast it settles (1/s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float AimSettleRate = 1.6f;
	/** Extra error per 1 m/s of the target's sideways speed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float TargetMoveError = 0.4f;
	/** Extra error while the bot itself moves at walking speed. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float SelfMoveError = 1.6f;
	/** 0..1: how much of the BB's flight time a bot leads moving targets by, and of its drop it holds over. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float LeadSkill = 0.55f;
	/** Fastest turn (deg/s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float TurnRate = 320.f;
	/** Fires once the aim is within this many target half-widths of where the bot wants it (bigger = trigger-happy). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float TriggerDiscipline = 1.9f;
	/** Shortest gap between semi-auto taps (on top of the gun's own limit). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float TapInterval = 0.32f;
	/** Rounds per full-auto burst (longer up close) and the pause between bursts. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 BurstMin = 3;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 BurstMax = 6;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float BurstPause = 0.4f;
	/** Chances, each time a bot re-picks its fighting stance, to crouch or to strafe. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float CrouchChance = 0.25f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float StrafeChance = 0.4f;
	/** Seconds an unseen enemy's last known position is remembered (and investigated). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float MemoryTime = 6.f;
	/** Chance to throw the grenade when enemies are bunched up. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float GrenadeChance = 0.25f;
	/** Multiplies the hearing ranges in the settings. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float HearingScale = 1.f;

	/** Built-in defaults for a difficulty (AirsoftSettings.cpp). */
	static FAirsoftBotTuning Preset(EAirsoftBotSkill Skill);
};

/** Host bot options as stored in FAirsoftUserSettings (BotFill / BotSkill). */
namespace AirsoftBots
{
	constexpr int32 NumFillOptions = 5;
	constexpr int32 NumSkillOptions = 4;

	/** Players per team the bots fill up to: Off, 4v4, 6v6, 8v8, 10v10. */
	inline int32 TeamSize(int32 FillIndex)
	{
		switch (FMath::Clamp(FillIndex, 0, NumFillOptions - 1))
		{
		case 1: return 4;
		case 2: return 6;
		case 3: return 8;
		case 4: return 10;
		default: return 0;
		}
	}

	inline FString FillLabel(int32 FillIndex)
	{
		const int32 Size = TeamSize(FillIndex);
		return Size > 0 ? FString::Printf(TEXT("%dV%d"), Size, Size) : FString(TEXT("OFF"));
	}

	inline EAirsoftBotSkill SkillFromIndex(int32 SkillIndex)
	{
		return static_cast<EAirsoftBotSkill>(FMath::Clamp(SkillIndex, 0, NumSkillOptions - 1));
	}

	inline FString SkillLabel(int32 SkillIndex)
	{
		switch (SkillFromIndex(SkillIndex))
		{
		case EAirsoftBotSkill::Easy: return TEXT("EASY");
		case EAirsoftBotSkill::Hard: return TEXT("HARD");
		case EAirsoftBotSkill::Expert: return TEXT("EXPERT");
		default: return TEXT("NORMAL");
		}
	}
}

namespace AirsoftColors
{
	inline FLinearColor Team(EAirsoftTeam InTeam)
	{
		switch (InTeam)
		{
		case EAirsoftTeam::Blue: return FLinearColor(0.08f, 0.30f, 1.0f);
		case EAirsoftTeam::Red: return FLinearColor(1.0f, 0.09f, 0.07f);
		default: return FLinearColor(1.0f, 0.55f, 0.05f);
		}
	}

	inline FLinearColor Accent() { return FLinearColor(1.0f, 0.55f, 0.05f); }

	inline FString TeamName(EAirsoftTeam InTeam)
	{
		switch (InTeam)
		{
		case EAirsoftTeam::Blue: return TEXT("Blue Squad");
		case EAirsoftTeam::Red: return TEXT("Red Squad");
		default: return TEXT("Unassigned");
		}
	}
}
