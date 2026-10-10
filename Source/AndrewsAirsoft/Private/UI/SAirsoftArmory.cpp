// Andrew's Airsoft - armory: pick primary/secondary, fit attachments per slot,
// choose a finish (rank-locked), and read the resulting stats. Every edit goes
// through AirsoftWeapons::Clean, is saved to the profile and pushed to the host.

#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftPlayerController.h"
#include "AirsoftSaveGame.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "AirsoftWeaponData.h"
#include "CoreGlobals.h"
#include "HAL/PlatformTime.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SNullWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftArmoryLocal
{
	struct FStats
	{
		float Range = 0.f;
		float Rate = 0.f;
		float Control = 0.f;
		float Handling = 0.f;
		float BaseRange = 0.f;
		float BaseRate = 0.f;
		float BaseControl = 0.f;
		float BaseHandling = 0.f;
	};

	FName GetSlotValue(const FAirsoftCustomization& C, FName Slot)
	{
		if (Slot == AirsoftWeapons::SlotOptic) return C.Optic;
		if (Slot == AirsoftWeapons::SlotMuzzle) return C.Muzzle;
		if (Slot == AirsoftWeapons::SlotGrip) return C.Grip;
		if (Slot == AirsoftWeapons::SlotLaser) return C.Laser;
		if (Slot == AirsoftWeapons::SlotMag) return C.Mag;
		return NAME_None;
	}

	void SetSlotValue(FAirsoftCustomization& C, FName Slot, FName Value)
	{
		if (Slot == AirsoftWeapons::SlotOptic) C.Optic = Value;
		else if (Slot == AirsoftWeapons::SlotMuzzle) C.Muzzle = Value;
		else if (Slot == AirsoftWeapons::SlotGrip) C.Grip = Value;
		else if (Slot == AirsoftWeapons::SlotLaser) C.Laser = Value;
		else if (Slot == AirsoftWeapons::SlotMag) C.Mag = Value;
	}

	FString ModesText(const FAirsoftWeaponDef& Def)
	{
		TArray<FString> Names;
		for (EAirsoftFireMode Mode : Def.FireModes)
		{
			Names.Add(AirsoftWeapons::FireModeName(Mode));
		}
		return FString::Join(Names, TEXT(" / "));
	}

	EVisibility ArmoryVis(bool bVisible)
	{
		return bVisible ? EVisibility::Visible : EVisibility::Collapsed;
	}
}

class SAirsoftArmory : public SAirsoftMenuBase
{
public:
	SLATE_BEGIN_ARGS(SAirsoftArmory) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

protected:
	virtual void HandleBack() override;

private:
	TSharedRef<SWidget> BuildWeaponColumn(const FString& Title, const TArray<FName>& Ids);
	TSharedRef<SWidget> BuildWeaponCard(FName Id);
	TSharedRef<SWidget> BuildDetail();
	TSharedRef<SWidget> BuildAttachmentRow(const FAirsoftWeaponDef& Def, FName Slot);
	TSharedRef<SWidget> BuildFinishes();
	TSharedRef<SWidget> StatBar(const FString& Label, TFunction<float()> Value, TFunction<float()> Base);
	TSharedRef<SWidget> StatNumber(const FString& Label, TFunction<FString()> Value);

	UAirsoftSaveGame* Profile() const { return AUI::GetProfile(WeakPC.Get()); }
	int32 PlayerRank() const;
	FAirsoftCustomization CustomFor(FName Id) const;
	bool IsEquipped(FName Id) const;
	AirsoftArmoryLocal::FStats ComputeStats() const;
	void Store(const FAirsoftCustomization& In, bool bEquip);
	void Select(FName Id);
	void SetAttachment(FName Slot, FName Choice);
	void SetSkin(FName SkinId);
	void Flash(const FString& Text);

