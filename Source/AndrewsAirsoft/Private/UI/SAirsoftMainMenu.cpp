// Andrew's Airsoft - title screen. The story leads: Continue, New Game (with a
// difficulty), Mission Select, then Skirmish against bots, the Practice Range,
// Armory, Settings and Quit, plus the call sign and service record. Host / Join
// and the Tailscale address only show when multiplayer is switched on
// (UAirsoftSettings::bEnableMultiplayer, developer only).

#include "AirsoftAssets.h"
#include "AirsoftCampaign.h"
#include "AirsoftGameInstance.h"
#include "AirsoftModeRules.h"
#include "AirsoftPlayerController.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "AirsoftWeaponData.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "IPAddress.h"
#include "SocketSubsystem.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/Layout/SWidgetSwitcher.h"
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
	/** Escape steps back from a sub-page; on the title page it does nothing. */
	virtual void HandleBack() override;

private:
	/** The left column's pages. */
	enum class EPage : int32
	{
		Home,
		NewGame,
		Missions,
		Skirmish,
		Practice
	};

	TSharedRef<SWidget> BuildLeftColumn();
	TSharedRef<SWidget> BuildHomePage();
	TSharedRef<SWidget> BuildNewGamePage();
	TSharedRef<SWidget> BuildMissionsPage();
	TSharedRef<SWidget> BuildSkirmishPage();
	TSharedRef<SWidget> BuildPracticePage();
	/** Page heading with a BACK button. */
	TSharedRef<SWidget> PageHeader(const FString& Title, const FString& Note);
	/** Label above a row of choice buttons. */
	TSharedRef<SWidget> ChoiceLabel(const FString& Label);
	TSharedRef<SWidget> MenuButton(const FText& Text, const TAttribute<FText>& SubText, TFunction<void()> OnClick, TSharedPtr<SAirsoftButton>* OutButton = nullptr);
	void ShowPage(EPage NewPage);
	UAirsoftGameInstance* GI() const { return AUI::GetGameInstance(WeakPC.Get()); }
	/** Continue has something to resume (a later mission or a mid-mission checkpoint). */
	bool HasProgress() const;
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

	EPage Page = EPage::Home;
	/** First button of each page, focused when the page opens (keyboard / gamepad). */
	TMap<EPage, TSharedPtr<SAirsoftButton>> PageFocus;
	/** Choices on the New Game and Skirmish pages (start from the saved settings). */
	int32 PickDifficulty = 1;
	int32 PickMode = 0;
	int32 PickMap = 0;
	int32 PickBots = 2;
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
	if (UAirsoftSettings::IsMultiplayerEnabled())
	{
		TailscaleIPs = AirsoftMainMenuLocal::FindTailscaleAddresses();
	}
	if (UAirsoftGameInstance* G = AUI::GetGameInstance(InPC))
	{
		const FAirsoftUserSettings& S = G->GetUserSettings();
		PickDifficulty = FMath::Clamp(S.Difficulty, 0, AirsoftDifficulty::Num - 1);
		PickBots = FMath::Clamp(S.BotFill, 1, AirsoftBots::NumFillOptions - 1);
	}
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

bool SAirsoftMainMenu::HasProgress() const
{
	UAirsoftGameInstance* G = GI();
	const UAirsoftSaveGame* P = Profile();
	return (G && G->GetContinueMission() > 1) || (P && P->CheckpointMission > 0);
}

void SAirsoftMainMenu::HandleBack()
{
	if (Page != EPage::Home)
	{
		ShowPage(EPage::Home);
	}
}

void SAirsoftMainMenu::ShowPage(EPage NewPage)
{
	Page = NewPage;
	LocalMessage.Reset();
	const TSharedPtr<SAirsoftButton>* Focus = PageFocus.Find(NewPage);
	if (Focus && Focus->IsValid() && FSlateApplication::IsInitialized())
	{
		FSlateApplication::Get().SetKeyboardFocus((*Focus)->GetButton(), EFocusCause::SetDirectly);
	}
	if (AAirsoftPlayerController* PC = WeakPC.Get())
	{
		AirsoftAssets::Play2D(PC, TEXT("UIClick"), 0.35f, 1.f);
	}
}

