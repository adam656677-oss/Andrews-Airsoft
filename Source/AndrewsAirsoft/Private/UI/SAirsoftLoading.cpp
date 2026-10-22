// Andrew's Airsoft - the loading card between maps, and the practice-range
// walkthrough that teaches the controls one step at a time.
//
// The loading card is painted by the movie player from its own thread while the
// old world is torn down, so it holds only strings and Slate: no UObjects.

#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftKeyBindings.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPracticeTarget.h"
#include "AirsoftSaveGame.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "EngineUtils.h"
#include "HAL/PlatformTime.h"
#include "Rendering/DrawElements.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftLoadingLocal
{
	/** Key cap text for a rebindable control, from the player's saved bindings. */
	FString Key(const FAirsoftUserSettings* Settings, const TCHAR* SlotId)
	{
		static const FAirsoftUserSettings Defaults;
		return AirsoftKeyBindings::KeyLabel(AirsoftKeyBindings::KeyFor(Settings ? *Settings : Defaults, FName(SlotId)));
	}

	const FAirsoftUserSettings* CurrentSettings()
	{
		UGameViewportClient* Viewport = GEngine ? GEngine->GameViewport : nullptr;
		UAirsoftGameInstance* GI = Viewport ? Cast<UAirsoftGameInstance>(Viewport->GetGameInstance()) : nullptr;
		return GI ? &GI->GetUserSettings() : nullptr;
	}

	/** One tip, picked at random, with the player's own keys filled in. */
	FString PickTip()
	{
		const FAirsoftUserSettings* S = CurrentSettings();
		const TArray<FString> Tips = {
			FString::Printf(TEXT("Lean with %s and %s to look past cover without stepping out of it."), *Key(S, TEXT("LeanLeft")), *Key(S, TEXT("LeanRight"))),
			FString::Printf(TEXT("Sprint (%s), then crouch (%s), to slide into cover."), *Key(S, TEXT("Sprint")), *Key(S, TEXT("Crouch"))),
			TEXT("BBs drop and drift over distance. At long range, hold a little high."),
			FString::Printf(TEXT("%s switches between first and third person; %s swaps the shoulder."), *Key(S, TEXT("CameraView")), *Key(S, TEXT("Shoulder"))),
			FString::Printf(TEXT("%s toggles your weapon light. Useful in the garage, a giveaway in the open."), *Key(S, TEXT("Light"))),
			FString::Printf(TEXT("%s changes fire mode. Short bursts land better than a held trigger."), *Key(S, TEXT("FireMode"))),
			FString::Printf(TEXT("Grenades (%s) bounce off walls. Clear a room before you walk into it."), *Key(S, TEXT("Grenade"))),
			FString::Printf(TEXT("Change your guns, sights and finishes in the Armory (%s)."), *Key(S, TEXT("Loadout"))),
			TEXT("Every key can be changed in Settings > Key bindings."),
			TEXT("Settings > Accessibility has colour-blind-safe team colours and subtitles."),
			TEXT("Reload behind cover: an empty magazine in the open is a tag waiting to happen."),
		};
		return Tips[FMath::RandRange(0, Tips.Num() - 1)];
	}
}

// ---------------------------------------------------------------------------
// Loading card
// ---------------------------------------------------------------------------

/** Neon-noir backdrop: near-black, a slow amber sweep along the bottom rule, three pulsing bars. */
class SAirsoftLoadingBackdrop : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftLoadingBackdrop) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs)
	{
		StartTime = FPlatformTime::Seconds();
		ForceVolatile(true);
	}

	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override
	{
		return FVector2D(16.f, 16.f);
	}

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override
	{
		const FVector2f Size(AllottedGeometry.GetLocalSize());
		const float T = static_cast<float>(FPlatformTime::Seconds() - StartTime);
		const FLinearColor Amber = AUI::Accent();
		const FLinearColor Magenta(0.95f, 0.08f, 0.45f);

		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Size, FLinearColor(0.006f, 0.006f, 0.008f, 1.f));
		// Faint rain streaks: fixed columns, each falling at its own pace.
		for (int32 i = 0; i < 48; ++i)
		{
			const float X = Size.X * FMath::Frac(i * 0.61803f);
			const float Speed = 0.35f + FMath::Frac(i * 0.377f) * 0.5f;
			const float Y = FMath::Frac(T * Speed + i * 0.13f) * (Size.Y + 120.f) - 120.f;
			AUI::PaintRect(OutDrawElements, LayerId + 1, AllottedGeometry, FVector2f(X, Y), FVector2f(1.f, 70.f), FLinearColor(0.55f, 0.6f, 0.75f, 0.05f));
		}
		// Bottom rule with a sweep of light travelling along it.
		const float RuleY = Size.Y - 120.f;
		AUI::PaintRect(OutDrawElements, LayerId + 1, AllottedGeometry, FVector2f(110.f, RuleY), FVector2f(Size.X - 220.f, 1.f), FLinearColor(1.f, 1.f, 1.f, 0.08f));
		const float Sweep = FMath::Frac(T * 0.35f);
		const float SweepW = 220.f;
		const float SweepX = 110.f + (Size.X - 220.f - SweepW) * Sweep;
		AUI::PaintRect(OutDrawElements, LayerId + 2, AllottedGeometry, FVector2f(SweepX, RuleY - 1.f), FVector2f(SweepW, 3.f), AUI::WithAlpha(Amber, 0.85f));
		// Three bars pulsing in turn, bottom right.
		for (int32 i = 0; i < 3; ++i)
		{
			const float Phase = FMath::Frac(T * 1.2f - i * 0.18f);
			const float Height = 8.f + 18.f * FMath::Sin(Phase * PI);
			const FVector2f Pos(Size.X - 150.f + i * 14.f, RuleY - 30.f - Height);
			AUI::PaintRect(OutDrawElements, LayerId + 2, AllottedGeometry, Pos, FVector2f(6.f, Height), i == 1 ? AUI::WithAlpha(Magenta, 0.9f) : AUI::WithAlpha(Amber, 0.9f));
		}
		return LayerId + 2;
	}