	FName ViewId;
	TSharedPtr<SBox> DetailBox;
	TMap<FName, TSharedPtr<SAirsoftButton>> CardButtons;
	FString Message;
	double MessageTime = -100.0;
	mutable uint64 StatsFrame = TNumericLimits<uint64>::Max();
	mutable AirsoftArmoryLocal::FStats CachedStats;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateArmory(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftArmory, PC);
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

int32 SAirsoftArmory::PlayerRank() const
{
	const UAirsoftSaveGame* P = Profile();
	return AirsoftWeapons::RankIndexForXP(P ? P->XP : 0);
}

FAirsoftCustomization SAirsoftArmory::CustomFor(FName Id) const
{
	FAirsoftCustomization C;
	C.WeaponId = Id;
	if (const UAirsoftSaveGame* P = Profile())
	{
		if (P->Loadout.Primary.WeaponId == Id)
		{
			C = P->Loadout.Primary;
		}
		else if (P->Loadout.Secondary.WeaponId == Id)
		{
			C = P->Loadout.Secondary;
		}
		else if (const FAirsoftCustomization* Saved = P->Customizations.Find(Id))
		{
			C = *Saved;
		}
	}
	C.WeaponId = Id;
	return AirsoftWeapons::Clean(C);
}

bool SAirsoftArmory::IsEquipped(FName Id) const
{
	const UAirsoftSaveGame* P = Profile();
	return P && (P->Loadout.Primary.WeaponId == Id || P->Loadout.Secondary.WeaponId == Id);
}

AirsoftArmoryLocal::FStats SAirsoftArmory::ComputeStats() const
{
	if (StatsFrame == GFrameCounter)
	{
		return CachedStats;
	}
	AirsoftArmoryLocal::FStats S;
	const FAirsoftWeaponDef* Base = AirsoftWeapons::Find(ViewId);
	if (!Base)
	{
		return S;
	}
	const FAirsoftWeaponDef R = AirsoftWeapons::Resolve(CustomFor(ViewId));
	S.BaseRange = Base->StatRange;
	S.BaseRate = Base->StatRate;
	S.BaseControl = Base->StatControl;
	S.BaseHandling = Base->StatHandling;
	S.Range = FMath::Clamp(Base->StatRange * (R.MuzzleVelocity / FMath::Max(Base->MuzzleVelocity, 1.f)), 0.f, 1.f);
	S.Rate = Base->StatRate;
	S.Control = FMath::Clamp(Base->StatControl * (Base->RecoilUp / FMath::Max(R.RecoilUp, 0.01f)), 0.f, 1.f);
	S.Handling = FMath::Clamp(Base->StatHandling * (Base->AimTime / FMath::Max(R.AimTime, 0.01f)), 0.f, 1.f);
	StatsFrame = GFrameCounter;
	CachedStats = S;
	return S;
}

void SAirsoftArmory::Store(const FAirsoftCustomization& In, bool bEquip)
{
	UAirsoftSaveGame* P = Profile();
	const FAirsoftCustomization C = AirsoftWeapons::Clean(In);
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(C.WeaponId);
	if (!P || !Def)
	{
		return;
	}
	P->Customizations.Add(C.WeaponId, C);
	if (bEquip || IsEquipped(C.WeaponId))
	{
		if (Def->IsSecondary())
		{
			P->Loadout.Secondary = C;
		}
		else
		{
			P->Loadout.Primary = C;
		}
	}
	if (UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get()))
	{
		GI->SaveProfile();
	}
	if (AAirsoftPlayerController* PC = WeakPC.Get())
	{
		PC->PushLoadoutToServer();
	}
}

void SAirsoftArmory::Select(FName Id)
{
	if (!AirsoftWeapons::Find(Id))
	{
		return;
	}
	const bool bChanged = ViewId != Id;
	ViewId = Id;
	if (!IsEquipped(Id))
	{
		Store(CustomFor(Id), true);
	}
	if (bChanged && DetailBox.IsValid())
	{
		DetailBox->SetContent(BuildDetail());
	}
}

void SAirsoftArmory::SetAttachment(FName Slot, FName Choice)
{
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(ViewId);
	if (!Def)
	{
		return;
	}
	if (Choice == AirsoftWeapons::AttachOff && Def->RequiredSlots.Contains(Slot))
	{
		Flash(TEXT("This weapon needs something in that slot."));
		return;
	}
	FAirsoftCustomization C = CustomFor(ViewId);
	AirsoftArmoryLocal::SetSlotValue(C, Slot, Choice);
	Store(C, false);
}

