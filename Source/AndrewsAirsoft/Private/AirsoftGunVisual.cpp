#include "AirsoftGunVisual.h"

#include "AirsoftAssets.h"
#include "AirsoftWeaponData.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

namespace
{
	FVector JsonVector(const TSharedPtr<FJsonValue>& Value)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (Value.IsValid() && Value->TryGetArray(Arr) && Arr->Num() >= 3)
		{
			return FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		}
		return FVector::ZeroVector;
	}

	bool IsPistol(const FAirsoftWeaponDef* W)
	{
		return W && W->Class == TEXT("Pistol");
	}

	/** Reasonable stand-in points (cm) when no JSON layout exists yet. */
	void DefaultPoints(const FAirsoftWeaponDef* W, TMap<FName, FVector>& Out)
	{
		if (IsPistol(W))
		{
			Out.Add(TEXT("Muzzle"), FVector(17.f, 0.f, 7.f));
			Out.Add(TEXT("Aim"), FVector(-12.f, 0.f, 10.5f));
			Out.Add(TEXT("LeftHand"), FVector(0.f, -1.5f, -2.f));
			Out.Add(TEXT("MagWell"), FVector(0.f, 0.f, 2.f));
			Out.Add(TEXT("Optic"), FVector(3.f, 0.f, 9.f));
			Out.Add(TEXT("Underbarrel"), FVector(10.f, 0.f, 3.f));
			Out.Add(TEXT("MuzzleMount"), FVector(16.f, 0.f, 7.f));
			return;
		}
		float MuzzleX = 55.f;
		if (W)
		{
			if (W->Class == TEXT("SMG")) MuzzleX = 40.f;
			else if (W->Class == TEXT("Sniper")) MuzzleX = 78.f;
			else if (W->Class == TEXT("LMG")) MuzzleX = 66.f;
			else if (W->Class == TEXT("DMR")) MuzzleX = 70.f;
		}
		Out.Add(TEXT("Muzzle"), FVector(MuzzleX, 0.f, 9.f));
		Out.Add(TEXT("Aim"), FVector(-14.f, 0.f, 15.f));
		Out.Add(TEXT("LeftHand"), FVector(28.f, 0.f, 4.f));
		Out.Add(TEXT("MagWell"), FVector(12.f, 0.f, 2.f));
		Out.Add(TEXT("Optic"), FVector(5.f, 0.f, 12.5f));
		Out.Add(TEXT("Underbarrel"), FVector(30.f, 0.f, 3.f));
		Out.Add(TEXT("MuzzleMount"), FVector(MuzzleX - 4.f, 0.f, 9.f));
		Out.Add(TEXT("Side"), FVector(30.f, 3.5f, 8.f));
	}

	FVector DefaultAimOffset(FName Optic)
	{
		if (Optic == TEXT("Magnifier")) return FVector(-20.f, 0.f, 3.8f);
		if (Optic == TEXT("Scope4x")) return FVector(-15.f, 0.f, 4.2f);
		if (Optic == TEXT("ScopeLong")) return FVector(-20.f, 0.f, 4.8f);
		if (Optic == TEXT("Holo")) return FVector(-12.f, 0.f, 3.8f);
		return FVector(-12.f, 0.f, 3.6f);
	}

	/** Where the support hand sits relative to an underbarrel attachment's mount. */
	FVector DefaultHandOffset(FName Grip)
	{
		if (Grip == TEXT("AngledGrip")) return FVector(-0.5f, 0.f, -2.5f);
		if (Grip == TEXT("Bipod")) return FVector(-12.f, 0.f, -1.f); // hand stays on the handguard behind the clamp
		return FVector(0.f, 0.f, -6.f);
	}

	FVector DefaultMuzzleOffset(FName Muzzle)
	{
		return Muzzle == TEXT("Suppressor") ? FVector(17.f, 0.f, 0.f) : FVector(5.f, 0.f, 0.f);
	}

	UMaterialInterface* BasicShapeMaterial()
	{
		static TWeakObjectPtr<UMaterialInterface> Mat;
		if (!Mat.IsValid())
		{
			Mat = LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"), nullptr, LOAD_NoWarn | LOAD_Quiet);
		}
		return Mat.Get();
	}
}