TSharedRef<SWidget> SAirsoftMainMenu::MenuButton(const FText& Text, const TAttribute<FText>& SubText, TFunction<void()> OnClick, TSharedPtr<SAirsoftButton>* OutButton)
{
	TSharedPtr<SAirsoftButton> Button;
	TSharedRef<SWidget> Widget = SNew(SBox)
		.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
		[
			SAssignNew(Button, SAirsoftButton)
			.Text(Text)
			.SubText(SubText)
			.FontSize(14)
			.OnClicked_Lambda([OnClick]()
			{
				OnClick();
				return FReply::Handled();
			})
		];
	if (OutButton)
	{
		*OutButton = Button;
	}
	return Widget;
}

TSharedRef<SWidget> SAirsoftMainMenu::PageHeader(const FString& Title, const FString& Note)
{
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(FText::FromString(Title))
				.Font(AUI::Font(AUI::EFontWeight::Bold, 22, 220))
				.ColorAndOpacity(FLinearColor::White)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(110.f)
				[
					SNew(SAirsoftButton)
					.Text(FText::FromString(TEXT("BACK")))
					.FontSize(11)
					.HAlign(HAlign_Center)
					.ShowEdge(false)
					.ContentPadding(FMargin(8.f, 6.f))
					.OnClicked_Lambda([this]()
					{
						ShowPage(EPage::Home);
						return FReply::Handled();
					})
				]
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.f, 6.f, 0.f, 4.f))
		[
			SNew(STextBlock)
			.Visibility(Note.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible)
			.AutoWrapText(true)
			.Text(FText::FromString(Note))
			.Font(AUI::Font(AUI::EFontWeight::Regular, 11, 20))
			.ColorAndOpacity(AUI::TextDim())
		];
}

