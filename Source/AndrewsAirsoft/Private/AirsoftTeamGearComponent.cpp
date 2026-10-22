#include "AirsoftTeamGearComponent.h"

#include "AirsoftAssets.h"
#include "AirsoftCharacter.h"
#include "AirsoftGearSettings.h"
#include "Components/SceneComponent.h"
#include "Components/SkinnedMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/SkinnedAsset.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/Crc.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "ReferenceSkeleton.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UObjectIterator.h"

DEFINE_LOG_CATEGORY_STATIC(LogAirsoftGear, Log, All);

// ---------------------------------------------------------------------------
// Gear.json database
// ---------------------------------------------------------------------------

namespace AirsoftTeamGear
{
	/** Where a piece sits: its anchor bone plus a character-space offset (cm) from that bone's reference-pose pivot. */
	struct FGearAnchor
	{
		FName Bone;
		/** Optional: turn the piece so ModelDir (its modelled bone direction) follows Bone -> AlignBone in the reference pose. */
		FName AlignBone;
		FVector ModelDir = FVector::ZeroVector;
		FVector Offset = FVector::ZeroVector;
		FRotator Rotation = FRotator::ZeroRotator;
		float Scale = 1.f;
		FVector AssumedBonePos = FVector::ZeroVector;
		bool bHasAssumed = false;
		bool bValid = false;
	};

	struct FGearPieceDef
	{
		FName Name;
		FName Kind;
		FGearAnchor Anchor;
		bool bOwnAnchor = false;
	};

	struct FGearAssetDef
	{
		FName Id;
		TArray<FGearPieceDef> Pieces;
		FGearAnchor Anchor;
		FName Colorway;
		/** Non-empty for outfit assets (Gear.json "Outfit" block, e.g. the suit) instead of team gear. */
		FName Outfit;
		/** Outfit mask roles: "Suit" (R cloth, G shirt, B tie) or "Hair" (R hair). */
		FName SuitTint;
		float TintRoughness = 0.5f;
		float RoughnessDetail = 1.f;
		float TintMetallic = 0.f;
		bool bHasGlass = false;
		FLinearColor GlassTint = FLinearColor(0.025f, 0.027f, 0.03f);
		float GlassOpacity = 0.62f;
		float GlassRoughness = 0.04f;
	};

	struct FGearColorway
	{
		FName Name;
		FLinearColor Primary = FLinearColor::Black;
		FLinearColor Secondary = FLinearColor::Black;
	};

	struct FGearOption
	{
		FName Asset;
		float Weight = 1.f;
	};

	struct FGearSlot
	{
		FName Slot;
		float Chance = 1.f;
		TArray<FGearOption> Options;
	};

	struct FSuitColor
	{
		FName Name;
		FLinearColor Color = FLinearColor::Black;
		float Weight = 1.f;
	};

	struct FGearDatabase
	{
		TMap<FName, FGearAssetDef> Assets;
		/** Gear.json "Suit": assets worn together, colourway groups (Suit, Shirt, Tie, Hair), multiplayer suit colourways. */
		TArray<FName> SuitAssets;
		TMap<FName, TArray<FSuitColor>> SuitColorways;
		TArray<FName> MultiplayerSuits;
		TMap<FName, TArray<FGearColorway>> Colorways;
		TArray<FGearSlot> Slots;
		/** Cranium centre relative to the head pivot (cm): the stand-in sphere head stands for it. */
		FVector FallbackHeadCenter = FVector(0.8f, 0.f, 8.8f);
		/** GearHeads.json "Heads": story character -> head asset, the Ledger crew heads (picked by seed), and the
		 *  suit assets a head replaces (the suit's own haircut). */
		TMap<FName, FName> HeadCast;
		TArray<FName> CrewHeads;
		TArray<FName> HideHair;
	};

	/** Live tuning (airsoft.gear.tune): Offset / Rotation / Scale per anchor key. */
	static TMap<FName, FGearAnchor> GOverrides;
	static bool GShowGear = true;
	static int32 GSeedOffset = 0;