UAirsoftGunVisual::UAirsoftGunVisual()
{
	PrimaryComponentTick.bCanEverTick = false;
}

const FAirsoftAssetLayout& UAirsoftGunVisual::Layout(const FString& Category, FName Id)
{
	static TMap<FString, FAirsoftAssetLayout> Cache;
	const FString Key = Category + TEXT("/") + Id.ToString();
	if (FAirsoftAssetLayout* Found = Cache.Find(Key))
	{
		return *Found;
	}
	FAirsoftAssetLayout& L = Cache.Add(Key);
	TSharedPtr<FJsonObject> Root = AirsoftAssets::LoadData(Category + TEXT(".json"));
	const TSharedPtr<FJsonObject>* Assets = nullptr;
	const TSharedPtr<FJsonObject>* Asset = nullptr;
	if (Root.IsValid() && Root->TryGetObjectField(TEXT("Assets"), Assets) && (*Assets)->TryGetObjectField(Id.ToString(), Asset))
	{
		L.bLoaded = true;
		const TSharedPtr<FJsonObject>* Points = nullptr;
		if ((*Asset)->TryGetObjectField(TEXT("Points"), Points))
		{
			for (const auto& Pair : (*Points)->Values)
			{
				L.Points.Add(FName(*Pair.Key), JsonVector(Pair.Value));
			}
		}
		// The generators write attachment offsets next to Points rather than inside it.
		for (const TCHAR* Key : { TEXT("AimOffset"), TEXT("MuzzleOffset"), TEXT("Hand") })
		{
			if (const TSharedPtr<FJsonValue> Value = (*Asset)->TryGetField(Key))
			{
				L.Points.FindOrAdd(FName(Key)) = JsonVector(Value);
			}
		}
		const TArray<TSharedPtr<FJsonValue>>* Pieces = nullptr;
		if ((*Asset)->TryGetArrayField(TEXT("Pieces"), Pieces))
		{
			for (const TSharedPtr<FJsonValue>& PieceValue : *Pieces)
			{
				const TSharedPtr<FJsonObject>* PieceObj = nullptr;
				if (PieceValue->TryGetObject(PieceObj))
				{
					L.Pieces.Add(FName(*(*PieceObj)->GetStringField(TEXT("Name"))));
					FString Kind;
					(*PieceObj)->TryGetStringField(TEXT("Kind"), Kind);
					L.Kinds.Add(FName(*Kind));
				}
			}
		}
	}
	return L;
}

void UAirsoftGunVisual::Clear()
{
	for (UStaticMeshComponent* Part : Parts)
	{
		if (Part)
		{
			Part->DestroyComponent();
		}
	}
	Parts.Reset();
	PartInfo.Reset();
	if (Light)
	{
		Light->DestroyComponent();
		Light = nullptr;
	}
	bHasLaser = false;
}

