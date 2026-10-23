// Andrew's Airsoft - project settings (Project Settings > Game > Airsoft).

#pragma once

#include "CoreMinimal.h"
#include "Engine/DeveloperSettings.h"
#include "AirsoftTypes.h"
#include "AirsoftSettings.generated.h"

class UAnimInstance;
class USkeletalMesh;
class UMaterialInterface;

/**
 * Story and skirmish difficulty, picked on New Game and in Skirmish and saved as
 * FAirsoftUserSettings::Difficulty. Same order as EAirsoftBotSkill, so the index
 * doubles as the enemy bot skill (AirsoftDifficulty::BotSkill).
 */
UENUM(BlueprintType)
enum class EAirsoftDifficulty : uint8
{
	/** Slow, forgiving enemies; for enjoying the story. */
	Recruit,
	Operator,
	Professional,
	/** Fast, accurate enemies that flank. */
	Legend
};

namespace AirsoftDifficulty
{
	constexpr int32 Num = 4;

	inline EAirsoftDifficulty FromIndex(int32 Index)
	{
		return static_cast<EAirsoftDifficulty>(FMath::Clamp(Index, 0, Num - 1));
	}

	inline FString Label(EAirsoftDifficulty Difficulty)
	{
		switch (Difficulty)
		{
		case EAirsoftDifficulty::Recruit: return TEXT("RECRUIT");
		case EAirsoftDifficulty::Professional: return TEXT("PROFESSIONAL");
		case EAirsoftDifficulty::Legend: return TEXT("LEGEND");
		default: return TEXT("OPERATOR");
		}
	}

	inline FString Blurb(EAirsoftDifficulty Difficulty)
	{
		switch (Difficulty)
		{
		case EAirsoftDifficulty::Recruit: return TEXT("Enemies react slowly and miss often. For the story.");
		case EAirsoftDifficulty::Professional: return TEXT("Quick, accurate enemies. Cover matters.");
		case EAirsoftDifficulty::Legend: return TEXT("They see you first, flank and rarely miss.");
		default: return TEXT("A fair fight. The intended experience.");
		}
	}

	/** Enemy bot skill for a difficulty (same order). */
	inline EAirsoftBotSkill BotSkill(EAirsoftDifficulty Difficulty)
	{
		return static_cast<EAirsoftBotSkill>(static_cast<uint8>(Difficulty));
	}
}

/**
 * Procedural gun motion: aim settle, breathing, recoil spring, landing, lean and the melee strike
 * (Project Settings > Game > Airsoft > Viewmodel). First person and the third-person gun share it.
 */
USTRUCT(BlueprintType)
struct FAirsoftViewmodelTuning
{
	GENERATED_BODY()

	/** How far past the sights the gun swings when it arrives at aim, as a share of the hip-to-sights distance. 0 = no settle. */
	UPROPERTY(EditAnywhere, Category = "Aim", meta = (ClampMin = "0", ClampMax = "0.3"))
	float AimOvershoot = 0.06f;

	/** Spring stiffness of the aim settle (higher = quicker settle). */
	UPROPERTY(EditAnywhere, Category = "Aim", meta = (ClampMin = "20"))
	float AimSpringStiffness = 260.f;

	/** Damping ratio of the aim settle: 1 = no bounce, lower bounces more. */
	UPROPERTY(EditAnywhere, Category = "Aim", meta = (ClampMin = "0.05", ClampMax = "1"))
	float AimSpringDamping = 0.5f;

	/** Breathing: degrees the gun drifts at the hip. */
	UPROPERTY(EditAnywhere, Category = "Breathing", meta = (ClampMin = "0"))
	float BreathDegrees = 0.45f;

	/** Share of the breathing drift left while aiming. */
	UPROPERTY(EditAnywhere, Category = "Breathing", meta = (ClampMin = "0", ClampMax = "1"))
	float BreathAimScale = 0.3f;

	/** Breaths per second. */
	UPROPERTY(EditAnywhere, Category = "Breathing", meta = (ClampMin = "0.05"))
	float BreathRate = 0.22f;

	/** Recoil: cm the gun jumps back per unit of the gun's RecoilUp. */
	UPROPERTY(EditAnywhere, Category = "Recoil", meta = (ClampMin = "0"))
	float RecoilKickBack = 3.4f;

