#include "SAirsoftCredits.h"

#include "AirsoftCampaign.h"
#include "AirsoftUIStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftCreditsLocal
{
	/** Black fades in over this long before the roll starts. */
	constexpr float FadeIn = 1.5f;
}

void SAirsoftCredits::Construct(const FArguments& InArgs)
{
	OnFinished = InArgs._OnFinished;
	ScrollSpeed = FMath::Max(10.f, InArgs._ScrollSpeed);
	SetVisibility(EVisibility::HitTestInvisible);
	Content = BuildContent();
	Content->SetRenderOpacity(0.f);

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.BorderImage(AUI::WhiteBrush())
			.BorderBackgroundColor_Lambda([this]() -> FSlateColor
			{
				return FSlateColor(FLinearColor(0.f, 0.f, 0.f, FMath::Clamp(Elapsed / AirsoftCreditsLocal::FadeIn, 0.f, 1.f)));
			})
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Top)
		[
			Content.ToSharedRef()
		]
	];
}

TSharedRef<SWidget> SAirsoftCredits::BuildContent() const
{
	TSharedRef<SVerticalBox> Column = SNew(SVerticalBox);
	bool bFirst = true;
	for (const AirsoftCampaign::FCreditsBlock& Block : AirsoftCampaign::Credits())
	{
		if (!Block.Heading.IsEmpty())
		{
			Column->AddSlot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 0.f, 0.f, 10.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(Block.Heading.ToUpper()))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 12, 320))
					.ColorAndOpacity(AUI::Accent())
				];
		}
		for (int32 i = 0; i < Block.Lines.Num(); ++i)
		{
			// The opening block is the title card: big type.
			const bool bTitle = bFirst && Block.Heading.IsEmpty();
			Column->AddSlot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.f, 0.f, 0.f, bTitle ? 8.f : 6.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(Block.Lines[i]))
					.Font(bTitle ? AUI::Font(AUI::EFontWeight::Bold, i == 0 ? 40 : 22, 260) : AUI::Font(AUI::EFontWeight::Regular, 17))
					.ColorAndOpacity(bTitle && i > 0 ? AUI::Accent() : AUI::TextColor())
					.Justification(ETextJustify::Center)
				];
		}
		// Space between blocks.
		Column->AddSlot()
			.AutoHeight()
			[
				SNew(SBox).HeightOverride(bFirst ? 140.f : 70.f)
			];
		bFirst = false;
	}
	return SNew(SBox)
		.WidthOverride(1000.f)
		[
			Column
		];
}

void SAirsoftCredits::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
	if (bFinished || !Content.IsValid())
	{
		return;
	}
	Elapsed += InDeltaTime;
	const float ScreenH = AllottedGeometry.GetLocalSize().Y;
	if (Offset < 0.f)
	{
		Offset = ScreenH; // start just below the bottom edge
	}
	if (Elapsed > AirsoftCreditsLocal::FadeIn)
	{
		Offset -= ScrollSpeed * InDeltaTime;
		Content->SetRenderOpacity(1.f);
	}
	Content->SetRenderTransform(FSlateRenderTransform(FVector2f(0.f, Offset)));

	const float ContentH = static_cast<float>(Content->GetDesiredSize().Y);
	if (ContentH > 0.f && Offset < -ContentH)
	{
		Finish();
	}
}

void SAirsoftCredits::Finish()
{
	if (bFinished)
	{
		return;
	}
	bFinished = true;
	OnFinished.ExecuteIfBound();
}
