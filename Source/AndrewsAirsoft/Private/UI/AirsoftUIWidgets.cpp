// Andrew's Airsoft - shared Slate widgets.

#include "AirsoftUIWidgets.h"

#include "AirsoftPlayerController.h"
#include "AirsoftUIStyle.h"
#include "HAL/PlatformTime.h"
#include "InputCoreTypes.h"
#include "Rendering/DrawElements.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SNullWidget.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

// ---------------------------------------------------------------------------
// SAirsoftButton
// ---------------------------------------------------------------------------

void SAirsoftButton::Construct(const FArguments& InArgs)
{
	IsSelectedAttr = InArgs._IsSelected;
	IsDimmedAttr = InArgs._IsDimmed;
	bShowEdge = InArgs._ShowEdge;

	TSharedRef<SWidget> Body = InArgs._Content.Widget;
	if (Body == SNullWidget::NullWidget)
	{
		const int32 SubSize = FMath::Max(8, InArgs._FontSize - 3);
		Body = SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.HAlign(InArgs._HAlign)
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(InArgs._Text)
				.Font(AUI::Font(AUI::EFontWeight::Bold, InArgs._FontSize, 180))
				.ColorAndOpacity_Lambda([this]() -> FSlateColor { return GetTextColor(); })
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(14.f, 0.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Visibility(InArgs._SubText.IsSet() ? EVisibility::HitTestInvisible : EVisibility::Collapsed)
				.Text(InArgs._SubText)
				.Font(AUI::Font(AUI::EFontWeight::Regular, SubSize, 120))
				.ColorAndOpacity_Lambda([this]() -> FSlateColor { return GetSubTextColor(); })
			];
	}

	ChildSlot
	[
		SAssignNew(Button, SButton)
		.ButtonStyle(&AUI::ClearButtonStyle())
		.ContentPadding(FMargin(0.f))
		.HAlign(HAlign_Fill)
		.VAlign(VAlign_Fill)
		.IsFocusable(true)
		.OnClicked(InArgs._OnClicked)
		[
			SNew(SBorder)
			.BorderImage(AUI::RoundedBrush())
			.BorderBackgroundColor_Lambda([this]() -> FSlateColor { return GetBackColor(); })
			.Padding(FMargin(0.f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(bShowEdge ? 2.f : 0.f)
					[
						SNew(SBorder)
						.BorderImage(AUI::WhiteBrush())
						.BorderBackgroundColor_Lambda([this]() -> FSlateColor { return GetEdgeColor(); })
						.Padding(FMargin(0.f))
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.Padding(InArgs._ContentPadding)
				[
					Body
				]
			]
		]
	];
}

bool SAirsoftButton::IsActive() const
{
	return Button.IsValid() && (Button->IsHovered() || Button->HasKeyboardFocus());
}

FSlateColor SAirsoftButton::GetTextColor() const
{
	if (IsDimmedAttr.Get())
	{
		return AUI::TextMuted();
	}
	if (IsSelectedAttr.Get())
	{
		return AUI::Accent();
	}
	return IsActive() ? FLinearColor::White : AUI::TextColor();
}

FSlateColor SAirsoftButton::GetSubTextColor() const
{
	if (IsSelectedAttr.Get())
	{
		return AUI::WithAlpha(AUI::Accent(), 0.85f);
	}
	return IsActive() ? AUI::TextColor() : AUI::TextDim();
}

FSlateColor SAirsoftButton::GetBackColor() const
{
	const bool bPressed = Button.IsValid() && Button->IsPressed();
	const bool bSelected = IsSelectedAttr.Get();
	const bool bActive = IsActive();
	if (bPressed)
	{
		return FLinearColor(1.f, 0.55f, 0.05f, 0.22f);
	}
	if (bSelected)
	{
		return FLinearColor(1.f, 0.55f, 0.05f, bActive ? 0.2f : 0.12f);
	}
	return bActive ? FLinearColor(1.f, 1.f, 1.f, 0.075f) : FLinearColor(0.f, 0.f, 0.f, 0.42f);
}

FSlateColor SAirsoftButton::GetEdgeColor() const
{
	if (IsSelectedAttr.Get())
	{
		return AUI::Accent();
	}
	return IsActive() ? AUI::WithAlpha(AUI::Accent(), 0.85f) : FLinearColor(1.f, 1.f, 1.f, 0.06f);
}

// ---------------------------------------------------------------------------
// SAirsoftBar
// ---------------------------------------------------------------------------

void SAirsoftBar::Construct(const FArguments& InArgs)
{
	Fraction = InArgs._Fraction;
	Marker = InArgs._Marker;
	FillColor = InArgs._FillColor;
	TrackColor = InArgs._TrackColor;
	Width = InArgs._Width;
	Height = InArgs._Height;
	SetCanTick(false);
}

int32 SAirsoftBar::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	const float H = FMath::Min(Height, Size.Y);
	const float Y = (Size.Y - H) * 0.5f;
	AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, Y), FVector2f(Size.X, H), TrackColor.Get() * Tint);
	const float F = FMath::Clamp(Fraction.Get(), 0.f, 1.f);
	AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, Y), FVector2f(Size.X * F, H), FillColor.Get() * Tint);
	const float M = Marker.Get();
	if (M >= 0.f)
	{
		const float X = Size.X * FMath::Clamp(M, 0.f, 1.f);
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(X - 0.75f, Y - 3.f), FVector2f(1.5f, H + 6.f), FLinearColor(1.f, 1.f, 1.f, 0.7f) * Tint);
	}
	return LayerId;
}

