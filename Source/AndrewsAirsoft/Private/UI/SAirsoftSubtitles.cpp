#include "SAirsoftSubtitles.h"

#include "AirsoftGameInstance.h"
#include "AirsoftSaveGame.h"
#include "AirsoftUIStyle.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftSubtitlesLocal
{
	struct FLine
	{
		FString Speaker;
		FString Text;
		FLinearColor Color = FLinearColor::White;
		double Until = 0.0;
	};

	constexpr int32 MaxRows = 2;
	constexpr double FadeTime = 0.4;

	TArray<FLine>& Lines()
	{
		static TArray<FLine> Queue;
		return Queue;
	}

	void Prune()
	{
		const double Now = FPlatformTime::Seconds();
		Lines().RemoveAll([Now](const FLine& L) { return L.Until <= Now; });
	}

	/** Row 0 is the older line, row 1 the newest (always at the bottom). */
	const FLine* LineForRow(int32 Row)
	{
		Prune();
		const TArray<FLine>& Queue = Lines();
		const int32 Index = Queue.Num() - (MaxRows - Row);
		return Queue.IsValidIndex(Index) ? &Queue[Index] : nullptr;
	}

	float RowAlpha(int32 Row)
	{
		const FLine* Line = LineForRow(Row);
		if (!Line)
		{
			return 0.f;
		}
		return static_cast<float>(FMath::Clamp((Line->Until - FPlatformTime::Seconds()) / FadeTime, 0.0, 1.0));
	}
}

namespace AirsoftSubtitles
{
	void Show(const FString& Speaker, const FString& Text, const FLinearColor& SpeakerColor, float Duration)
	{
		using namespace AirsoftSubtitlesLocal;
		if (Text.IsEmpty())
		{
			return;
		}
		Prune();
		FLine Line;
		Line.Speaker = Speaker.ToUpper();
		Line.Text = Text;
		Line.Color = SpeakerColor;
		Line.Until = FPlatformTime::Seconds() + FMath::Max(1.5f, Duration);
		Lines().Add(MoveTemp(Line));
		while (Lines().Num() > MaxRows)
		{
			Lines().RemoveAt(0);
		}
	}

	void Clear()
	{
		AirsoftSubtitlesLocal::Lines().Reset();
	}
}

void SAirsoftSubtitles::Construct(const FArguments& InArgs, APlayerController* InPC)
{
	WeakPC = InPC;
	SetVisibility(EVisibility::HitTestInvisible);

	ChildSlot
	[
		SNew(SBox)
		.MaxDesiredWidth(1100.f)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(FMargin(0.f, 0.f, 0.f, 6.f))
			[
				BuildRow(0)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				BuildRow(1)
			]
		]
	];
}

bool SAirsoftSubtitles::IsEnabled() const
{
	const APlayerController* PC = WeakPC.Get();
	UAirsoftGameInstance* GI = PC ? PC->GetGameInstance<UAirsoftGameInstance>() : nullptr;
	return !GI || GI->GetUserSettings().bSubtitles;
}

TSharedRef<SWidget> SAirsoftSubtitles::BuildRow(int32 Row)
{
	using namespace AirsoftSubtitlesLocal;
	return SNew(SBorder)
		.BorderImage(AUI::WhiteBrush())
		.Padding(FMargin(14.f, 6.f, 14.f, 7.f))
		.Visibility_Lambda([this, Row]() -> EVisibility
		{
			return (IsEnabled() && LineForRow(Row)) ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
		})
		.BorderBackgroundColor_Lambda([Row]() -> FSlateColor
		{
			return FSlateColor(FLinearColor(0.f, 0.f, 0.f, 0.55f * RowAlpha(Row)));
		})
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(0.f, 1.f, 10.f, 0.f))
			[
				SNew(STextBlock)
				.Visibility_Lambda([Row]() -> EVisibility
				{
					const FLine* Line = LineForRow(Row);
					return (Line && !Line->Speaker.IsEmpty()) ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
				})
				.Text_Lambda([Row]() -> FText
				{
					const FLine* Line = LineForRow(Row);
					return Line ? FText::FromString(Line->Speaker) : FText::GetEmpty();
				})
				.Font(AUI::Font(AUI::EFontWeight::Bold, 13, 120))
				.ColorAndOpacity_Lambda([Row]() -> FSlateColor
				{
					const FLine* Line = LineForRow(Row);
					return FSlateColor(AUI::WithAlpha(Line ? Line->Color : AUI::Accent(), RowAlpha(Row)));
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			[
				SNew(STextBlock)
				.Text_Lambda([Row]() -> FText
				{
					const FLine* Line = LineForRow(Row);
					return Line ? FText::FromString(Line->Text) : FText::GetEmpty();
				})
				.Font(AUI::Font(AUI::EFontWeight::Regular, 17))
				.WrapTextAt(900.f)
				.ColorAndOpacity_Lambda([Row]() -> FSlateColor
				{
					return FSlateColor(AUI::WithAlpha(AUI::TextColor(), RowAlpha(Row)));
				})
				.ShadowOffset(FVector2D(1.f, 1.f))
				.ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.8f))
			]
		];
}
