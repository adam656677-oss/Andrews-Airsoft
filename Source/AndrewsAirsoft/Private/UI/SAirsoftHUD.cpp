// Andrew's Airsoft - HUD layout: timer/scores/objectives, kill feed, weapon
// panel, announcements, tagged overlay / team camera, prompts, chat box and
// the staging vote panel. Text is STextBlocks bound to lambdas so everything
// updates live; shapes are painted by SAirsoftHUDCanvas underneath.

#include "SAirsoftHUD.h"

#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameState.h"
#include "AirsoftModeRules.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
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

namespace AirsoftHUDLocal
{
	constexpr int32 FeedRows = 5;
	constexpr float FeedLife = 6.f;
	constexpr float FeedFade = 0.6f;
	constexpr int32 MaxBadges = 5;
	constexpr int32 MaxGrenadeIcons = 3;

	EVisibility HudVis(bool bVisible)
	{
		return bVisible ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
	}

	/** "[F] Customize M4A1 Carbine" -> key "F", text "Customize M4A1 Carbine". */
	void SplitPrompt(const FString& Prompt, FString& OutKey, FString& OutText)
	{
		OutKey.Reset();
		OutText = Prompt;
		int32 Close = INDEX_NONE;
		if (Prompt.StartsWith(TEXT("[")) && Prompt.FindChar(TEXT(']'), Close) && Close > 1)
		{
			OutKey = Prompt.Mid(1, Close - 1);
			OutText = Prompt.Mid(Close + 1).TrimStart();
		}
	}

	/** Wraps content so its whole subtree (backgrounds included) fades with Alpha. */
	TSharedRef<SWidget> Fader(const TAttribute<FLinearColor>& Alpha, const TSharedRef<SWidget>& Content)
	{
		return SNew(SBorder)
			.BorderImage(AUI::NoBrush())
			.Padding(FMargin(0.f))
			.ColorAndOpacity(Alpha)
			[
				Content
			];
	}

	/** Index of the most votes (lowest index on a tie, so the highlight doesn't flicker), or INDEX_NONE when nobody voted. */
	int32 LeadingVote(const TArray<int32>& Votes)
	{
		int32 Best = INDEX_NONE;
		for (int32 i = 0; i < Votes.Num(); ++i)
		{
			if (Votes[i] > 0 && (Best == INDEX_NONE || Votes[i] > Votes[Best]))
			{
				Best = i;
			}
		}
		return Best;
	}

	FString WeaponLabel(FName WeaponId)
	{
		return AUI::WeaponName(WeaponId).ToUpper();
	}
}

using AirsoftHUDLocal::HudVis;

TSharedRef<SWidget> AirsoftUIScreens::CreateHUD(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftHUD, PC);
}

void SAirsoftHUD::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	SetVisibility(EVisibility::HitTestInvisible);
	ForceVolatile(true);

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SAirsoftHUDCanvas, InPC)
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.f, 22.f, 0.f, 0.f))
		[
			BuildTopCenter()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Right)
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.f, 24.f, 28.f, 0.f))
		[
			BuildKillFeed()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Right)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(0.f, 0.f, 36.f, 32.f))
		[
			BuildWeaponPanel()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Top)
		.Padding(FMargin(32.f, 110.f, 0.f, 0.f))
		[
			BuildVotePanel()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(32.f, 0.f, 0.f, 200.f))
		[
			AirsoftUIScreens::CreateChatBox(InPC)
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		.Padding(FMargin(0.f, 0.f, 0.f, 110.f))
		[
			BuildTaggedOverlay()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		.Padding(FMargin(0.f, 96.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
				return HudVis(!IsHidden() && !IsOut() && PS && PS->IsProtected());
			})
			.Text(FText::FromString(TEXT("PROTECTED")))
			.Font(AUI::Font(AUI::EFontWeight::Bold, 9, 360))
			.ColorAndOpacity(AUI::WithAlpha(AUI::Accent(), 0.9f))
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.7f))
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(0.f, 0.f, 0.f, 196.f))
		[
			BuildBottomCenter()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.f, 270.f, 0.f, 0.f))
		[
			BuildAnnouncement()
		]
	];
}

bool SAirsoftHUD::IsHidden() const
{
	return AirsoftHUDShared::IsGameplayHidden(WeakPC.Get());
}

bool SAirsoftHUD::IsOut() const
{
	const AAirsoftCharacter* Character = AUI::GetCharacter(WeakPC.Get());
	return Character && Character->IsOut();
}

// ---------------------------------------------------------------------------
// Top centre: scores, timer, mode/map, objectives, status
// ---------------------------------------------------------------------------