void UAirsoftGunVisual::Build(const FAirsoftCustomization& Custom, const FLinearColor& TeamAccent, bool bFirstPerson, bool bThirdPerson)
{
	Clear();
	Built = AirsoftWeapons::Clean(Custom);
	Accent = TeamAccent;
	bFP = bFirstPerson;
	bTP = bThirdPerson;

	const FAirsoftWeaponDef* W = AirsoftWeapons::Find(Built.WeaponId);
	const FAirsoftAssetLayout& L = Layout(TEXT("Weapons"), Built.WeaponId);

	TMap<FName, FVector> Points;
	DefaultPoints(W, Points);
	for (const auto& Pair : L.Points)
	{
		Points.Add(Pair.Key, Pair.Value);
	}
	AimPointLocal = Points.FindRef(TEXT("Aim"));
	MuzzleLocal = Points.FindRef(TEXT("Muzzle"));
	LeftHandLocal = Points.FindRef(TEXT("LeftHand"));
	MagWellLocal = Points.FindRef(TEXT("MagWell"));

	// Gun pieces. Each is exported with its origin at the grip, so all sit at identity.
	const bool bCustomMag = Built.Mag == TEXT("ExtMag") || Built.Mag == TEXT("DrumMag");
	TArray<FName> PieceNames = L.Pieces;
	TArray<FName> PieceKinds = L.Kinds;
	if (PieceNames.Num() == 0)
	{
		PieceNames = { TEXT("Body"), TEXT("Mag"), TEXT("Slide"), TEXT("Bolt"), TEXT("Pump"), TEXT("Glass") };
		PieceKinds = PieceNames;
	}
	bool bAnyMesh = false;
	for (int32 i = 0; i < PieceNames.Num(); ++i)
	{
		const FName Kind = PieceKinds.IsValidIndex(i) && !PieceKinds[i].IsNone() ? PieceKinds[i] : PieceNames[i];
		if (Kind == TEXT("Mag") && bCustomMag)
		{
			continue;
		}
		if (UStaticMesh* Mesh = AirsoftAssets::FindMesh(TEXT("Weapons"), Built.WeaponId, PieceNames[i].ToString()))
		{
			AddPart(Mesh, Kind, FTransform::Identity, Kind == TEXT("Mag") ? MagWellLocal : FVector::ZeroVector);
			bAnyMesh = bAnyMesh || Kind == TEXT("Body");
		}
	}
	if (!bAnyMesh)
	{
		BuildFallbackGun(Built);
	}

	// Attachments.
	struct FSlotMount
	{
		FName Slot;
		FName Choice;
		FName PointName;
	};
	const FSlotMount Mounts[] = {
		{ AirsoftWeapons::SlotOptic, Built.Optic, TEXT("Optic") },
		{ AirsoftWeapons::SlotMuzzle, Built.Muzzle, TEXT("MuzzleMount") },
		{ AirsoftWeapons::SlotGrip, Built.Grip, TEXT("Underbarrel") },
		{ AirsoftWeapons::SlotLaser, Built.Laser, Points.Contains(TEXT("Side")) ? FName(TEXT("Side")) : FName(TEXT("Underbarrel")) },
		{ AirsoftWeapons::SlotMag, Built.Mag, TEXT("MagWell") },
	};
	for (const FSlotMount& M : Mounts)
	{
		if (M.Choice.IsNone() || M.Choice == AirsoftWeapons::AttachOff)
		{
			continue;
		}
		const FVector* MountPoint = Points.Find(M.PointName);
		if (!MountPoint)
		{
			continue;
		}
		const int32 FirstNewPart = Parts.Num();
		const FAirsoftAssetLayout& AL = Layout(TEXT("Attachments"), M.Choice);
		bool bBuiltMesh = false;
		TArray<FName> AttPieces = AL.Pieces.Num() > 0 ? AL.Pieces : TArray<FName>{ TEXT("Body"), TEXT("Glass") };
		for (int32 i = 0; i < AttPieces.Num(); ++i)
		{
			if (UStaticMesh* Mesh = AirsoftAssets::FindMesh(TEXT("Attachments"), M.Choice, AttPieces[i].ToString()))
			{
				const FName Kind = M.Slot == AirsoftWeapons::SlotMag ? FName(TEXT("Mag")) : (AL.Kinds.IsValidIndex(i) ? AL.Kinds[i] : AttPieces[i]);
				AddPart(Mesh, Kind, FTransform(*MountPoint), MagWellLocal);
				bBuiltMesh = true;
			}
		}
		if (!bBuiltMesh)
		{
			BuildFallbackAttachment(M.Choice, M.Slot, *MountPoint);
		}

		if (M.Slot == AirsoftWeapons::SlotOptic)
		{
			const FVector* Aim = AL.Point(TEXT("AimOffset"));
			AimPointLocal = *MountPoint + (Aim ? *Aim : DefaultAimOffset(M.Choice));
			// Magnified optics hide their housing at full aim so the zoomed sight picture is clear;
			// open sights (red dot, holo) keep their frame and reticle.
			const bool bMagnified = M.Choice == TEXT("Scope4x") || M.Choice == TEXT("Magnifier") || M.Choice == TEXT("ScopeLong");
			for (int32 i = FirstNewPart; i < PartInfo.Num(); ++i)
			{
				const FName K = PartInfo[i].Kind;
				PartInfo[i].bOptic = bMagnified && K != TEXT("Glass") && K != TEXT("Reticle") && K != TEXT("Emissive");
			}
		}
		else if (M.Slot == AirsoftWeapons::SlotMuzzle)
		{
			const FVector* Off = AL.Point(TEXT("MuzzleOffset"));
			MuzzleLocal = *MountPoint + (Off ? *Off : DefaultMuzzleOffset(M.Choice));
		}
		else if (M.Slot == AirsoftWeapons::SlotGrip)
		{
			const FVector* Hand = AL.Point(TEXT("Hand"));
			LeftHandLocal = *MountPoint + (Hand ? *Hand : DefaultHandOffset(M.Choice));
		}
		else if (M.Slot == AirsoftWeapons::SlotLaser)
		{
			const FVector* Beam = AL.Point(TEXT("Beam"));
			LaserLocal = *MountPoint + (Beam ? *Beam : FVector(8.f, 0.f, 0.f));
			bHasLaser = true;
			Light = NewObject<USpotLightComponent>(GetOwner());
			Light->SetupAttachment(this);
			Light->SetRelativeLocation(LaserLocal);
			Light->SetInnerConeAngle(10.f);
			Light->SetOuterConeAngle(26.f);
			Light->SetIntensity(18000.f);
			Light->SetAttenuationRadius(3500.f);
			Light->SetLightColor(FLinearColor(1.f, 0.96f, 0.9f));
			Light->SetCastShadows(true);
			Light->SetVisibility(bLightOn);
			Light->RegisterComponent();
		}
	}
	if (bFP && !bTP)
	{
		AddHands(IsPistol(W));
	}
	SetOpticFade(OpticFade);
}

