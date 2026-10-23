// Andrew's Airsoft - game mode rules (see AirsoftModeRules.h).

#include "AirsoftModeRules.h"

#include "AirsoftSettings.h"
#include "AirsoftWeaponData.h"

// A new EAirsoftMode needs NumModes (and the switches below) updated with it.
static_assert(static_cast<int32>(EAirsoftMode::VIP) + 1 == AirsoftRules::NumModes, "AirsoftRules::NumModes must match EAirsoftMode");

namespace AirsoftRules
{
	EAirsoftMode ModeFromIndex(int32 Index)
	{
		return static_cast<EAirsoftMode>(FMath::Clamp(Index, 0, NumModes - 1));
	}

	int32 ModeIndex(EAirsoftMode Mode)
	{
		return FMath::Clamp(static_cast<int32>(Mode), 0, NumModes - 1);
	}

	FString ModeName(EAirsoftMode Mode)
	{
		switch (Mode)
		{
		case EAirsoftMode::Domination: return TEXT("Domination");
		case EAirsoftMode::Elimination: return TEXT("Elimination");
		case EAirsoftMode::GunGame: return TEXT("Gun Game");
		case EAirsoftMode::VIP: return TEXT("VIP Escort");
		default: return TEXT("Team Deathmatch");
		}
	}

	FString ModeBlurb(EAirsoftMode Mode)
	{
		switch (Mode)
		{
		case EAirsoftMode::Domination:
			return TEXT("Hold A, B and C. Every held point scores over time.");
		case EAirsoftMode::Elimination:
			return FString::Printf(TEXT("One life per round. Last side standing takes it. First to %d rounds."), ScoreLimit(Mode));
		case EAirsoftMode::GunGame:
			return TEXT("Everyone for themselves. Each tag hands you the next gun; tag with the last one to win.");
		case EAirsoftMode::VIP:
			return TEXT("Attackers walk a pistol-only VIP to extraction. Defenders tag the VIP or run the clock. Sides swap at half.");
		default:
			return TEXT("Tag the other team. First to the limit wins.");
		}
	}

	FString ModeOption(EAirsoftMode Mode)
	{
		switch (Mode)
		{
		case EAirsoftMode::Domination: return TEXT("Domination");
		case EAirsoftMode::Elimination: return TEXT("Elimination");
		case EAirsoftMode::GunGame: return TEXT("GunGame");
		case EAirsoftMode::VIP: return TEXT("VIP");
		default: return TEXT("TDM");
		}
	}

	EAirsoftMode ModeFromOption(const FString& Option)
	{
		for (int32 Index = 0; Index < NumModes; ++Index)
		{
			const EAirsoftMode Mode = ModeFromIndex(Index);
			if (Option.Equals(ModeOption(Mode), ESearchCase::IgnoreCase))
			{
				return Mode;
			}
		}
		return EAirsoftMode::TDM;
	}

	bool IsFreeForAll(EAirsoftMode Mode)
	{
		return Mode == EAirsoftMode::GunGame;
	}

	bool IsRoundBased(EAirsoftMode Mode)
	{
		return Mode == EAirsoftMode::Elimination || Mode == EAirsoftMode::VIP;
	}

	bool HasRespawns(EAirsoftMode Mode)
	{
		return !IsRoundBased(Mode);
	}

	bool AllowsGrenades(EAirsoftMode Mode)
	{
		return Mode != EAirsoftMode::GunGame;
	}

	float RoundTime(EAirsoftMode Mode)
	{
		const UAirsoftSettings* S = UAirsoftSettings::Get();
		switch (Mode)
		{
		case EAirsoftMode::Elimination: return FMath::Max(S->EliminationRoundTime, 20.f);
		case EAirsoftMode::GunGame: return FMath::Max(S->GunGameTime, 30.f);
		case EAirsoftMode::VIP: return FMath::Max(S->VIPRoundTime, 20.f);
		default: return FMath::Max(S->RoundTime, 30.f);
		}
	}