TSharedRef<SWidget> SAirsoftHUD::BuildTeamScore(uint8 TeamValue)
{
	const EAirsoftTeam Team = static_cast<EAirsoftTeam>(TeamValue);
	const FLinearColor Col = AUI::TeamColor(Team);
	const FString TeamLabel = Team == EAirsoftTeam::Blue ? TEXT("BLUE") : TEXT("RED");

	return SNew(SBox)
		.WidthOverride(112.f)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
			return HudVis(GS && GS->bIsMatchMap && !GS->IsFreeForAll());
		})
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(0.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::Rule(Col, 2.f)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 3.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 26))
					.ColorAndOpacity(FLinearColor::White)
					.Text_Lambda([this, Team]()
					{
						// Tags, points or round wins, depending on the mode.
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						return FText::AsNumber(GS ? GS->GetScore(Team) : 0);
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 0.f, 0.f, 2.f))
				[
					SNew(STextBlock)
					.Font(AUI::Caption(8))
					.ColorAndOpacity(Col)
					.Text_Lambda([this, Team, TeamLabel]()
					{
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
						FString Label = PS && PS->Team == Team ? TeamLabel + TEXT(" \u00B7 YOU") : TeamLabel;
						if (GS && GS->Mode == EAirsoftMode::VIP && GS->AttackingTeam != EAirsoftTeam::None)
						{
							Label += GS->AttackingTeam == Team ? TEXT(" \u00B7 ATK") : TEXT(" \u00B7 DEF");
						}
						return FText::FromString(Label);
					})
				]
				// Players still standing this round (one-life modes).
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 0.f, 0.f, 6.f))
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 9, 160))
					.ColorAndOpacity(AUI::TextColor())
					.Visibility_Lambda([this]() -> EVisibility
					{
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						return HudVis(GS && GS->IsRoundBased() && (GS->Phase == EAirsoftPhase::Live || GS->Phase == EAirsoftPhase::PostRound));
					})
					.Text_Lambda([this, Team]()
					{
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						return FText::FromString(FString::Printf(TEXT("%d STANDING"), GS ? GS->GetAlive(Team) : 0));
					})
				]
			]
		];
}

TSharedRef<SWidget> SAirsoftHUD::BuildFreeForAllBox(bool bLeader)
{
	return SNew(SBox)
		.WidthOverride(150.f)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
			return HudVis(GS && GS->IsFreeForAll());
		})
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(0.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::Rule(AUI::Accent(), 2.f)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 3.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 26))
					.ColorAndOpacity(FLinearColor::White)
					.Text_Lambda([this, bLeader]()
					{
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						const AAirsoftPlayerState* PS = bLeader ? (GS ? GS->GetGunGameLeader() : nullptr) : AUI::GetPlayerState(WeakPC.Get());
						return FText::FromString(FString::Printf(TEXT("%d/%d"), PS ? PS->GunLevel + 1 : 0, GS ? GS->ScoreLimit : 0));
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(6.f, 0.f, 6.f, 7.f))
				[
					SNew(STextBlock)
					.Font(AUI::Caption(8))
					.ColorAndOpacity(AUI::Accent())
					.Text_Lambda([this, bLeader]()
					{
						if (!bLeader)
						{
							return FText::FromString(TEXT("YOUR LEVEL"));
						}
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						const AAirsoftPlayerState* Leader = GS ? GS->GetGunGameLeader() : nullptr;
						return Leader ? AUI::Upper(Leader->GetPlayerName().Left(14)) : FText::FromString(TEXT("LEADER"));
					})
				]
			]
		];
}

FText SAirsoftHUD::PhaseCaption() const
{
	const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
	if (!GS)
	{
		return FText::FromString(TEXT("CONNECTING"));
	}
	switch (GS->Phase)
	{
	case EAirsoftPhase::Waiting: return FText::FromString(GS->bIsMatchMap ? TEXT("STANDBY") : TEXT("WAITING FOR PLAYERS"));
	case EAirsoftPhase::Intermission: return FText::FromString(TEXT("NEXT MATCH IN"));
	case EAirsoftPhase::Briefing:
		return GS->IsRoundBased() ? FText::FromString(FString::Printf(TEXT("ROUND %d \u00B7 FREEZE"), GS->RoundNumber)) : FText::FromString(TEXT("BRIEFING"));
	case EAirsoftPhase::Live:
		if (!GS->bIsMatchMap)
		{
			return FText::FromString(TEXT("STAGING"));
		}
		switch (GS->Mode)
		{
		case EAirsoftMode::Elimination: return FText::FromString(FString::Printf(TEXT("ROUND %d \u00B7 FIRST TO %d"), GS->RoundNumber, GS->ScoreLimit));
		case EAirsoftMode::VIP: return FText::FromString(FString::Printf(TEXT("ROUND %d / %d"), GS->RoundNumber, GS->MaxRounds));
		case EAirsoftMode::GunGame: return FText::FromString(FString::Printf(TEXT("%d GUNS TO CLIMB"), GS->ScoreLimit));
		default: return FText::FromString(FString::Printf(TEXT("FIRST TO %d"), GS->ScoreLimit));
		}
	case EAirsoftPhase::PostRound:
		return FText::FromString(GS->bMatchOver ? TEXT("MATCH OVER") : TEXT("ROUND OVER"));
	}
	return FText::GetEmpty();
}

FString SAirsoftHUD::ModeLine() const
{
	const AAirsoftPlayerController* PC = WeakPC.Get();
	const AAirsoftGameState* GS = AUI::GetGameState(PC);
	const AAirsoftPlayerState* PS = AUI::GetPlayerState(PC);
	if (!GS || !GS->bIsMatchMap || GS->Phase == EAirsoftPhase::Waiting)
	{
		return FString();
	}
	if (GS->Mode == EAirsoftMode::VIP)
	{
		const AAirsoftPlayerState* VIP = GS->VIPPlayer.Get();
		if (VIP && VIP == PS)
		{
			return TEXT("YOU ARE THE VIP \u00B7 PISTOL ONLY \u00B7 GET TO EXTRACT");
		}
		const bool bAttack = PS && PS->Team == GS->AttackingTeam;
		const FString Who = VIP ? VIP->GetPlayerName().ToUpper() : FString(TEXT("NO VIP"));
		return bAttack ? FString::Printf(TEXT("ESCORT %s TO EXTRACT"), *Who) : FString::Printf(TEXT("STOP %s \u00B7 DEFEND EXTRACT"), *Who);
	}
	if (GS->Mode == EAirsoftMode::GunGame && PS)
	{
		const TArray<FName> Ladder = AirsoftRules::GunGameLadder();
		if (Ladder.Num() == 0)
		{
			return FString();
		}
		const int32 Level = FMath::Clamp(PS->GunLevel, 0, Ladder.Num() - 1);
		if (Level >= Ladder.Num() - 1)
		{
			return TEXT("FINAL WEAPON \u00B7 ONE TAG WINS");
		}
		return FString::Printf(TEXT("NEXT GUN: %s"), *AirsoftHUDLocal::WeaponLabel(Ladder[Level + 1]));
	}
	return FString();
}