void UAirsoftGunVisual::AddHands(bool bPistol)
{
	// Gun space: origin at the grip, barrel +X. The shooter's shoulders sit behind and below.
	const FVector RightElbow(-30.f, 9.f, -22.f);
	const FVector LeftElbow = bPistol ? FVector(-30.f, -16.f, -22.f) : FVector(LeftHandLocal.X - 34.f, -24.f, -20.f);
	const FVector LeftHand = bPistol ? FVector(-1.f, -3.f, -2.f) : LeftHandLocal;

	UStaticMesh* RightMesh = AirsoftAssets::FindMesh(TEXT("Gear"), TEXT("Gloves"), TEXT("RightGrip"));
	UStaticMesh* LeftMesh = AirsoftAssets::FindMesh(TEXT("Gear"), TEXT("Gloves"), bPistol ? TEXT("LeftPistol") : TEXT("LeftSupport"));
	if (RightMesh && LeftMesh)
	{
		AddPart(RightMesh, TEXT("Hand"), FTransform::Identity, FVector::ZeroVector);
		AddPart(LeftMesh, TEXT("LeftHand"), FTransform(LeftHand), FVector::ZeroVector);
		return;
	}

	// Stand-ins: dark gloves and sleeves.
	const FLinearColor Glove(0.035f, 0.035f, 0.032f);
	const FLinearColor Sleeve(0.06f, 0.065f, 0.05f);
	AddBox(FVector(-1.f, 0.f, -2.f), FVector(6.f, 5.f, 9.f), Glove, TEXT("Hand"));
	AddLimb(FVector(-3.f, 1.f, -6.f), RightElbow, 7.f, Sleeve, TEXT("Hand"));
	AddBox(LeftHand + FVector(0.f, -1.f, -2.5f), FVector(7.f, 5.f, 5.f), Glove, TEXT("LeftHand"));
	AddLimb(LeftHand + FVector(-2.f, -2.f, -4.f), LeftElbow, 7.f, Sleeve, TEXT("LeftHand"));
}

