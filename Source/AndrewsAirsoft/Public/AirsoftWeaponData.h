// Andrew's Airsoft - weapon, attachment, finish and rank definitions.
// Units: centimetres, seconds, degrees. Everything gameplay-tunable lives here.

#pragma once

#include "CoreMinimal.h"
#include "AirsoftTypes.h"

struct FAirsoftWeaponDef
{
	FName Id;
	FString Name;
	FString Kind;   // AEG, Gas, Spring
	FString Class;  // Rifle, DMR, Sniper, LMG, SMG, Shotgun, Pistol, Grenade
	FString Description;
	EAirsoftSlot Slot = EAirsoftSlot::Primary;
	TArray<EAirsoftFireMode> FireModes;

	float FireInterval = 0.08f;
	int32 MagSize = 30;
	int32 Reserve = 180;
	float ReloadTime = 2.1f;
	float EmptyReloadTime = 2.5f;

	/** BB physics: muzzle velocity (cm/s), hop-up lift (1 = balanced at the muzzle), drag (1/cm). */
	float MuzzleVelocity = 11000.f;
	float Hop = 1.0f;
	float Drag = 0.000121f;
	float MaxRange = 6000.f;

	float HipSpread = 2.4f;
	float AimSpread = 0.35f;
	float RecoilUp = 0.55f;
	float RecoilSide = 0.25f;
	float AimFOV = 62.f;
	float AimTime = 0.2f;
	int32 Pellets = 1;
	FName Sound = TEXT("FireRifle");
	bool bQuiet = false;
	bool bBuiltInSuppressor = false;
	bool bScopeOverlay = false;
	float SpeedMultiplier = 1.f;

	/** Allowed attachments per slot ("Optic", "Muzzle", "Grip", "Laser", "Mag"). AirsoftWeapons::AttachOff in a list means the slot may be left empty. */
	TMap<FName, TArray<FName>> Options;
	TMap<FName, FName> Defaults;
	TSet<FName> RequiredSlots;

	/** Display-only 0..1 ratings for the armory. */
	float StatRange = 0.5f, StatRate = 0.5f, StatControl = 0.5f, StatHandling = 0.5f;

	bool IsPrimary() const { return Slot == EAirsoftSlot::Primary; }
	bool IsSecondary() const { return Slot == EAirsoftSlot::Secondary; }
};

struct FAirsoftAttachmentDef
{
	FName Id;
	FName Slot;
	FString Name;
	FString Blurb;
	float AimFOV = 0.f;          // 0 = no change
	float AimTimeMult = 1.f;
	float RecoilMult = 1.f;
	float SpreadMult = 1.f;
	float HipSpreadMult = 1.f;
	float VelocityMult = 1.f;
	float ReloadTimeMult = 1.f;
	int32 MagSizeOverride = 0;   // 0 = keep weapon mag
	bool bQuiet = false;
	bool bOverlay = false;       // full-screen scope picture when aimed
};

struct FAirsoftSkinDef
{
	FName Id;
	FString Name;
	FLinearColor Primary;
	FLinearColor Secondary;
	float Metallic = 0.f;
	float Roughness = 0.55f;
	int32 UnlockRank = 1;
};

struct FAirsoftRankDef
{
	FString Name;
	int32 XP = 0;
};

namespace AirsoftWeapons
{
	extern const FName SlotOptic;
	extern const FName SlotMuzzle;
	extern const FName SlotGrip;
	extern const FName SlotLaser;
	extern const FName SlotMag;
	/** Explicit "nothing fitted" choice for an attachment slot. */
	extern const FName AttachOff;
	const TArray<FName>& AttachmentSlots();

	ANDREWSAIRSOFT_API const FAirsoftWeaponDef* Find(FName Id);
	ANDREWSAIRSOFT_API const TArray<FName>& Primaries();
	ANDREWSAIRSOFT_API const TArray<FName>& Secondaries();
	ANDREWSAIRSOFT_API const FAirsoftAttachmentDef* FindAttachment(FName Id);
	ANDREWSAIRSOFT_API const TArray<FAirsoftSkinDef>& Skins();
	ANDREWSAIRSOFT_API const FAirsoftSkinDef& FindSkin(FName Id);
	ANDREWSAIRSOFT_API const TArray<FAirsoftRankDef>& Ranks();

	/** Fill empty slots with defaults and drop anything the weapon doesn't accept. */
	ANDREWSAIRSOFT_API FAirsoftCustomization Clean(const FAirsoftCustomization& In);

	/** Weapon stats with attachments applied. */
	ANDREWSAIRSOFT_API FAirsoftWeaponDef Resolve(const FAirsoftCustomization& In);

	/** 1-based rank index for an XP total. */
	ANDREWSAIRSOFT_API int32 RankIndexForXP(int32 XP);

	ANDREWSAIRSOFT_API FString FireModeName(EAirsoftFireMode Mode);

	ANDREWSAIRSOFT_API FAirsoftLoadout DefaultLoadout();

	/** Grenade tuning. */
	constexpr float GrenadeFuse = 2.2f;
	constexpr float GrenadeThrowSpeed = 1800.f;
	constexpr float GrenadeRadius = 550.f;
	constexpr int32 GrenadesPerLife = 1;
}