TSharedRef<SWidget> SAirsoftHUD::BuildTopCenter()
{
	TSharedRef<SHorizontalBox> Badges = SNew(SHorizontalBox);
	for (int32 i = 0; i < AirsoftHUDLocal::MaxBadges; ++i)
	{
		Badges->AddSlot()
		.AutoWidth()
		.Padding(FMargin(3.f, 0.f))
		[
			SNew(SBox)
			.Visibility_Lambda([this, i]() -> EVisibility
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				const bool bShow = GS && GS->Mode == EAirsoftMode::Domination && GS->Objectives.IsValidIndex(i)
					&& GS->Objectives[i] && GS->Objectives[i]->bActive;
				return HudVis(bShow);
			})
			[
				SNew(SAirsoftObjectiveBadge, WeakPC.Get(), i)
			]
		];
	}

	return SNew(SVerticalBox)
		.Visibility_Lambda([this]() -> EVisibility { return HudVis(!IsHidden()); })
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				BuildTeamScore(static_cast<uint8>(EAirsoftTeam::Blue))
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				BuildFreeForAllBox(false)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(4.f, 0.f))
			[
				SNew(SBox)
				.MinDesiredWidth(150.f)
				[
					SNew(SBorder)
					.BorderImage(AUI::PanelBrush())
					.Padding(FMargin(18.f, 5.f, 18.f, 7.f))
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot()
						.AutoHeight()
						.HAlign(HAlign_Center)
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 26, 60))
							.Visibility_Lambda([this]() -> EVisibility
							{
								const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
								return HudVis(GS && GS->GetTimeRemaining() >= 0.f);
							})
							.Text_Lambda([this]()
							{
								const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
								return FText::FromString(AUI::TimeString(GS ? GS->GetTimeRemaining() : 0.f));
							})
							.ColorAndOpacity_Lambda([this]() -> FSlateColor
							{
								const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
								if (GS && GS->bIsMatchMap && GS->Phase == EAirsoftPhase::Live)
								{
									const float T = GS->GetTimeRemaining();
									if (T >= 0.f && T <= 10.f)
									{
										return FLinearColor::LerpUsingHSV(AUI::Danger(), FLinearColor::White, AUI::Pulse(1.f) * 0.4f);
									}
									if (T >= 0.f && T <= 30.f)
									{
										return AUI::Accent();
									}
								}
								return FLinearColor::White;
							})
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						.HAlign(HAlign_Center)
						[
							SNew(STextBlock)
							.Font(AUI::Caption(8))
							.ColorAndOpacity(AUI::TextDim())
							.Text_Lambda([this]() { return PhaseCaption(); })
						]
					]
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				BuildTeamScore(static_cast<uint8>(EAirsoftTeam::Red))
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				BuildFreeForAllBox(true)
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 8.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Caption(9))
			.ColorAndOpacity(AUI::TextColor())
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.7f))
			.Text_Lambda([this]()
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				if (!GS || !GS->bIsMatchMap)
				{
					return FText::FromString(TEXT("STAGING AREA"));
				}
				return FText::FromString(FString::Printf(TEXT("%s  \u00B7  %s"),
					*AAirsoftGameState::ModeDisplayName(GS->Mode).ToUpper(), *AAirsoftGameState::MapDisplayName(GS->MapId).ToUpper()));
			})
		]
		// VIP role / Gun Game next weapon.
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 4.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Bold, 10, 200))
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.7f))
			.Visibility_Lambda([this]() -> EVisibility { return HudVis(!ModeLine().IsEmpty()); })
			.Text_Lambda([this]() { return FText::FromString(ModeLine()); })
			.ColorAndOpacity_Lambda([this]() -> FSlateColor
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
				if (GS && GS->Mode == EAirsoftMode::VIP && PS)
				{
					return GS->VIPPlayer.Get() == PS ? AUI::Accent() : AUI::TeamColor(PS->Team);
				}
				return AUI::Accent();
			})
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 8.f, 0.f, 0.f))
		[
			Badges
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 40))
			.ColorAndOpacity(AUI::Accent())
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.8f))
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				return HudVis(GS && !GS->StatusMessage.IsEmpty());
			})
			.Text_Lambda([this]()
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				return GS ? FText::FromString(GS->StatusMessage) : FText::GetEmpty();
			})
		];
}

// ---------------------------------------------------------------------------
// Kill feed
// ---------------------------------------------------------------------------

