// Andrew's Airsoft - story gun unlocks. A new profile opens a few guns; each finished
// story mission adds more (Campaign.json "GunUnlocks"). Granted guns live in
// UAirsoftSaveGame::UnlockedGuns. Missions and skirmish use unlocked guns only; the
// practice range lets you try any gun without putting it in the saved loadout.

#pragma once

#include "CoreMinimal.h"
#include "AirsoftTypes.h"

class UAirsoftSaveGame;
class UWorld;

namespace AirsoftUnlocks
{
	/** The mission whose completion unlocks this gun; 0 = open from the start (and for any gun the table doesn't list). */
	ANDREWSAIRSOFT_API int32 UnlockMission(FName WeaponId);

	/** Open from the start, or granted to this profile. */
	ANDREWSAIRSOFT_API bool IsUnlocked(const UAirsoftSaveGame* Profile, FName WeaponId);

	/** Grants the guns of every mission the profile has already finished (saves from before unlocks existed). Returns the newly added ids. */
	ANDREWSAIRSOFT_API TArray<FName> Sync(UAirsoftSaveGame* Profile);

	/** Story mission Number finished: grants its guns. Returns the ones that were new to this profile. */
	ANDREWSAIRSOFT_API TArray<FName> GrantForMission(UAirsoftSaveGame* Profile, int32 Number);

	/** Swaps a locked gun in Loadout for the best unlocked gun of the same slot (its saved setup if it has one). True if anything changed. */
	ANDREWSAIRSOFT_API bool SanitizeLoadout(const UAirsoftSaveGame* Profile, FAirsoftLoadout& Loadout);

	/** The same, on the profile's saved loadout. */
	ANDREWSAIRSOFT_API bool SanitizeLoadout(UAirsoftSaveGame* Profile);

	/** The practice range (opened with ?Practice, outside the story): any gun can be tried there. */
	ANDREWSAIRSOFT_API bool CanTryLockedGuns(const UWorld* World);

	/** "MP7 GBB, Vector .45 and G34 Competition". */
	ANDREWSAIRSOFT_API FString NamesText(const TArray<FName>& WeaponIds);
}