TSharedRef<SWidget> SAirsoftMainMenu::ChoiceLabel(const FString& Label)
{
	return SNew(SBox)
		.Padding(FMargin(2.f, 14.f, 0.f, 6.f))
		[
			SNew(STextBlock)
			.Text(FText::FromString(Label))
			.Font(AUI::Caption(8))
			.ColorAndOpacity(AUI::TextDim())
		];
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildLeftColumn()
{
	return SNew(SBox)
		.WidthOverride(440.f)
		[
			SNew(SVerticalBox)
			// Title treatment
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("A STORY CAMPAIGN  ·  SINGLE PLAYER")))
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 22.f, 0.f, 0.f))
			[
				// Wide-tracked title: shrink to the column rather than clip the last letters.
				SNew(SScaleBox)
				.Stretch(EStretch::ScaleToFit)
				.StretchDirection(EStretchDirection::DownOnly)
				.HAlign(HAlign_Left)
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("ANDREW")))
					.Font(AUI::Font(AUI::EFontWeight::Light, 40, 900))
					.ColorAndOpacity(AUI::TextColor())
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(SScaleBox)
				.Stretch(EStretch::ScaleToFit)
				.StretchDirection(EStretchDirection::DownOnly)
				.HAlign(HAlign_Left)
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("LAST CONTRACT")))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 78, 260))
					.ColorAndOpacity(FLinearColor::White)
					.ShadowOffset(FVector2D(0.f, 3.f))
					.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.6f))
				]
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
				.Text(FText::FromString(TEXT("Five years out. One debt left to settle.")))
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
					const UAirsoftGameInstance* G = GI();
					const bool bShow = !LocalMessage.IsEmpty() || (G && !G->PendingMenuMessage.IsEmpty());
					return bShow ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
				})
				.Text_Lambda([this]()
				{
					if (!LocalMessage.IsEmpty())
					{
						return FText::FromString(LocalMessage);
					}
					const UAirsoftGameInstance* G = GI();
					return G ? FText::FromString(G->PendingMenuMessage) : FText::GetEmpty();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 28.f, 0.f, 0.f))
			[
				SNew(SWidgetSwitcher)
				.WidgetIndex_Lambda([this]() { return static_cast<int32>(Page); })
				+ SWidgetSwitcher::Slot()[BuildHomePage()]
				+ SWidgetSwitcher::Slot()[BuildNewGamePage()]
				+ SWidgetSwitcher::Slot()[BuildMissionsPage()]
				+ SWidgetSwitcher::Slot()[BuildSkirmishPage()]
				+ SWidgetSwitcher::Slot()[BuildPracticePage()]
			]
		];
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildHomePage()
{
	TSharedPtr<SAirsoftButton> ContinueButton;
	TSharedPtr<SAirsoftButton> NewGameButton;
	const bool bMultiplayer = UAirsoftSettings::IsMultiplayerEnabled();

	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	// Continue: the furthest mission, from its last checkpoint when there is one.
	Box->AddSlot()
	.AutoHeight()
	[
		SNew(SBox)
		.Visibility_Lambda([this]() { return HasProgress() ? EVisibility::Visible : EVisibility::Collapsed; })
		[
			MenuButton(FText::FromString(TEXT("CONTINUE")),
				TAttribute<FText>::CreateLambda([this]()
				{
					UAirsoftGameInstance* G = GI();
					const UAirsoftSaveGame* P = Profile();
					const bool bCheckpoint = P && P->CheckpointMission > 0;
					const int32 Number = bCheckpoint ? P->CheckpointMission : (G ? G->GetContinueMission() : 1);
					const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(Number);
					return FText::FromString(FString::Printf(TEXT("MISSION %d · %s%s"), Number, Mission ? *Mission->Title.ToUpper() : TEXT(""),
						bCheckpoint ? TEXT(" · CHECKPOINT") : TEXT("")));
				}),
				[this]()
				{
					if (UAirsoftGameInstance* G = GI())
					{
						const UAirsoftSaveGame* P = Profile();
						G->StartMission((P && P->CheckpointMission > 0) ? P->CheckpointMission : G->GetContinueMission());
					}
				}, &ContinueButton)
		]
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("NEW GAME")),
			TAttribute<FText>::CreateLambda([this]() { return FText::FromString(HasProgress() ? TEXT("FROM MISSION 1") : TEXT("BEGIN THE STORY")); }),
			[this]() { ShowPage(EPage::NewGame); }, &NewGameButton)
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("MISSION SELECT")),
			TAttribute<FText>::CreateLambda([this]()
			{
				UAirsoftGameInstance* G = GI();
				const int32 Count = AirsoftCampaign::Missions().Num();
				const int32 Open = G ? FMath::Min(G->GetContinueMission(), Count) : 1;
				return FText::FromString(FString::Printf(TEXT("%d OF %d UNLOCKED"), Open, Count));
			}),
			[this]() { ShowPage(EPage::Missions); })
	];
	Box->AddSlot().AutoHeight().Padding(FMargin(0.f, 14.f, 0.f, 0.f))
	[
		MenuButton(FText::FromString(TEXT("SKIRMISH")), FText::FromString(TEXT("YOU AND BOTS")),
			[this]() { ShowPage(EPage::Skirmish); })
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("PRACTICE RANGE")),
			TAttribute<FText>::CreateLambda([this]()
			{
				const UAirsoftSaveGame* P = Profile();
				return FText::FromString((P && P->Settings.bTutorialDone) ? TEXT("FIRING LANES") : TEXT("LEARN THE CONTROLS"));
			}),
			[this]() { ShowPage(EPage::Practice); })
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("ARMORY")), FText::FromString(TEXT("LOADOUT & FINISHES")),
			[this]()
			{
				if (AAirsoftPlayerController* PC = WeakPC.Get())
				{
					PC->OpenArmory();
				}
			})
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("SETTINGS")), FText::GetEmpty(),
			[this]()
			{
				if (AAirsoftPlayerController* PC = WeakPC.Get())
				{
					PC->ShowMenu(EAirsoftMenu::Settings);
				}
			})
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("QUIT")), FText::GetEmpty(),
			[this]()
			{
				if (UAirsoftGameInstance* G = GI())
				{
					G->SaveProfile();
				}
				FPlatformMisc::RequestExit(false);
			})
	];

	// Developer only: the online code is kept, and shows here when multiplayer is switched on.
	if (bMultiplayer)
	{
		Box->AddSlot().AutoHeight().Padding(FMargin(0.f, 22.f, 0.f, 8.f))
		[
			AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("MULTIPLAYER  ·  DEV")))
		];
		Box->AddSlot().AutoHeight()
		[
			MenuButton(FText::FromString(TEXT("HOST")),
				FText::FromString(TailscaleIPs.IsEmpty() ? FString(TEXT("NO TAILSCALE ADDRESS")) : TailscaleIPs),
				[this]()
				{
					if (UAirsoftGameInstance* G = GI())
					{
						if (NameBox.IsValid())
						{
							SaveName(NameBox->GetText().ToString());
						}
						G->HostGame();
					}
				})
		];
		Box->AddSlot().AutoHeight().Padding(FMargin(0.f, 6.f, 0.f, 0.f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			[
				SAssignNew(AddressBox, SEditableTextBox)
				.Style(&AUI::TextBoxStyle())
				.Font(AUI::Font(AUI::EFontWeight::Bold, 13, 60))
				.ForegroundColor(FLinearColor::White)
				.BackgroundColor(FLinearColor::White)
				.HintText(FText::FromString(TEXT("Host address, e.g. 100.101.102.103")))
				.Text(FText::FromString(GI() ? GI()->GetUserSettings().LastJoinAddress : FString()))
				.OnTextCommitted_Lambda([this](const FText&, ETextCommit::Type CommitType)
				{
					if (CommitType == ETextCommit::OnEnter)
					{
						Join();
					}
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(6.f, 0.f, 0.f, 0.f))
			[
				SNew(SBox)
				.WidthOverride(110.f)
				[
					SNew(SAirsoftButton)
					.Text(FText::FromString(TEXT("JOIN")))
					.FontSize(12)
					.HAlign(HAlign_Center)
					.OnClicked_Lambda([this]()
					{
						Join();
						return FReply::Handled();
					})
				]
			]
		];
	}

	Box->AddSlot()
	.AutoHeight()
	.Padding(FMargin(4.f, 26.f, 0.f, 0.f))
	[
		SNew(STextBlock)
		.AutoWrapText(true)
		.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 20))
		.ColorAndOpacity(AUI::TextDim())
		.Text_Lambda([this]()
		{
			UAirsoftGameInstance* G = GI();
			const int32 Difficulty = G ? G->GetUserSettings().Difficulty : 1;
			return FText::FromString(FString::Printf(TEXT("LAST CONTRACT · A story in %d missions · Difficulty %s"),
				AirsoftCampaign::Missions().Num(), *AirsoftDifficulty::Label(AirsoftDifficulty::FromIndex(Difficulty))));
		})
	];

	// Keyboard / gamepad start on Continue when there is one, else New Game.
	SetInitialFocus(HasProgress() ? ContinueButton : NewGameButton);
	PageFocus.Add(EPage::Home, HasProgress() ? ContinueButton : NewGameButton);
	return Box;
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildNewGamePage()
{
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()
	[
		PageHeader(TEXT("NEW GAME"), TEXT("Pick how hard the story fights back. You can change it later in Settings."))
	];
	TSharedPtr<SAirsoftButton> First;
	for (int32 i = 0; i < AirsoftDifficulty::Num; ++i)
	{
		const EAirsoftDifficulty Difficulty = AirsoftDifficulty::FromIndex(i);
		TSharedPtr<SAirsoftButton> Button;
		Box->AddSlot().AutoHeight().Padding(FMargin(0.f, i == 0 ? 10.f : 4.f, 0.f, 0.f))
		[
			SAssignNew(Button, SAirsoftButton)
			.Text(FText::FromString(AirsoftDifficulty::Label(Difficulty)))
			.SubText(FText::FromString(AirsoftDifficulty::Blurb(Difficulty).ToUpper()))
			.FontSize(13)
			.IsSelected_Lambda([this, i]() { return PickDifficulty == i; })
			.OnClicked_Lambda([this, i]()
			{
				PickDifficulty = i;
				return FReply::Handled();
			})
		];
		if (i == 1)
		{
			First = Button;
		}
	}
	Box->AddSlot().AutoHeight().Padding(FMargin(4.f, 14.f, 0.f, 0.f))
	[
		SNew(STextBlock)
		.AutoWrapText(true)
		.Visibility_Lambda([this]() { return HasProgress() ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
		.Text(FText::FromString(TEXT("Starts the story again from Mission 1 and clears the last checkpoint. Unlocked missions stay in Mission Select.")))
		.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 20))
		.ColorAndOpacity(AUI::Accent())
	];
	Box->AddSlot().AutoHeight().Padding(FMargin(0.f, 10.f, 0.f, 0.f))
	[
		MenuButton(FText::FromString(TEXT("BEGIN")), FText::FromString(TEXT("MISSION 1")),
			[this]()
			{
				if (UAirsoftGameInstance* G = GI())
				{
					G->StartNewGame(AirsoftDifficulty::FromIndex(PickDifficulty));
				}
			})
	];
	PageFocus.Add(EPage::NewGame, First);
	return Box;
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildMissionsPage()
{
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()
	[
		PageHeader(TEXT("MISSION SELECT"), TEXT("Replay any mission you have reached."))
	];
	TSharedPtr<SAirsoftButton> First;
	const TArray<AirsoftCampaign::FMission>& Missions = AirsoftCampaign::Missions();
	for (int32 i = 0; i < Missions.Num(); ++i)
	{
		const int32 Number = i + 1;
		const FString Title = Missions[i].Title.ToUpper();
		TSharedPtr<SAirsoftButton> Button;
		Box->AddSlot().AutoHeight().Padding(FMargin(0.f, i == 0 ? 10.f : 4.f, 0.f, 0.f))
		[
			SAssignNew(Button, SAirsoftButton)
			.Text(FText::FromString(FString::Printf(TEXT("%d  ·  %s"), Number, *Title)))
			.FontSize(13)
			.IsDimmed_Lambda([this, Number]()
			{
				UAirsoftGameInstance* G = GI();
				return !G || Number > G->GetContinueMission();
			})
			.SubText_Lambda([this, Number]()
			{
				UAirsoftGameInstance* G = GI();
				const bool bLocked = !G || Number > G->GetContinueMission();
				return FText::FromString(bLocked ? TEXT("LOCKED") : TEXT("PLAY"));
			})
			.OnClicked_Lambda([this, Number]()
			{
				UAirsoftGameInstance* G = GI();
				if (!G || Number > G->GetContinueMission())
				{
					LocalMessage = TEXT("Finish the mission before it to unlock this one.");
					return FReply::Handled();
				}
				G->StartMission(Number);
				return FReply::Handled();
			})
		];
		if (i == 0)
		{
			First = Button;
		}
	}
	PageFocus.Add(EPage::Missions, First);
	return Box;
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildSkirmishPage()
{
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()
	[
		PageHeader(TEXT("SKIRMISH"), TEXT("An offline match against bots on this PC."))
	];

	auto Choice = [](const FString& Label, TFunction<bool()> IsSelected, TFunction<bool()> IsDimmed, TFunction<void()> OnPick)
	{
		return SNew(SAirsoftButton)
			.Text(FText::FromString(Label))
			.FontSize(10)
			.HAlign(HAlign_Center)
			.ShowEdge(false)
			.ContentPadding(FMargin(6.f, 7.f))
			.IsSelected_Lambda([IsSelected]() { return IsSelected(); })
			.IsDimmed_Lambda([IsDimmed]() { return IsDimmed(); })
			.OnClicked_Lambda([OnPick]()
			{
				OnPick();
				return FReply::Handled();
			});
	};

	// Mode: a 3 + 2 grid.
	TSharedRef<SUniformGridPanel> Modes = SNew(SUniformGridPanel).SlotPadding(FMargin(0.f, 0.f, 4.f, 4.f));
	TSharedPtr<SAirsoftButton> First;
	for (int32 i = 0; i < AirsoftRules::NumModes; ++i)
	{
		TSharedRef<SAirsoftButton> Button = Choice(AirsoftRules::ModeName(AirsoftRules::ModeFromIndex(i)).ToUpper(),
			[this, i]() { return PickMode == i; },
			[]() { return false; },
			[this, i]()
			{
				PickMode = i;
				// Keep the map valid for the mode.
				const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
				if (Maps.IsValidIndex(PickMap) && !Maps[PickMap].SupportsMode(AirsoftRules::ModeFromIndex(i)))
				{
					for (int32 m = 0; m < Maps.Num(); ++m)
					{
						if (Maps[m].SupportsMode(AirsoftRules::ModeFromIndex(i)))
						{
							PickMap = m;
							break;
						}
					}
				}
			});
		if (i == 0)
		{
			First = Button;
		}
		Modes->AddSlot(i % 3, i / 3)[Button];
	}
	Box->AddSlot().AutoHeight()[ChoiceLabel(TEXT("MODE"))];
	Box->AddSlot().AutoHeight()[Modes];
	Box->AddSlot().AutoHeight().Padding(FMargin(2.f, 2.f, 0.f, 0.f))
	[
		SNew(STextBlock)
		.AutoWrapText(true)
		.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 20))
		.ColorAndOpacity(AUI::TextDim())
		.Text_Lambda([this]() { return FText::FromString(AirsoftRules::ModeBlurb(AirsoftRules::ModeFromIndex(PickMode))); })
	];

	TSharedRef<SUniformGridPanel> Maps = SNew(SUniformGridPanel).SlotPadding(FMargin(0.f, 0.f, 4.f, 4.f));
	const TArray<FAirsoftMapInfo>& MapList = AirsoftRules::Maps();
	for (int32 i = 0; i < MapList.Num(); ++i)
	{
		Maps->AddSlot(i, 0)
		[
			Choice(AirsoftRules::MapDisplayName(MapList[i].Key).ToUpper(),
				[this, i]() { return PickMap == i; },
				[this, i]()
				{
					const TArray<FAirsoftMapInfo>& List = AirsoftRules::Maps();
					return List.IsValidIndex(i) && !List[i].SupportsMode(AirsoftRules::ModeFromIndex(PickMode));
				},
				[this, i]() { PickMap = i; })
		];
	}
	Box->AddSlot().AutoHeight()[ChoiceLabel(TEXT("MAP"))];
	Box->AddSlot().AutoHeight()[Maps];

	TSharedRef<SUniformGridPanel> Bots = SNew(SUniformGridPanel).SlotPadding(FMargin(0.f, 0.f, 4.f, 4.f));
	for (int32 Fill = 1; Fill < AirsoftBots::NumFillOptions; ++Fill)
	{
		Bots->AddSlot(Fill - 1, 0)
		[
			Choice(AirsoftBots::FillLabel(Fill),
				[this, Fill]() { return PickBots == Fill; },
				[]() { return false; },
				[this, Fill]() { PickBots = Fill; })
		];
	}
	Box->AddSlot().AutoHeight()[ChoiceLabel(TEXT("TEAM SIZE  ·  YOU PLUS BOTS"))];
	Box->AddSlot().AutoHeight()[Bots];

	TSharedRef<SUniformGridPanel> Difficulty = SNew(SUniformGridPanel).SlotPadding(FMargin(0.f, 0.f, 4.f, 4.f));
	for (int32 i = 0; i < AirsoftDifficulty::Num; ++i)
	{
		Difficulty->AddSlot(i, 0)
		[
			Choice(AirsoftDifficulty::Label(AirsoftDifficulty::FromIndex(i)),
				[this, i]() { return PickDifficulty == i; },
				[]() { return false; },
				[this, i]() { PickDifficulty = i; })
		];
	}
	Box->AddSlot().AutoHeight()[ChoiceLabel(TEXT("BOT DIFFICULTY"))];
	Box->AddSlot().AutoHeight()[Difficulty];

	Box->AddSlot().AutoHeight().Padding(FMargin(0.f, 10.f, 0.f, 0.f))
	[
		MenuButton(FText::FromString(TEXT("START SKIRMISH")),
			TAttribute<FText>::CreateLambda([this]()
			{
				const TArray<FAirsoftMapInfo>& List = AirsoftRules::Maps();
				const FString Map = List.IsValidIndex(PickMap) ? AirsoftRules::MapDisplayName(List[PickMap].Key).ToUpper() : FString();
				return FText::FromString(Map + TEXT(" · ") + AirsoftBots::FillLabel(PickBots));
			}),
			[this]()
			{
				if (UAirsoftGameInstance* G = GI())
				{
					G->StartSkirmish(AirsoftRules::ModeFromIndex(PickMode), PickMap, PickBots, AirsoftDifficulty::FromIndex(PickDifficulty));
				}
			})
	];
	PageFocus.Add(EPage::Skirmish, First);
	return Box;
}

