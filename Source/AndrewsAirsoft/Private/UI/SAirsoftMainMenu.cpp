// Andrew's Airsoft - title screen: host, join by IP, armory, settings, quit,
// call sign and the player's service record.

#include "AirsoftGameInstance.h"
#include "AirsoftPlayerController.h"
#include "AirsoftSaveGame.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "AirsoftWeaponData.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "IPAddress.h"
#include "SocketSubsystem.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftMainMenuLocal
{
	constexpr int32 MaxNameLength = 20;

	/** This PC's Tailscale (100.64.0.0/10) IPv4 addresses, space separated. */
	FString FindTailscaleAddresses()
	{
		ISocketSubsystem* Sockets = ISocketSubsystem::Get(PLATFORM_SOCKETSUBSYSTEM);
		if (!Sockets)
		{
			return FString();
		}
		TArray<TSharedPtr<FInternetAddr>> Addresses;
		if (!Sockets->GetLocalAdapterAddresses(Addresses))
		{
			return FString();
		}
		TArray<FString> Found;
		for (const TSharedPtr<FInternetAddr>& Addr : Addresses)
		{
			if (!Addr.IsValid())
			{
				continue;
			}
			const FString Text = Addr->ToString(false);
			TArray<FString> Parts;
			Text.ParseIntoArray(Parts, TEXT("."), true);
			if (Parts.Num() == 4 && Parts[0] == TEXT("100"))
			{
				const int32 Second = FCString::Atoi(*Parts[1]);
				if (Second >= 64 && Second <= 127)
				{
					Found.AddUnique(Text);
				}
			}
		}
		return FString::Join(Found, TEXT("   "));
	}
}

class SAirsoftMainMenu : public SAirsoftMenuBase
{
public:
	SLATE_BEGIN_ARGS(SAirsoftMainMenu) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

protected:
	/** Escape does nothing on the title screen. */
	virtual void HandleBack() override {}

private:
	TSharedRef<SWidget> BuildLeftColumn();
	TSharedRef<SWidget> BuildProfileCard();
	TSharedRef<SWidget> MakeStat(const FString& Label, TFunction<int32(const UAirsoftSaveGame&)> Getter);
	void Join();
	void SaveName(const FString& Raw);
	UAirsoftSaveGame* Profile() const;
	float FadeIn() const;

	TSharedPtr<SEditableTextBox> AddressBox;
	TSharedPtr<SEditableTextBox> NameBox;
	FString TailscaleIPs;
	FString LocalMessage;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateMainMenu(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftMainMenu, PC);
}

UAirsoftSaveGame* SAirsoftMainMenu::Profile() const
{
	return AUI::GetProfile(WeakPC.Get());
}

float SAirsoftMainMenu::FadeIn() const
{
	return AUI::Ease(static_cast<float>((FPlatformTime::Seconds() - OpenTime) / 0.35));
}