	/** Recoil: degrees the muzzle climbs per unit of RecoilUp. */
	UPROPERTY(EditAnywhere, Category = "Recoil", meta = (ClampMin = "0"))
	float RecoilKickPitch = 5.f;

	/** Recoil: degrees of random roll per unit of RecoilUp. */
	UPROPERTY(EditAnywhere, Category = "Recoil", meta = (ClampMin = "0"))
	float RecoilKickRoll = 2.5f;

	/** Recoil spring stiffness (higher = snappier return). */
	UPROPERTY(EditAnywhere, Category = "Recoil", meta = (ClampMin = "20"))
	float RecoilSpringStiffness = 340.f;

	/** Recoil damping ratio: 1 = no bounce, lower overshoots forward a little on the way back. */
	UPROPERTY(EditAnywhere, Category = "Recoil", meta = (ClampMin = "0.05", ClampMax = "1"))
	float RecoilSpringDamping = 0.45f;

	/** Landing: cm the gun dips for each cm the camera dips. */
	UPROPERTY(EditAnywhere, Category = "Movement", meta = (ClampMin = "0"))
	float LandDipScale = 0.6f;

	/** Leaning: extra roll of the gun at a full lean, in degrees. */
	UPROPERTY(EditAnywhere, Category = "Movement", meta = (ClampMin = "0"))
	float LeanRollDegrees = 5.f;

	/** Strafing: degrees the gun rolls into the direction you strafe at full run. */
	UPROPERTY(EditAnywhere, Category = "Movement", meta = (ClampMin = "0"))
	float StrafeRollDegrees = 3.f;

	/** Melee (rifle butt / pistol whip): whole strike, wind-up to recovery, in seconds. */
	UPROPERTY(EditAnywhere, Category = "Melee", meta = (ClampMin = "0.15"))
	float MeleeDuration = 0.35f;

	/** Melee reach from the eyes, in cm. */
	UPROPERTY(EditAnywhere, Category = "Melee", meta = (ClampMin = "50"))
	float MeleeRange = 170.f;

	/** Seconds between strikes. */
	UPROPERTY(EditAnywhere, Category = "Melee", meta = (ClampMin = "0.2"))
	float MeleeCooldown = 0.6f;