private:
	double StartTime = 0.0;
};

class SAirsoftLoadingScreen : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftLoadingScreen) {}
		SLATE_ARGUMENT(FString, Title)
		SLATE_ARGUMENT(FString, Subtitle)
		SLATE_ARGUMENT(FString, Tip)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs)
	{
		ChildSlot
		[
			SNew(SOverlay)
			+ SOverlay::Slot()
			[
				SNew(SAirsoftLoadingBackdrop)
			]
			+ SOverlay::Slot()
			.VAlign(VAlign_Bottom)
			.HAlign(HAlign_Left)
			.Padding(FMargin(110.f, 0.f, 110.f, 160.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("LOADING")))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 14.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Text(AUI::Upper(InArgs._Title))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 54, 240))
					.ColorAndOpacity(FLinearColor::White)
					.ShadowOffset(FVector2D(0.f, 3.f))
					.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.6f))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(4.f, 4.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Visibility(InArgs._Subtitle.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible)
					.Text(AUI::Upper(InArgs._Subtitle))
					.Font(AUI::Caption(11))
					.ColorAndOpacity(AUI::Accent())
				]
			]
			+ SOverlay::Slot()
			.VAlign(VAlign_Bottom)
			.HAlign(HAlign_Left)
			.Padding(FMargin(110.f, 0.f, 260.f, 62.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Top)
				.Padding(FMargin(0.f, 1.f, 14.f, 0.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("TIP")))
					.Font(AUI::Caption(9))
					.ColorAndOpacity(AUI::Accent())
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				[
					SNew(STextBlock)
					.AutoWrapText(true)
					.Text(FText::FromString(InArgs._Tip))
					.Font(AUI::Font(AUI::EFontWeight::Regular, 13, 20))
					.ColorAndOpacity(AUI::TextColor())
				]
			]
		];
	}
};

TSharedRef<SWidget> AirsoftUIScreens::CreateLoadingScreen(const FString& Title, const FString& Subtitle)
{
	return SNew(SAirsoftLoadingScreen)
		.Title(Title)
		.Subtitle(Subtitle)
		.Tip(AirsoftLoadingLocal::PickTip());
}

// ---------------------------------------------------------------------------
// Practice walkthrough
// ---------------------------------------------------------------------------

class SAirsoftWalkthrough : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftWalkthrough) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, UAirsoftGameInstance* InGI);
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;

private:
	enum class EStep : uint8
	{
		Move,
		Aim,
		Shoot,
		Reload,
		Grenade,
		Slide,
		Done
	};

	struct FStepText
	{
		FString Title;
		FString Body;
	};

	static constexpr int32 NumSteps = static_cast<int32>(EStep::Done);

	FStepText TextFor(EStep InStep) const;
	AAirsoftPlayerController* GetPC() const;
	int32 PlateHits(UWorld* World) const;
	void Advance();
	/** 0..1 progress within the current step (for the bar). */
	float StepProgress() const;

	TWeakObjectPtr<UAirsoftGameInstance> WeakGI;
	EStep Step = EStep::Move;
	/** Per-step counters: distance walked, seconds aimed, plate hits at the start of the step. */
	FVector LastLocation = FVector::ZeroVector;
	bool bHaveLocation = false;
	float Walked = 0.f;
	float AimedFor = 0.f;
	int32 HitsAtStart = -1;
	int32 HitsNow = 0;
	double StepStartedAt = 0.0;
	double DoneAt = 0.0;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateWalkthrough(UAirsoftGameInstance* GameInstance)
{
	return SNew(SAirsoftWalkthrough, GameInstance);
}