void SAirsoftArmory::SetSkin(FName SkinId)
{
	const FAirsoftSkinDef& Skin = AirsoftWeapons::FindSkin(SkinId);
	if (PlayerRank() < Skin.UnlockRank)
	{
		Flash(FString::Printf(TEXT("%s unlocks at rank %d (%s)."), *Skin.Name, Skin.UnlockRank, *AUI::RankName(Skin.UnlockRank)));
		return;
	}
	FAirsoftCustomization C = CustomFor(ViewId);
	C.Skin = Skin.Id;
	Store(C, false);
}

void SAirsoftArmory::Flash(const FString& Text)
{
	Message = Text;
	MessageTime = FPlatformTime::Seconds();
}

void SAirsoftArmory::HandleBack()
{
	AAirsoftPlayerController* PC = WeakPC.Get();
	if (!PC)
	{
		return;
	}
	if (PC->IsMainMenu())
	{
		PC->ShowMenu(EAirsoftMenu::MainMenu);
	}
	else if (!PC->GetArmoryFocus().IsNone())
	{
		// Opened from a weapon rack: Escape goes straight back to the game.
		PC->CloseMenus();
	}
	else
	{
		PC->ShowMenu(EAirsoftMenu::GameMenu);
	}
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

void SAirsoftArmory::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	OpenTime = FPlatformTime::Seconds();
	ForceVolatile(true);

	// Start on the rack's weapon if opened from one, otherwise the equipped primary.
	const FName Focus = InPC ? InPC->GetArmoryFocus() : NAME_None;
	if (!Focus.IsNone() && AirsoftWeapons::Find(Focus))
	{
		ViewId = Focus;
	}
	else if (const UAirsoftSaveGame* P = Profile())
	{
		ViewId = P->Loadout.Primary.WeaponId;
	}
	if (!AirsoftWeapons::Find(ViewId) && AirsoftWeapons::Primaries().Num() > 0)
	{
		ViewId = AirsoftWeapons::Primaries()[0];
	}

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SAirsoftBackdrop)
			.Opacity(0.92f)
			.ColumnWidth(0.f)
		]
		+ SOverlay::Slot()
		.Padding(FMargin(80.f, 56.f, 80.f, 40.f))
		[
			SNew(SVerticalBox)
			// Header
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("LOADOUT")))
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 10.f, 0.f, 0.f))
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("ARMORY")))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 40, 240))
						.ColorAndOpacity(FLinearColor::White)
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				[
					SNew(SSpacer)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Bottom)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					[
						SNew(STextBlock)
						.Font(AUI::Caption(9))
						.ColorAndOpacity(AUI::TextDim())
						.Text_Lambda([this]()
						{
							const int32 Rank = PlayerRank();
							return FText::FromString(FString::Printf(TEXT("RANK %d  \u00B7  %s"), Rank, *AUI::RankName(Rank).ToUpper()));
						})
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					.Padding(FMargin(0.f, 6.f, 0.f, 4.f))
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("Changes apply on your next spawn")))
						.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 20))
						.ColorAndOpacity(AUI::Accent())
						.Visibility_Lambda([this]() -> EVisibility
						{
							const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
							const bool bLive = GS && GS->bIsMatchMap && GS->Phase == EAirsoftPhase::Live;
							return bLive ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
						})
					]
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 14.f, 0.f, 0.f))
			[
				AirsoftUIWidgets::Rule(AUI::Hairline())
			]
			// Body
			+ SVerticalBox::Slot()
			.FillHeight(1.f)
			.Padding(FMargin(0.f, 18.f, 0.f, 0.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(604.f)
					[
						SNew(SScrollBox)
						+ SScrollBox::Slot()
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot()
							.AutoWidth()
							[
								BuildWeaponColumn(TEXT("PRIMARY"), AirsoftWeapons::Primaries())
							]
							+ SHorizontalBox::Slot()
							.AutoWidth()
							.Padding(FMargin(12.f, 0.f, 0.f, 0.f))
							[
								BuildWeaponColumn(TEXT("SECONDARY"), AirsoftWeapons::Secondaries())
							]
						]
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.Padding(FMargin(36.f, 0.f, 0.f, 0.f))
				[
					SNew(SScrollBox)
					+ SScrollBox::Slot()
					.Padding(FMargin(0.f, 0.f, 14.f, 0.f))
					[
						SAssignNew(DetailBox, SBox)
						[
							BuildDetail()
						]
					]
				]
			]
			// Footer
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 18.f, 0.f, 0.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(220.f)
					[
						SNew(SAirsoftButton)
						.Text(FText::FromString(TEXT("BACK")))
						.FontSize(13)
						.OnClicked_Lambda([this]()
						{
							ReturnToParentMenu();
							return FReply::Handled();
						})
					]
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(24.f, 0.f, 0.f, 0.f))
				[
					AirsoftUIWidgets::Hint(FText::FromString(TEXT("ESC")), FText::FromString(TEXT("BACK")))
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.HAlign(HAlign_Right)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 20))
					.ColorAndOpacity(AUI::Accent())
					.Text_Lambda([this]() { return FText::FromString(Message); })
					.Visibility_Lambda([this]() -> EVisibility
					{
						return (!Message.IsEmpty() && FPlatformTime::Seconds() - MessageTime < 4.0) ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
					})
				]
			]
		]
	];

	if (const TSharedPtr<SAirsoftButton>* Card = CardButtons.Find(ViewId))
	{
		SetInitialFocus(*Card);
	}
}