void SAirsoftMainMenu::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	OpenTime = FPlatformTime::Seconds();
	TailscaleIPs = AirsoftMainMenuLocal::FindTailscaleAddresses();
	ForceVolatile(true);

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SAirsoftBackdrop)
			.Opacity(0.9f)
			.ColumnWidth(0.4f)
		]
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.BorderImage(AUI::NoBrush())
			.Padding(FMargin(0.f))
			.ColorAndOpacity_Lambda([this]() -> FLinearColor { return FLinearColor(1.f, 1.f, 1.f, FadeIn()); })
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(FMargin(110.f, 84.f, 0.f, 56.f))
				[
					BuildLeftColumn()
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				[
					SNew(SSpacer)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Bottom)
				.Padding(FMargin(0.f, 0.f, 90.f, 72.f))
				[
					BuildProfileCard()
				]
			]
		]
	];
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildLeftColumn()
{
	UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
	const FString LastAddress = GI ? GI->GetUserSettings().LastJoinAddress : FString();

	TSharedPtr<SAirsoftButton> HostButton;

	TSharedRef<SWidget> Column = SNew(SBox)
		.WidthOverride(440.f)
		[
			SNew(SVerticalBox)
			// Title treatment
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("PRIVATE MATCHES  \u00B7  FRIENDS ONLY")))
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 22.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(TEXT("ANDREW'S")))
				.Font(AUI::Font(AUI::EFontWeight::Light, 40, 900))
				.ColorAndOpacity(AUI::TextColor())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 0.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(TEXT("AIRSOFT")))
				.Font(AUI::Font(AUI::EFontWeight::Bold, 78, 260))
				.ColorAndOpacity(FLinearColor::White)
				.ShadowOffset(FVector2D(0.f, 3.f))
				.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.6f))
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(4.f, 4.f, 0.f, 0.f))
			[
				AirsoftUIWidgets::AccentRule(132.f, 2.f)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(4.f, 14.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(TEXT("Every hit is called. Every call is honoured.")))
				.Font(AUI::Font(AUI::EFontWeight::Light, 14, 40))
				.ColorAndOpacity(AUI::TextDim())
			]
			// Disconnect / error message
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(4.f, 18.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.AutoWrapText(true)
				.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 20))
				.ColorAndOpacity(AUI::Accent())
				.Visibility_Lambda([this]() -> EVisibility
				{
					const UAirsoftGameInstance* G = AUI::GetGameInstance(WeakPC.Get());
					const bool bShow = !LocalMessage.IsEmpty() || (G && !G->PendingMenuMessage.IsEmpty());
					return bShow ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
				})
				.Text_Lambda([this]()
				{
					if (!LocalMessage.IsEmpty())
					{
						return FText::FromString(LocalMessage);
					}
					const UAirsoftGameInstance* G = AUI::GetGameInstance(WeakPC.Get());
					return G ? FText::FromString(G->PendingMenuMessage) : FText::GetEmpty();
				})
			]
			// Buttons
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 36.f, 0.f, 0.f))
			[
				SAssignNew(HostButton, SAirsoftButton)
				.Text(FText::FromString(TEXT("HOST GAME")))
				.SubText(FText::FromString(TEXT("YOU ARE THE SERVER")))
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (UAirsoftGameInstance* G = AUI::GetGameInstance(WeakPC.Get()))
					{
						G->PendingMenuMessage.Reset();
						G->HostGame();
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.VAlign(VAlign_Fill)
				.Padding(FMargin(0.f, 0.f, 6.f, 0.f))
				[
					SAssignNew(AddressBox, SEditableTextBox)
					.Style(&AUI::TextBoxStyle())
					.Font(AUI::Font(AUI::EFontWeight::Regular, 13, 40))
					.ForegroundColor(AUI::TextColor())
					.BackgroundColor(FLinearColor::White)
					.Text(FText::FromString(LastAddress))
					.HintText(FText::FromString(TEXT("Host IP, e.g. 100.101.102.103")))
					.SelectAllTextWhenFocused(true)
					.ClearKeyboardFocusOnCommit(false)
					.OnTextCommitted_Lambda([this](const FText& NewText, ETextCommit::Type CommitType)
					{
						if (CommitType == ETextCommit::OnEnter)
						{
							Join();
						}
					})
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(120.f)
					[
						SNew(SAirsoftButton)
						.Text(FText::FromString(TEXT("JOIN")))
						.FontSize(14)
						.HAlign(HAlign_Center)
						.OnClicked_Lambda([this]()
						{
							Join();
							return FReply::Handled();
						})
					]
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Text(FText::FromString(TEXT("ARMORY")))
				.SubText(FText::FromString(TEXT("LOADOUT & FINISHES")))
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (AAirsoftPlayerController* PC = WeakPC.Get())
					{
						PC->OpenArmory();
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Text(FText::FromString(TEXT("SETTINGS")))
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (AAirsoftPlayerController* PC = WeakPC.Get())
					{
						PC->ShowMenu(EAirsoftMenu::Settings);
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Text(FText::FromString(TEXT("QUIT")))
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (UAirsoftGameInstance* G = AUI::GetGameInstance(WeakPC.Get()))
					{
						G->SaveProfile();
					}
					FPlatformMisc::RequestExit(false);
					return FReply::Handled();
				})
			]
			// Help
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(4.f, 30.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.AutoWrapText(true)
				.Text(FText::FromString(TEXT("Friends join over Tailscale: share your 100.x.y.z address")))
				.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 20))
				.ColorAndOpacity(AUI::TextDim())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(4.f, 6.f, 0.f, 0.f))
			[
				SNew(SHorizontalBox)
				.Visibility(TailscaleIPs.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("YOUR TAILSCALE IP")))
					.Font(AUI::Caption(8))
					.ColorAndOpacity(AUI::TextDim())
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(12.f, 0.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(TailscaleIPs))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 12, 60))
					.ColorAndOpacity(AUI::Accent())
				]
			]
		];

	SetInitialFocus(HostButton);
	return Column;
}