namespace AirsoftWalkthroughLocal
{
	constexpr float WalkDistance = 600.f;   // cm
	constexpr float AimSeconds = 1.f;
	constexpr int32 PlateHitsWanted = 3;
	/** The finished card stays up this long, then the overlay steps aside. */
	constexpr double DoneHold = 8.0;
}

SAirsoftWalkthrough::FStepText SAirsoftWalkthrough::TextFor(EStep InStep) const
{
	using AirsoftLoadingLocal::Key;
	const UAirsoftGameInstance* GI = WeakGI.Get();
	const FAirsoftUserSettings* S = GI ? &const_cast<UAirsoftGameInstance*>(GI)->GetUserSettings() : nullptr;
	switch (InStep)
	{
	case EStep::Move:
		return { TEXT("Move"), FString::Printf(TEXT("Walk with %s %s %s %s. Look around with the mouse."),
			*Key(S, TEXT("MoveForward")), *Key(S, TEXT("MoveLeft")), *Key(S, TEXT("MoveBack")), *Key(S, TEXT("MoveRight"))) };
	case EStep::Aim:
		return { TEXT("Aim"), FString::Printf(TEXT("Hold %s to aim down the sights."), *Key(S, TEXT("Aim"))) };
	case EStep::Shoot:
		return { TEXT("Shoot"), FString::Printf(TEXT("Ring a steel plate downrange %d times with %s. Hold a little high on the far ones."),
			AirsoftWalkthroughLocal::PlateHitsWanted, *Key(S, TEXT("Fire"))) };
	case EStep::Reload:
		return { TEXT("Reload"), FString::Printf(TEXT("Press %s to reload. Do it behind cover in a real fight."), *Key(S, TEXT("Reload"))) };
	case EStep::Grenade:
		return { TEXT("Grenade"), FString::Printf(TEXT("Throw a grenade with %s. It bounces off walls and floors."), *Key(S, TEXT("Grenade"))) };
	case EStep::Slide:
		return { TEXT("Slide"), FString::Printf(TEXT("Sprint with %s, then press %s to slide."), *Key(S, TEXT("Sprint")), *Key(S, TEXT("Crouch"))) };
	default:
		return { TEXT("Range complete"), TEXT("That's everything. Keep practising, or open the menu (Esc) to head out.") };
	}
}

void SAirsoftWalkthrough::Construct(const FArguments& InArgs, UAirsoftGameInstance* InGI)
{
	WeakGI = InGI;
	StepStartedAt = FPlatformTime::Seconds();
	SetCanTick(true);

	TSharedRef<SVerticalBox> Checklist = SNew(SVerticalBox);
	for (int32 i = 0; i < NumSteps; ++i)
	{
		Checklist->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.f, 0.f, 0.f, 4.f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(0.f, 0.f, 10.f, 0.f))
			[
				SNew(SBox)
				.WidthOverride(14.f)
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 10))
					.Text_Lambda([this, i]()
					{
						return FText::FromString(static_cast<int32>(Step) > i ? TEXT("✓") : (static_cast<int32>(Step) == i ? TEXT("›") : TEXT("·")));
					})
					.ColorAndOpacity_Lambda([this, i]() -> FSlateColor
					{
						return static_cast<int32>(Step) >= i ? FSlateColor(AUI::Accent()) : FSlateColor(AUI::TextDim());
					})
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			[
				SNew(STextBlock)
				.Font(AUI::Caption(9))
				.Text(AUI::Upper(TextFor(static_cast<EStep>(i)).Title))
				.ColorAndOpacity_Lambda([this, i]() -> FSlateColor
				{
					if (static_cast<int32>(Step) == i)
					{
						return FSlateColor(FLinearColor::White);
					}
					return FSlateColor(static_cast<int32>(Step) > i ? AUI::TextDim() : AUI::TextMuted());
				})
			]
		];
	}

	ChildSlot
	.HAlign(HAlign_Right)
	.VAlign(VAlign_Center)
	.Padding(FMargin(0.f, 0.f, 60.f, 80.f))
	[
		SNew(SBox)
		.WidthOverride(360.f)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftPlayerController* PC = GetPC();
			if (!PC || PC->IsMenuOpen())
			{
				return EVisibility::Collapsed;
			}
			if (Step == EStep::Done && FPlatformTime::Seconds() - DoneAt > AirsoftWalkthroughLocal::DoneHold)
			{
				return EVisibility::Collapsed;
			}
			return EVisibility::HitTestInvisible;
		})
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelBrush())
			.Padding(FMargin(22.f, 18.f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.FillWidth(1.f)
					[
						AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("HOW TO PLAY")))
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Font(AUI::Caption(8))
						.ColorAndOpacity(AUI::TextDim())
						.Text_Lambda([this]()
						{
							const int32 Shown = FMath::Min(static_cast<int32>(Step) + 1, NumSteps);
							return FText::FromString(FString::Printf(TEXT("%d / %d"), Shown, NumSteps));
						})
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 12.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 24, 180))
					.ColorAndOpacity(FLinearColor::White)
					.Text_Lambda([this]() { return AUI::Upper(TextFor(Step).Title); })
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 6.f, 0.f, 0.f))
				[
					SNew(STextBlock)
					.AutoWrapText(true)
					.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 20))
					.ColorAndOpacity(AUI::TextColor())
					.Text_Lambda([this]() { return FText::FromString(TextFor(Step).Body); })
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 12.f, 0.f, 14.f))
				[
					SNew(SAirsoftBar)
					.Width(316.f)
					.Height(3.f)
					.Fraction_Lambda([this]() { return StepProgress(); })
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					Checklist
				]
			]
		]
	];
}

