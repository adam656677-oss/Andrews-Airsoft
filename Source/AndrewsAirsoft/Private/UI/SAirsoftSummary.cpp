// Andrew's Airsoft - after-action report shown in the post-round phase (after
// the final-tag replay): result, team tables, XP earned and rank progress.

#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "AirsoftWeaponData.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

class SAirsoftSummary : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftSummary) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

private:
	TSharedRef<SWidget> BuildTeamTable(EAirsoftTeam Team, const FAirsoftMatchSummary& Summary);
	TSharedRef<SWidget> BuildXPPanel(const FAirsoftMatchSummary& Summary);
	/** Seconds since the summary was posted (controller clock). */
	float Age() const;
	/** XP value shown by the animated bar. */
	int32 ShownXP() const;

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
	double StartTime = 0.0;
	bool bDomination = false;
	FString MyName;
	int32 XPBefore = 0;
	int32 XPAfter = 0;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateSummary(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftSummary, PC);
}

float SAirsoftSummary::Age() const
{
	return static_cast<float>(AUI::HudNow(WeakPC.Get()) - StartTime);
}

int32 SAirsoftSummary::ShownXP() const
{
	const float T = AUI::Ease((Age() - 0.8f) / 1.8f);
	return XPBefore + FMath::RoundToInt(static_cast<float>(XPAfter - XPBefore) * T);
}