TSharedRef<SWidget> SAirsoftMainMenu::MakeStat(const FString& Label, TFunction<int32(const UAirsoftSaveGame&)> Getter)
{
	return AirsoftUIWidgets::StatBlock(
		FText::FromString(Label),
		TAttribute<FText>::CreateLambda([this, Getter]()
		{
			const UAirsoftSaveGame* P = Profile();
			return FText::AsNumber(P ? Getter(*P) : 0);
		}),
		18);
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildProfileCard()
{
	UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
	FString InitialName = GI ? GI->GetUserSettings().PlayerName : FString();
	if (InitialName.IsEmpty() && GI)
	{
		InitialName = GI->GetPlayerName();
	}

	return SNew(SBox)
		.WidthOverride(420.f)
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(24.f, 20.f, 24.f, 22.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("CALL SIGN")))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 10.f, 0.f, 0.f))
				[
					SAssignNew(NameBox, SEditableTextBox)
					.Style(&AUI::TextBoxStyle())
					.Font(AUI::Font(AUI::EFontWeight::Bold, 14, 100))
					.ForegroundColor(FLinearColor::White)
					.BackgroundColor(FLinearColor::White)
					.Text(FText::FromString(InitialName.Left(AirsoftMainMenuLocal::MaxNameLength)))
					.HintText(FText::FromString(TEXT("Your call sign")))
					.SelectAllTextWhenFocused(true)
					.ClearKeyboardFocusOnCommit(false)
					.OnTextChanged_Lambda([this](const FText& NewText)
					{
						const FString S = NewText.ToString();
						if (S.Len() > AirsoftMainMenuLocal::MaxNameLength && NameBox.IsValid())
						{
							NameBox->SetText(FText::FromString(S.Left(AirsoftMainMenuLocal::MaxNameLength)));
						}
					})
					.OnTextCommitted_Lambda([this](const FText& NewText, ETextCommit::Type CommitType)
					{
						if (CommitType == ETextCommit::OnEnter || CommitType == ETextCommit::OnUserMovedFocus)
						{
							SaveName(NewText.ToString());
						}
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("Up to 20 characters. Shown to everyone in the match.")))
					.Font(AUI::Font(AUI::EFontWeight::Regular, 9, 20))
					.ColorAndOpacity(AUI::TextDim())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 20.f, 0.f, 18.f))
				[
					AirsoftUIWidgets::Rule(AUI::Hairline())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("SERVICE RECORD")))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 10.f, 0.f, 0.f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.FillWidth(1.f)
					.VAlign(VAlign_Bottom)
					[
						SNew(STextBlock)
						.Font(AUI::Font(AUI::EFontWeight::Bold, 22, 160))
						.ColorAndOpacity(FLinearColor::White)
						.Text_Lambda([this]()
						{
							const UAirsoftSaveGame* P = Profile();
							return AUI::Upper(AUI::RankName(AirsoftWeapons::RankIndexForXP(P ? P->XP : 0)));
						})
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Bottom)
					.Padding(FMargin(0.f, 0.f, 0.f, 4.f))
					[
						SNew(STextBlock)
						.Font(AUI::Caption(8))
						.ColorAndOpacity(AUI::TextDim())
						.Text_Lambda([this]()
						{
							const UAirsoftSaveGame* P = Profile();
							return FText::FromString(FString::Printf(TEXT("RANK %d OF %d"),
								AirsoftWeapons::RankIndexForXP(P ? P->XP : 0), AirsoftWeapons::Ranks().Num()));
						})
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 10.f, 0.f, 0.f))
				[
					SNew(SAirsoftBar)
					.Width(372.f)
					.Height(4.f)
					.Fraction_Lambda([this]()
					{
						const UAirsoftSaveGame* P = Profile();
						return AUI::RankProgress(P ? P->XP : 0);
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Caption(8))
					.ColorAndOpacity(AUI::TextDim())
					.Text_Lambda([this]()
					{
						const UAirsoftSaveGame* P = Profile();
						const int32 XP = P ? P->XP : 0;
						const int32 Next = AUI::NextRankXP(XP);
						if (Next < 0)
						{
							return FText::FromString(FString::Printf(TEXT("%s XP  \u00B7  HIGHEST RANK"), *FText::AsNumber(XP).ToString()));
						}
						const FString NextName = AUI::RankName(AirsoftWeapons::RankIndexForXP(XP) + 1).ToUpper();
						return FText::FromString(FString::Printf(TEXT("%s XP  \u00B7  %s TO %s"),
							*FText::AsNumber(XP).ToString(), *FText::AsNumber(Next - XP).ToString(), *NextName));
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 18.f, 0.f, 0.f))
				[
					SNew(SUniformGridPanel)
					.SlotPadding(FMargin(0.f, 0.f, 12.f, 12.f))
					+ SUniformGridPanel::Slot(0, 0)
					[
						MakeStat(TEXT("TAGS"), [](const UAirsoftSaveGame& P) { return P.Tags; })
					]
					+ SUniformGridPanel::Slot(1, 0)
					[
						MakeStat(TEXT("OUTS"), [](const UAirsoftSaveGame& P) { return P.Outs; })
					]
					+ SUniformGridPanel::Slot(2, 0)
					[
						MakeStat(TEXT("WINS"), [](const UAirsoftSaveGame& P) { return P.Wins; })
					]
					+ SUniformGridPanel::Slot(0, 1)
					[
						MakeStat(TEXT("MATCHES"), [](const UAirsoftSaveGame& P) { return P.Matches; })
					]
					+ SUniformGridPanel::Slot(1, 1)
					[
						MakeStat(TEXT("CAPTURES"), [](const UAirsoftSaveGame& P) { return P.Captures; })
					]
					+ SUniformGridPanel::Slot(2, 1)
					[
						MakeStat(TEXT("BEST STREAK"), [](const UAirsoftSaveGame& P) { return P.BestStreak; })
					]
				]
			]
		];
}

void SAirsoftMainMenu::Join()
{
	UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
	if (!GI || !AddressBox.IsValid())
	{
		return;
	}
	const FString Address = AddressBox->GetText().ToString().TrimStartAndEnd();
	if (Address.IsEmpty())
	{
		LocalMessage = TEXT("Enter the host's address first, e.g. 100.101.102.103");
		return;
	}
	// Save the call sign too, in case it was edited without pressing Enter.
	if (NameBox.IsValid())
	{
		SaveName(NameBox->GetText().ToString());
	}
	LocalMessage = FString::Printf(TEXT("Connecting to %s..."), *Address);
	GI->PendingMenuMessage.Reset();
	GI->JoinGame(Address);
}

void SAirsoftMainMenu::SaveName(const FString& Raw)
{
	UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
	if (!GI)
	{
		return;
	}
	const FString Clean = Raw.TrimStartAndEnd().Left(AirsoftMainMenuLocal::MaxNameLength);
	FAirsoftUserSettings Settings = GI->GetUserSettings();
	if (Settings.PlayerName == Clean)
	{
		return;
	}
	Settings.PlayerName = Clean;
	GI->SetUserSettings(Settings);
}