const FAirsoftKillFeedEntry* SAirsoftHUD::FeedEntry(int32 Row) const
{
	const AAirsoftPlayerController* PC = WeakPC.Get();
	if (!PC)
	{
		return nullptr;
	}
	const TArray<FAirsoftKillFeedEntry>& Feed = PC->GetKillFeed();
	const int32 Index = Feed.Num() - 1 - Row;
	return Feed.IsValidIndex(Index) ? &Feed[Index] : nullptr;
}

float SAirsoftHUD::FeedAlpha(int32 Row) const
{
	const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
	if (!Entry)
	{
		return 0.f;
	}
	const float Age = FMath::Max(0.f, static_cast<float>(AUI::HudNow(WeakPC.Get()) - Entry->Time));
	if (Age >= AirsoftHUDLocal::FeedLife + AirsoftHUDLocal::FeedFade)
	{
		return 0.f;
	}
	return AUI::Ease(Age / 0.2f) * (1.f - AUI::Ease((Age - AirsoftHUDLocal::FeedLife) / AirsoftHUDLocal::FeedFade));
}

TSharedRef<SWidget> SAirsoftHUD::BuildKillFeedRow(int32 Row)
{
	const FSlateFontInfo NameFont = AUI::Font(AUI::EFontWeight::Bold, 11, 40);
	return AirsoftHUDLocal::Fader(
		TAttribute<FLinearColor>::CreateLambda([this, Row]() { return FLinearColor(1.f, 1.f, 1.f, FeedAlpha(Row)); }),
		SNew(SBorder)
		.Visibility_Lambda([this, Row]() -> EVisibility { return HudVis(!IsHidden() && FeedAlpha(Row) > 0.f); })
		.BorderImage(AUI::RoundedBrush())
		.BorderBackgroundColor_Lambda([this, Row]() -> FSlateColor
		{
			const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
			return (Entry && Entry->bInvolvesMe) ? FLinearColor(1.f, 0.55f, 0.05f, 0.16f) : FLinearColor(0.f, 0.f, 0.f, 0.5f);
		})
		.Padding(FMargin(12.f, 5.f, 0.f, 5.f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Font(NameFont)
				.Text_Lambda([this, Row]()
				{
					const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
					return Entry ? FText::FromString(Entry->Shooter) : FText::GetEmpty();
				})
				.ColorAndOpacity_Lambda([this, Row]() -> FSlateColor
				{
					const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
					return Entry ? AUI::TeamColor(Entry->ShooterTeam) : AUI::TextColor();
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(10.f, 0.f))
			[
				SNew(STextBlock)
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextDim())
				.Text_Lambda([this, Row]()
				{
					const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
					return Entry ? AUI::Upper(AUI::WeaponName(Entry->WeaponId)) : FText::GetEmpty();
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Font(NameFont)
				.Text_Lambda([this, Row]()
				{
					const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
					return Entry ? FText::FromString(Entry->Victim) : FText::GetEmpty();
				})
				.ColorAndOpacity_Lambda([this, Row]() -> FSlateColor
				{
					const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
					return Entry ? AUI::TeamColor(Entry->VictimTeam) : AUI::TextColor();
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(12.f, 0.f, 0.f, 0.f))
			[
				SNew(SBox)
				.WidthOverride(2.f)
				[
					SNew(SBorder)
					.BorderImage(AUI::WhiteBrush())
					.Padding(FMargin(0.f))
					.BorderBackgroundColor_Lambda([this, Row]() -> FSlateColor
					{
						const FAirsoftKillFeedEntry* Entry = FeedEntry(Row);
						return (Entry && Entry->bInvolvesMe) ? AUI::Accent() : FLinearColor(0.f, 0.f, 0.f, 0.f);
					})
				]
			]
		]);
}

TSharedRef<SWidget> SAirsoftHUD::BuildKillFeed()
{
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox);
	for (int32 Row = 0; Row < AirsoftHUDLocal::FeedRows; ++Row)
	{
		Box->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Right)
		.Padding(FMargin(0.f, 0.f, 0.f, 4.f))
		[
			BuildKillFeedRow(Row)
		];
	}
	return Box;
}

// ---------------------------------------------------------------------------
// Weapon panel (bottom right)
// ---------------------------------------------------------------------------

TSharedRef<SWidget> SAirsoftHUD::BuildWeaponPanel()
{
	TSharedRef<SHorizontalBox> Grenades = SNew(SHorizontalBox);
	for (int32 i = 0; i < AirsoftHUDLocal::MaxGrenadeIcons; ++i)
	{
		Grenades->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(0.f, 0.f, 4.f, 0.f))
		[
			SNew(SBox)
			.WidthOverride(7.f)
			.HeightOverride(12.f)
			.Visibility_Lambda([this, i]() -> EVisibility
			{
				const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
				return HudVis(Combat && i < Combat->GetGrenades());
			})
			[
				SNew(SBorder)
				.BorderImage(AUI::RoundedBrush())
				.BorderBackgroundColor(AUI::WithAlpha(AUI::TextColor(), 0.85f))
				.Padding(FMargin(0.f))
			]
		];
	}

	return SNew(SBox)
		.Visibility_Lambda([this]() -> EVisibility
		{
			return HudVis(!IsHidden() && !IsOut() && AUI::GetCombat(WeakPC.Get()) != nullptr);
		})
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(20.f, 12.f, 0.f, 14.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SVerticalBox)
					// Weapon name
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					[
						SNew(STextBlock)
						.Font(AUI::Caption(10))
						.ColorAndOpacity(AUI::TextColor())
						.Text_Lambda([this]()
						{
							const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
							if (!Combat)
							{
								return FText::GetEmpty();
							}
							const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(Combat->Current().Id);
							return AUI::Upper(Def ? Def->Name : Combat->Current().Name);
						})
					]
					// Mag / reserve
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Bottom)
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Bold, 40))
							.Text_Lambda([this]()
							{
								const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
								return FText::AsNumber(Combat ? Combat->GetLocalMag() : 0);
							})
							.ColorAndOpacity_Lambda([this]() -> FSlateColor
							{
								const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
								if (!Combat)
								{
									return FLinearColor::White;
								}
								const int32 Mag = Combat->GetLocalMag();
								const int32 MagSize = FMath::Max(1, Combat->Current().MagSize);
								if (Mag <= 0)
								{
									return AUI::WithAlpha(AUI::Danger(), 0.55f + 0.45f * AUI::Pulse(2.5f));
								}
								if (Mag * 4 <= MagSize)
								{
									return AUI::Accent();
								}
								return FLinearColor::White;
							})
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Bottom)
						.Padding(FMargin(8.f, 0.f, 0.f, 8.f))
						[
							SNew(STextBlock)
							.Font(AUI::Font(AUI::EFontWeight::Regular, 15, 40))
							.ColorAndOpacity(AUI::TextDim())
							.Text_Lambda([this]()
							{
								const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
								return FText::FromString(FString::Printf(TEXT("/ %d"), Combat ? Combat->GetLocalReserve() : 0));
							})
						]
					]
					// Grenades, light, fire mode
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					.Padding(FMargin(0.f, 2.f, 0.f, 0.f))
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						.Padding(FMargin(0.f, 0.f, 8.f, 0.f))
						[
							Grenades
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						.Padding(FMargin(0.f, 0.f, 8.f, 0.f))
						[
							SNew(SBorder)
							.Visibility_Lambda([this]() -> EVisibility
							{
								const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
								return HudVis(Combat && Combat->IsLightOn());
							})
							.BorderImage(AUI::RoundedBrush())
							.BorderBackgroundColor(AUI::Accent())
							.Padding(FMargin(6.f, 1.f))
							[
								SNew(STextBlock)
								.Text(FText::FromString(TEXT("LIGHT")))
								.Font(AUI::Font(AUI::EFontWeight::Bold, 8, 200))
								.ColorAndOpacity(FLinearColor(0.02f, 0.02f, 0.02f))
							]
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.VAlign(VAlign_Center)
						[
							SNew(SBorder)
							.BorderImage(AUI::OutlineBrush())
							.BorderBackgroundColor(FLinearColor(1.f, 1.f, 1.f, 0.35f))
							.Padding(FMargin(6.f, 1.f))
							[
								SNew(STextBlock)
								.Font(AUI::Font(AUI::EFontWeight::Bold, 8, 200))
								.ColorAndOpacity(AUI::TextColor())
								.Text_Lambda([this]()
								{
									const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
									return Combat ? FText::FromString(AirsoftWeapons::FireModeName(Combat->GetFireMode())) : FText::GetEmpty();
								})
							]
						]
					]
					// Reload progress
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					.Padding(FMargin(0.f, 8.f, 0.f, 0.f))
					[
						SNew(SVerticalBox)
						.Visibility_Lambda([this]() -> EVisibility
						{
							const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
							return HudVis(Combat && Combat->IsReloading());
						})
						+ SVerticalBox::Slot()
						.AutoHeight()
						.HAlign(HAlign_Right)
						[
							SNew(STextBlock)
							.Text(FText::FromString(TEXT("RELOADING")))
							.Font(AUI::Caption(8))
							.ColorAndOpacity(AUI::Accent())
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						.Padding(FMargin(0.f, 4.f, 0.f, 0.f))
						[
							SNew(SAirsoftBar)
							.Width(170.f)
							.Height(3.f)
							.Fraction_Lambda([this]()
							{
								const UAirsoftCombatComponent* Combat = AUI::GetCombat(WeakPC.Get());
								return Combat ? Combat->GetReloadProgress() : 0.f;
							})
						]
					]
				]
				// Amber edge on the right.
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(FMargin(16.f, 0.f, 0.f, 0.f))
				[
					SNew(SBox)
					.WidthOverride(2.f)
					[
						SNew(SBorder)
						.BorderImage(AUI::WhiteBrush())
						.BorderBackgroundColor(AUI::Accent())
						.Padding(FMargin(0.f))
					]
				]
			]
		];
}