	static FVector ReadVector(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, const FVector& Default)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (Obj.IsValid() && Obj->TryGetArrayField(Field, Arr) && Arr && Arr->Num() >= 3)
		{
			return FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		}
		return Default;
	}

	static FLinearColor ReadColor(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, const FLinearColor& Default)
	{
		const FVector V = ReadVector(Obj, Field, FVector(Default.R, Default.G, Default.B));
		return FLinearColor(static_cast<float>(V.X), static_cast<float>(V.Y), static_cast<float>(V.Z), 1.f);
	}

	static float ReadFloat(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, float Default)
	{
		double Value = 0.0;
		return Obj.IsValid() && Obj->TryGetNumberField(Field, Value) ? static_cast<float>(Value) : Default;
	}

	static FName ReadName(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field)
	{
		FString Value;
		return Obj.IsValid() && Obj->TryGetStringField(Field, Value) && !Value.IsEmpty() ? FName(*Value) : FName();
	}

	static FGearAnchor ReadAnchor(const TSharedPtr<FJsonObject>& Obj)
	{
		FGearAnchor A;
		A.Bone = ReadName(Obj, TEXT("Bone"));
		if (A.Bone.IsNone())
		{
			return A;
		}
		A.AlignBone = ReadName(Obj, TEXT("AlignBone"));
		A.ModelDir = ReadVector(Obj, TEXT("ModelDir"), FVector::ZeroVector);
		A.Offset = ReadVector(Obj, TEXT("Offset"), FVector::ZeroVector);
		const FVector Rot = ReadVector(Obj, TEXT("Rotation"), FVector::ZeroVector); // [Pitch, Yaw, Roll]
		A.Rotation = FRotator(Rot.X, Rot.Y, Rot.Z);
		A.Scale = FMath::Max(0.05f, ReadFloat(Obj, TEXT("Scale"), 1.f));
		const TArray<TSharedPtr<FJsonValue>>* Assumed = nullptr;
		A.bHasAssumed = Obj->TryGetArrayField(TEXT("AssumedBonePos"), Assumed);
		A.AssumedBonePos = ReadVector(Obj, TEXT("AssumedBonePos"), FVector::ZeroVector);
		A.bValid = true;
		return A;
	}

	static void AddDefaults(FGearDatabase& Db)
	{
		if (Db.Slots.Num() == 0)
		{
			auto Slot = [&Db](const TCHAR* Name, float Chance, std::initializer_list<FGearOption> Options)
			{
				FGearSlot S;
				S.Slot = FName(Name);
				S.Chance = Chance;
				S.Options = TArray<FGearOption>(Options);
				Db.Slots.Add(S);
			};
			Slot(TEXT("Torso"), 1.f, { { FName(TEXT("PlateCarrier")), 1.f } });
			Slot(TEXT("Head"), 1.f, { { FName(TEXT("Helmet")), 0.6f }, { FName(TEXT("SoftCap")), 0.4f } });
			Slot(TEXT("Eyes"), 1.f, { { FName(TEXT("Goggles")), 1.f } });
			Slot(TEXT("Face"), 1.f, { { FName(TEXT("FaceMask")), 1.f } });
			Slot(TEXT("Arm"), 1.f, { { FName(TEXT("Armband")), 1.f } });
			Slot(TEXT("Knees"), 0.55f, { { FName(TEXT("KneePads")), 1.f } });
		}
		if (Db.SuitAssets.Num() == 0)
		{
			Db.SuitAssets = { FName(TEXT("Suit")), FName(TEXT("HairSlick")) };
		}
		if (Db.MultiplayerSuits.Num() == 0)
		{
			Db.MultiplayerSuits = { FName(TEXT("Charcoal")), FName(TEXT("MidnightNavy")), FName(TEXT("Black")) };
		}
		auto SuitDefault = [&Db](const TCHAR* Group, std::initializer_list<FSuitColor> Colors)
		{
			if (!Db.SuitColorways.Contains(FName(Group)))
			{
				Db.SuitColorways.Add(FName(Group), TArray<FSuitColor>(Colors));
			}
		};
		SuitDefault(TEXT("Suit"), { { FName(TEXT("Charcoal")), FLinearColor(0.047f, 0.047f, 0.051f), 1.f }, { FName(TEXT("MidnightNavy")), FLinearColor(0.016f, 0.021f, 0.047f), 1.f },
			{ FName(TEXT("Oxblood")), FLinearColor(0.074f, 0.013f, 0.017f), 1.f }, { FName(TEXT("Black")), FLinearColor(0.021f, 0.021f, 0.023f), 1.f } });
		SuitDefault(TEXT("Shirt"), { { FName(TEXT("Black")), FLinearColor(0.022f, 0.022f, 0.024f), 0.65f }, { FName(TEXT("White")), FLinearColor(1.f, 1.f, 0.97f), 0.35f } });
		SuitDefault(TEXT("Tie"), { { FName(TEXT("Black")), FLinearColor(0.016f, 0.016f, 0.017f), 0.6f }, { FName(TEXT("Graphite")), FLinearColor(0.032f, 0.032f, 0.035f), 0.25f },
			{ FName(TEXT("Wine")), FLinearColor(0.05f, 0.008f, 0.012f), 0.15f } });
		SuitDefault(TEXT("Hair"), { { FName(TEXT("Black")), FLinearColor(0.013f, 0.011f, 0.01f), 0.4f }, { FName(TEXT("DarkBrown")), FLinearColor(0.034f, 0.021f, 0.014f), 0.35f },
			{ FName(TEXT("Brown")), FLinearColor(0.075f, 0.046f, 0.028f), 0.15f }, { FName(TEXT("Grey")), FLinearColor(0.17f, 0.17f, 0.17f), 0.1f } });
		if (Db.Colorways.Num() == 0)
		{
			auto Add = [&Db](const TCHAR* Group, const TCHAR* Name, const FLinearColor& P, const FLinearColor& S)
			{
				FGearColorway C;
				C.Name = FName(Name);
				C.Primary = P;
				C.Secondary = S;
				Db.Colorways.FindOrAdd(FName(Group)).Add(C);
			};
			const FLinearColor Black(0.034f, 0.034f, 0.037f), Charcoal(0.08f, 0.08f, 0.084f), Ranger(0.096f, 0.106f, 0.066f);
			const FLinearColor BlackS(0.03f, 0.03f, 0.033f), CharcoalS(0.042f, 0.042f, 0.045f), RangerS(0.06f, 0.066f, 0.044f);
			for (const TCHAR* Group : { TEXT("Kit"), TEXT("Helmet"), TEXT("Cap") })
			{
				Add(Group, TEXT("Black"), Black, BlackS);
				Add(Group, TEXT("Charcoal"), Charcoal, CharcoalS);
				Add(Group, TEXT("RangerGreen"), Ranger, RangerS);
			}
		}
	}

	static TSharedPtr<FJsonObject> LoadJson(const FString& Path)
	{
		FString Text;
		TSharedPtr<FJsonObject> Root;
		if (FFileHelper::LoadFileToString(Text, *Path))
		{
			TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
			FJsonSerializer::Deserialize(Reader, Root);
		}
		return Root;
	}

	/** Reads every "Assets" entry (team gear or an outfit such as the suit or a character head) into Db. */
	static void ParseAssets(const TSharedPtr<FJsonObject>& Root, FGearDatabase& Db)
	{
		const TSharedPtr<FJsonObject>* Assets = nullptr;
		if (Root->TryGetObjectField(TEXT("Assets"), Assets))
		{
			for (const auto& Pair : (*Assets)->Values)
			{
				const TSharedPtr<FJsonObject>* AssetObj = nullptr;
				const TSharedPtr<FJsonObject>* TeamGear = nullptr;
				const TSharedPtr<FJsonObject>* OutfitObj = nullptr;
				if (!Pair.Value.IsValid() || !Pair.Value->TryGetObject(AssetObj))
				{
					continue;
				}
				const bool bOutfit = !(*AssetObj)->TryGetObjectField(TEXT("TeamGear"), TeamGear) && (*AssetObj)->TryGetObjectField(TEXT("Outfit"), OutfitObj);
				if (bOutfit)
				{
					TeamGear = OutfitObj; // same tint fields
				}
				else if (!TeamGear)
				{
					continue; // neither team gear nor an outfit (e.g. the first-person gloves)
				}
				FGearAssetDef Def;
				Def.Id = FName(*Pair.Key);
				if (bOutfit)
				{
					Def.Outfit = ReadName(*OutfitObj, TEXT("Outfit"));
					Def.SuitTint = ReadName(*OutfitObj, TEXT("Tint"));
					if (Def.Outfit.IsNone())
					{
						Def.Outfit = FName(TEXT("Suit"));
					}
				}
				const TSharedPtr<FJsonObject>* AnchorObj = nullptr;
				if ((*AssetObj)->TryGetObjectField(TEXT("Anchor"), AnchorObj))
				{
					Def.Anchor = ReadAnchor(*AnchorObj);
				}
				Def.Colorway = ReadName(*TeamGear, TEXT("Colorway"));
				Def.TintRoughness = ReadFloat(*TeamGear, TEXT("TintRoughness"), 0.5f);
				Def.RoughnessDetail = ReadFloat(*TeamGear, TEXT("RoughnessDetail"), 1.f);
				Def.TintMetallic = ReadFloat(*TeamGear, TEXT("TintMetallic"), 0.f);
				const TSharedPtr<FJsonObject>* Glass = nullptr;
				if ((*TeamGear)->TryGetObjectField(TEXT("Glass"), Glass))
				{
					Def.bHasGlass = true;
					Def.GlassTint = ReadColor(*Glass, TEXT("Tint"), Def.GlassTint);
					Def.GlassOpacity = ReadFloat(*Glass, TEXT("Opacity"), Def.GlassOpacity);
					Def.GlassRoughness = ReadFloat(*Glass, TEXT("Roughness"), Def.GlassRoughness);
				}
				const TArray<TSharedPtr<FJsonValue>>* Pieces = nullptr;
				if ((*AssetObj)->TryGetArrayField(TEXT("Pieces"), Pieces))
				{
					for (const TSharedPtr<FJsonValue>& PieceValue : *Pieces)
					{
						const TSharedPtr<FJsonObject>* PieceObj = nullptr;
						if (!PieceValue.IsValid() || !PieceValue->TryGetObject(PieceObj))
						{
							continue;
						}
						FGearPieceDef Piece;
						Piece.Name = ReadName(*PieceObj, TEXT("Name"));
						Piece.Kind = ReadName(*PieceObj, TEXT("Kind"));
						const TSharedPtr<FJsonObject>* PieceAnchor = nullptr;
						if ((*PieceObj)->TryGetObjectField(TEXT("Anchor"), PieceAnchor))
						{
							Piece.Anchor = ReadAnchor(*PieceAnchor);
							Piece.bOwnAnchor = Piece.Anchor.bValid;
						}
						if (!Piece.Name.IsNone())
						{
							Def.Pieces.Add(Piece);
						}
					}
				}
				Db.Assets.Add(Def.Id, Def);
			}
		}
	}

	static void ReadNameArray(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, TArray<FName>& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
		if (Obj.IsValid() && Obj->TryGetArrayField(Field, List))
		{
			for (const TSharedPtr<FJsonValue>& V : *List)
			{
				FString Name;
				if (V.IsValid() && V->TryGetString(Name) && !Name.IsEmpty())
				{
					Out.AddUnique(FName(*Name));
				}
			}
		}
	}

	static FGearDatabase& GearDatabase(bool bReload = false)
	{
		static FGearDatabase Db;
		static bool bLoaded = false;
		if (bLoaded && !bReload)
		{
			return Db;
		}
		bLoaded = true;
		Db = FGearDatabase();

		const FString Path = FPaths::ProjectContentDir() / TEXT("Airsoft/Data/Gear.json");
		const TSharedPtr<FJsonObject> Root = LoadJson(Path);
		if (Root.IsValid())
		{
			ParseAssets(Root, Db);

			const TSharedPtr<FJsonObject>* TeamGear = nullptr;
			if (Root->TryGetObjectField(TEXT("TeamGear"), TeamGear))
			{
				Db.FallbackHeadCenter = ReadVector(*TeamGear, TEXT("FallbackHeadCenter"), Db.FallbackHeadCenter);
				const TSharedPtr<FJsonObject>* Colorways = nullptr;
				if ((*TeamGear)->TryGetObjectField(TEXT("Colorways"), Colorways))
				{
					for (const auto& Group : (*Colorways)->Values)
					{
						const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
						if (!Group.Value.IsValid() || !Group.Value->TryGetArray(List))
						{
							continue;
						}
						TArray<FGearColorway>& Out = Db.Colorways.FindOrAdd(FName(*Group.Key));
						for (const TSharedPtr<FJsonValue>& Entry : *List)
						{
							const TSharedPtr<FJsonObject>* Obj = nullptr;
							if (Entry.IsValid() && Entry->TryGetObject(Obj))
							{
								FGearColorway C;
								C.Name = ReadName(*Obj, TEXT("Name"));
								C.Primary = ReadColor(*Obj, TEXT("Primary"), FLinearColor(0.04f, 0.04f, 0.043f));
								C.Secondary = ReadColor(*Obj, TEXT("Secondary"), C.Primary);
								Out.Add(C);
							}
						}
					}
				}
				const TArray<TSharedPtr<FJsonValue>>* Slots = nullptr;
				if ((*TeamGear)->TryGetArrayField(TEXT("Slots"), Slots))
				{
					for (const TSharedPtr<FJsonValue>& SlotValue : *Slots)
					{
						const TSharedPtr<FJsonObject>* SlotObj = nullptr;
						if (!SlotValue.IsValid() || !SlotValue->TryGetObject(SlotObj))
						{
							continue;
						}
						FGearSlot S;
						S.Slot = ReadName(*SlotObj, TEXT("Slot"));
						S.Chance = FMath::Clamp(ReadFloat(*SlotObj, TEXT("Chance"), 1.f), 0.f, 1.f);
						const TArray<TSharedPtr<FJsonValue>>* Options = nullptr;
						if ((*SlotObj)->TryGetArrayField(TEXT("Options"), Options))
						{
							for (const TSharedPtr<FJsonValue>& OptionValue : *Options)
							{
								const TSharedPtr<FJsonObject>* OptionObj = nullptr;
								if (OptionValue.IsValid() && OptionValue->TryGetObject(OptionObj))
								{
									FGearOption O;
									O.Asset = ReadName(*OptionObj, TEXT("Asset"));
									O.Weight = ReadFloat(*OptionObj, TEXT("Weight"), 1.f);
									if (!O.Asset.IsNone())
									{
										S.Options.Add(O);
									}
								}
							}
						}
						if (!S.Slot.IsNone() && S.Options.Num() > 0)
						{
							Db.Slots.Add(S);
						}
					}
				}
			}
		}
		const TSharedPtr<FJsonObject>* SuitObj = nullptr;
		if (Root.IsValid() && Root->TryGetObjectField(TEXT("Suit"), SuitObj))
		{
			const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
			if ((*SuitObj)->TryGetArrayField(TEXT("Assets"), List))
			{
				for (const TSharedPtr<FJsonValue>& V : *List)
				{
					FString Name;
					if (V.IsValid() && V->TryGetString(Name) && !Name.IsEmpty())
					{
						Db.SuitAssets.Add(FName(*Name));
					}
				}
			}
			if ((*SuitObj)->TryGetArrayField(TEXT("MultiplayerSuits"), List))
			{
				for (const TSharedPtr<FJsonValue>& V : *List)
				{
					FString Name;
					if (V.IsValid() && V->TryGetString(Name) && !Name.IsEmpty())
					{
						Db.MultiplayerSuits.Add(FName(*Name));
					}
				}
			}
			const TSharedPtr<FJsonObject>* Groups = nullptr;
			if ((*SuitObj)->TryGetObjectField(TEXT("Colorways"), Groups))
			{
				for (const auto& Group : (*Groups)->Values)
				{
					const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
					if (!Group.Value.IsValid() || !Group.Value->TryGetArray(Entries))
					{
						continue;
					}
					TArray<FSuitColor>& Out = Db.SuitColorways.FindOrAdd(FName(*Group.Key));
					for (const TSharedPtr<FJsonValue>& Entry : *Entries)
					{
						const TSharedPtr<FJsonObject>* Obj = nullptr;
						if (Entry.IsValid() && Entry->TryGetObject(Obj))
						{
							FSuitColor C;
							C.Name = ReadName(*Obj, TEXT("Name"));
							C.Color = ReadColor(*Obj, TEXT("Primary"), FLinearColor(0.04f, 0.04f, 0.043f));
							C.Weight = FMath::Max(0.f, ReadFloat(*Obj, TEXT("Weight"), 1.f));
							Out.Add(C);
						}
					}
				}
			}
		}
		// Character heads (Tools/Blender/heads/build_heads.py): their own file, same asset format.
		const TSharedPtr<FJsonObject> HeadsRoot = LoadJson(FPaths::ProjectContentDir() / TEXT("Airsoft/Data/GearHeads.json"));
		if (HeadsRoot.IsValid())
		{
			ParseAssets(HeadsRoot, Db);
			const TSharedPtr<FJsonObject>* HeadsObj = nullptr;
			if (HeadsRoot->TryGetObjectField(TEXT("Heads"), HeadsObj))
			{
				const TSharedPtr<FJsonObject>* CastObj = nullptr;
				if ((*HeadsObj)->TryGetObjectField(TEXT("Cast"), CastObj))
				{
					for (const auto& Pair : (*CastObj)->Values)
					{
						FString Asset;
						if (Pair.Value.IsValid() && Pair.Value->TryGetString(Asset) && !Asset.IsEmpty())
						{
							Db.HeadCast.Add(FName(*Pair.Key), FName(*Asset));
						}
					}
				}
				ReadNameArray(*HeadsObj, TEXT("Crew"), Db.CrewHeads);
				ReadNameArray(*HeadsObj, TEXT("HideHair"), Db.HideHair);
			}
		}
		AddDefaults(Db);
		UE_LOG(LogAirsoftGear, Log, TEXT("Team gear: %d assets, %d slots, %d suit assets, %d character heads from %s"), Db.Assets.Num(), Db.Slots.Num(),
			Db.SuitAssets.Num(), Db.HeadCast.Num() + Db.CrewHeads.Num(), *Path);
		return Db;
	}

	static const FGearPieceDef* FindPiece(const FGearAssetDef& Def, FName Piece)
	{
		for (const FGearPieceDef& P : Def.Pieces)
		{
			if (P.Name == Piece)
			{
				return &P;
			}
		}
		return nullptr;
	}

	/** The anchor in effect: Gear.json, with any live tuning on top. */
	static FGearAnchor ResolveAnchor(FName AssetId, FName Piece, FName Key)
	{
		FGearAnchor A;
		const FGearAssetDef* Def = GearDatabase().Assets.Find(AssetId);
		if (!Def)
		{
			return A;
		}
		const FGearPieceDef* P = FindPiece(*Def, Piece);
		A = (P && P->bOwnAnchor) ? P->Anchor : Def->Anchor;
		if (const FGearAnchor* Tuned = GOverrides.Find(Key))
		{
			A.Offset = Tuned->Offset;
			A.Rotation = Tuned->Rotation;
			A.Scale = Tuned->Scale;
		}
		return A;
	}

	/** Deterministic on every machine (string CRC, not FName hashes). */
	static uint32 GearHash(int32 Seed, const FString& Salt)
	{
		uint32 H = FCrc::StrCrc32(*Salt) ^ (static_cast<uint32>(Seed) * 0x9E3779B1u);
		H ^= H >> 16;
		H *= 0x7FEB352Du;
		H ^= H >> 15;
		H *= 0x846CA68Bu;
		H ^= H >> 16;
		return H;
	}

	static float GearUnit(int32 Seed, const FString& Salt)
	{
		return static_cast<float>(GearHash(Seed, Salt) & 0xFFFFFFu) / 16777216.f;
	}

	static FName PickOption(const FGearSlot& S, int32 Seed)
	{
		float Total = 0.f;
		for (const FGearOption& O : S.Options)
		{
			Total += FMath::Max(O.Weight, 0.f);
		}
		if (Total <= 0.f)
		{
			return NAME_None;
		}
		float R = GearUnit(Seed, S.Slot.ToString() + TEXT("/Pick")) * Total;
		FName Last = NAME_None;
		for (const FGearOption& O : S.Options)
		{
			if (O.Weight <= 0.f)
			{
				continue;
			}
			Last = O.Asset;
			if (R < O.Weight)
			{
				return O.Asset;
			}
			R -= O.Weight;
		}
		return Last;
	}

	/** A suit colourway by name (nullptr when the group or name is unknown). */
	static const FSuitColor* FindSuitColor(FName Group, FName Name)
	{
		if (const TArray<FSuitColor>* List = GearDatabase().SuitColorways.Find(Group))
		{
			for (const FSuitColor& C : *List)
			{
				if (C.Name == Name)
				{
					return &C;
				}
			}
		}
		return nullptr;
	}

	/** Weighted pick from a suit colourway group, hashed from the seed. */
	static FLinearColor PickSuitColor(FName Group, int32 Seed, const FLinearColor& Default)
	{
		const TArray<FSuitColor>* List = GearDatabase().SuitColorways.Find(Group);
		if (!List || List->Num() == 0)
		{
			return Default;
		}
		float Total = 0.f;
		for (const FSuitColor& C : *List)
		{
			Total += C.Weight;
		}
		if (Total <= 0.f)
		{
			return (*List)[0].Color;
		}
		float R = GearUnit(Seed, TEXT("Suit/") + Group.ToString()) * Total;
		for (const FSuitColor& C : *List)
		{
			if (R < C.Weight)
			{
				return C.Color;
			}
			R -= C.Weight;
		}
		return List->Last().Color;
	}

	/** Component-space transform of a bone in the reference pose. */
	static FTransform RefPoseComponentSpace(const FReferenceSkeleton& Ref, int32 BoneIndex)
	{
		const TArray<FTransform>& Pose = Ref.GetRefBonePose();
		FTransform Result = FTransform::Identity;
		int32 Index = BoneIndex;
		int32 Guard = 0;
		while (Index != INDEX_NONE && Pose.IsValidIndex(Index) && Guard++ < 1024)
		{
			Result = Result * Pose[Index]; // child * parent
			Index = Ref.GetParentIndex(Index);
		}
		return Result;
	}

	static FQuat GearFacing()
	{
		return FRotator(0.f, UAirsoftGearSettings::Get()->MeshFacingYaw, 0.f).Quaternion();
	}

	static void WarnOnce(const FString& Key, const FString& Message)
	{
		static TSet<FString> Warned;
		if (!Warned.Contains(Key))
		{
			Warned.Add(Key);
			UE_LOG(LogAirsoftGear, Warning, TEXT("%s"), *Message);
		}
	}

	template <typename FuncType>
	static void ForEachGear(FuncType Func)
	{
		for (TObjectIterator<UAirsoftTeamGearComponent> It; It; ++It)
		{
			if (!It->IsTemplate() && It->GetWorld())
			{
				Func(**It);
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

UAirsoftTeamGearComponent::UAirsoftTeamGearComponent()
{
	// Only polls whether the owner is looking through this body (cheap, 10 Hz).
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickInterval = 0.1f;
}

bool UAirsoftTeamGearComponent::IsOwnerViewing() const
{
	if (!UAirsoftGearSettings::Get()->bHideFromOwnerView)
	{
		return false;
	}
	const APawn* Pawn = Cast<APawn>(GetOwner());
	if (!Pawn || !Pawn->IsLocallyControlled())
	{
		return false;
	}
	// Bots are locally controlled on the server too, but never by a PlayerController.
	const APlayerController* PC = Cast<APlayerController>(Pawn->GetController());
	if (const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(Pawn); C && C->IsThirdPersonView())
	{
		return false; // third-person camera: the owner sees their own gear / suit
	}
	return PC && PC->GetViewTarget() == Pawn;
}

void UAirsoftTeamGearComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (Components.Num() > 0)
	{
		const bool bHide = IsOwnerViewing();
		if (bHide != bOwnerViewHidden)
		{
			bOwnerViewHidden = bHide;
			RefreshVisibility();
		}
	}
}

void UAirsoftTeamGearComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	using namespace AirsoftTeamGear;
	Clear();
	Super::EndPlay(EndPlayReason);
}

bool UAirsoftTeamGearComponent::ApplyTo(USkinnedMeshComponent* Body, EAirsoftTeam Team, int32 VariantSeed)
{
	using namespace AirsoftTeamGear;
	if (!Body)
	{
		Clear();
		return false;
	}
	UObject* Asset = Body->GetSkinnedAsset();
	if (bApplied && !bFallback && !bSuit && Parent.Get() == Body && ParentAsset.Get() == Asset && AppliedSeed == VariantSeed)
	{
		if (Team != AppliedTeam)
		{
			SetTeam(Team);
		}
		return HasGear();
	}
	return Build(Body, false, Team, VariantSeed);
}

bool UAirsoftTeamGearComponent::ApplyToFallbackHead(USceneComponent* Head, EAirsoftTeam Team, int32 VariantSeed)
{
	using namespace AirsoftTeamGear;
	if (!Head)
	{
		Clear();
		return false;
	}
	if (bApplied && bFallback && !bSuit && Parent.Get() == Head && AppliedSeed == VariantSeed)
	{
		if (Team != AppliedTeam)
		{
			SetTeam(Team);
		}
		return HasGear();
	}
	return Build(Head, true, Team, VariantSeed);
}

void UAirsoftTeamGearComponent::Clear()
{
	using namespace AirsoftTeamGear;
	for (UStaticMeshComponent* Comp : Components)
	{
		if (Comp)
		{
			Comp->DestroyComponent();
		}
	}
	Components.Reset();
	Parts.Reset();
	Parent.Reset();
	ParentAsset.Reset();
	bApplied = false;
	bSuit = false;
	bHeadOnly = false;
	AppliedHead = NAME_None;
}

bool UAirsoftTeamGearComponent::Build(USceneComponent* InParent, bool bInFallback, EAirsoftTeam Team, int32 VariantSeed)
{
	using namespace AirsoftTeamGear;
	Clear();
	const UAirsoftGearSettings* Settings = UAirsoftGearSettings::Get();
	AActor* Owner = GetOwner();
	if (!InParent || !Owner || !Settings->bEnableTeamGear || (bInFallback && !Settings->bGearOnFallbackBody) || GetNetMode() == NM_DedicatedServer)
	{
		return false;
	}
	USkinnedMeshComponent* Skinned = bInFallback ? nullptr : Cast<USkinnedMeshComponent>(InParent);
	if (!bInFallback && (!Skinned || !Skinned->GetSkinnedAsset()))
	{
		return false;
	}
	Parent = InParent;
	ParentAsset = Skinned ? Skinned->GetSkinnedAsset() : nullptr;
	bFallback = bInFallback;
	bSuit = false;
	AppliedSeed = VariantSeed;
	AppliedTeam = Team;
	bApplied = true;

	bOwnerViewHidden = IsOwnerViewing();
	static const FName NameHead(TEXT("Head")), NameEyes(TEXT("Eyes")), NameFace(TEXT("Face"));
	const FGearDatabase& Db = GearDatabase();
	const int32 Seed = VariantSeed + GSeedOffset;
	for (const FGearSlot& Slot : Db.Slots)
	{
		if (bInFallback && !(Slot.Slot == NameHead || Slot.Slot == NameEyes || Slot.Slot == NameFace))
		{
			continue;
		}
		if (Slot.Chance < 1.f && GearUnit(Seed, Slot.Slot.ToString() + TEXT("/Chance")) >= Slot.Chance)
		{
			continue;
		}
		const FName AssetId = PickOption(Slot, Seed);
		const FGearAssetDef* Def = Db.Assets.Find(AssetId);
		if (!Def)
		{
			continue;
		}
		FLinearColor Primary(0.04f, 0.04f, 0.043f), Secondary(0.04f, 0.04f, 0.043f);
		if (const TArray<FGearColorway>* List = Db.Colorways.Find(Def->Colorway))
		{
			if (List->Num() > 0)
			{
				const int32 Index = static_cast<int32>(GearHash(Seed, TEXT("Colorway/") + Def->Colorway.ToString()) % static_cast<uint32>(List->Num()));
				const FGearColorway& C = (*List)[Index];
				Primary = C.Primary;
				Secondary = C.Secondary;
			}
		}
		for (const FGearPieceDef& PieceDef : Def->Pieces)
		{
			UStaticMesh* Mesh = AirsoftAssets::FindMesh(TEXT("Gear"), AssetId, PieceDef.Name.ToString());
			if (!Mesh)
			{
				continue; // not imported yet: the game works without the art
			}
			FPart Part;
			Part.AssetId = AssetId;
			Part.Piece = PieceDef.Name;
			Part.Kind = PieceDef.Kind;
			Part.Slot = Slot.Slot;
			Part.AnchorKey = PieceDef.bOwnAnchor ? FName(*FString::Printf(TEXT("%s/%s"), *AssetId.ToString(), *PieceDef.Name.ToString())) : AssetId;
			Part.Bone = bInFallback ? FName() : (PieceDef.bOwnAnchor ? PieceDef.Anchor.Bone : Def->Anchor.Bone);
			Part.Primary = Primary;
			Part.Secondary = Secondary;

			AddPart(Part, Mesh, InParent, bInFallback, Team);
		}
	}
	return Components.Num() > 0;
}

bool UAirsoftTeamGearComponent::AddPart(const FPart& Part, UStaticMesh* Mesh, USceneComponent* InParent, bool bInFallback, EAirsoftTeam Team)
{
	using namespace AirsoftTeamGear;
	const UAirsoftGearSettings* Settings = UAirsoftGearSettings::Get();
	AActor* Owner = GetOwner();
	if (!Mesh || !InParent || !Owner)
	{
		return false;
	}
	// Components must stay named TeamGear_*: AAirsoftCharacter finds them by that prefix for its third-person camera.
	FTransform Relative;
	if (!ComputeRelative(Part, Relative))
	{
		return false;
	}
	const FName CompName = MakeUniqueObjectName(Owner, UStaticMeshComponent::StaticClass(), FName(*FString::Printf(TEXT("TeamGear_%s_%s"), *Part.AssetId.ToString(), *Part.Piece.ToString())));
	UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(Owner, CompName);
	Comp->SetStaticMesh(Mesh);
	Comp->SetupAttachment(InParent, Part.Bone);
	if (bInFallback)
	{
		Comp->SetUsingAbsoluteScale(true);
	}
	Comp->SetRelativeTransform(Relative);
	Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Comp->SetGenerateOverlapEvents(false);
	Comp->SetCanEverAffectNavigation(false);
	Comp->bReceivesDecals = false;
	Comp->SetOwnerNoSee(true); // the owner sees first-person arms instead
	const bool bGlass = Part.Kind == TEXT("Glass");
	Comp->SetCastShadow(Settings->bCastShadows && !bGlass);
	Comp->bCastHiddenShadow = Settings->bOwnerSeesShadow && !bGlass;
	if (bGlass && Settings->GlassCullDistance > 0.f)
	{
		Comp->SetCullDistance(Settings->GlassCullDistance);
	}
	Comp->SetVisibility(bWantVisible && GShowGear && !bOwnerViewHidden);
	Comp->RegisterComponent();
	ApplyMaterials(Comp, Part, Team);
	Components.Add(Comp);
	Parts.Add(Part); // parallel to Components
	return true;
}

bool UAirsoftTeamGearComponent::ApplySuit(USkinnedMeshComponent* Body, FLinearColor InSuitColor, int32 VariantSeed, FName Shirt)
{
	if (!Body)
	{
		Clear();
		return false;
	}
	if (bApplied && bSuit && !bSuitTeamTie && Parent.Get() == Body && ParentAsset.Get() == Body->GetSkinnedAsset() && AppliedSeed == VariantSeed
		&& AppliedShirt == Shirt && AppliedSuitColor.Equals(InSuitColor, 1e-4f))
	{
		return HasGear();
	}
	return BuildSuit(Body, InSuitColor, VariantSeed, Shirt, false, AppliedTeam);
}

FName UAirsoftTeamGearComponent::HeadFor(FName Character, int32 VariantSeed)
{
	using namespace AirsoftTeamGear;
	const FGearDatabase& Db = GearDatabase();
	if (!Character.IsNone())
	{
		if (const FName* Found = Db.HeadCast.Find(Character))
		{
			return *Found;
		}
		// Bosses go by "Name, the Title" in Campaign.json; the head list uses the name.
		FString Name = Character.ToString();
		int32 Comma = INDEX_NONE;
		if (Name.FindChar(TEXT(','), Comma))
		{
			Name.LeftInline(Comma);
			Name.TrimStartAndEndInline();
			if (const FName* Found = Db.HeadCast.Find(FName(*Name)))
			{
				return *Found;
			}
		}
		return NAME_None;
	}
	if (Db.CrewHeads.Num() == 0)
	{
		return NAME_None;
	}
	return Db.CrewHeads[static_cast<int32>(GearHash(VariantSeed + GSeedOffset, TEXT("Head/Crew")) % static_cast<uint32>(Db.CrewHeads.Num()))];
}

bool UAirsoftTeamGearComponent::ApplyHead(USkinnedMeshComponent* Body, FName Character, int32 VariantSeed)
{
	using namespace AirsoftTeamGear;
	static const FName SlotHead(TEXT("Head"));
	if (!Body || !Body->GetSkinnedAsset() || !GetOwner() || !UAirsoftGearSettings::Get()->bEnableSuit || GetNetMode() == NM_DedicatedServer)
	{
		return false;
	}
	const FName AssetId = HeadFor(Character, VariantSeed);
	const FGearDatabase& Db = GearDatabase();
	const FGearAssetDef* Def = AssetId.IsNone() ? nullptr : Db.Assets.Find(AssetId);
	if (!Def)
	{
		return false;
	}
	if (bApplied && Parent.Get() == Body && ParentAsset.Get() == Body->GetSkinnedAsset() && AppliedHead == AssetId && HasHead())
	{
		return true; // already wearing it
	}
	// Meshes first: when the head isn't imported nothing changes (the suit keeps its own haircut).
	TArray<TPair<const FGearPieceDef*, UStaticMesh*>> Meshes;
	for (const FGearPieceDef& PieceDef : Def->Pieces)
	{
		if (UStaticMesh* Mesh = AirsoftAssets::FindMesh(TEXT("Gear"), AssetId, PieceDef.Name.ToString()))
		{
			Meshes.Emplace(&PieceDef, Mesh);
		}
	}
	if (Meshes.Num() == 0)
	{
		WarnOnce(TEXT("head/") + AssetId.ToString(), FString::Printf(TEXT("Character head %s is not imported - the suit's haircut stays"), *AssetId.ToString()));
		return false;
	}
	if (!bApplied || Parent.Get() != Body || ParentAsset.Get() != Body->GetSkinnedAsset())
	{
		Clear();
		Parent = Body;
		ParentAsset = Body->GetSkinnedAsset();
		bFallback = false;
		bSuit = false;
		bApplied = true;
		bHeadOnly = true;
		AppliedSeed = VariantSeed;
		bOwnerViewHidden = IsOwnerViewing();
	}
	// Drop the previous head and the suit's haircut (the head brings its own hair).
	for (int32 i = Components.Num() - 1; i >= 0; --i)
	{
		const bool bDrop = Parts.IsValidIndex(i) && (Parts[i].Slot == SlotHead || Db.HideHair.Contains(Parts[i].AssetId));
		if (bDrop)
		{
			if (Components[i])
			{
				Components[i]->DestroyComponent();
			}
			Components.RemoveAt(i);
			Parts.RemoveAt(i);
		}
	}
	for (const TPair<const FGearPieceDef*, UStaticMesh*>& Pair : Meshes)
	{
		const FGearPieceDef& PieceDef = *Pair.Key;
		FPart Part;
		Part.AssetId = AssetId;
		Part.Piece = PieceDef.Name;
		Part.Kind = PieceDef.Kind;
		Part.Slot = SlotHead;
		Part.AnchorKey = PieceDef.bOwnAnchor ? FName(*FString::Printf(TEXT("%s/%s"), *AssetId.ToString(), *PieceDef.Name.ToString())) : AssetId;
		Part.Bone = PieceDef.bOwnAnchor ? PieceDef.Anchor.Bone : Def->Anchor.Bone;
		Part.Primary = FLinearColor::White; // colours are baked (empty role mask)
		Part.Secondary = FLinearColor::White;
		Part.Accent = FLinearColor::White;
		Part.bTeamAccent = false;
		AddPart(Part, Pair.Value, Body, false, AppliedTeam);
	}
	AppliedHead = AssetId;
	AppliedHeadCharacter = Character;
	AppliedHeadSeed = VariantSeed;
	return HasHead();
}

bool UAirsoftTeamGearComponent::HasHead() const
{
	for (int32 i = 0; i < Parts.Num(); ++i)
	{
		if (Parts[i].Slot == TEXT("Head") && Components.IsValidIndex(i) && Components[i])
		{
			return true;
		}
	}
	return false;
}

bool UAirsoftTeamGearComponent::ApplyOutfit(USkinnedMeshComponent* Body, EAirsoftOutfit Outfit, EAirsoftTeam Team, int32 VariantSeed)
{
	using namespace AirsoftTeamGear;
	if (Outfit == EAirsoftOutfit::TeamGear)
	{
		return ApplyTo(Body, Team, VariantSeed);
	}
	if (!Body)
	{
		Clear();
		return false;
	}
	if (bApplied && bSuit && bSuitTeamTie && Parent.Get() == Body && ParentAsset.Get() == Body->GetSkinnedAsset() && AppliedSeed == VariantSeed)
	{
		if (Team != AppliedTeam)
		{
			SetTeam(Team);
		}
		return HasGear();
	}
	const TArray<FName>& Choices = GearDatabase().MultiplayerSuits;
	const FName Pick = Choices.Num() > 0 ? Choices[static_cast<int32>(GearHash(VariantSeed + GSeedOffset, TEXT("Suit/Multiplayer")) % static_cast<uint32>(Choices.Num()))] : FName(TEXT("Charcoal"));
	return BuildSuit(Body, SuitColor(Pick), VariantSeed, NAME_None, true, Team);
}

FLinearColor UAirsoftTeamGearComponent::SuitColor(FName Colorway)
{
	using namespace AirsoftTeamGear;
	if (const FSuitColor* C = FindSuitColor(FName(TEXT("Suit")), Colorway))
	{
		return C->Color;
	}
	if (const FSuitColor* C = FindSuitColor(FName(TEXT("Suit")), FName(TEXT("Charcoal"))))
	{
		return C->Color;
	}
	return FLinearColor(0.047f, 0.047f, 0.051f);
}

bool UAirsoftTeamGearComponent::BuildSuit(USkinnedMeshComponent* Body, FLinearColor InSuitColor, int32 VariantSeed, FName Shirt, bool bTeamTie, EAirsoftTeam Team)
{
	using namespace AirsoftTeamGear;
	Clear();
	const UAirsoftGearSettings* Settings = UAirsoftGearSettings::Get();
	if (!Body || !Body->GetSkinnedAsset() || !GetOwner() || !Settings->bEnableSuit || GetNetMode() == NM_DedicatedServer)
	{
		return false;
	}
	Parent = Body;
	ParentAsset = Body->GetSkinnedAsset();
	bFallback = false;
	bSuit = true;
	bSuitTeamTie = bTeamTie;
	AppliedSuitColor = InSuitColor;
	AppliedShirt = Shirt;
	AppliedSeed = VariantSeed;
	AppliedTeam = Team;
	bApplied = true;
	bOwnerViewHidden = IsOwnerViewing();

	const FGearDatabase& Db = GearDatabase();
	const int32 Seed = VariantSeed + GSeedOffset;
	static const FName GroupShirt(TEXT("Shirt")), GroupTie(TEXT("Tie")), GroupHair(TEXT("Hair")), TintHair(TEXT("Hair")), SlotSuit(TEXT("Suit"));
	const FSuitColor* Named = Shirt.IsNone() ? nullptr : FindSuitColor(GroupShirt, Shirt);
	const FLinearColor ShirtColor = Named ? Named->Color : PickSuitColor(GroupShirt, Seed, FLinearColor(0.022f, 0.022f, 0.024f));
	const FLinearColor TieColor = PickSuitColor(GroupTie, Seed, FLinearColor(0.016f, 0.016f, 0.017f));
	const FLinearColor HairColor = PickSuitColor(GroupHair, Seed, FLinearColor(0.013f, 0.011f, 0.01f));
	for (const FName AssetId : Db.SuitAssets)
	{
		const FGearAssetDef* Def = Db.Assets.Find(AssetId);
		if (!Def)
		{
			WarnOnce(TEXT("suit/") + AssetId.ToString(), FString::Printf(TEXT("Suit asset %s is not in Gear.json - skipped"), *AssetId.ToString()));
			continue;
		}
		const bool bHair = Def->SuitTint == TintHair;
		for (const FGearPieceDef& PieceDef : Def->Pieces)
		{
			UStaticMesh* Mesh = AirsoftAssets::FindMesh(TEXT("Gear"), AssetId, PieceDef.Name.ToString());
			if (!Mesh)
			{
				continue; // not imported yet: the caller keeps its fallback look
			}
			FPart Part;
			Part.AssetId = AssetId;
			Part.Piece = PieceDef.Name;
			Part.Kind = PieceDef.Kind;
			Part.Slot = SlotSuit;
			Part.AnchorKey = PieceDef.bOwnAnchor ? FName(*FString::Printf(TEXT("%s/%s"), *AssetId.ToString(), *PieceDef.Name.ToString())) : AssetId;
			Part.Bone = PieceDef.bOwnAnchor ? PieceDef.Anchor.Bone : Def->Anchor.Bone;
			Part.Primary = bHair ? HairColor : InSuitColor;
			Part.Secondary = bHair ? HairColor : ShirtColor;
			Part.Accent = bHair ? HairColor : TieColor;
			Part.bTeamAccent = bTeamTie && !bHair;
			AddPart(Part, Mesh, Body, false, Team);
		}
	}
	return Components.Num() > 0;
}

bool UAirsoftTeamGearComponent::ComputeRelative(const FPart& Part, FTransform& OutRelative) const
{
	using namespace AirsoftTeamGear;
	const UAirsoftGearSettings* Settings = UAirsoftGearSettings::Get();
	const FGearAnchor A = ResolveAnchor(Part.AssetId, Part.Piece, Part.AnchorKey);
	if (!A.bValid)
	{
		WarnOnce(Part.AssetId.ToString(), FString::Printf(TEXT("Team gear %s has no Anchor in Gear.json - skipped"), *Part.AssetId.ToString()));
		return false;
	}
	const FQuat UserRot = A.Rotation.Quaternion();

	if (bFallback)
	{
		// The pieces' origin is the head pivot; the stand-in sphere's centre stands for the cranium centre.
		// The sphere is scaled, so the pieces use absolute scale and their offset is divided by the parent's scale.
		const float S = A.Scale * Settings->FallbackHeadScale;
		const FVector Center = GearDatabase().FallbackHeadCenter;
		const FVector Loc = UserRot.RotateVector(-Center * S) + A.Offset;
		const USceneComponent* P = Parent.Get();
		const FVector PS = P ? P->GetComponentScale() : FVector::OneVector;
		const FVector Rel(Loc.X / FMath::Max(PS.X, 0.001), Loc.Y / FMath::Max(PS.Y, 0.001), Loc.Z / FMath::Max(PS.Z, 0.001));
		OutRelative = FTransform(UserRot, Rel, FVector(S));
		return true;
	}

	const USkinnedMeshComponent* Skinned = Cast<USkinnedMeshComponent>(Parent.Get());
	const USkinnedAsset* Asset = Skinned ? Skinned->GetSkinnedAsset() : nullptr;
	if (!Asset)
	{
		return false;
	}
	const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
	const int32 BoneIndex = Ref.FindBoneIndex(A.Bone);
	if (BoneIndex == INDEX_NONE)
	{
		WarnOnce(Part.AssetId.ToString() + A.Bone.ToString(), FString::Printf(TEXT("Team gear %s: bone '%s' not in %s - skipped"), *Part.AssetId.ToString(), *A.Bone.ToString(), *Asset->GetName()));
		return false;
	}
	const FTransform BoneCS = RefPoseComponentSpace(Ref, BoneIndex);
	const FQuat Face = GearFacing();

	// Limb pieces: turn the modelled bone direction onto the skeleton's (reference pose) direction.
	FQuat Align = FQuat::Identity;
	if (!A.AlignBone.IsNone() && !A.ModelDir.IsNearlyZero())
	{
		const int32 AlignIndex = Ref.FindBoneIndex(A.AlignBone);
		if (AlignIndex != INDEX_NONE)
		{
			const FVector DirK = RefPoseComponentSpace(Ref, AlignIndex).GetLocation() - BoneCS.GetLocation();
			const FVector DirC = Face.UnrotateVector(DirK).GetSafeNormal();
			const FVector Model = A.ModelDir.GetSafeNormal();
			const double CosAngle = FVector::DotProduct(Model, DirC);
			if (!DirC.IsNearlyZero() && CosAngle >= FMath::Cos(FMath::DegreesToRadians(static_cast<double>(Settings->MaxAlignAngle))))
			{
				Align = FQuat::FindBetweenNormals(Model, DirC);
			}
			else
			{
				WarnOnce(Part.AssetId.ToString() + TEXT("/align"), FString::Printf(TEXT("Team gear %s: %s->%s direction is far from the modelled one - alignment skipped"),
					*Part.AssetId.ToString(), *A.Bone.ToString(), *A.AlignBone.ToString()));
			}
		}
	}

	// Desired component-space pose: modelled in character space around the bone's reference-pose pivot,
	// turned into the mesh's facing. Attached to the bone, the relative transform is Desired * BoneCS^-1.
	const FTransform PieceC(UserRot * Align, A.Offset, FVector(A.Scale));
	const FTransform AnchorK(Face, BoneCS.GetLocation());
	const FTransform DesiredK = PieceC * AnchorK;
	OutRelative = DesiredK.GetRelativeTransform(BoneCS);
	return true;
}

void UAirsoftTeamGearComponent::ApplyMaterials(UStaticMeshComponent* Comp, const FPart& Part, EAirsoftTeam Team) const
{
	using namespace AirsoftTeamGear;
	if (!Comp)
	{
		return;
	}
	const FGearAssetDef* Def = GearDatabase().Assets.Find(Part.AssetId);
	const bool bGlass = Part.Kind == TEXT("Glass");
	for (int32 Slot = 0; Slot < Comp->GetNumMaterials(); ++Slot)
	{
		UMaterialInterface* Base = Comp->GetMaterial(Slot);
		if (!Base)
		{
			continue;
		}
		UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(Base);
		if (!MID)
		{
			MID = Comp->CreateDynamicMaterialInstance(Slot, Base);
		}
		if (!MID)
		{
			continue;
		}
		if (bGlass)
		{
			// M_Glass: smoked lens.
			if (Def && Def->bHasGlass)
			{
				MID->SetVectorParameterValue(TEXT("Tint"), Def->GlassTint);
				MID->SetScalarParameterValue(TEXT("Opacity"), Def->GlassOpacity);
				MID->SetScalarParameterValue(TEXT("Roughness"), Def->GlassRoughness);
			}
			continue;
		}
		// M_AirsoftPBR: Mask R = kit colourway, G = secondary, B = team colour (the suit: cloth, shirt, tie). TintRoughness 0.5 with
		// RoughnessDetail 1 keeps the baked fabric roughness inside the tinted areas.
		MID->SetVectorParameterValue(TEXT("PrimaryTint"), Part.Primary);
		MID->SetVectorParameterValue(TEXT("SecondaryTint"), Part.Secondary);
		const float TeamScale = Part.Slot == TEXT("Suit") ? UAirsoftGearSettings::Get()->SuitTeamTieScale : 1.f;
		MID->SetVectorParameterValue(TEXT("AccentTint"), Part.bTeamAccent ? AirsoftColors::Team(Team) * TeamScale : Part.Accent);
		MID->SetScalarParameterValue(TEXT("TintRoughness"), Def ? Def->TintRoughness : 0.5f);
		MID->SetScalarParameterValue(TEXT("RoughnessDetail"), Def ? Def->RoughnessDetail : 1.f);
		MID->SetScalarParameterValue(TEXT("TintMetallic"), Def ? Def->TintMetallic : 0.f);
	}
}

void UAirsoftTeamGearComponent::SetTeam(EAirsoftTeam Team)
{
	using namespace AirsoftTeamGear;
	AppliedTeam = Team;
	for (int32 i = 0; i < Components.Num(); ++i)
	{
		if (Components[i] && Parts.IsValidIndex(i))
		{
			ApplyMaterials(Components[i], Parts[i], Team);
		}
	}
}

void UAirsoftTeamGearComponent::SetGearVisible(bool bVisible)
{
	using namespace AirsoftTeamGear;
	bWantVisible = bVisible;
	RefreshVisibility();
}

void UAirsoftTeamGearComponent::RefreshVisibility()
{
	using namespace AirsoftTeamGear;
	for (UStaticMeshComponent* Comp : Components)
	{
		if (Comp)
		{
			Comp->SetVisibility(bWantVisible && GShowGear && !bOwnerViewHidden);
		}
	}
}

bool UAirsoftTeamGearComponent::HasArmband() const
{
	using namespace AirsoftTeamGear;
	for (int32 i = 0; i < Parts.Num(); ++i)
	{
		if (Parts[i].Slot == TEXT("Arm") && Components.IsValidIndex(i) && Components[i])
		{
			return true;
		}
	}
	return false;
}

void UAirsoftTeamGearComponent::Rebuild()
{
	using namespace AirsoftTeamGear;
	if (bApplied && Parent.IsValid())
	{
		USceneComponent* P = Parent.Get();
		const bool bWasFallback = bFallback;
		const int32 Seed = AppliedSeed;
		const EAirsoftTeam Team = AppliedTeam;
		const bool bHadHead = !AppliedHead.IsNone();
		const FName HeadCharacter = AppliedHeadCharacter;
		const int32 HeadSeed = AppliedHeadSeed;
		if (bHeadOnly)
		{
			Clear();
		}
		else if (bSuit)
		{
			BuildSuit(Cast<USkinnedMeshComponent>(P), AppliedSuitColor, Seed, AppliedShirt, bSuitTeamTie, Team);
		}
		else
		{
			Build(P, bWasFallback, Team, Seed);
		}
		if (bHadHead)
		{
			ApplyHead(Cast<USkinnedMeshComponent>(P), HeadCharacter, HeadSeed);
		}
	}
}

void UAirsoftTeamGearComponent::RefreshPlacement()
{
	using namespace AirsoftTeamGear;
	for (int32 i = 0; i < Components.Num(); ++i)
	{
		FTransform Relative;
		if (Components[i] && Parts.IsValidIndex(i) && ComputeRelative(Parts[i], Relative))
		{
			Components[i]->SetRelativeTransform(Relative);
		}
	}
}

void UAirsoftTeamGearComponent::LogBones() const
{
	using namespace AirsoftTeamGear;
	const USkinnedMeshComponent* Skinned = Cast<USkinnedMeshComponent>(Parent.Get());
	const USkinnedAsset* Asset = Skinned ? Skinned->GetSkinnedAsset() : nullptr;
	if (!Asset)
	{
		UE_LOG(LogAirsoftGear, Display, TEXT("%s: no skinned body (fallback head or nothing applied)"), *GetNameSafe(GetOwner()));
		return;
	}
	const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
	const FQuat Face = GearFacing();
	UE_LOG(LogAirsoftGear, Display, TEXT("%s reference pose, character space cm (X forward, Y right, Z up) - actual vs assumed by the gear generator:"), *Asset->GetName());
	TSet<FName> Seen;
	for (const auto& Pair : GearDatabase().Assets)
	{
		TArray<FGearAnchor> Anchors = { Pair.Value.Anchor };
		for (const FGearPieceDef& P : Pair.Value.Pieces)
		{
			if (P.bOwnAnchor)
			{
				Anchors.Add(P.Anchor);
			}
		}
		for (const FGearAnchor& A : Anchors)
		{
			for (const FName BoneName : { A.Bone, A.AlignBone })
			{
				if (BoneName.IsNone() || Seen.Contains(BoneName))
				{
					continue;
				}
				Seen.Add(BoneName);
				const int32 Index = Ref.FindBoneIndex(BoneName);
				if (Index == INDEX_NONE)
				{
					UE_LOG(LogAirsoftGear, Display, TEXT("  %-12s MISSING"), *BoneName.ToString());
					continue;
				}
				const FVector C = Face.UnrotateVector(RefPoseComponentSpace(Ref, Index).GetLocation());
				if (BoneName == A.Bone && A.bHasAssumed)
				{
					const FVector D = C - A.AssumedBonePos;
					UE_LOG(LogAirsoftGear, Display, TEXT("  %-12s (%6.1f, %6.1f, %6.1f)  assumed (%6.1f, %6.1f, %6.1f)  delta (%5.1f, %5.1f, %5.1f)"),
						*BoneName.ToString(), C.X, C.Y, C.Z, A.AssumedBonePos.X, A.AssumedBonePos.Y, A.AssumedBonePos.Z, D.X, D.Y, D.Z);
				}
				else
				{
					UE_LOG(LogAirsoftGear, Display, TEXT("  %-12s (%6.1f, %6.1f, %6.1f)"), *BoneName.ToString(), C.X, C.Y, C.Z);
				}
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Console commands (live tuning)
// ---------------------------------------------------------------------------

#if !UE_BUILD_SHIPPING
namespace AirsoftTeamGear
{
	static FString AnchorJson(const FGearAnchor& A)
	{
		FString S = FString::Printf(TEXT("\"Anchor\": { \"Bone\": \"%s\", \"Offset\": [%.1f, %.1f, %.1f], \"Rotation\": [%.1f, %.1f, %.1f], \"Scale\": %.3f"),
			*A.Bone.ToString(), A.Offset.X, A.Offset.Y, A.Offset.Z, A.Rotation.Pitch, A.Rotation.Yaw, A.Rotation.Roll, A.Scale);
		if (!A.AlignBone.IsNone())
		{
			S += FString::Printf(TEXT(", \"AlignBone\": \"%s\", \"ModelDir\": [%.4f, %.4f, %.4f]"), *A.AlignBone.ToString(), A.ModelDir.X, A.ModelDir.Y, A.ModelDir.Z);
		}
		if (A.bHasAssumed)
		{
			S += FString::Printf(TEXT(", \"AssumedBonePos\": [%.1f, %.1f, %.1f]"), A.AssumedBonePos.X, A.AssumedBonePos.Y, A.AssumedBonePos.Z);
		}
		return S + TEXT(" }");
	}

	static void Say(const FString& Message)
	{
		UE_LOG(LogAirsoftGear, Display, TEXT("%s"), *Message);
		if (GEngine)
		{
			GEngine->AddOnScreenDebugMessage(-1, 12.f, FColor::Cyan, Message);
		}
	}

	static void TuneCommand(const TArray<FString>& Args, UWorld* World)
	{
		if (Args.Num() < 4)
		{
			Say(TEXT("airsoft.gear.tune <AssetId[/Piece]> <x> <y> <z> [pitch yaw roll [scale]]  (cm / degrees, character space: X forward, Y right, Z up, from the anchor bone)"));
			return;
		}
		FString AssetStr = Args[0];
		FString PieceStr;
		Args[0].Split(TEXT("/"), &AssetStr, &PieceStr);
		const FGearAssetDef* Def = GearDatabase().Assets.Find(FName(*AssetStr));
		if (!Def)
		{
			Say(FString::Printf(TEXT("airsoft.gear.tune: unknown team gear asset '%s' (see airsoft.gear.list)"), *AssetStr));
			return;
		}
		// Pieces with their own anchor (knee pads) are tuned as "Asset/Piece", everything else per asset.
		const FName PieceName = PieceStr.IsEmpty() ? FName() : FName(*PieceStr);
		const FGearPieceDef* PieceDef = FindPiece(*Def, PieceName);
		const bool bPieceKey = PieceDef && PieceDef->bOwnAnchor;
		if (!bPieceKey)
		{
			PieceStr.Reset();
		}
		const FName Key = bPieceKey ? FName(*FString::Printf(TEXT("%s/%s"), *AssetStr, *PieceStr)) : Def->Id;
		FGearAnchor A = ResolveAnchor(Def->Id, bPieceKey ? PieceName : FName(), Key);
		A.Offset = FVector(FCString::Atof(*Args[1]), FCString::Atof(*Args[2]), FCString::Atof(*Args[3]));
		if (Args.Num() >= 7)
		{
			A.Rotation = FRotator(FCString::Atof(*Args[4]), FCString::Atof(*Args[5]), FCString::Atof(*Args[6]));
		}
		if (Args.Num() >= 8)
		{
			A.Scale = FMath::Max(0.05f, FCString::Atof(*Args[7]));
		}
		GOverrides.Add(Key, A);
		ForEachGear([](UAirsoftTeamGearComponent& Gear) { Gear.RefreshPlacement(); });
		Say(FString::Printf(TEXT("Gear.json Assets.%s%s: %s"), *AssetStr, PieceStr.IsEmpty() ? TEXT("") : *FString::Printf(TEXT(" (Pieces[%s])"), *PieceStr), *AnchorJson(A)));
	}

	static void ShowCommand(const TArray<FString>& Args, UWorld* World)
	{
		GShowGear = Args.Num() > 0 ? FCString::Atoi(*Args[0]) != 0 : !GShowGear;
		ForEachGear([](UAirsoftTeamGearComponent& Gear) { Gear.RefreshVisibility(); });
		Say(FString::Printf(TEXT("Team gear %s"), GShowGear ? TEXT("shown") : TEXT("hidden")));
	}

	static void ReloadCommand(const TArray<FString>& Args, UWorld* World)
	{
		GearDatabase(true);
		GOverrides.Reset();
		ForEachGear([](UAirsoftTeamGearComponent& Gear) { Gear.Rebuild(); });
		Say(TEXT("Team gear: Gear.json reloaded, tuning cleared, gear rebuilt"));
	}

	static void RerollCommand(const TArray<FString>& Args, UWorld* World)
	{
		GSeedOffset = Args.Num() > 0 ? FCString::Atoi(*Args[0]) : GSeedOffset + 1;
		ForEachGear([](UAirsoftTeamGearComponent& Gear) { Gear.Rebuild(); });
		Say(FString::Printf(TEXT("Team gear variants re-rolled (seed offset %d)"), GSeedOffset));
	}

	static void BonesCommand(const TArray<FString>& Args, UWorld* World)
	{
		TSet<const UObject*> Done;
		ForEachGear([&Done](UAirsoftTeamGearComponent& Gear)
		{
			if (Gear.HasGear() && !Done.Contains(Gear.GetOwner()))
			{
				Done.Add(Gear.GetOwner());
				if (Done.Num() == 1)
				{
					Gear.LogBones();
				}
			}
		});
		if (Done.Num() == 0)
		{
			Say(TEXT("airsoft.gear.bones: no gear in the world yet (gear is only built for other players' bodies)"));
		}
	}

	static void ListCommand(const TArray<FString>& Args, UWorld* World)
	{
		for (const auto& Pair : GearDatabase().Assets)
		{
			const FGearAssetDef& Def = Pair.Value;
			Say(FString::Printf(TEXT("%s: %s"), *Def.Id.ToString(), *AnchorJson(ResolveAnchor(Def.Id, NAME_None, Def.Id))));
			for (const FGearPieceDef& P : Def.Pieces)
			{
				if (P.bOwnAnchor)
				{
					const FName Key(*FString::Printf(TEXT("%s/%s"), *Def.Id.ToString(), *P.Name.ToString()));
					Say(FString::Printf(TEXT("  %s: %s"), *Key.ToString(), *AnchorJson(ResolveAnchor(Def.Id, P.Name, Key))));
				}
			}
		}
	}

	static FAutoConsoleCommandWithWorldAndArgs GTuneCmd(TEXT("airsoft.gear.tune"),
		TEXT("airsoft.gear.tune <AssetId[/Piece]> <x> <y> <z> [pitch yaw roll [scale]] - moves a team gear piece on every body (cm/deg, character space from its anchor bone) and logs the Gear.json Anchor to paste back"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&TuneCommand));
	static FAutoConsoleCommandWithWorldAndArgs GShowCmd(TEXT("airsoft.gear.show"), TEXT("airsoft.gear.show 0|1 - hides/shows all third-person team gear"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&ShowCommand));
	static FAutoConsoleCommandWithWorldAndArgs GReloadCmd(TEXT("airsoft.gear.reload"), TEXT("airsoft.gear.reload - re-reads Content/Airsoft/Data/Gear.json, clears live tuning and rebuilds the gear"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&ReloadCommand));
	static FAutoConsoleCommandWithWorldAndArgs GRerollCmd(TEXT("airsoft.gear.reroll"), TEXT("airsoft.gear.reroll [offset] - shuffles every player's gear variant (preview helmets/caps/colourways)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&RerollCommand));
	static FAutoConsoleCommandWithWorldAndArgs GBonesCmd(TEXT("airsoft.gear.bones"), TEXT("airsoft.gear.bones - logs the body's reference-pose anchor bones vs the generator's assumed positions"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&BonesCommand));
	static FAutoConsoleCommandWithWorldAndArgs GListCmd(TEXT("airsoft.gear.list"), TEXT("airsoft.gear.list - prints every team gear anchor in effect (Gear.json + live tuning)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&ListCommand));
}
#endif