TSharedRef<SWidget> SAirsoftArmory::BuildWeaponColumn(const FString& Title, const TArray<FName>& Ids)
{
	TSharedRef<SVerticalBox> Column = SNew(SVerticalBox);
	Column->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.f, 0.f, 0.f, 10.f))
	[
		AirsoftUIWidgets::SectionLabel(FText::FromString(Title))
	];
	for (const FName Id : Ids)
	{
		if (!AirsoftWeapons::Find(Id))
		{
			continue;
		}
		Column->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 6.f))
		[
			BuildWeaponCard(Id)
		];
	}
	return SNew(SBox)
		.WidthOverride(290.f)
		[
			Column
		];
}

TSharedRef<SWidget> SAirsoftArmory::BuildWeaponCard(FName Id)
{
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(Id);
	check(Def);
	TSharedPtr<SAirsoftButton> Button;
	TSharedRef<SWidget> Card = SAssignNew(Button, SAirsoftButton)
		.ContentPadding(FMargin(14.f, 10.f, 12.f, 11.f))
		.IsSelected_Lambda([this, Id]() { return ViewId == Id; })
		.OnClicked_Lambda([this, Id]()
		{
			Select(Id);
			return FReply::Handled();
		})
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(AUI::Upper(Def->Name))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 11, 120))
					.ColorAndOpacity_Lambda([this, Id]() -> FSlateColor { return ViewId == Id ? AUI::Accent() : FLinearColor::White; })
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(SBorder)
					.Visibility_Lambda([this, Id]() -> EVisibility { return IsEquipped(Id) ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
					.BorderImage(AUI::OutlineBrush())
					.BorderBackgroundColor(AUI::WithAlpha(AUI::Accent(), 0.8f))
					.Padding(FMargin(5.f, 0.f))
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("EQUIPPED")))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 7, 160))
						.ColorAndOpacity(AUI::Accent())
					]
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 3.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(FString::Printf(TEXT("%s  \u00B7  %s"), *Def->Class.ToUpper(), *Def->Kind.ToUpper())))
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextDim())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 5.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(Def->Description))
				.AutoWrapText(true)
				.Font(AUI::Font(AUI::EFontWeight::Regular, 9))
				.ColorAndOpacity(AUI::TextDim())
			]
		];
	CardButtons.Add(Id, Button);
	return Card;
}