// ---------------------------------------------------------------------------
// Announcement
// ---------------------------------------------------------------------------

float SAirsoftHUD::AnnouncementAlpha() const
{
	const AAirsoftPlayerController* PC = WeakPC.Get();
	if (!PC)
	{
		return 0.f;
	}
	const FAirsoftAnnouncement& A = PC->GetAnnouncement();
	if (A.Duration <= 0.f || (A.Title.IsEmpty() && A.Sub.IsEmpty()))
	{
		return 0.f;
	}
	const float Age = static_cast<float>(AUI::HudNow(PC) - A.Time);
	if (Age < 0.f || Age > A.Duration)
	{
		return 0.f;
	}
	const float FadeOut = FMath::Max(0.05f, FMath::Min(0.6f, A.Duration * 0.3f));
	return AUI::Ease(Age / 0.25f) * (1.f - AUI::Ease((Age - (A.Duration - FadeOut)) / FadeOut));
}

TSharedRef<SWidget> SAirsoftHUD::BuildAnnouncement()
{
	return AirsoftHUDLocal::Fader(
		TAttribute<FLinearColor>::CreateLambda([this]() { return FLinearColor(1.f, 1.f, 1.f, AnnouncementAlpha()); }),
		SNew(SVerticalBox)
		.Visibility_Lambda([this]() -> EVisibility { return HudVis(AnnouncementAlpha() > 0.f); })
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(56.f)
			.HeightOverride(2.f)
			[
				SNew(SBorder)
				.BorderImage(AUI::WhiteBrush())
				.Padding(FMargin(0.f))
				.BorderBackgroundColor_Lambda([this]() -> FSlateColor
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return PC ? PC->GetAnnouncement().Color : AUI::Accent();
				})
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Bold, 34, 320))
			.ShadowOffset(FVector2D(1.f, 2.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.75f))
			.Text_Lambda([this]()
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return PC ? AUI::Upper(PC->GetAnnouncement().Title) : FText::GetEmpty();
			})
			.ColorAndOpacity_Lambda([this]() -> FSlateColor
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return PC ? PC->GetAnnouncement().Color : FLinearColor::White;
			})
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 4.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Regular, 15, 60))
			.ColorAndOpacity(AUI::TextColor())
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.75f))
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return HudVis(PC && !PC->GetAnnouncement().Sub.IsEmpty());
			})
			.Text_Lambda([this]()
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return PC ? FText::FromString(PC->GetAnnouncement().Sub) : FText::GetEmpty();
			})
		]);
}