FVector2D SAirsoftBar::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Width, FMath::Max(Height, 1.f));
}

// ---------------------------------------------------------------------------
// SAirsoftSlider
// ---------------------------------------------------------------------------

namespace AirsoftSliderLocal
{
	constexpr float Pad = 7.f;
}

void SAirsoftSlider::Construct(const FArguments& InArgs)
{
	Value = InArgs._Value;
	Step = InArgs._Step;
	Width = InArgs._Width;
	OnValueChanged = InArgs._OnValueChanged;
	OnCommit = InArgs._OnCommit;
	SetCanTick(false);
}

int32 SAirsoftSlider::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace AirsoftSliderLocal;
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	const bool bFocused = HasKeyboardFocus();
	const bool bActive = bFocused || IsHovered() || IsDragging();
	const float V = FMath::Clamp(Value.Get(), 0.f, 1.f);
	const float Usable = FMath::Max(Size.X - 2.f * Pad, 1.f);
	const float X = Pad + Usable * V;
	const float CY = Size.Y * 0.5f;

	if (bFocused)
	{
		AUI::PaintFrame(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Size, AUI::WithAlpha(AUI::Accent(), 0.35f) * Tint, 1.f);
	}
	AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(Pad, CY - 1.f), FVector2f(Usable, 2.f), FLinearColor(1.f, 1.f, 1.f, 0.12f) * Tint);
	AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(Pad, CY - 1.f), FVector2f(X - Pad, 2.f), AUI::Accent() * Tint);
	const FLinearColor Thumb = bActive ? AUI::Accent() : AUI::TextColor();
	AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(X - 3.f, CY - 8.f), FVector2f(6.f, 16.f), Thumb * Tint);
	return LayerId;
}

FVector2D SAirsoftSlider::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Width, 26.f);
}

void SAirsoftSlider::SetFromScreen(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	using namespace AirsoftSliderLocal;
	const FVector2f Local(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	const FVector2f Size(MyGeometry.GetLocalSize());
	const float Usable = FMath::Max(Size.X - 2.f * Pad, 1.f);
	Change((Local.X - Pad) / Usable);
}

void SAirsoftSlider::Change(float NewValue)
{
	const float Clamped = FMath::Clamp(NewValue, 0.f, 1.f);
	if (!FMath::IsNearlyEqual(Clamped, Value.Get()))
	{
		OnValueChanged.ExecuteIfBound(Clamped);
	}
}

FReply SAirsoftSlider::OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (MouseEvent.GetEffectingButton() != EKeys::LeftMouseButton)
	{
		return FReply::Unhandled();
	}
	bDragging = true;
	SetFromScreen(MyGeometry, MouseEvent);
	return FReply::Handled().CaptureMouse(SharedThis(this)).SetUserFocus(SharedThis(this), EFocusCause::Mouse);
}

