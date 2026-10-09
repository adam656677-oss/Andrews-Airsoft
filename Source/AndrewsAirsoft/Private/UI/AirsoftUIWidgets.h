// Andrew's Airsoft - small reusable Slate widgets shared by every screen.

#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/Input/SButton.h"

class AAirsoftPlayerController;

/**
 * Flat menu button: dark glass, amber edge bar when hovered/focused/selected.
 * Either give it Text (+ optional SubText on the right) or custom content.
 */
class SAirsoftButton : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftButton)
		: _FontSize(13)
		, _IsSelected(false)
		, _IsDimmed(false)
		, _ContentPadding(FMargin(18.f, 11.f))
		, _HAlign(HAlign_Left)
		, _ShowEdge(true)
	{}
		SLATE_ATTRIBUTE(FText, Text)
		SLATE_ATTRIBUTE(FText, SubText)
		SLATE_ARGUMENT(int32, FontSize)
		/** Selected = amber text, tinted background, solid edge. */
		SLATE_ATTRIBUTE(bool, IsSelected)
		/** Dimmed = muted text (e.g. locked); still clickable. */
		SLATE_ATTRIBUTE(bool, IsDimmed)
		SLATE_ARGUMENT(FMargin, ContentPadding)
		SLATE_ARGUMENT(EHorizontalAlignment, HAlign)
		SLATE_ARGUMENT(bool, ShowEdge)
		SLATE_EVENT(FOnClicked, OnClicked)
		SLATE_DEFAULT_SLOT(FArguments, Content)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** True while hovered or focused (keyboard / gamepad). */
	bool IsActive() const;
	bool IsSelectedNow() const { return IsSelectedAttr.Get(); }
	/** The focusable inner button (give this to SetUserFocus). */
	TSharedPtr<SButton> GetButton() const { return Button; }

	/** Colours other content can bind to so it reacts like the button text. */
	FSlateColor GetTextColor() const;
	FSlateColor GetSubTextColor() const;

private:
	FSlateColor GetBackColor() const;
	FSlateColor GetEdgeColor() const;

	TSharedPtr<SButton> Button;
	TAttribute<bool> IsSelectedAttr;
	TAttribute<bool> IsDimmedAttr;
	bool bShowEdge = true;
};

/** Thin horizontal bar: track + fill, optional marker. */
class SAirsoftBar : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftBar)
		: _Fraction(0.f)
		, _Marker(-1.f)
		, _FillColor(FLinearColor(1.f, 0.55f, 0.05f))
		, _TrackColor(FLinearColor(1.f, 1.f, 1.f, 0.08f))
		, _Width(120.f)
		, _Height(4.f)
	{}
		SLATE_ATTRIBUTE(float, Fraction)
		/** 0..1 position of a thin reference tick, or < 0 for none. */
		SLATE_ATTRIBUTE(float, Marker)
		SLATE_ATTRIBUTE(FLinearColor, FillColor)
		SLATE_ATTRIBUTE(FLinearColor, TrackColor)
		SLATE_ARGUMENT(float, Width)
		SLATE_ARGUMENT(float, Height)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	TAttribute<float> Fraction;
	TAttribute<float> Marker;
	TAttribute<FLinearColor> FillColor;
	TAttribute<FLinearColor> TrackColor;
	float Width = 120.f;
	float Height = 4.f;
};

DECLARE_DELEGATE_OneParam(FOnAirsoftSliderValue, float);

/**
 * Minimal slider over a normalised 0..1 value. Mouse drag, or left/right
 * (keys, D-pad, stick) while focused. OnCommit fires when a drag ends.
 */
class SAirsoftSlider : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftSlider)
		: _Value(0.f)
		, _Step(0.02f)
		, _Width(320.f)
	{}
		SLATE_ATTRIBUTE(float, Value)
		SLATE_ARGUMENT(float, Step)
		SLATE_ARGUMENT(float, Width)
		SLATE_EVENT(FOnAirsoftSliderValue, OnValueChanged)
		SLATE_EVENT(FSimpleDelegate, OnCommit)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	bool IsDragging() const { return bDragging && HasMouseCapture(); }

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FNavigationReply OnNavigation(const FGeometry& MyGeometry, const FNavigationEvent& InNavigationEvent) override;

private:
	void SetFromScreen(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent);
	void Change(float NewValue);

	TAttribute<float> Value;
	float Step = 0.02f;
	float Width = 320.f;
	bool bDragging = false;
	FOnAirsoftSliderValue OnValueChanged;
	FSimpleDelegate OnCommit;
};

/** Full-screen dimmer for menus: near-black with a darker left column and soft top/bottom falloff. */
class SAirsoftBackdrop : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftBackdrop)
		: _Opacity(0.8f)
		, _ColumnWidth(0.42f)
	{}
		SLATE_ARGUMENT(float, Opacity)
		/** Fraction of the width darkened as a menu column (0 = none). */
		SLATE_ARGUMENT(float, ColumnWidth)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	float Opacity = 0.8f;
	float ColumnWidth = 0.42f;
	double StartTime = 0.0;
};

/**
 * Base for full-screen menus: focusable root, Escape / gamepad B go "back",
 * and keyboard/gamepad focus is forwarded to the first button when the
 * controller focuses the root.
 */
class SAirsoftMenuBase : public SCompoundWidget
{
public:
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual FReply OnFocusReceived(const FGeometry& MyGeometry, const FFocusEvent& InFocusEvent) override;

protected:
	/** Escape / gamepad B. */
	virtual void HandleBack() {}
	/** Back to the menu this sub-screen came from (main menu or pause menu). */
	void ReturnToParentMenu();
	void SetInitialFocus(const TSharedPtr<SAirsoftButton>& InButton);
	void SetInitialFocusWidget(const TSharedPtr<SWidget>& InWidget) { InitialFocus = InWidget; }

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
	TWeakPtr<SWidget> InitialFocus;
	double OpenTime = 0.0;
};

namespace AirsoftUIWidgets
{
	/** Amber caption with a short rule in front of it ("-- LOADOUT"). */
	TSharedRef<SWidget> SectionLabel(const FText& Text);
	/** Full-width hairline. */
	TSharedRef<SWidget> Rule(const FLinearColor& Color, float Thickness = 1.f);
	/** Short amber accent line. */
	TSharedRef<SWidget> AccentRule(float Width, float Thickness = 2.f);
	/** Keyboard key cap, e.g. "F1". */
	TSharedRef<SWidget> KeyCap(const FText& Key, int32 FontSize = 9);
	/** Label above a value ("TAGS" / "128"). */
	TSharedRef<SWidget> StatBlock(const FText& Label, const TAttribute<FText>& Value, int32 ValueSize = 20);
	/** Footer line of controller hints: "[ESC] BACK". */
	TSharedRef<SWidget> Hint(const FText& Key, const FText& Action);
}