// ---------------------------------------------------------------------------
// Tagged ("HIT") overlay
// ---------------------------------------------------------------------------

TSharedRef<SWidget> SAirsoftHUD::BuildTaggedOverlay()
{
	return SNew(SVerticalBox)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftPlayerController* PC = WeakPC.Get();
			return HudVis(!IsHidden() && IsOut() && PC && !PC->IsTeamCamActive());
		})
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Visibility_Lambda([this]() -> EVisibility
			{
				// The controller also announces "HIT" when you are tagged; don't show it twice.
				const AAirsoftPlayerController* PC = WeakPC.Get();
				const bool bAnnouncingHit = PC && AnnouncementAlpha() > 0.f && PC->GetAnnouncement().Title.Equals(TEXT("HIT"), ESearchCase::IgnoreCase);
				return bAnnouncingHit ? EVisibility::Hidden : EVisibility::HitTestInvisible;
			})
			.Text(FText::FromString(TEXT("HIT")))
			.Font(AUI::Font(AUI::EFontWeight::Bold, 60, 700))
			.ColorAndOpacity(AUI::Danger())
			.ShadowOffset(FVector2D(2.f, 2.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.8f))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 2.f, 0.f, 12.f))
		[
			SNew(SBox)
			.WidthOverride(64.f)
			.HeightOverride(2.f)
			[
				SNew(SBorder)
				.BorderImage(AUI::WhiteBrush())
				.BorderBackgroundColor(AUI::WithAlpha(AUI::Danger(), 0.8f))
				.Padding(FMargin(0.f))
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Regular, 15, 40))
			.ColorAndOpacity(AUI::TextColor())
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.8f))
			.Text_Lambda([this]()
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				const AAirsoftPlayerState* PS = AUI::GetPlayerState(PC);
				FString By = PS ? PS->LastTaggedBy : FString();
				if (By.IsEmpty())
				{
					if (const AAirsoftCharacter* Character = AUI::GetCharacter(PC))
					{
						By = Character->TaggedByName;
					}
				}
				return By.IsEmpty()
					? FText::FromString(TEXT("You're out \u2014 walk off"))
					: FText::FromString(FString::Printf(TEXT("Tagged by %s \u2014 walk off"), *By));
			})
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Bold, 13, 300))
			.ColorAndOpacity(AUI::Accent())
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.8f))
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
				return HudVis(PS && PS->RespawnAt > 0.f);
			})
			.Text_Lambda([this]()
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				const AAirsoftPlayerState* PS = AUI::GetPlayerState(PC);
				const AAirsoftGameState* GS = AUI::GetGameState(PC);
				if (!PS || !GS || PS->RespawnAt <= 0.f)
				{
					return FText::GetEmpty();
				}
				const double Remaining = static_cast<double>(PS->RespawnAt) - static_cast<double>(GS->GetServerWorldTimeSeconds());
				if (Remaining <= 0.0)
				{
					return FText::FromString(TEXT("BACK IN"));
				}
				return FText::FromString(FString::Printf(TEXT("BACK IN %d"), FMath::CeilToInt(static_cast<float>(Remaining))));
			})
		]
		// One-life modes: no respawn until the next round.
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
		[
			SNew(STextBlock)
			.Font(AUI::Font(AUI::EFontWeight::Bold, 13, 300))
			.ColorAndOpacity(AUI::Accent())
			.ShadowOffset(FVector2D(1.f, 1.f))
			.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.8f))
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				return HudVis(GS && GS->bIsMatchMap && !AirsoftRules::HasRespawns(GS->Mode));
			})
			.Text(FText::FromString(TEXT("OUT FOR THE ROUND · WATCHING YOUR TEAM IN A MOMENT")))
		];
}

// ---------------------------------------------------------------------------
// Bottom centre: briefing freeze + interact prompt
// ---------------------------------------------------------------------------