FReply SAirsoftSlider::OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (MouseEvent.GetEffectingButton() != EKeys::LeftMouseButton || !bDragging)
	{
		return FReply::Unhandled();
	}
	bDragging = false;
	OnCommit.ExecuteIfBound();
	return FReply::Handled().ReleaseMouseCapture();
}

FReply SAirsoftSlider::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (bDragging && HasMouseCapture())
	{
		SetFromScreen(MyGeometry, MouseEvent);
		return FReply::Handled();
	}
	return FReply::Unhandled();
}

FNavigationReply SAirsoftSlider::OnNavigation(const FGeometry& MyGeometry, const FNavigationEvent& InNavigationEvent)
{
	const EUINavigation Nav = InNavigationEvent.GetNavigationType();
	if (Nav == EUINavigation::Left || Nav == EUINavigation::Right)
	{
		Change(Value.Get() + (Nav == EUINavigation::Right ? Step : -Step));
		return FNavigationReply::Stop();
	}
	return SLeafWidget::OnNavigation(MyGeometry, InNavigationEvent);
}

// ---------------------------------------------------------------------------
// SAirsoftBackdrop
// ---------------------------------------------------------------------------

void SAirsoftBackdrop::Construct(const FArguments& InArgs)
{
	Opacity = InArgs._Opacity;
	ColumnWidth = InArgs._ColumnWidth;
	StartTime = FPlatformTime::Seconds();
	SetCanTick(false);
}

int32 SAirsoftBackdrop::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const float Fade = AUI::Ease(static_cast<float>((FPlatformTime::Seconds() - StartTime) / 0.25));
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint() * FLinearColor(1.f, 1.f, 1.f, Fade);
	const FLinearColor InkColor = AUI::Ink();

	AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Size, AUI::WithAlpha(InkColor, Opacity * 0.72f) * Tint);

	// Darker menu column fading out to the right.
	if (ColumnWidth > 0.f)
	{
		const int32 Bands = 28;
		const float ColumnW = Size.X * ColumnWidth;
		const float FadeW = Size.X * 0.22f;
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), FVector2f(ColumnW, Size.Y), AUI::WithAlpha(InkColor, Opacity * 0.6f) * Tint);
		for (int32 i = 0; i < Bands; ++i)
		{
			const float T0 = static_cast<float>(i) / Bands;
			const float Alpha = Opacity * 0.6f * (1.f - AUI::Ease(T0));
			AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(ColumnW + FadeW * T0, 0.f), FVector2f(FadeW / Bands + 0.5f, Size.Y),
				AUI::WithAlpha(InkColor, Alpha) * Tint);
		}
	}

	// Soft top and bottom falloff.
	const int32 Rows = 16;
	const float FallH = Size.Y * 0.16f;
	for (int32 i = 0; i < Rows; ++i)
	{
		const float T = static_cast<float>(i) / Rows;
		const float Alpha = 0.45f * (1.f - AUI::Ease(T));
		const float H = FallH / Rows + 0.5f;
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, FallH * T), FVector2f(Size.X, H), AUI::WithAlpha(InkColor, Alpha) * Tint);
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, Size.Y - FallH * T - H), FVector2f(Size.X, H), AUI::WithAlpha(InkColor, Alpha) * Tint);
	}
	return LayerId;
}

FVector2D SAirsoftBackdrop::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(16.f, 16.f);
}

// ---------------------------------------------------------------------------
// SAirsoftMenuBase
// ---------------------------------------------------------------------------