TSharedRef<SWidget> SAirsoftArmory::StatBar(const FString& Label, TFunction<float()> Value, TFunction<float()> Base)
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(96.f)
			[
				SNew(STextBlock)
				.Text(FText::FromString(Label))
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextDim())
			]
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SAirsoftBar)
			.Width(230.f)
			.Height(4.f)
			.Fraction_Lambda([Value]() { return Value(); })
			.Marker_Lambda([Value, Base]()
			{
				const float B = Base();
				return FMath::IsNearlyEqual(B, Value(), 0.005f) ? -1.f : B;
			})
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(12.f, 0.f, 0.f, 0.f))
		[
			SNew(SBox)
			.WidthOverride(30.f)
			[
				SNew(STextBlock)
				.Font(AUI::Font(AUI::EFontWeight::Bold, 10))
				.Text_Lambda([Value]() { return FText::AsNumber(FMath::RoundToInt(Value() * 100.f)); })
				.ColorAndOpacity_Lambda([Value, Base]() -> FSlateColor
				{
					const float Delta = Value() - Base();
					if (Delta > 0.005f)
					{
						return AUI::Accent();
					}
					return Delta < -0.005f ? AUI::Danger() : AUI::TextColor();
				})
			]
		];
}

TSharedRef<SWidget> SAirsoftArmory::StatNumber(const FString& Label, TFunction<FString()> Value)
{
	return AirsoftUIWidgets::StatBlock(FText::FromString(Label),
		TAttribute<FText>::CreateLambda([Value]() { return FText::FromString(Value()); }), 16);
}

TSharedRef<SWidget> SAirsoftArmory::BuildDetail()
{
	using namespace AirsoftArmoryLocal;
	const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(ViewId);
	if (!Def)
	{
		return SNullWidget::NullWidget;
	}

	TSharedRef<SVerticalBox> Attachments = SNew(SVerticalBox);
	for (const FName Slot : AirsoftWeapons::AttachmentSlots())
	{
		const TArray<FName>* Options = Def->Options.Find(Slot);
		if (!Options || Options->Num() == 0)
		{
			continue;
		}
		Attachments->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 12.f))
		[
			BuildAttachmentRow(*Def, Slot)
		];
	}

	const FName Id = ViewId;
	return SNew(SVerticalBox)
		// Title block
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(AUI::Upper(Def->Name))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 30, 160))
					.ColorAndOpacity(FLinearColor::White)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 4.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(FString::Printf(TEXT("%s  \u00B7  %s  \u00B7  %s"), *Def->Class.ToUpper(), *Def->Kind.ToUpper(), *ModesText(*Def))))
					.Font(AUI::Caption(9))
					.ColorAndOpacity(AUI::Accent())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 8.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(Def->Description))
					.AutoWrapText(true)
					.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 10))
					.ColorAndOpacity(AUI::TextDim())
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(20.f, 4.f, 0.f, 0.f))
			[
				SNew(SBox)
				.WidthOverride(200.f)
				[
					SNew(SOverlay)
					+ SOverlay::Slot()
					[
						SNew(SAirsoftButton)
						.Visibility_Lambda([this, Id]() -> EVisibility { return ArmoryVis(!IsEquipped(Id)); })
						.Text(FText::FromString(Def->IsSecondary() ? TEXT("EQUIP SIDEARM") : TEXT("EQUIP PRIMARY")))
						.FontSize(12)
						.HAlign(HAlign_Center)
						.OnClicked_Lambda([this, Id]()
						{
							Store(CustomFor(Id), true);
							return FReply::Handled();
						})
					]
					+ SOverlay::Slot()
					.HAlign(HAlign_Right)
					.VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Visibility_Lambda([this, Id]() -> EVisibility { return IsEquipped(Id) ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
						.Text(FText::FromString(Def->IsSecondary() ? TEXT("EQUIPPED SIDEARM") : TEXT("EQUIPPED PRIMARY")))
						.Font(AUI::Caption(9))
						.ColorAndOpacity(AUI::Accent())
					]
				]
			]
		]
		// Stats
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.f, 22.f, 0.f, 0.f))
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(20.f, 16.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 9.f))
					[
						StatBar(TEXT("RANGE"), [this]() { return ComputeStats().Range; }, [this]() { return ComputeStats().BaseRange; })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 9.f))
					[
						StatBar(TEXT("RATE"), [this]() { return ComputeStats().Rate; }, [this]() { return ComputeStats().BaseRate; })
					]
					+ SVerticalBox::Slot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 9.f))
					[
						StatBar(TEXT("CONTROL"), [this]() { return ComputeStats().Control; }, [this]() { return ComputeStats().BaseControl; })
					]
					+ SVerticalBox::Slot().AutoHeight()
					[
						StatBar(TEXT("HANDLING"), [this]() { return ComputeStats().Handling; }, [this]() { return ComputeStats().BaseHandling; })
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.Padding(FMargin(36.f, 0.f, 0.f, 0.f))
				.VAlign(VAlign_Center)
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot().FillWidth(1.f)
					[
						StatNumber(TEXT("MAGAZINE"), [this]()
						{
							return FString::Printf(TEXT("%d"), AirsoftWeapons::Resolve(CustomFor(ViewId)).MagSize);
						})
					]
					+ SHorizontalBox::Slot().FillWidth(1.f)
					[
						StatNumber(TEXT("RPM"), [this]()
						{
							const FAirsoftWeaponDef R = AirsoftWeapons::Resolve(CustomFor(ViewId));
							return FString::Printf(TEXT("%d"), FMath::RoundToInt(60.f / FMath::Max(R.FireInterval, 0.001f)));
						})
					]
					+ SHorizontalBox::Slot().FillWidth(1.f)
					[
						StatNumber(TEXT("VELOCITY"), [this]()
						{
							const FAirsoftWeaponDef R = AirsoftWeapons::Resolve(CustomFor(ViewId));
							return FString::Printf(TEXT("%d m/s"), FMath::RoundToInt(R.MuzzleVelocity / 100.f));
						})
					]
					+ SHorizontalBox::Slot().FillWidth(1.f)
					[
						StatNumber(TEXT("RELOAD"), [this]()
						{
							const FAirsoftWeaponDef R = AirsoftWeapons::Resolve(CustomFor(ViewId));
							return FString::Printf(TEXT("%.1f s"), R.ReloadTime);
						})
					]
				]
			]
		]
		// Attachments
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.f, 24.f, 0.f, 12.f))
		[
			AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("ATTACHMENTS")))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			Attachments
		]
		// Finishes
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.f, 12.f, 0.f, 12.f))
		[
			AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("FINISH")))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			BuildFinishes()
		];
}