TSharedRef<SWidget> SAirsoftHUD::BuildBottomCenter()
{
	return SNew(SVerticalBox)
		.Visibility_Lambda([this]() -> EVisibility { return HudVis(!IsHidden()); })
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 0.f, 0.f, 10.f))
		[
			SNew(SBorder)
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
				const AAirsoftCharacter* Character = AUI::GetCharacter(WeakPC.Get());
				return HudVis(GS && GS->Phase == EAirsoftPhase::Briefing && Character && Character->IsFrozen());
			})
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(18.f, 8.f))
			[
				SNew(STextBlock)
				.Text_Lambda([this]()
				{
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					if (GS && GS->IsRoundBased())
					{
						return FText::FromString(FString::Printf(TEXT("ROUND %d \u2014 FROZEN \u00b7 PICK YOUR LOADOUT [L]"), GS->RoundNumber));
					}
					if (GS && GS->IsFreeForAll())
					{
						return FText::FromString(TEXT("FROZEN \u2014 EVERYONE IS AN ENEMY"));
					}
					return FText::FromString(TEXT("FROZEN \u2014 BRIEFING"));
				})
				.Font(AUI::Font(AUI::EFontWeight::Bold, 11, 320))
				.ColorAndOpacity(AUI::TextColor())
			]
		]
		// Team camera: who we are watching and how to switch.
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.f, 0.f, 0.f, 10.f))
		[
			SNew(SBorder)
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return HudVis(PC && PC->IsTeamCamActive());
			})
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(16.f, 8.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.f, 0.f, 12.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 11, 260))
					.Text_Lambda([this]()
					{
						const AAirsoftPlayerController* PC = WeakPC.Get();
						return FText::FromString(FString::Printf(TEXT("WATCHING %s"), PC ? *PC->GetTeamCamName().ToUpper() : TEXT("")));
					})
					.ColorAndOpacity_Lambda([this]() -> FSlateColor
					{
						const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
						return AUI::TeamColor(PS ? PS->Team : EAirsoftTeam::None);
					})
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					AirsoftUIWidgets::Hint(FText::FromString(TEXT("LMB")), FText::FromString(TEXT("NEXT TEAMMATE")))
				]
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(SBorder)
			.Visibility_Lambda([this]() -> EVisibility
			{
				const AAirsoftPlayerController* PC = WeakPC.Get();
				return HudVis(PC && !IsOut() && !PC->GetInteractPrompt().IsEmpty());
			})
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(12.f, 7.f, 16.f, 7.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.f, 0.f, 10.f, 0.f))
				[
					SNew(SBorder)
					.Visibility_Lambda([this]() -> EVisibility
					{
						const AAirsoftPlayerController* PC = WeakPC.Get();
						FString Key, Text;
						AirsoftHUDLocal::SplitPrompt(PC ? PC->GetInteractPrompt() : FString(), Key, Text);
						return HudVis(!Key.IsEmpty());
					})
					.BorderImage(AUI::OutlineBrush())
					.BorderBackgroundColor(AUI::Accent())
					.Padding(FMargin(7.f, 1.f))
					[
						SNew(STextBlock)
						.Font(AUI::Font(AUI::EFontWeight::Bold, 10, 60))
						.ColorAndOpacity(AUI::Accent())
						.Text_Lambda([this]()
						{
							const AAirsoftPlayerController* PC = WeakPC.Get();
							FString Key, Text;
							AirsoftHUDLocal::SplitPrompt(PC ? PC->GetInteractPrompt() : FString(), Key, Text);
							return FText::FromString(Key);
						})
					]
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 40))
					.ColorAndOpacity(AUI::TextColor())
					.Text_Lambda([this]()
					{
						const AAirsoftPlayerController* PC = WeakPC.Get();
						FString Key, Text;
						AirsoftHUDLocal::SplitPrompt(PC ? PC->GetInteractPrompt() : FString(), Key, Text);
						return FText::FromString(Text);
					})
				]
			]
		];
}

// ---------------------------------------------------------------------------
// Staging vote panel
// ---------------------------------------------------------------------------