	float RespawnTime(EAirsoftMode Mode)
	{
		const UAirsoftSettings* S = UAirsoftSettings::Get();
		return Mode == EAirsoftMode::GunGame ? FMath::Max(S->GunGameRespawnTime, 0.5f) : FMath::Max(S->RespawnTime, 0.5f);
	}

	float FreezeTime(EAirsoftMode Mode)
	{
		const UAirsoftSettings* S = UAirsoftSettings::Get();
		return IsRoundBased(Mode) ? FMath::Max(S->BriefingTime, S->RoundFreezeTime) : S->BriefingTime;
	}

	int32 ScoreLimit(EAirsoftMode Mode)
	{
		const UAirsoftSettings* S = UAirsoftSettings::Get();
		switch (Mode)
		{
		case EAirsoftMode::Domination: return FMath::Max(S->DominationScoreLimit, 1);
		case EAirsoftMode::Elimination: return FMath::Max(S->EliminationRoundsToWin, 1);
		case EAirsoftMode::GunGame: return GunGameLadder().Num();
		case EAirsoftMode::VIP: return FMath::Max(S->VIPRoundsPerHalf, 1) + 1; // a majority of both halves
		default: return FMath::Max(S->TDMScoreLimit, 1);
		}
	}

	int32 MaxRounds(EAirsoftMode Mode)
	{
		switch (Mode)
		{
		// Room for a couple of drawn rounds (both sides out at once, or nobody left at the whistle).
		case EAirsoftMode::Elimination: return ScoreLimit(Mode) * 2 + 1;
		case EAirsoftMode::VIP: return RoundsPerHalf(Mode) * 2;
		default: return 0;
		}
	}

	int32 RoundsPerHalf(EAirsoftMode Mode)
	{
		return Mode == EAirsoftMode::VIP ? FMath::Max(UAirsoftSettings::Get()->VIPRoundsPerHalf, 1) : 0;
	}

	TArray<FName> GunGameLadder()
	{
		TArray<FName> Ladder;
		for (const FName& Id : UAirsoftSettings::Get()->GunGameLadder)
		{
			if (AirsoftWeapons::Find(Id))
			{
				Ladder.Add(Id);
			}
		}
		if (Ladder.Num() < 2)
		{
			Ladder.Reset();
			for (const FName& Id : UAirsoftSettings::DefaultGunGameLadder())
			{
				if (AirsoftWeapons::Find(Id))
				{
					Ladder.Add(Id);
				}
			}
		}
		return Ladder;
	}

	bool AreHostile(EAirsoftMode Mode, EAirsoftTeam A, EAirsoftTeam B)
	{
		if (IsFreeForAll(Mode))
		{
			return true;
		}
		return A != EAirsoftTeam::None && B != EAirsoftTeam::None && A != B;
	}

	const TArray<FAirsoftMapInfo>& Maps()
	{
		const TArray<FAirsoftMapInfo>& Configured = UAirsoftSettings::Get()->MatchMaps;
		if (Configured.Num() > 0)
		{
			return Configured;
		}
		static const TArray<FAirsoftMapInfo> Fallback = UAirsoftSettings::DefaultMatchMaps();
		return Fallback;
	}

	int32 NumMaps()
	{
		return Maps().Num();
	}

	int32 MapIndex(FName Key)
	{
		const TArray<FAirsoftMapInfo>& List = Maps();
		for (int32 Index = 0; Index < List.Num(); ++Index)
		{
			if (List[Index].Key == Key)
			{
				return Index;
			}
		}
		return INDEX_NONE;
	}

	const FAirsoftMapInfo* FindMap(FName Key)
	{
		const int32 Index = MapIndex(Key);
		return Index != INDEX_NONE ? &Maps()[Index] : nullptr;
	}

	FString MapDisplayName(FName Key)
	{
		if (const FAirsoftMapInfo* Info = Key.IsNone() ? nullptr : FindMap(Key))
		{
			return Info->DisplayName.IsEmpty() ? Key.ToString() : Info->DisplayName;
		}
		return TEXT("Staging Area");
	}
}