TSharedRef<SWidget> SAirsoftArmory::BuildAttachmentRow(const FAirsoftWeaponDef& Def, FName Slot)
{
	using namespace AirsoftArmoryLocal;
	const TArray<FName>* Options = Def.Options.Find(Slot);
	const bool bRequired = Def.RequiredSlots.Contains(Slot);

	TSharedRef<SHorizontalBox> Choices = SNew(SHorizontalBox);
	if (Options)
	{
		for (const FName Choice : *Options)
		{
			if (Choice == AirsoftWeapons::AttachOff && bRequired)
			{
				continue;
			}
			const FAirsoftAttachmentDef* Attachment = AirsoftWeapons::FindAttachment(Choice);
			const FString Name = (Choice == AirsoftWeapons::AttachOff || !Attachment) ? FString(TEXT("None")) : Attachment->Name;
			Choices->AddSlot()
			.FillWidth(1.f)
			.Padding(FMargin(0.f, 0.f, 4.f, 0.f))
			[
				SNew(SBox)
				.HeightOverride(44.f)
				[
					SNew(SAirsoftButton)
					.ShowEdge(false)
					.ContentPadding(FMargin(8.f, 4.f))
					.IsSelected_Lambda([this, Slot, Choice]() { return GetSlotValue(CustomFor(ViewId), Slot) == Choice; })
					.OnClicked_Lambda([this, Slot, Choice]()
					{
						SetAttachment(Slot, Choice);
						return FReply::Handled();
					})
					[
						SNew(SBox)
						.VAlign(VAlign_Center)
						[
							SNew(STextBlock)
							.Text(FText::FromString(Name))
							.AutoWrapText(true)
							.Justification(ETextJustify::Center)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 9, 40))
							.ColorAndOpacity_Lambda([this, Slot, Choice]() -> FSlateColor
							{
								return GetSlotValue(CustomFor(ViewId), Slot) == Choice ? AUI::Accent() : AUI::TextColor();
							})
						]
					]
				]
			];
		}
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(110.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(AUI::Upper(Slot.ToString()))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 10, 220))
						.ColorAndOpacity(AUI::TextColor())
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Visibility(bRequired ? EVisibility::HitTestInvisible : EVisibility::Collapsed)
						.Text(FText::FromString(TEXT("REQUIRED")))
						.Font(AUI::Caption(7))
						.ColorAndOpacity(AUI::TextDim())
					]
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			[
				Choices
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(110.f, 5.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 10))
			.ColorAndOpacity(AUI::TextDim())
			.Text_Lambda([this, Slot]()
			{
				const FName Current = GetSlotValue(CustomFor(ViewId), Slot);
				const FAirsoftAttachmentDef* Attachment = AirsoftWeapons::FindAttachment(Current);
				return FText::FromString(Attachment ? Attachment->Blurb : FString(TEXT("Nothing fitted.")));
			})
		];
}

