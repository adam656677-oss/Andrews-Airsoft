// Andrew's Airsoft - held-Tab scoreboard: two team columns sorted by tags
// (free-for-all: one standings list by ladder level, split over both columns).
// The third number column follows the mode: CAPS (Domination), EXTR (VIP
// extractions), LVL (Gun Game ladder level); the VIP gets a tag by their name.

#include "AirsoftGameState.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "GameFramework/PlayerState.h"
#include "HAL/PlatformTime.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftScoreboardLocal
{
	constexpr int32 RowsPerTeam = 16;
	constexpr float ColTags = 46.f;
	constexpr float ColOuts = 46.f;
	constexpr float ColMode = 46.f;
	constexpr float ColXP = 58.f;
	constexpr float ColPing = 50.f;

	EVisibility BoardVis(bool bVisible)
	{
		return bVisible ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
	}
}

class SAirsoftScoreboard : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftScoreboard) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;

private:
	void Refresh();
	TSharedRef<SWidget> BuildHeaderScore(EAirsoftTeam Team);
	TSharedRef<SWidget> BuildColumn(int32 TeamIndex);
	TSharedRef<SWidget> BuildColumnHeader();
	TSharedRef<SWidget> BuildRow(int32 TeamIndex, int32 Row);
	TSharedRef<SWidget> Cell(float Width, const TAttribute<FText>& Text, const TAttribute<FSlateColor>& Color, bool bBold, const TAttribute<EVisibility>& InVisibility = EVisibility::Visible);
	AAirsoftPlayerState* RowPS(int32 TeamIndex, int32 Row) const;
	bool IsFreeForAll() const;
	/** Header of the mode column ("CAPS", "EXTR", "LVL"), empty when the mode has none. */
	FString ModeColumnLabel() const;
	int32 ModeColumnValue(const AAirsoftPlayerState* PS) const;

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
	TArray<TWeakObjectPtr<AAirsoftPlayerState>> Teams[2];
	FString UnassignedNames;
	double OpenTime = 0.0;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateScoreboard(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftScoreboard, PC);
}

bool SAirsoftScoreboard::IsFreeForAll() const
{
	const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
	return GS && GS->IsFreeForAll();
}

FString SAirsoftScoreboard::ModeColumnLabel() const
{
	const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
	if (!GS || !GS->bIsMatchMap)
	{
		return FString();
	}
	switch (GS->Mode)
	{
	case EAirsoftMode::Domination: return TEXT("CAPS");
	case EAirsoftMode::VIP: return TEXT("EXTR");
	case EAirsoftMode::GunGame: return TEXT("LVL");
	default: return FString();
	}
}

int32 SAirsoftScoreboard::ModeColumnValue(const AAirsoftPlayerState* PS) const
{
	const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
	if (!PS || !GS)
	{
		return 0;
	}
	return GS->Mode == EAirsoftMode::GunGame ? PS->GunLevel + 1 : PS->Round.Captures;
}

AAirsoftPlayerState* SAirsoftScoreboard::RowPS(int32 TeamIndex, int32 Row) const
{
	if (TeamIndex < 0 || TeamIndex > 1 || !Teams[TeamIndex].IsValidIndex(Row))
	{
		return nullptr;
	}
	return Teams[TeamIndex][Row].Get();
}