TSharedRef<SWidget> SAirsoftMainMenu::BuildPracticePage()
{
	TSharedPtr<SAirsoftButton> First;
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	Box->AddSlot().AutoHeight()
	[
		PageHeader(TEXT("PRACTICE RANGE"), TEXT("Steel plates down the lanes, every gun in the armory, and nobody shooting back."))
	];
	Box->AddSlot().AutoHeight().Padding(FMargin(0.f, 4.f, 0.f, 0.f))
	[
		MenuButton(FText::FromString(TEXT("HOW TO PLAY")), FText::FromString(TEXT("STEP BY STEP · 2 MINUTES")),
			[this]()
			{
				if (UAirsoftGameInstance* G = GI())
				{
					G->StartPractice(true);
				}
			}, &First)
	];
	Box->AddSlot().AutoHeight()
	[
		MenuButton(FText::FromString(TEXT("FREE PRACTICE")), FText::FromString(TEXT("JUST THE RANGE")),
			[this]()
			{
				if (UAirsoftGameInstance* G = GI())
				{
					G->StartPractice(false);
				}
			})
	];
	PageFocus.Add(EPage::Practice, First);
	return Box;
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
					.Text(FText::FromString(UAirsoftSettings::IsMultiplayerEnabled()
							? TEXT("Up to 20 characters. Shown to everyone in the match.")
							: TEXT("Up to 20 characters. Your name on the scoreboard.")))
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
