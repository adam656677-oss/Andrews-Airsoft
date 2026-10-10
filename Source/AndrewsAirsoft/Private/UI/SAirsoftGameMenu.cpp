// Andrew's Airsoft - in-game menu: resume, armory, settings, and in the
// staging area the next-match vote, team switch and (host) force start;
// the host can also turn bots on and set their skill here.

#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftModeRules.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "HAL/PlatformTime.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftGameMenuLocal
{
	EVisibility MenuVis(bool bVisible)
	{
		return bVisible ? EVisibility::Visible : EVisibility::Collapsed;
	}

	FString PhaseName(EAirsoftPhase Phase)
	{
		switch (Phase)
		{
		case EAirsoftPhase::Waiting: return TEXT("WAITING");
		case EAirsoftPhase::Intermission: return TEXT("INTERMISSION");
		case EAirsoftPhase::Briefing: return TEXT("BRIEFING");
		case EAirsoftPhase::Live: return TEXT("LIVE");
		case EAirsoftPhase::PostRound: return TEXT("ROUND OVER");
		}
		return FString();
	}

	FText VotesText(int32 Votes)
	{
		return FText::FromString(Votes == 1 ? FString(TEXT("1 VOTE")) : FString::Printf(TEXT("%d VOTES"), Votes));
	}
}

class SAirsoftGameMenu : public SAirsoftMenuBase
{
public:
	SLATE_BEGIN_ARGS(SAirsoftGameMenu) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

protected:
	virtual void HandleBack() override;

private:
	TSharedRef<SWidget> BuildLeftColumn();
	TSharedRef<SWidget> BuildRightColumn();
	AAirsoftGameState* GS() const { return AUI::GetGameState(WeakPC.Get()); }
	bool IsStaging() const;
	bool CanVote() const;
	bool IsLeaveArmed() const { return FPlatformTime::Seconds() - LeaveArmedAt < 3.0; }
	/** Host's bot fill option (0 = off). */
	int32 BotFill() const;

	double LeaveArmedAt = -100.0;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateGameMenu(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftGameMenu, PC);
}

bool SAirsoftGameMenu::IsStaging() const
{
	const AAirsoftGameState* State = GS();
	return State && !State->bIsMatchMap;
}

int32 SAirsoftGameMenu::BotFill() const
{
	UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
	return GI ? FMath::Clamp(GI->GetUserSettings().BotFill, 0, AirsoftBots::NumFillOptions - 1) : 0;
}

bool SAirsoftGameMenu::CanVote() const
{
	const AAirsoftGameState* State = GS();
	return State && !State->bIsMatchMap && (State->Phase == EAirsoftPhase::Waiting || State->Phase == EAirsoftPhase::Intermission);
}

void SAirsoftGameMenu::HandleBack()
{
	if (AAirsoftPlayerController* PC = WeakPC.Get())
	{
		PC->CloseMenus();
	}
}

void SAirsoftGameMenu::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	OpenTime = FPlatformTime::Seconds();
	ForceVolatile(true);

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SAirsoftBackdrop)
			.Opacity(0.78f)
			.ColumnWidth(0.36f)
		]
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.BorderImage(AUI::NoBrush())
			.Padding(FMargin(0.f))
			.ColorAndOpacity_Lambda([this]() -> FLinearColor
			{
				return FLinearColor(1.f, 1.f, 1.f, AUI::Ease(static_cast<float>((FPlatformTime::Seconds() - OpenTime) / 0.2)));
			})
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(FMargin(110.f, 90.f, 0.f, 60.f))
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
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.f, 0.f, 110.f, 0.f))
				[
					BuildRightColumn()
				]
			]
		]
	];
}