void SAirsoftScoreboard::Refresh()
{
	Teams[0].Reset();
	Teams[1].Reset();
	UnassignedNames.Reset();
	const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
	if (!GS)
	{
		return;
	}
	const bool bFreeForAll = GS->IsFreeForAll();
	TArray<FString> Unassigned;
	TArray<TWeakObjectPtr<AAirsoftPlayerState>> Everyone;
	for (const TObjectPtr<APlayerState>& Entry : GS->PlayerArray)
	{
		AAirsoftPlayerState* PS = Cast<AAirsoftPlayerState>(Entry.Get());
		if (!PS)
		{
			continue;
		}
		if (bFreeForAll)
		{
			Everyone.Add(PS);
		}
		else if (PS->Team == EAirsoftTeam::Blue)
		{
			Teams[0].Add(PS);
		}
		else if (PS->Team == EAirsoftTeam::Red)
		{
			Teams[1].Add(PS);
		}
		else
		{
			Unassigned.Add(PS->GetPlayerName());
		}
	}
	auto ByScore = [bFreeForAll](const TWeakObjectPtr<AAirsoftPlayerState>& A, const TWeakObjectPtr<AAirsoftPlayerState>& B)
	{
		const AAirsoftPlayerState* PA = A.Get();
		const AAirsoftPlayerState* PB = B.Get();
		if (!PA || !PB)
		{
			return PA != nullptr;
		}
		if (bFreeForAll && PA->GunLevel != PB->GunLevel)
		{
			return PA->GunLevel > PB->GunLevel;
		}
		if (PA->Round.Tags != PB->Round.Tags)
		{
			return PA->Round.Tags > PB->Round.Tags;
		}
		if (PA->Round.XP != PB->Round.XP)
		{
			return PA->Round.XP > PB->Round.XP;
		}
		return PA->GetPlayerName() < PB->GetPlayerName();
	};
	if (bFreeForAll)
	{
		// One standings list: the top half on the left, the rest on the right.
		Everyone.Sort(ByScore);
		const int32 LeftCount = (Everyone.Num() + 1) / 2;
		for (int32 i = 0; i < Everyone.Num(); ++i)
		{
			Teams[i < LeftCount ? 0 : 1].Add(Everyone[i]);
		}
	}
	else
	{
		for (TArray<TWeakObjectPtr<AAirsoftPlayerState>>& List : Teams)
		{
			List.Sort(ByScore);
		}
	}
	UnassignedNames = FString::Join(Unassigned, TEXT(",  "));
}

void SAirsoftScoreboard::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
	Refresh();
}

TSharedRef<SWidget> SAirsoftScoreboard::Cell(float Width, const TAttribute<FText>& Text, const TAttribute<FSlateColor>& Color, bool bBold, const TAttribute<EVisibility>& InVisibility)
{
	return SNew(SBox)
		.WidthOverride(Width)
		.Visibility(InVisibility)
		.HAlign(HAlign_Right)
		[
			SNew(STextBlock)
			.Text(Text)
			.Font(bBold ? AUI::Font(AUI::EFontWeight::Bold, 12, 20) : AUI::Font(AUI::EFontWeight::Regular, 11, 20))
			.ColorAndOpacity(Color)
		];
}