AAirsoftPlayerController* SAirsoftWalkthrough::GetPC() const
{
	UAirsoftGameInstance* GI = WeakGI.Get();
	return GI ? Cast<AAirsoftPlayerController>(GI->GetFirstLocalPlayerController()) : nullptr;
}

int32 SAirsoftWalkthrough::PlateHits(UWorld* World) const
{
	int32 Total = 0;
	if (World)
	{
		for (TActorIterator<AAirsoftPracticeTarget> It(World); It; ++It)
		{
			Total += It->GetHits();
		}
	}
	return Total;
}

float SAirsoftWalkthrough::StepProgress() const
{
	using namespace AirsoftWalkthroughLocal;
	switch (Step)
	{
	case EStep::Move: return FMath::Clamp(Walked / WalkDistance, 0.f, 1.f);
	case EStep::Aim: return FMath::Clamp(AimedFor / AimSeconds, 0.f, 1.f);
	case EStep::Shoot: return HitsAtStart < 0 ? 0.f : FMath::Clamp(static_cast<float>(HitsNow - HitsAtStart) / PlateHitsWanted, 0.f, 1.f);
	case EStep::Done: return 1.f;
	default: return 0.f;
	}
}

void SAirsoftWalkthrough::Advance()
{
	Step = static_cast<EStep>(static_cast<int32>(Step) + 1);
	StepStartedAt = FPlatformTime::Seconds();
	Walked = 0.f;
	AimedFor = 0.f;
	HitsAtStart = -1;
	if (AAirsoftPlayerController* PC = GetPC())
	{
		AirsoftAssets::Play2D(PC, TEXT("HitMarker"), 0.5f, 1.2f);
	}
	if (Step == EStep::Done)
	{
		DoneAt = FPlatformTime::Seconds();
		if (UAirsoftGameInstance* GI = WeakGI.Get())
		{
			GI->FinishWalkthrough();
		}
	}
}

void SAirsoftWalkthrough::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
	using namespace AirsoftWalkthroughLocal;
	AAirsoftPlayerController* PC = GetPC();
	AAirsoftCharacter* Pawn = PC ? Cast<AAirsoftCharacter>(PC->GetPawn()) : nullptr;
	if (!Pawn || PC->IsMenuOpen() || Step == EStep::Done)
	{
		bHaveLocation = false;
		return;
	}
	// A short beat between steps so each tick-off registers.
	if (FPlatformTime::Seconds() - StepStartedAt < 0.6)
	{
		return;
	}
	UAirsoftCombatComponent* Combat = Pawn->GetCombat();
	switch (Step)
	{
	case EStep::Move:
	{
		const FVector Here = Pawn->GetActorLocation();
		if (bHaveLocation)
		{
			Walked += FVector::Dist2D(Here, LastLocation);
		}
		LastLocation = Here;
		bHaveLocation = true;
		if (Walked >= WalkDistance)
		{
			Advance();
		}
		break;
	}
	case EStep::Aim:
		if (Combat && Combat->IsAiming())
		{
			AimedFor += InDeltaTime;
		}
		if (AimedFor >= AimSeconds)
		{
			Advance();
		}
		break;
	case EStep::Shoot:
		HitsNow = PlateHits(Pawn->GetWorld());
		if (HitsAtStart < 0)
		{
			HitsAtStart = HitsNow;
		}
		if (HitsNow - HitsAtStart >= PlateHitsWanted)
		{
			Advance();
		}
		break;
	case EStep::Reload:
		if (Combat && Combat->IsReloading())
		{
			Advance();
		}
		break;
	case EStep::Grenade:
		if (Combat && Combat->IsThrowing())
		{
			Advance();
		}
		break;
	case EStep::Slide:
		if (Pawn->IsSliding())
		{
			Advance();
		}
		break;
	default:
		break;
	}
}