	/** Story missions: damage of one strike (enemies have 100 health). Airsoft matches: a strike is a tag. */
	UPROPERTY(EditAnywhere, Category = "Melee", meta = (ClampMin = "0"))
	float MeleeDamage = 80.f;
};

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

	/** Practice Range and its how-to-play walkthrough: the staging area's firing lanes. */
	UPROPERTY(Config, EditAnywhere, Category = "Maps")
	FString PracticeMap = TEXT("/Game/Maps/L_Staging");

	/**
	 * Developer only. The game ships single-player: off hides Host/Join, the Tailscale address,
	 * text chat, lobby votes and Start Match Now, and staging works as a hub. The online code stays.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Multiplayer")
	bool bEnableMultiplayer = false;

	static bool IsMultiplayerEnabled() { return Get()->bEnableMultiplayer; }

	/**
	 * Match maps offered in the lobby vote, in vote order: key, display name, level, the modes each
	 * one runs (empty = all) and the recommended head count. Empty list = the built-in three.
	 */
	UPROPERTY(Config, EditAnywhere, Category = "Maps")
	TArray<FAirsoftMapInfo> MatchMaps = DefaultMatchMaps();

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

	/** Round-based modes (Elimination, VIP): frozen at the start of every round - time to pick a loadout. */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|Rounds", meta = (ClampMin = "2"))
	float RoundFreezeTime = 8.f;

	/** Round-based modes: pause between rounds (the final-tag replay plays in it). */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|Rounds", meta = (ClampMin = "3"))
	float RoundOverTime = 7.f;

	/** Elimination: rounds a side needs to win the match. */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|Elimination", meta = (ClampMin = "1"))
	int32 EliminationRoundsToWin = 5;

	UPROPERTY(Config, EditAnywhere, Category = "Rules|Elimination", meta = (ClampMin = "20"))
	float EliminationRoundTime = 120.f;

	/** VIP: rounds per half. Sides swap at half time; the side with more round wins takes the match. */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|VIP", meta = (ClampMin = "1"))
	int32 VIPRoundsPerHalf = 3;

	UPROPERTY(Config, EditAnywhere, Category = "Rules|VIP", meta = (ClampMin = "20"))
	float VIPRoundTime = 150.f;

	/** VIP: seconds the VIP must stand in the extraction zone. */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|VIP", meta = (ClampMin = "0.5"))
	float VIPExtractTime = 3.f;

	/** Gun Game: match length (the highest level when time runs out wins). */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|Gun Game", meta = (ClampMin = "30"))
	float GunGameTime = 600.f;

	UPROPERTY(Config, EditAnywhere, Category = "Rules|Gun Game", meta = (ClampMin = "0.5"))
	float GunGameRespawnTime = 3.f;

	/** Gun Game: weapon ids from first to last (a tag with the last one wins). Unknown ids are skipped. */
	UPROPERTY(Config, EditAnywhere, Category = "Rules|Gun Game")
	TArray<FName> GunGameLadder = DefaultGunGameLadder();

	/** Chat: longest message the host accepts (longer ones are cut). */
	UPROPERTY(Config, EditAnywhere, Category = "Chat", meta = (ClampMin = "8"))
	int32 ChatMaxLength = 120;

	/** Chat rate limit: messages a player may send back to back... */
	UPROPERTY(Config, EditAnywhere, Category = "Chat", meta = (ClampMin = "1"))
	int32 ChatBurst = 4;

	/** ...and the seconds it takes to earn one more. */
	UPROPERTY(Config, EditAnywhere, Category = "Chat", meta = (ClampMin = "0.1"))
	float ChatRefillSeconds = 1.5f;

	/** Bots now and then say a short line in chat. */
	UPROPERTY(Config, EditAnywhere, Category = "Chat")
	bool bBotChatter = true;

	/** Bot behaviour per difficulty. The host turns bots on and picks the difficulty in Settings > Host. */
	UPROPERTY(Config, EditAnywhere, Category = "Bots")
	FAirsoftBotTuning BotEasy = FAirsoftBotTuning::Preset(EAirsoftBotSkill::Easy);

	UPROPERTY(Config, EditAnywhere, Category = "Bots")
	FAirsoftBotTuning BotNormal = FAirsoftBotTuning::Preset(EAirsoftBotSkill::Normal);

	UPROPERTY(Config, EditAnywhere, Category = "Bots")
	FAirsoftBotTuning BotHard = FAirsoftBotTuning::Preset(EAirsoftBotSkill::Hard);

	UPROPERTY(Config, EditAnywhere, Category = "Bots")
	FAirsoftBotTuning BotExpert = FAirsoftBotTuning::Preset(EAirsoftBotSkill::Expert);

	/** How far bots hear an ordinary shot (cm, before the difficulty's HearingScale). */
	UPROPERTY(Config, EditAnywhere, Category = "Bots")
	float BotHearingRange = 4500.f;

	/** How far bots hear a quiet shot (suppressor, MP5 SD, spring sniper). */
	UPROPERTY(Config, EditAnywhere, Category = "Bots")
	float BotQuietHearingRange = 1500.f;

	/** Procedural gun motion and the melee strike. */
	UPROPERTY(Config, EditAnywhere, Category = "Viewmodel", meta = (ShowOnlyInnerProperties))
	FAirsoftViewmodelTuning Viewmodel;

	const FAirsoftBotTuning& GetBotTuning(EAirsoftBotSkill Skill) const
	{
		switch (Skill)
		{
		case EAirsoftBotSkill::Easy: return BotEasy;
		case EAirsoftBotSkill::Hard: return BotHard;
		case EAirsoftBotSkill::Expert: return BotExpert;
		default: return BotNormal;
		}
	}

	/** Ironwood Yard, Velvet Club, Nightjar Garage, Saltmarsh Terminal and Ledger Tower (AirsoftSettings.cpp). */
	static TArray<FAirsoftMapInfo> DefaultMatchMaps();

	/** Pistols -> SMGs -> rifles -> shotgun -> sniper -> a final pistol. */
	static TArray<FName> DefaultGunGameLadder();

	static const UAirsoftSettings* Get() { return GetDefault<UAirsoftSettings>(); }
};