TSharedRef<SWidget> SAirsoftScoreboard::BuildColumnHeader()
{
	using namespace AirsoftScoreboardLocal;
	auto Head = [](const TCHAR* Label) { return FText::FromString(Label); };
	const FSlateColor Dim = AUI::TextDim();
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			SNew(SBox).WidthOverride(24.f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			SNew(SBox)
			.WidthOverride(100.f)
			[
				SNew(STextBlock).Text(Head(TEXT("RANK"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.f)
		[
			SNew(STextBlock).Text(Head(TEXT("CALL SIGN"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SBox).WidthOverride(ColMode).HAlign(HAlign_Right)
			.Visibility_Lambda([this]() -> EVisibility { return BoardVis(IsFreeForAll()); })
			[
				SNew(STextBlock).Text(Head(TEXT("LVL"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SBox).WidthOverride(ColTags).HAlign(HAlign_Right)
			[
				SNew(STextBlock).Text(Head(TEXT("TAGS"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SBox).WidthOverride(ColOuts).HAlign(HAlign_Right)
			[
				SNew(STextBlock).Text(Head(TEXT("OUTS"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SBox).WidthOverride(ColMode).HAlign(HAlign_Right)
			.Visibility_Lambda([this]() -> EVisibility { return BoardVis(!IsFreeForAll() && !ModeColumnLabel().IsEmpty()); })
			[
				SNew(STextBlock).Text_Lambda([this]() { return FText::FromString(ModeColumnLabel()); }).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SBox).WidthOverride(ColXP).HAlign(HAlign_Right)
			[
				SNew(STextBlock).Text(Head(TEXT("XP"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		]
		+ SHorizontalBox::Slot().AutoWidth()
		[
			SNew(SBox).WidthOverride(ColPing).HAlign(HAlign_Right)
			[
				SNew(STextBlock).Text(Head(TEXT("PING"))).Font(AUI::Caption(7)).ColorAndOpacity(Dim)
			]
		];
}

TSharedRef<SWidget> SAirsoftScoreboard::BuildRow(int32 TeamIndex, int32 Row)
{
	using namespace AirsoftScoreboardLocal;
	auto IsMe = [this, TeamIndex, Row]()
	{
		const AAirsoftPlayerState* PS = RowPS(TeamIndex, Row);
		return PS && PS == AUI::GetPlayerState(WeakPC.Get());
	};
	auto NumberText = [this, TeamIndex, Row](int32 Which)
	{
		return TAttribute<FText>::CreateLambda([this, TeamIndex, Row, Which]()
		{
			const AAirsoftPlayerState* PS = RowPS(TeamIndex, Row);
			if (!PS)
			{
				return FText::GetEmpty();
			}
			switch (Which)
			{
			case 0: return FText::AsNumber(PS->Round.Tags);
			case 1: return FText::AsNumber(PS->Round.Outs);
			case 2: return FText::AsNumber(ModeColumnValue(PS));
			case 3: return FText::AsNumber(PS->Round.XP);
			default: return PS->IsABot() ? FText::FromString(TEXT("-")) : FText::AsNumber(FMath::RoundToInt(PS->GetPingInMilliseconds()));
			}
		});
	};
	const TAttribute<FSlateColor> Bright = TAttribute<FSlateColor>::CreateLambda([IsMe]() -> FSlateColor { return IsMe() ? AUI::Accent() : FLinearColor::White; });
	const TAttribute<FSlateColor> Normal = TAttribute<FSlateColor>::CreateLambda([IsMe]() -> FSlateColor { return IsMe() ? AUI::Accent() : AUI::TextColor(); });
	const TAttribute<FSlateColor> Dim = TAttribute<FSlateColor>(AUI::TextDim());

	return SNew(SBorder)
		.Visibility_Lambda([this, TeamIndex, Row]() -> EVisibility { return BoardVis(RowPS(TeamIndex, Row) != nullptr); })
		.BorderImage(AUI::RoundedBrush())
		.BorderBackgroundColor_Lambda([IsMe, Row]() -> FSlateColor
		{
			if (IsMe())
			{
				return FLinearColor(1.f, 0.55f, 0.05f, 0.14f);
			}
			return FLinearColor(0.f, 0.f, 0.f, (Row % 2 == 0) ? 0.34f : 0.2f);
		})
		.Padding(FMargin(0.f, 6.f, 12.f, 6.f))
		[
			SNew(SHorizontalBox)
			// Local-player edge + out marker
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				SNew(SBox)
				.WidthOverride(2.f)
				[
					SNew(SBorder)
					.BorderImage(AUI::WhiteBrush())
					.Padding(FMargin(0.f))
					.BorderBackgroundColor_Lambda([IsMe]() -> FSlateColor { return IsMe() ? AUI::Accent() : FLinearColor(0.f, 0.f, 0.f, 0.f); })
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(22.f)
				.HAlign(HAlign_Center)
				[
					SNew(SBox)
					.WidthOverride(6.f)
					.HeightOverride(6.f)
					.Visibility_Lambda([this, TeamIndex, Row]() -> EVisibility
					{
						const AAirsoftPlayerState* PS = RowPS(TeamIndex, Row);
						return (PS && PS->bOut) ? EVisibility::HitTestInvisible : EVisibility::Hidden;
					})
					[
						SNew(SBorder)
						.BorderImage(AUI::RoundedBrush())
						.BorderBackgroundColor(AUI::Danger())
						.Padding(FMargin(0.f))
					]
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(100.f)
				[
					SNew(STextBlock)
					.Font(AUI::Caption(7))
					.ColorAndOpacity(AUI::TextDim())
					.Text_Lambda([this, TeamIndex, Row]()
					{
						const AAirsoftPlayerState* PS = RowPS(TeamIndex, Row);
						if (!PS)
						{
							return FText::GetEmpty();
						}
						// Bots have no career, just a tag.
						return PS->IsABot() ? FText::FromString(TEXT("BOT")) : AUI::Upper(AUI::RankName(PS->RankIndex()));
					})
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.VAlign(VAlign_Center)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 12, 40))
					.ColorAndOpacity(Bright)
					.Text_Lambda([this, TeamIndex, Row]()
					{
						const AAirsoftPlayerState* PS = RowPS(TeamIndex, Row);
						if (!PS)
						{
							return FText::GetEmpty();
						}
						return FText::FromString(PS->bOut ? PS->GetPlayerName() + TEXT("   OUT") : PS->GetPlayerName());
					})
				]
				// VIP tag.
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(8.f, 0.f, 0.f, 0.f))
				[
					SNew(SBorder)
					.Visibility_Lambda([this, TeamIndex, Row]() -> EVisibility
					{
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						const AAirsoftPlayerState* PS = RowPS(TeamIndex, Row);
						return BoardVis(GS && PS && GS->Mode == EAirsoftMode::VIP && GS->VIPPlayer.Get() == PS);
					})
					.BorderImage(AUI::RoundedBrush())
					.BorderBackgroundColor(FLinearColor(1.f, 0.78f, 0.2f))
					.Padding(FMargin(5.f, 0.f))
					[
						SNew(STextBlock)
						.Text(FText::FromString(TEXT("VIP")))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 8, 200))
						.ColorAndOpacity(FLinearColor(0.02f, 0.02f, 0.02f))
					]
				]
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				Cell(ColMode, NumberText(2), Bright, true,
					TAttribute<EVisibility>::CreateLambda([this]() -> EVisibility { return IsFreeForAll() ? EVisibility::Visible : EVisibility::Collapsed; }))
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				Cell(ColTags, NumberText(0), Bright, true)
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				Cell(ColOuts, NumberText(1), Normal, false)
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				Cell(ColMode, NumberText(2), Normal, false,
					TAttribute<EVisibility>::CreateLambda([this]() -> EVisibility
					{
						return (!IsFreeForAll() && !ModeColumnLabel().IsEmpty()) ? EVisibility::Visible : EVisibility::Collapsed;
					}))
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				Cell(ColXP, NumberText(3), Normal, false)
			]
			+ SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
			[
				Cell(ColPing, NumberText(4), Dim, false)
			]
		];
}

TSharedRef<SWidget> SAirsoftScoreboard::BuildColumn(int32 TeamIndex)
{
	const EAirsoftTeam Team = TeamIndex == 0 ? EAirsoftTeam::Blue : EAirsoftTeam::Red;
	TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
	for (int32 Row = 0; Row < AirsoftScoreboardLocal::RowsPerTeam; ++Row)
	{
		Rows->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 2.f))
		[
			BuildRow(TeamIndex, Row)
		];
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SBox)
			.HeightOverride(2.f)
			[
				SNew(SBorder)
				.BorderImage(AUI::WhiteBrush())
				.Padding(FMargin(0.f))
				.BorderBackgroundColor_Lambda([this, Team]() -> FSlateColor { return IsFreeForAll() ? AUI::Accent() : AUI::TeamColor(Team); })
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.f, 10.f, 0.f, 8.f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			[
				SNew(STextBlock)
				.Font(AUI::Heading(12))
				.Text_Lambda([this, Team, TeamIndex]()
				{
					if (IsFreeForAll())
					{
						return FText::FromString(TeamIndex == 0 ? TEXT("STANDINGS") : TEXT("CHASING"));
					}
					FString Name = AirsoftColors::TeamName(Team).ToUpper();
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					if (GS && GS->Mode == EAirsoftMode::VIP && GS->AttackingTeam != EAirsoftTeam::None)
					{
						Name += GS->AttackingTeam == Team ? TEXT("  \u00B7  ATTACK") : TEXT("  \u00B7  DEFEND");
					}
					return FText::FromString(Name);
				})
				.ColorAndOpacity_Lambda([this, Team]() -> FSlateColor { return IsFreeForAll() ? AUI::Accent() : AUI::TeamColor(Team); })
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				SNew(STextBlock)
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextDim())
				.Text_Lambda([this, TeamIndex, Team]()
				{
					const int32 Count = Teams[TeamIndex].Num();
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					if (GS && GS->IsRoundBased() && GS->Phase == EAirsoftPhase::Live)
					{
						return FText::FromString(FString::Printf(TEXT("%d OF %d STANDING"), GS->GetAlive(Team), Count));
					}
					return FText::FromString(FString::Printf(TEXT("%d %s"), Count, Count == 1 ? TEXT("PLAYER") : TEXT("PLAYERS")));
				})
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 12.f, 6.f))
		[
			BuildColumnHeader()
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			Rows
		];
}

TSharedRef<SWidget> SAirsoftScoreboard::BuildHeaderScore(EAirsoftTeam Team)
{
	return SNew(SBox)
		.WidthOverride(150.f)
		.HAlign(Team == EAirsoftTeam::Blue ? HAlign_Left : HAlign_Right)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
			return (GS && GS->bIsMatchMap && !GS->IsFreeForAll()) ? EVisibility::HitTestInvisible : EVisibility::Hidden;
		})
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Bold, 40, 40))
			.ColorAndOpacity(AUI::TeamColor(Team))
			.Text_Lambda([this, Team]()
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				return FText::AsNumber(GS ? GS->GetScore(Team) : 0);
			})
		];
}

void SAirsoftScoreboard::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	OpenTime = FPlatformTime::Seconds();
	SetVisibility(EVisibility::HitTestInvisible);
	ForceVolatile(true);
	Refresh();

	ChildSlot
	.HAlign(HAlign_Center)
	.VAlign(VAlign_Center)
	[
		SNew(SBorder)
		.BorderImage(AUI::NoBrush())
		.Padding(FMargin(0.f))
		.ColorAndOpacity_Lambda([this]() -> FLinearColor
		{
			return FLinearColor(1.f, 1.f, 1.f, AUI::Ease(static_cast<float>((FPlatformTime::Seconds() - OpenTime) / 0.12)));
		})
		[
			SNew(SBox)
			.WidthOverride(1240.f)
			[
				SNew(SBorder)
				.BorderImage(AUI::PanelSolidBrush())
				.Padding(FMargin(32.f, 24.f, 32.f, 22.f))
				[
					SNew(SVerticalBox)
					// Header
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						[
							BuildHeaderScore(EAirsoftTeam::Blue)
						]
						+ SHorizontalBox::Slot()
						.FillWidth(1.f)
						.HAlign(HAlign_Center)
						.VAlign(VAlign_Center)
						[
							SNew(SVerticalBox)
							+ SVerticalBox::Slot()
							.AutoHeight()
							.HAlign(HAlign_Center)
							[
								SNew(STextBlock)
								.Font(AUI::Heading(16))
								.ColorAndOpacity(FLinearColor::White)
								.Text_Lambda([this]()
								{
									const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
									if (!GS || !GS->bIsMatchMap)
									{
										return FText::FromString(TEXT("STAGING AREA"));
									}
									return AUI::Upper(AAirsoftGameState::MapDisplayName(GS->MapId));
								})
							]
							+ SVerticalBox::Slot()
							.AutoHeight()
							.HAlign(HAlign_Center)
							.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
							[
								SNew(STextBlock)
								.Font(AUI::Caption(9))
								.ColorAndOpacity(AUI::TextDim())
								.Text_Lambda([this]()
								{
									const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
									if (!GS)
									{
										return FText::GetEmpty();
									}
									FString Line = AAirsoftGameState::ModeDisplayName(GS->Mode).ToUpper();
									if (GS->bIsMatchMap)
									{
										switch (GS->Mode)
										{
										case EAirsoftMode::Elimination:
											Line += FString::Printf(TEXT("  \u00B7  ROUND %d  \u00B7  FIRST TO %d"), GS->RoundNumber, GS->ScoreLimit);
											break;
										case EAirsoftMode::VIP:
											Line += FString::Printf(TEXT("  \u00B7  ROUND %d / %d"), GS->RoundNumber, GS->MaxRounds);
											break;
										case EAirsoftMode::GunGame:
										{
											const AAirsoftPlayerState* Leader = GS->GetGunGameLeader();
											Line += Leader ? FString::Printf(TEXT("  \u00B7  LEADER %s (%d/%d)"), *Leader->GetPlayerName().ToUpper(), Leader->GunLevel + 1, GS->ScoreLimit)
												: FString::Printf(TEXT("  \u00B7  %d GUNS"), GS->ScoreLimit);
											break;
										}
										default:
											Line += FString::Printf(TEXT("  \u00B7  FIRST TO %d"), GS->ScoreLimit);
											break;
										}
									}
									const float T = GS->GetTimeRemaining();
									if (T >= 0.f)
									{
										Line += TEXT("  \u00B7  ") + AUI::TimeString(T);
									}
									return FText::FromString(Line);
								})
							]
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						[
							BuildHeaderScore(EAirsoftTeam::Red)
						]
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 18.f, 0.f, 18.f))
					[
						AirsoftUIWidgets::Rule(AUI::Hairline())
					]
					// Teams (or the free-for-all standings split in two)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.FillWidth(1.f)
						.Padding(FMargin(0.f, 0.f, 16.f, 0.f))
						[
							BuildColumn(0)
						]
						+ SHorizontalBox::Slot()
						.FillWidth(1.f)
						.Padding(FMargin(16.f, 0.f, 0.f, 0.f))
						[
							BuildColumn(1)
						]
					]
					// Footer
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 14.f, 0.f, 0.f))
					[
						SNew(STextBlock)
						.AutoWrapText(true)
						.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 20))
						.ColorAndOpacity(AUI::TextDim())
						.Visibility_Lambda([this]() -> EVisibility { return UnassignedNames.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible; })
						.Text_Lambda([this]() { return FText::FromString(FString::Printf(TEXT("Unassigned: %s"), *UnassignedNames)); })
					]
				]
			]
		]
	];
}
