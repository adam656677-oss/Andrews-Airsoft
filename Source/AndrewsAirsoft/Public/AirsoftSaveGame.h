// Andrew's Airsoft - local profile: rank, career stats, settings and loadout.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/SaveGame.h"
#include "AirsoftTypes.h"
#include "AirsoftSaveGame.generated.h"

USTRUCT(BlueprintType)
struct FAirsoftUserSettings
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite) float Sensitivity = 1.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float AimSensitivity = 0.7f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float FieldOfView = 90.f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bToggleAim = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bInvertY = false;
	/** 0 = Low .. 3 = Epic (engine scalability). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 Quality = 2;
	/** Internal render resolution percentage before TSR upscaling. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float RenderScale = 60.f;
	/** 0 = Window (title bar: minimise / close), 1 = Borderless, 2 = Fullscreen. Alt+Enter also toggles. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 WindowMode = 0;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) float MasterVolume = 0.8f;
	/** Big-screen cinematic gunfire (true) or realistic mechanical airsoft sounds (false). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bCinematicGunSounds = true;
	/** Cinematic muzzle puffs, flashes and hit pulses (true) or airsoft-authentic: gas-gun vapour only, no flashes (false). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bCinematicEffects = true;
	/** Camera shake from nearby grenades and when you are tagged. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bScreenShake = true;
	/** Over-the-shoulder camera in airsoft matches. Off by default: first person is the airsoft view (no corner peeking). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bThirdPersonMatches = false;
	/** Over-the-shoulder camera in the story campaign. On by default: the suit, the rain, the noir framing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bThirdPersonStory = true;
	/** Third person: camera over the left shoulder instead of the right. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) bool bLeftShoulder = false;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString LastJoinAddress;
	UPROPERTY(EditAnywhere, BlueprintReadWrite) FString PlayerName;
	/** When hosting: fill both teams with bots on match maps (AirsoftBots::TeamSize: 0 off, 1 4v4, 2 6v6, 3 8v8, 4 10v10). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 BotFill = 0;
	/** When hosting: bot difficulty (EAirsoftBotSkill: 0 Easy .. 3 Expert). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite) int32 BotSkill = 1;
};

UCLASS()
class ANDREWSAIRSOFT_API UAirsoftSaveGame : public USaveGame
{
	GENERATED_BODY()

public:
	static constexpr const TCHAR* SlotName = TEXT("AirsoftProfile");

	UPROPERTY() int32 Version = 1;
	UPROPERTY() int32 XP = 0;
	UPROPERTY() int32 Tags = 0;
	UPROPERTY() int32 Outs = 0;
	UPROPERTY() int32 Wins = 0;
	UPROPERTY() int32 Matches = 0;
	UPROPERTY() int32 Captures = 0;
	UPROPERTY() int32 BestStreak = 0;
	UPROPERTY() FAirsoftUserSettings Settings;
	/** Story campaign: the furthest mission unlocked (1-based) and whether the last one has been beaten. */
	UPROPERTY() int32 CampaignReached = 1;
	UPROPERTY() bool bCampaignFinished = false;
	UPROPERTY() FAirsoftLoadout Loadout;
	/** Saved attachments/finish per weapon id, so swapping guns keeps each one's setup. */
	UPROPERTY() TMap<FName, FAirsoftCustomization> Customizations;
};