void SAirsoftSummary::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	SetVisibility(EVisibility::HitTestInvisible);
	ForceVolatile(true);

	static const FAirsoftMatchSummary Empty = FAirsoftMatchSummary();
	const FAirsoftMatchSummary& Summary = InPC ? InPC->GetSummary() : Empty;
	StartTime = (Summary.bValid && Summary.Time > 0.0) ? Summary.Time : AUI::HudNow(InPC);
	if (StartTime > AUI::HudNow(InPC))
	{
		StartTime = AUI::HudNow(InPC);
	}

	const AAirsoftGameState* GS = AUI::GetGameState(InPC);
	bDomination = GS && GS->Mode == EAirsoftMode::Domination;
	if (const AAirsoftPlayerState* PS = AUI::GetPlayerState(InPC))
	{
		MyName = PS->GetPlayerName();
	}
	else if (UAirsoftGameInstance* GI = AUI::GetGameInstance(InPC))
	{
		MyName = GI->GetPlayerName();
	}

	// The profile normally already includes this match's XP; if it doesn't yet, add it.
	const UAirsoftSaveGame* Profile = AUI::GetProfile(InPC);
	const int32 ProfileXP = Profile ? Profile->XP : 0;
	XPAfter = ProfileXP;
	if (AirsoftWeapons::RankIndexForXP(ProfileXP) != Summary.RankAfter && AirsoftWeapons::RankIndexForXP(ProfileXP + Summary.XPEarned) == Summary.RankAfter)
	{
		XPAfter = ProfileXP + Summary.XPEarned;
	}
	XPBefore = FMath::Max(0, XPAfter - Summary.XPEarned);

	FString Title = TEXT("MATCH OVER");
	FLinearColor TitleColor = FLinearColor::White;
	FString Verdict;
	FLinearColor VerdictColor = AUI::TextDim();
	if (Summary.bValid)
	{
		if (Summary.Winner == EAirsoftTeam::None)
		{
			Title = TEXT("DRAW");
			Verdict = TEXT("STALEMATE");
		}
		else
		{
			Title = AirsoftColors::TeamName(Summary.Winner).ToUpper() + TEXT(" WINS");
			TitleColor = AUI::TeamColor(Summary.Winner);
			if (Summary.MyTeam != EAirsoftTeam::None)
			{
				const bool bWon = Summary.MyTeam == Summary.Winner;
				Verdict = bWon ? TEXT("VICTORY") : TEXT("DEFEAT");
				VerdictColor = bWon ? AUI::Accent() : AUI::TextDim();
			}
		}
	}

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SAirsoftBackdrop)
			.Opacity(0.9f)
			.ColumnWidth(0.f)
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		[
			SNew(SBorder)
			.BorderImage(AUI::NoBrush())
			.Padding(FMargin(0.f))
			.ColorAndOpacity_Lambda([this]() -> FLinearColor { return FLinearColor(1.f, 1.f, 1.f, AUI::Ease(Age() / 0.5f)); })
			[
				SNew(SBox)
				.WidthOverride(1180.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					[
						AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("AFTER-ACTION REPORT")))
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(FMargin(0.f, 18.f, 0.f, 0.f))
					[
						SNew(STextBlock)
						.Text(FText::FromString(Title))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 48, 300))
						.ColorAndOpacity(TitleColor)
						.ShadowOffset(FVector2D(0.f, 2.f))
						.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.6f))
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
					[
						SNew(STextBlock)
						.Visibility(Verdict.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible)
						.Text(FText::FromString(Verdict))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 15, 700))
						.ColorAndOpacity(VerdictColor)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(FMargin(0.f, 14.f, 0.f, 0.f))
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 26))
							.ColorAndOpacity(AUI::TeamColor(EAirsoftTeam::Blue))
							.Text_Lambda([this]()
							{
								const AAirsoftGameState* State = AUI::GetGameState(WeakPC.Get());
								return FText::AsNumber(State ? State->BlueScore : 0);
							})
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						.Padding(FMargin(22.f, 0.f))
						[
							SNew(STextBlock)
							.Font(AUI::Caption(9))
							.ColorAndOpacity(AUI::TextDim())
							.Text_Lambda([this]()
							{
								const AAirsoftGameState* State = AUI::GetGameState(WeakPC.Get());
								if (!State)
								{
									return FText::GetEmpty();
								}
								return FText::FromString(FString::Printf(TEXT("%s  \u00B7  %s"),
									*AAirsoftGameState::ModeDisplayName(State->Mode).ToUpper(), *AAirsoftGameState::MapDisplayName(State->MapId).ToUpper()));
							})
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 26))
							.ColorAndOpacity(AUI::TeamColor(EAirsoftTeam::Red))
							.Text_Lambda([this]()
							{
								const AAirsoftGameState* State = AUI::GetGameState(WeakPC.Get());
								return FText::AsNumber(State ? State->RedScore : 0);
							})
						]
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 26.f, 0.f, 0.f))
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.FillWidth(1.f)
						.Padding(FMargin(0.f, 0.f, 16.f, 0.f))
						[
							BuildTeamTable(EAirsoftTeam::Blue, Summary)
						]
						+ SHorizontalBox::Slot()
						.FillWidth(1.f)
						.Padding(FMargin(16.f, 0.f, 0.f, 0.f))
						[
							BuildTeamTable(EAirsoftTeam::Red, Summary)
						]
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(FMargin(0.f, 26.f, 0.f, 0.f))
					[
						BuildXPPanel(Summary)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(FMargin(0.f, 22.f, 0.f, 0.f))
					[
						SNew(STextBlock)
						.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 120))
						.ColorAndOpacity(AUI::TextDim())
						.Visibility_Lambda([this]() -> EVisibility
						{
							const AAirsoftGameState* State = AUI::GetGameState(WeakPC.Get());
							return (State && State->GetTimeRemaining() >= 0.f) ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
						})
						.Text_Lambda([this]()
						{
							const AAirsoftGameState* State = AUI::GetGameState(WeakPC.Get());
							const int32 Seconds = State ? FMath::CeilToInt(State->GetTimeRemaining()) : 0;
							return FText::FromString(FString::Printf(TEXT("Returning to staging in %d"), FMath::Max(0, Seconds)));
						})
					]
				]
			]
		]
	];
}

