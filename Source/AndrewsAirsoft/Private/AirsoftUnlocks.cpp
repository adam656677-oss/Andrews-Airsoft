#include "AirsoftUnlocks.h"

#include "AirsoftAssets.h"
#include "AirsoftCampaign.h"
#include "AirsoftSaveGame.h"
#include "AirsoftWeaponData.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "GameFramework/GameModeBase.h"
#include "Kismet/GameplayStatics.h"

namespace AirsoftUnlocksLocal
{
	/** Weapon id -> the mission that unlocks it (0 = from the start), read once from Campaign.json. */
	const TMap<FName, int32>& Table()
	{
		static const TMap<FName, int32> Unlocks = []()
		{
			TMap<FName, int32> Out;
			const TSharedPtr<FJsonObject> Root = AirsoftAssets::LoadData(TEXT("Campaign.json"));
			const TSharedPtr<FJsonObject>* Block = nullptr;
			if (!Root.IsValid() || !Root->TryGetObjectField(TEXT("GunUnlocks"), Block) || !Block || !Block->IsValid())
			{
				return Out; // no table: every gun is open
			}
			auto AddGuns = [&Out](const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, int32 Mission)
			{
				const TArray<TSharedPtr<FJsonValue>>* Guns = nullptr;
				if (Obj.IsValid() && Obj->TryGetArrayField(Field, Guns))
				{
					for (const TSharedPtr<FJsonValue>& V : *Guns)
					{
						FString Id;
						if (V.IsValid() && V->TryGetString(Id) && !Id.IsEmpty())
						{
							Out.Add(FName(*Id), Mission);
						}
					}
				}
			};
			AddGuns(*Block, TEXT("Start"), 0);
			const TArray<TSharedPtr<FJsonValue>>* Missions = nullptr;
			if ((*Block)->TryGetArrayField(TEXT("Missions"), Missions))
			{
				for (const TSharedPtr<FJsonValue>& V : *Missions)
				{
					const TSharedPtr<FJsonObject>* Entry = nullptr;
					if (!V.IsValid() || !V->TryGetObject(Entry) || !Entry)
					{
						continue;
					}
					int32 Mission = 0;
					(*Entry)->TryGetNumberField(TEXT("Mission"), Mission);
					AddGuns(*Entry, TEXT("Guns"), FMath::Max(Mission, 0));
				}
			}
			return Out;
		}();
		return Unlocks;
	}

	/** Story missions this profile has finished. */
	int32 MissionsFinished(const UAirsoftSaveGame* Profile)
	{
		if (!Profile)
		{
			return 0;
		}
		const int32 Count = AirsoftCampaign::Missions().Num();
		return Profile->bCampaignFinished ? Count : FMath::Clamp(Profile->CampaignReached - 1, 0, Count);
	}

	/** The saved setup for a gun the loadout falls back to. */
	FAirsoftCustomization SetupFor(const UAirsoftSaveGame* Profile, FName Id)
	{
		if (Profile)
		{
			if (const FAirsoftCustomization* Saved = Profile->Customizations.Find(Id))
			{
				FAirsoftCustomization C = *Saved;
				C.WeaponId = Id;
				return AirsoftWeapons::Clean(C);
			}
		}
		const FAirsoftLoadout Defaults = AirsoftWeapons::DefaultLoadout();
		if (Defaults.Primary.WeaponId == Id)
		{
			return Defaults.Primary;
		}
		if (Defaults.Secondary.WeaponId == Id)
		{
			return Defaults.Secondary;
		}
		FAirsoftCustomization C;
		C.WeaponId = Id;
		return AirsoftWeapons::Clean(C);
	}