UStaticMeshComponent* UAirsoftGunVisual::AddLimb(const FVector& From, const FVector& To, float Thickness, const FLinearColor& Color, FName Kind)
{
	const FVector Axis = To - From;
	const float Length = Axis.Size();
	if (Length < 1.f)
	{
		return nullptr;
	}
	const FQuat Rotation = FRotationMatrix::MakeFromZ(Axis / Length).ToQuat();
	const FTransform Relative(Rotation, (From + To) * 0.5f, FVector(Thickness / 100.f, Thickness / 100.f, Length / 100.f));
	UStaticMeshComponent* Comp = AddPart(AirsoftAssets::Cylinder(), Kind, Relative, FVector::ZeroVector);
	if (Comp)
	{
		if (UMaterialInterface* Mat = BasicShapeMaterial())
		{
			if (UMaterialInstanceDynamic* MID = Comp->CreateDynamicMaterialInstance(0, Mat))
			{
				MID->SetVectorParameterValue(TEXT("Color"), Color);
			}
		}
	}
	return Comp;
}

UStaticMeshComponent* UAirsoftGunVisual::AddPart(UStaticMesh* Mesh, FName Kind, const FTransform& Relative, const FVector& Pivot)
{
	AActor* Owner = GetOwner();
	if (!Owner || !Mesh)
	{
		return nullptr;
	}
	UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(Owner);
	Comp->SetStaticMesh(Mesh);
	Comp->SetupAttachment(this);
	Comp->SetRelativeTransform(Relative);
	Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Comp->SetGenerateOverlapEvents(false);
	Comp->bReceivesDecals = false;
	Comp->SetOnlyOwnerSee(bFP && !bTP);
	Comp->SetOwnerNoSee(bTP && !bFP);
	Comp->SetCastShadow(!bFP);
	Comp->bCastHiddenShadow = false;
	Comp->RegisterComponent();
	ApplyMaterials(Comp);
	Parts.Add(Comp);
	FPartInfo Info;
	Info.Kind = Kind;
	Info.Base = Relative;
	Info.Pivot = Pivot;
	PartInfo.Add(Info);
	return Comp;
}

void UAirsoftGunVisual::ApplyMaterials(UStaticMeshComponent* Comp)
{
	const FAirsoftSkinDef& Skin = AirsoftWeapons::FindSkin(Built.Skin);
	for (int32 Slot = 0; Slot < Comp->GetNumMaterials(); ++Slot)
	{
		UMaterialInterface* Base = Comp->GetMaterial(Slot);
		if (!Base)
		{
			continue;
		}
		UMaterialInstanceDynamic* MID = Comp->CreateDynamicMaterialInstance(Slot, Base);
		if (MID)
		{
			MID->SetVectorParameterValue(TEXT("PrimaryTint"), Skin.Primary);
			MID->SetVectorParameterValue(TEXT("SecondaryTint"), Skin.Secondary);
			MID->SetVectorParameterValue(TEXT("AccentTint"), Accent);
			MID->SetScalarParameterValue(TEXT("TintMetallic"), Skin.Metallic);
			MID->SetScalarParameterValue(TEXT("TintRoughness"), Skin.Roughness);
		}
	}
}