TSharedRef<SWidget> SAirsoftGameMenu::BuildLeftColumn()
{
	using namespace AirsoftGameMenuLocal;
	TSharedPtr<SAirsoftButton> ResumeButton;

	TSharedRef<SWidget> Column = SNew(SBox)
		.WidthOverride(420.f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("FIELD MENU")))
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 16.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Font(AUI::Font(AUI::EFontWeight::Bold, 40, 200))
				.ColorAndOpacity(FLinearColor::White)
				.Text_Lambda([this]()
				{
					const AAirsoftGameState* State = GS();
					return (State && State->bIsMatchMap) ? AUI::Upper(AAirsoftGameState::MapDisplayName(State->MapId)) : FText::FromString(TEXT("STAGING AREA"));
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(2.f, 6.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Font(AUI::Caption(9))
				.ColorAndOpacity(AUI::TextDim())
				.Text_Lambda([this]()
				{
					const AAirsoftGameState* State = GS();
					if (!State)
					{
						return FText::FromString(TEXT("CONNECTING"));
					}
					FString Line = AAirsoftGameState::ModeDisplayName(State->Mode).ToUpper() + TEXT("  \u00B7  ") + PhaseName(State->Phase);
					const float T = State->GetTimeRemaining();
					if (T >= 0.f)
					{
						Line += TEXT("  \u00B7  ") + AUI::TimeString(T);
					}
					return FText::FromString(Line);
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(2.f, 12.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Font(AUI::Font(AUI::EFontWeight::Bold, 11, 260))
				.Text_Lambda([this]()
				{
					const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
					const EAirsoftTeam Team = PS ? PS->Team : EAirsoftTeam::None;
					return FText::FromString(FString::Printf(TEXT("YOU  \u00B7  %s"), *AirsoftColors::TeamName(Team).ToUpper()));
				})
				.ColorAndOpacity_Lambda([this]() -> FSlateColor
				{
					const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
					return AUI::TeamColor(PS ? PS->Team : EAirsoftTeam::None);
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(2.f, 16.f, 0.f, 0.f))
			[
				AirsoftUIWidgets::AccentRule(96.f, 2.f)
			]
			// Buttons
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 30.f, 0.f, 0.f))
			[
				SAssignNew(ResumeButton, SAirsoftButton)
				.Text(FText::FromString(TEXT("RESUME")))
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (AAirsoftPlayerController* PC = WeakPC.Get())
					{
						PC->CloseMenus();
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Text(FText::FromString(TEXT("ARMORY")))
				.SubText_Lambda([this]()
				{
					const AAirsoftGameState* State = GS();
					const bool bLive = State && State->bIsMatchMap && State->Phase == EAirsoftPhase::Live;
					return FText::FromString(bLive ? TEXT("APPLIES NEXT SPAWN") : TEXT("LOADOUT & FINISHES"));
				})
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
				.Visibility_Lambda([this]() -> EVisibility { return MenuVis(IsStaging()); })
				.Text(FText::FromString(TEXT("SWITCH TEAM")))
				.SubText_Lambda([this]()
				{
					const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
					return AUI::Upper(AirsoftColors::TeamName(PS ? PS->Team : EAirsoftTeam::None));
				})
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (AAirsoftPlayerController* PC = WeakPC.Get())
					{
						PC->ServerSwitchTeam();
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Visibility_Lambda([this]() -> EVisibility
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return MenuVis(PC && PC->IsHost() && CanVote());
				})
				.Text(FText::FromString(TEXT("START MATCH NOW")))
				.SubText(FText::FromString(TEXT("HOST")))
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (AAirsoftPlayerController* PC = WeakPC.Get())
					{
						PC->ServerForceStart();
						PC->CloseMenus();
					}
					return FReply::Handled();
				})
			]
			// Host: bots (the host's saved setting; a running match adjusts within a second)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Visibility_Lambda([this]() -> EVisibility
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return MenuVis(PC && PC->IsHost());
				})
				.Text(FText::FromString(TEXT("BOTS")))
				.SubText_Lambda([this]()
				{
					const int32 Fill = BotFill();
					return FText::FromString(Fill > 0 ? TEXT("FILL ") + AirsoftBots::FillLabel(Fill) : FString(TEXT("OFF")));
				})
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get()))
					{
						FAirsoftUserSettings Settings = GI->GetUserSettings();
						Settings.BotFill = (FMath::Clamp(Settings.BotFill, 0, AirsoftBots::NumFillOptions - 1) + 1) % AirsoftBots::NumFillOptions;
						GI->SetUserSettings(Settings);
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Visibility_Lambda([this]() -> EVisibility
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return MenuVis(PC && PC->IsHost() && BotFill() > 0);
				})
				.Text(FText::FromString(TEXT("BOT SKILL")))
				.SubText_Lambda([this]()
				{
					UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
					return FText::FromString(AirsoftBots::SkillLabel(GI ? GI->GetUserSettings().BotSkill : 1));
				})
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get()))
					{
						FAirsoftUserSettings Settings = GI->GetUserSettings();
						Settings.BotSkill = (FMath::Clamp(Settings.BotSkill, 0, AirsoftBots::NumSkillOptions - 1) + 1) % AirsoftBots::NumSkillOptions;
						GI->SetUserSettings(Settings);
					}
					return FReply::Handled();
				})
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 22.f, 0.f, 0.f))
			[
				SNew(SAirsoftButton)
				.Text_Lambda([this]()
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					if (IsLeaveArmed())
					{
						return FText::FromString((PC && PC->IsHost()) ? TEXT("CONFIRM \u2014 END SESSION") : TEXT("CONFIRM \u2014 LEAVE"));
					}
					return FText::FromString(TEXT("LEAVE"));
				})
				.SubText_Lambda([this]()
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return FText::FromString((PC && PC->IsHost()) ? TEXT("ENDS IT FOR EVERYONE") : TEXT("BACK TO TITLE"));
				})
				.IsSelected_Lambda([this]() { return IsLeaveArmed(); })
				.FontSize(14)
				.OnClicked_Lambda([this]()
				{
					if (!IsLeaveArmed())
					{
						LeaveArmedAt = FPlatformTime::Seconds();
						return FReply::Handled();
					}
					if (UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get()))
					{
						GI->ReturnToMainMenu();
					}
					return FReply::Handled();
				})
			]
			// Hints
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(2.f, 30.f, 0.f, 0.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					AirsoftUIWidgets::Hint(FText::FromString(TEXT("ESC")), FText::FromString(TEXT("RESUME")))
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					AirsoftUIWidgets::Hint(FText::FromString(TEXT("TAB")), FText::FromString(TEXT("SCOREBOARD")))
				]
			]
		];

	SetInitialFocus(ResumeButton);
	return Column;
}