FReply SAirsoftMenuBase::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	const FKey Key = InKeyEvent.GetKey();
	if (Key == EKeys::Escape || Key == EKeys::Gamepad_FaceButton_Right || Key == EKeys::Virtual_Back)
	{
		HandleBack();
		return FReply::Handled();
	}
	return SCompoundWidget::OnKeyDown(MyGeometry, InKeyEvent);
}

FReply SAirsoftMenuBase::OnFocusReceived(const FGeometry& MyGeometry, const FFocusEvent& InFocusEvent)
{
	const TSharedPtr<SWidget> Target = InitialFocus.Pin();
	if (Target.IsValid() && InFocusEvent.GetCause() != EFocusCause::Mouse)
	{
		return FReply::Handled().SetUserFocus(Target.ToSharedRef(), EFocusCause::SetDirectly);
	}
	return SCompoundWidget::OnFocusReceived(MyGeometry, InFocusEvent);
}

void SAirsoftMenuBase::ReturnToParentMenu()
{
	if (AAirsoftPlayerController* PC = WeakPC.Get())
	{
		PC->ShowMenu(PC->IsMainMenu() ? EAirsoftMenu::MainMenu : EAirsoftMenu::GameMenu);
	}
}

void SAirsoftMenuBase::SetInitialFocus(const TSharedPtr<SAirsoftButton>& InButton)
{
	if (InButton.IsValid())
	{
		InitialFocus = InButton->GetButton();
	}
}

// ---------------------------------------------------------------------------
// Builders
// ---------------------------------------------------------------------------

namespace AirsoftUIWidgets
{
	TSharedRef<SWidget> SectionLabel(const FText& Text)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.f, 0.f, 10.f, 0.f))
			[
				AccentRule(16.f, 1.f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Text)
				.Font(AUI::Caption(9))
				.ColorAndOpacity(AUI::Accent())
			];
	}

	TSharedRef<SWidget> Rule(const FLinearColor& Color, float Thickness)
	{
		return SNew(SBox)
			.HeightOverride(Thickness)
			[
				SNew(SBorder)
				.BorderImage(AUI::WhiteBrush())
				.BorderBackgroundColor(Color)
				.Padding(FMargin(0.f))
			];
	}

	TSharedRef<SWidget> AccentRule(float Width, float Thickness)
	{
		return SNew(SBox)
			.WidthOverride(Width)
			.HeightOverride(Thickness)
			[
				SNew(SBorder)
				.BorderImage(AUI::WhiteBrush())
				.BorderBackgroundColor(AUI::Accent())
				.Padding(FMargin(0.f))
			];
	}

	TSharedRef<SWidget> KeyCap(const FText& Key, int32 FontSize)
	{
		return SNew(SBorder)
			.BorderImage(AUI::OutlineBrush())
			.BorderBackgroundColor(FLinearColor(1.f, 1.f, 1.f, 0.35f))
			.Padding(FMargin(6.f, 1.f))
			[
				SNew(STextBlock)
				.Text(Key)
				.Font(AUI::Font(AUI::EFontWeight::Bold, FontSize, 60))
				.ColorAndOpacity(AUI::TextColor())
			];
	}

	TSharedRef<SWidget> StatBlock(const FText& Label, const TAttribute<FText>& Value, int32 ValueSize)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextDim())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.f, 2.f, 0.f, 0.f))
			[
				SNew(STextBlock)
				.Text(Value)
				.Font(AUI::Font(AUI::EFontWeight::Bold, ValueSize, 40))
				.ColorAndOpacity(AUI::TextColor())
			];
	}

	TSharedRef<SWidget> Hint(const FText& Key, const FText& Action)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				KeyCap(Key, 8)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(8.f, 0.f, 22.f, 0.f))
			[
				SNew(STextBlock)
				.Text(Action)
				.Font(AUI::Caption(8))
				.ColorAndOpacity(AUI::TextDim())
			];
	}
}