UStaticMeshComponent* UAirsoftGunVisual::AddBox(const FVector& Center, const FVector& Size, const FLinearColor& Color, FName Kind)
{
	UStaticMeshComponent* Comp = AddPart(AirsoftAssets::Cube(), Kind, FTransform(FQuat::Identity, Center, Size / 100.f), Kind == TEXT("Mag") ? MagWellLocal : FVector::ZeroVector);
	if (Comp)
	{
		if (UMaterialInterface* Mat = BasicShapeMaterial())
		{
			UMaterialInstanceDynamic* MID = Comp->CreateDynamicMaterialInstance(0, Mat);
			if (MID)
			{
				MID->SetVectorParameterValue(TEXT("Color"), Color);
			}
		}
	}
	return Comp;
}

void UAirsoftGunVisual::BuildFallbackGun(const FAirsoftCustomization& Custom)
{
	const FAirsoftWeaponDef* W = AirsoftWeapons::Find(Custom.WeaponId);
	const FAirsoftSkinDef& Skin = AirsoftWeapons::FindSkin(Custom.Skin);
	const FLinearColor Metal(0.05f, 0.05f, 0.055f);
	if (IsPistol(W))
	{
		AddBox(FVector(-1.f, 0.f, -3.f), FVector(4.f, 3.f, 11.f), Skin.Secondary);       // grip
		AddBox(FVector(4.f, 0.f, 4.f), FVector(18.f, 2.8f, 3.f), Skin.Secondary);        // frame
		AddBox(FVector(4.f, 0.f, 7.f), FVector(19.f, 3.0f, 3.2f), Skin.Primary, TEXT("Slide"));
		AddBox(FVector(0.f, 0.f, -7.f), FVector(3.6f, 2.6f, 3.f), Metal, TEXT("Mag"));
		AddBox(FVector(-1.f, 1.6f, -3.f), FVector(4.f, 0.3f, 2.f), Accent);
		return;
	}
	const float MuzzleX = MuzzleLocal.X;
	AddBox(FVector(0.f, 0.f, -4.f), FVector(4.f, 3.f, 11.f), Skin.Secondary);                // grip
	AddBox(FVector(10.f, 0.f, 6.f), FVector(30.f, 4.5f, 8.f), Skin.Primary);                 // receiver
	AddBox(FVector(MuzzleX * 0.55f + 10.f, 0.f, 8.f), FVector(MuzzleX * 0.5f, 5.f, 6.f), Skin.Primary); // handguard
	AddBox(FVector(MuzzleX - 4.f, 0.f, 9.f), FVector(10.f, 1.6f, 1.6f), Metal);              // barrel
	AddBox(FVector(-22.f, 0.f, 6.f), FVector(22.f, 4.f, 9.f), Skin.Secondary);               // stock
	AddBox(MagWellLocal + FVector(0.f, 0.f, -9.f), FVector(6.f, 2.4f, 16.f), Metal, TEXT("Mag"));
	AddBox(FVector(MuzzleX * 0.55f + 4.f, 0.f, 8.f), FVector(2.f, 5.4f, 6.4f), Accent);      // team tape
}