TSharedRef<SWidget> SAirsoftGameMenu::BuildRightColumn()
{
	using namespace AirsoftGameMenuLocal;
	TSharedRef<SVerticalBox> Votes = SNew(SVerticalBox);

	Votes->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.f, 0.f, 0.f, 8.f))
	[
		SNew(STextBlock)
		.Text(FText::FromString(TEXT("MODE")))
		.Font(AUI::Caption(8))
		.ColorAndOpacity(AUI::TextDim())
	];
	for (int32 i = 0; i < AirsoftRules::NumModes; ++i)
	{
		Votes->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 3.f))
		[
			SNew(SAirsoftButton)
			.Text(AUI::Upper(AirsoftRules::ModeName(AirsoftRules::ModeFromIndex(i))))
			.FontSize(12)
			.ContentPadding(FMargin(16.f, 7.f))
			.SubText_Lambda([this, i]()
			{
				const AAirsoftGameState* State = GS();
				return VotesText((State && State->ModeVotes.IsValidIndex(i)) ? State->ModeVotes[i] : 0);
			})
			.IsSelected_Lambda([this, i]()
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return PC && PC->GetMyModeVote() == i;
			})
			.OnClicked_Lambda([this, i]()
			{
				if (AAirsoftPlayerController* PC = WeakPC.Get())
				{
					PC->VoteMode(i);
				}
				return FReply::Handled();
			})
		];
	}

	Votes->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.f, 10.f, 0.f, 8.f))
	[
		SNew(STextBlock)
		.Text(FText::FromString(TEXT("MAP")))
		.Font(AUI::Caption(8))
		.ColorAndOpacity(AUI::TextDim())
	];
	const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
	for (int32 i = 0; i < Maps.Num(); ++i)
	{
		const FString Players = FString::Printf(TEXT("%d\u2013%d"), Maps[i].MinPlayers, Maps[i].MaxPlayers);
		Votes->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 3.f))
		[
			SNew(SAirsoftButton)
			.Text(AUI::Upper(AirsoftRules::MapDisplayName(Maps[i].Key)))
			.FontSize(12)
			.ContentPadding(FMargin(16.f, 7.f))
			.SubText_Lambda([this, i, Players]()
			{
				const AAirsoftGameState* State = GS();
				return FText::FromString(Players + TEXT(" PLAYERS  \u00B7  ") + VotesText((State && State->MapVotes.IsValidIndex(i)) ? State->MapVotes[i] : 0).ToString());
			})
			.IsSelected_Lambda([this, i]()
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return PC && PC->GetMyMapVote() == i;
			})
			.IsDimmed_Lambda([this, i]()
			{
				// A map that can't run the mode this player picked.
				const AAirsoftPlayerController* PC = WeakPC.Get();
				const TArray<FAirsoftMapInfo>& List = AirsoftRules::Maps();
				return PC && PC->GetMyModeVote() >= 0 && List.IsValidIndex(i) && !List[i].SupportsMode(AirsoftRules::ModeFromIndex(PC->GetMyModeVote()));
			})
			.OnClicked_Lambda([this, i]()
			{
				if (AAirsoftPlayerController* PC = WeakPC.Get())
				{
					PC->VoteMap(i);
				}
				return FReply::Handled();
			})
		];
	}

	return SNew(SBox)
		.WidthOverride(420.f)
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(24.f, 20.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("ORDERS")))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 18, 200))
					.ColorAndOpacity(FLinearColor::White)
					.Text_Lambda([this]()
					{
						const AAirsoftGameState* State = GS();
						if (!State || !State->bIsMatchMap)
						{
							return FText::FromString(TEXT("STAGING"));
						}
						return AUI::Upper(AAirsoftGameState::ModeDisplayName(State->Mode));
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.AutoWrapText(true)
					.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 20))
					.ColorAndOpacity(AUI::TextDim())
					.Text_Lambda([this]()
					{
						const AAirsoftGameState* State = GS();
						if (!State || !State->bIsMatchMap)
						{
							return FText::FromString(TEXT("Warm up on the range, set your loadout, and vote for the next match. Teams are balanced when it starts."));
						}
						return FText::FromString(AAirsoftGameState::ModeBlurb(State->Mode));
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 18.f, 0.f, 0.f))
				[
					SNew(SVerticalBox)
					.Visibility_Lambda([this]() -> EVisibility { return MenuVis(CanVote()); })
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 0.f, 0.f, 14.f))
					[
						AirsoftUIWidgets::Rule(AUI::Hairline())
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 0.f, 0.f, 12.f))
					[
						AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("NEXT MATCH")))
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						Votes
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 8.f, 0.f, 0.f))
					[
						SNew(STextBlock)
						.AutoWrapText(true)
						.Text(FText::FromString(TEXT("Shortcut: F1 steps through the modes, F2 through the maps. Most votes wins; Start Match Now uses the leading votes.")))
						.Font(AUI::Font(AUI::EFontWeight::Regular, 10))
						.ColorAndOpacity(AUI::TextDim())
					]
				]
			]
		];
}