TSharedRef<SWidget> SAirsoftArmory::BuildFinishes()
{
	TSharedRef<SHorizontalBox> Box = SNew(SHorizontalBox);
	for (const FAirsoftSkinDef& Skin : AirsoftWeapons::Skins())
	{
		const FName SkinId = Skin.Id;
		const int32 Unlock = Skin.UnlockRank;
		const FLinearColor Primary(Skin.Primary.R, Skin.Primary.G, Skin.Primary.B, 1.f);
		const FLinearColor Secondary(Skin.Secondary.R, Skin.Secondary.G, Skin.Secondary.B, 1.f);
		Box->AddSlot()
		.FillWidth(1.f)
		.Padding(FMargin(0.f, 0.f, 6.f, 0.f))
		[
			SNew(SAirsoftButton)
			.ShowEdge(false)
			.ContentPadding(FMargin(6.f, 7.f))
			.IsSelected_Lambda([this, SkinId]() { return CustomFor(ViewId).Skin == SkinId; })
			.IsDimmed_Lambda([this, Unlock]() { return PlayerRank() < Unlock; })
			.OnClicked_Lambda([this, SkinId]()
			{
				SetSkin(SkinId);
				return FReply::Handled();
			})
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(SBorder)
					.BorderImage(AUI::NoBrush())
					.Padding(FMargin(0.f))
					.ColorAndOpacity_Lambda([this, Unlock]() -> FLinearColor
					{
						return FLinearColor(1.f, 1.f, 1.f, PlayerRank() < Unlock ? 0.3f : 1.f);
					})
					[
						SNew(SBox)
						.HeightOverride(30.f)
						[
							SNew(SBorder)
							.BorderImage(AUI::OutlineBrush())
							.BorderBackgroundColor(FLinearColor(1.f, 1.f, 1.f, 0.2f))
							.Padding(FMargin(1.f))
							[
								SNew(SHorizontalBox)
								+ SHorizontalBox::Slot()
								.FillWidth(0.68f)
								[
									SNew(SBorder)
									.BorderImage(AUI::WhiteBrush())
									.BorderBackgroundColor(Primary)
									.Padding(FMargin(0.f))
								]
								+ SHorizontalBox::Slot()
								.FillWidth(0.32f)
								[
									SNew(SBorder)
									.BorderImage(AUI::WhiteBrush())
									.BorderBackgroundColor(Secondary)
									.Padding(FMargin(0.f))
								]
							]
						]
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(AUI::Upper(Skin.Name))
					.AutoWrapText(true)
					.Justification(ETextJustify::Center)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 8, 80))
					.ColorAndOpacity_Lambda([this, SkinId, Unlock]() -> FSlateColor
					{
						if (PlayerRank() < Unlock)
						{
							return AUI::TextMuted();
						}
						return CustomFor(ViewId).Skin == SkinId ? AUI::Accent() : AUI::TextColor();
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 2.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Visibility_Lambda([this, Unlock]() -> EVisibility
					{
						return PlayerRank() < Unlock ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
					})
					.Text(FText::FromString(FString::Printf(TEXT("RANK %d"), Unlock)))
					.Font(AUI::Caption(7))
					.ColorAndOpacity(AUI::WithAlpha(AUI::Accent(), 0.7f))
				]
			]
		];
	}
	return Box;
}