TSharedRef<SWidget> SAirsoftSummary::BuildTeamTable(EAirsoftTeam Team, const FAirsoftMatchSummary& Summary)
{
	TArray<FAirsoftSummaryRow> Rows;
	for (const FAirsoftSummaryRow& Row : Summary.Rows)
	{
		if (Row.Team == Team)
		{
			Rows.Add(Row);
		}
	}
	Rows.Sort([](const FAirsoftSummaryRow& A, const FAirsoftSummaryRow& B)
	{
		if (A.Stats.Tags != B.Stats.Tags)
		{
			return A.Stats.Tags > B.Stats.Tags;
		}
		return A.Stats.XP > B.Stats.XP;
	});

	const FLinearColor TeamCol = AUI::TeamColor(Team);
	const EVisibility CapsVis = bDomination ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
	auto NumberCell = [](int32 Value, const FLinearColor& Color, bool bBold, EVisibility Vis) -> TSharedRef<SWidget>
	{
		return SNew(SBox)
			.WidthOverride(56.f)
			.HAlign(HAlign_Right)
			.Visibility(Vis)
			[
				SNew(STextBlock)
				.Text(FText::AsNumber(Value))
				.Font(bBold ? AUI::Font(AUI::EFontWeight::Bold, 12, 20) : AUI::Font(AUI::EFontWeight::Regular, 11, 20))
				.ColorAndOpacity(Color)
			];
	};
	auto HeadCell = [](const TCHAR* Label, EVisibility Vis) -> TSharedRef<SWidget>
	{
		return SNew(SBox)
			.WidthOverride(56.f)
			.HAlign(HAlign_Right)
			.Visibility(Vis)
			[
				SNew(STextBlock)
				.Text(FText::FromString(Label))
				.Font(AUI::Caption(7))
				.ColorAndOpacity(AUI::TextDim())
			];
	};

	TSharedRef<SVerticalBox> Table = SNew(SVerticalBox);
	Table->AddSlot()
	.AutoHeight()
	[
		AirsoftUIWidgets::Rule(TeamCol, 2.f)
	];
	Table->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.f, 10.f, 0.f, 8.f))
	[
		SNew(STextBlock)
		.Text(AUI::Upper(AirsoftColors::TeamName(Team)))
		.Font(AUI::Heading(12))
		.ColorAndOpacity(TeamCol)
	];
	Table->AddSlot()
	.AutoHeight()
	.Padding(FMargin(14.f, 0.f, 12.f, 6.f))
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.f)
		[
			SNew(STextBlock)
			.Text(FText::FromString(TEXT("CALL SIGN")))
			.Font(AUI::Caption(7))
			.ColorAndOpacity(AUI::TextDim())
		]
		+ SHorizontalBox::Slot().AutoWidth()[HeadCell(TEXT("TAGS"), EVisibility::HitTestInvisible)]
		+ SHorizontalBox::Slot().AutoWidth()[HeadCell(TEXT("OUTS"), EVisibility::HitTestInvisible)]
		+ SHorizontalBox::Slot().AutoWidth()[HeadCell(TEXT("CAPS"), CapsVis)]
		+ SHorizontalBox::Slot().AutoWidth()[HeadCell(TEXT("XP"), EVisibility::HitTestInvisible)]
	];

	if (Rows.Num() == 0)
	{
		Table->AddSlot()
		.AutoHeight()
		.Padding(FMargin(14.f, 8.f))
		[
			SNew(STextBlock)
			.Text(FText::FromString(TEXT("No players")))
			.Font(AUI::Font(AUI::EFontWeight::Regular, 11))
			.ColorAndOpacity(AUI::TextMuted())
		];
	}

	for (int32 i = 0; i < Rows.Num(); ++i)
	{
		const FAirsoftSummaryRow& Row = Rows[i];
		const bool bMe = !MyName.IsEmpty() && Row.Name == MyName;
		const FLinearColor NameCol = bMe ? AUI::Accent() : FLinearColor::White;
		const FLinearColor NumCol = bMe ? AUI::Accent() : AUI::TextColor();
		const FLinearColor Back = bMe ? FLinearColor(1.f, 0.55f, 0.05f, 0.14f) : FLinearColor(0.f, 0.f, 0.f, (i % 2 == 0) ? 0.34f : 0.2f);
		Table->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 2.f))
		[
			SNew(SBorder)
			.BorderImage(AUI::RoundedBrush())
			.BorderBackgroundColor(Back)
			.Padding(FMargin(14.f, 6.f, 12.f, 6.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(FText::FromString(Row.Name))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 12, 40))
					.ColorAndOpacity(NameCol)
				]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[NumberCell(Row.Stats.Tags, NameCol, true, EVisibility::HitTestInvisible)]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[NumberCell(Row.Stats.Outs, NumCol, false, EVisibility::HitTestInvisible)]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[NumberCell(Row.Stats.Captures, NumCol, false, CapsVis)]
				+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[NumberCell(Row.Stats.XP, NumCol, false, EVisibility::HitTestInvisible)]
			]
		];
	}
	return Table;
}