TSharedRef<SWidget> SAirsoftHUD::BuildVoteRow(const FText& Label, const FText& Detail, TFunction<int32()> Count, TFunction<bool()> IsMine,
	TFunction<bool()> IsLeading, TFunction<bool()> IsDimmed)
{
	return SNew(SBorder)
		.BorderImage(AUI::RoundedBrush())
		.BorderBackgroundColor_Lambda([IsMine, IsLeading]() -> FSlateColor
		{
			if (IsMine())
			{
				return FLinearColor(1.f, 0.55f, 0.05f, 0.16f);
			}
			return IsLeading() ? FLinearColor(1.f, 1.f, 1.f, 0.06f) : FLinearColor(0.f, 0.f, 0.f, 0.f);
		})
		.Padding(FMargin(0.f, 4.f, 8.f, 4.f))
		[
			SNew(SHorizontalBox)
			// Leading entry: amber edge.
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				SNew(SBox)
				.WidthOverride(2.f)
				[
					SNew(SBorder)
					.BorderImage(AUI::WhiteBrush())
					.Padding(FMargin(0.f))
					.BorderBackgroundColor_Lambda([IsLeading]() -> FSlateColor { return IsLeading() ? AUI::Accent() : FLinearColor(0.f, 0.f, 0.f, 0.f); })
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.VAlign(VAlign_Center)
			.Padding(FMargin(10.f, 0.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(Label)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 10, 160))
					.ColorAndOpacity_Lambda([IsMine, IsDimmed]() -> FSlateColor
					{
						if (IsMine())
						{
							return AUI::Accent();
						}
						return IsDimmed() ? AUI::TextMuted() : AUI::TextColor();
					})
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(8.f, 0.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Visibility(Detail.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible)
					.Text(Detail)
					.Font(AUI::Caption(7))
					.ColorAndOpacity(AUI::TextDim())
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Font(AUI::Font(AUI::EFontWeight::Bold, 11))
				.ColorAndOpacity_Lambda([IsMine]() -> FSlateColor { return IsMine() ? AUI::Accent() : AUI::TextDim(); })
				.Text_Lambda([Count]() { return FText::AsNumber(Count()); })
			]
		];
}

TSharedRef<SWidget> SAirsoftHUD::BuildVotePanel()
{
	auto Header = [](const TCHAR* Key, const TCHAR* Label, const TCHAR* Hint) -> TSharedRef<SWidget>
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				AirsoftUIWidgets::KeyCap(FText::FromString(Key), 8)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(8.f, 0.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(Label))
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextColor())
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(8.f, 0.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(FText::FromString(Hint))
				.Font(AUI::Caption(7))
				.ColorAndOpacity(AUI::TextDim())
			];
	};

	TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
	Rows->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		Header(TEXT("F1"), TEXT("MODE"), TEXT("NEXT MODE"))
	];
	for (int32 i = 0; i < AirsoftRules::NumModes; ++i)
	{
		const EAirsoftMode RowMode = AirsoftRules::ModeFromIndex(i);
		Rows->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 2.f))
		[
			BuildVoteRow(
				AUI::Upper(AirsoftRules::ModeName(RowMode)),
				FText::FromString(AirsoftRules::IsFreeForAll(RowMode) ? TEXT("FFA") : (AirsoftRules::IsRoundBased(RowMode) ? TEXT("ROUNDS") : TEXT(""))),
				[this, i]() -> int32
				{
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					return (GS && GS->ModeVotes.IsValidIndex(i)) ? GS->ModeVotes[i] : 0;
				},
				[this, i]() -> bool
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return PC && PC->GetMyModeVote() == i;
				},
				[this, i]() -> bool
				{
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					return GS && AirsoftHUDLocal::LeadingVote(GS->ModeVotes) == i;
				},
				[]() -> bool { return false; })
		];
	}

	Rows->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.f, 10.f, 0.f, 4.f))
	[
		Header(TEXT("F2"), TEXT("MAP"), TEXT("NEXT MAP"))
	];
	const TArray<FAirsoftMapInfo>& Maps = AirsoftRules::Maps();
	for (int32 i = 0; i < Maps.Num(); ++i)
	{
		const FAirsoftMapInfo& Info = Maps[i];
		const FString Players = FString::Printf(TEXT("%d–%d PLAYERS"), Info.MinPlayers, Info.MaxPlayers);
		Rows->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 2.f))
		[
			BuildVoteRow(
				AUI::Upper(AirsoftRules::MapDisplayName(Info.Key)),
				FText::FromString(Players),
				[this, i]() -> int32
				{
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					return (GS && GS->MapVotes.IsValidIndex(i)) ? GS->MapVotes[i] : 0;
				},
				[this, i]() -> bool
				{
					const AAirsoftPlayerController* PC = WeakPC.Get();
					return PC && PC->GetMyMapVote() == i;
				},
				[this, i]() -> bool
				{
					const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
					return GS && AirsoftHUDLocal::LeadingVote(GS->MapVotes) == i;
				},
				[this, i]() -> bool
				{
					// Dim maps that can't run the mode this player picked.
					const AAirsoftPlayerController* PC = WeakPC.Get();
					const TArray<FAirsoftMapInfo>& List = AirsoftRules::Maps();
					return PC && PC->GetMyModeVote() >= 0 && List.IsValidIndex(i) && !List[i].SupportsMode(AirsoftRules::ModeFromIndex(PC->GetMyModeVote()));
				})
		];
	}

	return SNew(SBox)
		.WidthOverride(340.f)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
			return HudVis(!IsHidden() && GS && !GS->bIsMatchMap
				&& (GS->Phase == EAirsoftPhase::Intermission || GS->Phase == EAirsoftPhase::Waiting));
		})
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(16.f, 14.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("NEXT MATCH")))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 6.f, 0.f, 12.f))
				[
					SNew(STextBlock)
					.AutoWrapText(true)
					.Text(FText::FromString(TEXT("F1 and F2 step your vote along each list. Or open the menu (Esc / P) and click.")))
					.Font(AUI::Font(AUI::EFontWeight::Regular, 10))
					.ColorAndOpacity(AUI::TextDim())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					Rows
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Caption(8))
					.ColorAndOpacity(AUI::Accent())
					.Text_Lambda([this]()
					{
						const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
						if (GS && GS->Phase == EAirsoftPhase::Intermission && GS->GetTimeRemaining() >= 0.f)
						{
							return FText::FromString(FString::Printf(TEXT("VOTES LOCK IN %s"), *AUI::TimeString(GS->GetTimeRemaining())));
						}
						return FText::FromString(TEXT("WAITING FOR PLAYERS"));
					})
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 4.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Caption(7))
					.ColorAndOpacity(AUI::TextDim())
					.Text(FText::FromString(TEXT("MOST VOTES WINS (TIES AT RANDOM)  ·  ENTER CHAT  ·  Y TEAM")))
				]
			]
		];
}