void UAirsoftGunVisual::BuildFallbackAttachment(FName AttachmentId, FName Slot, const FVector& Mount)
{
	const FLinearColor Black(0.02f, 0.02f, 0.022f);
	if (Slot == AirsoftWeapons::SlotOptic)
	{
		const bool bScope = AttachmentId == TEXT("Scope4x") || AttachmentId == TEXT("ScopeLong");
		const float Len = AttachmentId == TEXT("ScopeLong") ? 34.f : bScope ? 16.f : 8.f;
		// Hollow frame (two walls + hood) so the eye can see through.
		AddBox(Mount + FVector(0.f, 0.f, 0.8f), FVector(Len, 3.f, 1.6f), Black);
		AddBox(Mount + FVector(0.f, 1.6f, 3.6f), FVector(Len, 0.4f, 5.f), Black);
		AddBox(Mount + FVector(0.f, -1.6f, 3.6f), FVector(Len, 0.4f, 5.f), Black);
		AddBox(Mount + FVector(0.f, 0.f, 6.3f), FVector(Len, 3.6f, 0.5f), Black);
		for (int32 i = FMath::Max(Parts.Num() - 4, 0); i < Parts.Num(); ++i)
		{
			PartInfo[i].bOptic = bScope;
		}
		if (!bScope)
		{
			// Glowing dot for red dot / holo stand-ins.
			if (UStaticMeshComponent* Dot = AddPart(AirsoftAssets::Sphere(), TEXT("Reticle"), FTransform(FQuat::Identity, Mount + FVector(Len * 0.5f, 0.f, 3.6f), FVector(0.004f)), FVector::ZeroVector))
			{
				Dot->SetMaterial(0, AirsoftAssets::MakeEmissive(Dot, FLinearColor(1.f, 0.05f, 0.03f), 40.f));
			}
		}
	}
	else if (Slot == AirsoftWeapons::SlotMuzzle)
	{
		const float Len = AttachmentId == TEXT("Suppressor") ? 17.f : 5.f;
		AddBox(Mount + FVector(Len * 0.5f, 0.f, 0.f), FVector(Len, 3.4f, 3.4f), Black);
	}
	else if (Slot == AirsoftWeapons::SlotGrip)
	{
		AddBox(Mount + FVector(0.f, 0.f, -5.f), FVector(3.f, 3.f, 10.f), Black);
	}
	else if (Slot == AirsoftWeapons::SlotLaser)
	{
		AddBox(Mount + FVector(3.f, 1.5f, 0.f), FVector(8.f, 3.f, 3.f), FLinearColor(0.15f, 0.16f, 0.12f));
	}
	else if (Slot == AirsoftWeapons::SlotMag)
	{
		const bool bDrum = AttachmentId == TEXT("DrumMag");
		AddBox(Mount + FVector(0.f, 0.f, bDrum ? -9.f : -12.f), bDrum ? FVector(14.f, 8.f, 14.f) : FVector(6.f, 2.4f, 22.f), Black, TEXT("Mag"));
	}
}

void UAirsoftGunVisual::SetPartOffsets(const FTransform& Mag, const FTransform& Slide, const FTransform& Bolt, const FTransform& Pump, const FTransform& LeftHand)
{
	for (int32 i = 0; i < Parts.Num(); ++i)
	{
		UStaticMeshComponent* Part = Parts[i];
		if (!Part)
		{
			continue;
		}
		const FPartInfo& Info = PartInfo[i];
		const FTransform* Offset = nullptr;
		if (Info.Kind == TEXT("Mag")) Offset = &Mag;
		else if (Info.Kind == TEXT("Slide")) Offset = &Slide;
		else if (Info.Kind == TEXT("Bolt")) Offset = &Bolt;
		else if (Info.Kind == TEXT("Pump")) Offset = &Pump;
		else if (Info.Kind == TEXT("LeftHand")) Offset = &LeftHand;
		if (!Offset)
		{
			continue;
		}
		// Rotate/translate about the pivot (mag well for magazines).
		const FTransform PivotT(Info.Pivot);
		const FTransform Final = Info.Base * PivotT.Inverse() * (*Offset) * PivotT;
		Part->SetRelativeTransform(Final);
	}
}

void UAirsoftGunVisual::SetLightOn(bool bOn)
{
	bLightOn = bOn;
	if (Light)
	{
		Light->SetVisibility(bOn);
	}
}

void UAirsoftGunVisual::SetOpticFade(float Alpha)
{
	OpticFade = Alpha;
	// Hide housings at full aim (first person only).
	const bool bHide = bFP && Alpha > 0.9f;
	for (int32 i = 0; i < Parts.Num(); ++i)
	{
		if (Parts[i] && PartInfo[i].bOptic)
		{
			Parts[i]->SetVisibility(!bHide);
		}
	}
}