TSharedRef<SWidget> SAirsoftSummary::BuildXPPanel(const FAirsoftMatchSummary& Summary)
{
	const bool bPromoted = Summary.RankAfter > Summary.RankBefore;
	const FString PromotedText = FString::Printf(TEXT("PROMOTED: %s"), *AUI::RankName(Summary.RankAfter).ToUpper());
	const int32 Earned = Summary.XPEarned;

	return SNew(SBox)
		.WidthOverride(560.f)
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(24.f, 18.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.FillWidth(1.f)
					.VAlign(VAlign_Bottom)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(STextBlock)
							.Text(FText::FromString(TEXT("XP EARNED")))
							.Font(AUI::Caption(8))
							.ColorAndOpacity(AUI::TextDim())
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 28, 40))
							.ColorAndOpacity(AUI::Accent())
							.Text_Lambda([this, Earned]()
							{
								const float T = AUI::Ease((Age() - 0.3f) / 1.2f);
								return FText::FromString(FString::Printf(TEXT("+%s"), *FText::AsNumber(FMath::RoundToInt(Earned * T)).ToString()));
							})
						]
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Bottom)
					.Padding(FMargin(0.f, 0.f, 0.f, 4.f))
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot()
						.AutoHeight()
						.HAlign(HAlign_Right)
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 14, 200))
							.ColorAndOpacity(FLinearColor::White)
							.Text_Lambda([this]()
							{
								return AUI::Upper(AUI::RankName(AirsoftWeapons::RankIndexForXP(ShownXP())));
							})
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						.HAlign(HAlign_Right)
						[
							SNew(STextBlock)
							.Font(AUI::Caption(8))
							.ColorAndOpacity(AUI::TextDim())
							.Text_Lambda([this]()
							{
								const int32 XP = ShownXP();
								const int32 Next = AUI::NextRankXP(XP);
								if (Next < 0)
								{
									return FText::FromString(FString::Printf(TEXT("%s XP  \u00B7  HIGHEST RANK"), *FText::AsNumber(XP).ToString()));
								}
								return FText::FromString(FString::Printf(TEXT("%s / %s XP"), *FText::AsNumber(XP).ToString(), *FText::AsNumber(Next).ToString()));
							})
						]
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
				[
					SNew(SAirsoftBar)
					.Width(512.f)
					.Height(5.f)
					.Fraction_Lambda([this]() { return AUI::RankProgress(ShownXP()); })
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 14.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(PromotedText))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 16, 360))
					.ColorAndOpacity_Lambda([this]() -> FSlateColor
					{
						return AUI::WithAlpha(AUI::Accent(), AUI::Ease((Age() - 2.4f) / 0.5f));
					})
					.Visibility(bPromoted ? EVisibility::HitTestInvisible : EVisibility::Collapsed)
				]
			]
		];
}