	/** The latest-unlocked open gun of a slot (the first listed on a tie), or None. */
	FName BestUnlocked(const UAirsoftSaveGame* Profile, const TArray<FName>& Candidates)
	{
		FName Best = NAME_None;
		int32 BestMission = -1;
		for (const FName Id : Candidates)
		{
			if (!AirsoftWeapons::Find(Id) || !AirsoftUnlocks::IsUnlocked(Profile, Id))
			{
				continue;
			}
			const int32 Mission = AirsoftUnlocks::UnlockMission(Id);
			if (Mission > BestMission)
			{
				Best = Id;
				BestMission = Mission;
			}
		}
		return Best;
	}
}

namespace AirsoftUnlocks
{
	int32 UnlockMission(FName WeaponId)
	{
		const int32* Mission = AirsoftUnlocksLocal::Table().Find(WeaponId);
		return Mission ? *Mission : 0;
	}

	bool IsUnlocked(const UAirsoftSaveGame* Profile, FName WeaponId)
	{
		return UnlockMission(WeaponId) <= 0 || (Profile && Profile->UnlockedGuns.Contains(WeaponId));
	}

	TArray<FName> GrantForMission(UAirsoftSaveGame* Profile, int32 Number)
	{
		TArray<FName> Added;
		if (!Profile || Number <= 0)
		{
			return Added;
		}
		// Walk the weapon lists (not the map) so the names come out in a stable order.
		for (const TArray<FName>* List : { &AirsoftWeapons::Primaries(), &AirsoftWeapons::Secondaries() })
		{
			for (const FName Id : *List)
			{
				if (UnlockMission(Id) == Number && !Profile->UnlockedGuns.Contains(Id))
				{
					Profile->UnlockedGuns.Add(Id);
					Added.Add(Id);
				}
			}
		}
		return Added;
	}

	TArray<FName> Sync(UAirsoftSaveGame* Profile)
	{
		TArray<FName> Added;
		const int32 Finished = AirsoftUnlocksLocal::MissionsFinished(Profile);
		for (int32 Number = 1; Number <= Finished; ++Number)
		{
			Added.Append(GrantForMission(Profile, Number));
		}
		return Added;
	}

	bool SanitizeLoadout(const UAirsoftSaveGame* Profile, FAirsoftLoadout& Loadout)
	{
		bool bChanged = false;
		if (!IsUnlocked(Profile, Loadout.Primary.WeaponId))
		{
			const FName Best = AirsoftUnlocksLocal::BestUnlocked(Profile, AirsoftWeapons::Primaries());
			Loadout.Primary = Best.IsNone() ? AirsoftWeapons::DefaultLoadout().Primary : AirsoftUnlocksLocal::SetupFor(Profile, Best);
			bChanged = true;
		}
		if (!IsUnlocked(Profile, Loadout.Secondary.WeaponId))
		{
			const FName Best = AirsoftUnlocksLocal::BestUnlocked(Profile, AirsoftWeapons::Secondaries());
			Loadout.Secondary = Best.IsNone() ? AirsoftWeapons::DefaultLoadout().Secondary : AirsoftUnlocksLocal::SetupFor(Profile, Best);
			bChanged = true;
		}
		return bChanged;
	}

	bool SanitizeLoadout(UAirsoftSaveGame* Profile)
	{
		return Profile && SanitizeLoadout(Profile, Profile->Loadout);
	}

	bool CanTryLockedGuns(const UWorld* World)
	{
		const AGameModeBase* GM = World ? World->GetAuthGameMode() : nullptr;
		if (!GM || GM->IsA<AAirsoftCampaignGameMode>())
		{
			return false;
		}
		return UGameplayStatics::HasOption(GM->OptionsString, TEXT("Practice"));
	}

	FString NamesText(const TArray<FName>& WeaponIds)
	{
		TArray<FString> Names;
		for (const FName Id : WeaponIds)
		{
			const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(Id);
			Names.Add(Def ? Def->Name : Id.ToString());
		}
		if (Names.Num() <= 1)
		{
			return Names.Num() == 1 ? Names[0] : FString();
		}
		const FString Last = Names.Pop();
		return FString::Printf(TEXT("%s and %s"), *FString::Join(Names, TEXT(", ")), *Last);
	}
}
