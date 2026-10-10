// Andrew's Airsoft - the rules of every game mode in one place: names, flags
// (rounds, respawns, free-for-all), timers, limits, the Gun Game ladder and the
// match map list. Tunable numbers come from UAirsoftSettings (Project Settings >
// Game > Airsoft); the game mode, HUD and bots all ask here instead of switching
// on the mode themselves.
//
//   Mode          Teams  Rounds  Respawn  Score shown         Ends when
//   TDM           2      1       yes      team tags           a team hits the tag limit / time
//   Domination    2      1       yes      team points         a team hits the point limit / time
//   Elimination   2      many    no       round wins          a side wins N rounds
//   Gun Game      FFA    1       yes      ladder level        someone tags with the last gun / time
//   VIP           2      many    no       round wins          more round wins after both halves

#pragma once

#include "CoreMinimal.h"
#include "AirsoftTypes.h"

namespace AirsoftRules
{
	/** Every mode in vote order (index = the value PlayerStates vote with). */
	constexpr int32 NumModes = 5;
	ANDREWSAIRSOFT_API EAirsoftMode ModeFromIndex(int32 Index);
	ANDREWSAIRSOFT_API int32 ModeIndex(EAirsoftMode Mode);

	/** "Team Deathmatch", "Gun Game", ... */
	ANDREWSAIRSOFT_API FString ModeName(EAirsoftMode Mode);
	/** One line of rules for the briefing and the menu. */
	ANDREWSAIRSOFT_API FString ModeBlurb(EAirsoftMode Mode);
	/** Value of ?Mode= in the travel URL, and back. */
	ANDREWSAIRSOFT_API FString ModeOption(EAirsoftMode Mode);
	ANDREWSAIRSOFT_API EAirsoftMode ModeFromOption(const FString& Option);

	/** Nobody has a team: everyone is hostile (Gun Game). */
	ANDREWSAIRSOFT_API bool IsFreeForAll(EAirsoftMode Mode);
	/** Several rounds per match with a pause (and replay) between them. */
	ANDREWSAIRSOFT_API bool IsRoundBased(EAirsoftMode Mode);
	/** Tagged players come back during the round (false = out until the next round). */
	ANDREWSAIRSOFT_API bool HasRespawns(EAirsoftMode Mode);
	/** Everyone carries a grenade (false: Gun Game, where the ladder decides the weapon). */
	ANDREWSAIRSOFT_API bool AllowsGrenades(EAirsoftMode Mode);

	/** Seconds of a live round (whole match for single-round modes). */
	ANDREWSAIRSOFT_API float RoundTime(EAirsoftMode Mode);
	ANDREWSAIRSOFT_API float RespawnTime(EAirsoftMode Mode);
	/** Frozen briefing before each round (round-based modes use it to pick a loadout). */
	ANDREWSAIRSOFT_API float FreezeTime(EAirsoftMode Mode);
	/** TDM tags, Domination points, rounds to win (Elimination, VIP), or ladder length (Gun Game). */
	ANDREWSAIRSOFT_API int32 ScoreLimit(EAirsoftMode Mode);
	/** Most rounds a match can last (0 = single round). */
	ANDREWSAIRSOFT_API int32 MaxRounds(EAirsoftMode Mode);
	/** VIP: rounds before the sides swap (0 = never). */
	ANDREWSAIRSOFT_API int32 RoundsPerHalf(EAirsoftMode Mode);

	/** The Gun Game ladder from the settings, unknown ids removed (falls back to the default ladder). */
	ANDREWSAIRSOFT_API TArray<FName> GunGameLadder();

	/** Do these teams fight under Mode? Free-for-all: always. Team modes: two different, assigned teams. */
	ANDREWSAIRSOFT_API bool AreHostile(EAirsoftMode Mode, EAirsoftTeam A, EAirsoftTeam B);

	/** Match maps from the settings (the built-in list if the setting is empty). */
	ANDREWSAIRSOFT_API const TArray<FAirsoftMapInfo>& Maps();
	ANDREWSAIRSOFT_API int32 NumMaps();
	/** Index of a map key in Maps(), or INDEX_NONE. */
	ANDREWSAIRSOFT_API int32 MapIndex(FName Key);
	ANDREWSAIRSOFT_API const FAirsoftMapInfo* FindMap(FName Key);
	/** Display name for a map key ("Staging Area" for none / unknown). */
	ANDREWSAIRSOFT_API FString MapDisplayName(FName Key);
}
