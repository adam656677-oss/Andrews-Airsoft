// Andrew's Airsoft - neon HUD kit: angular chamfered panels with thin glowing outlines,
// slanted segmented gradient bars, the call-sign emblem, weapon glyphs and magazine pips.
// Everything is painted (no textures) in the HUD's 1080p layout units.
//
// Glow = the same outline drawn a few times, wider and fainter, under a whitened core.
// Fills = horizontal strips (Slate has no polygon fill without a custom vertex buffer).

#pragma once

#include "CoreMinimal.h"
#include "Layout/Geometry.h"
#include "Layout/Margin.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SLeafWidget.h"

class FSlateWindowElementList;

namespace AirsoftNeon
{
	// Which corners of a panel are cut (bit flags; combine with the named sets below).
	constexpr uint8 CornerTL = 1;
	constexpr uint8 CornerTR = 2;
	constexpr uint8 CornerBR = 4;
	constexpr uint8 CornerBL = 8;
	/** Top-left + bottom-right: the default HUD frame. */
	constexpr uint8 Diagonal = 5;
	/** Top-right + bottom-left. */
	constexpr uint8 DiagonalAlt = 10;
	constexpr uint8 AllCorners = 15;
	/** Both left corners (a panel pointing left), both right, both bottom (a tab hanging from the top edge). */
	constexpr uint8 LeftCorners = 9;
	constexpr uint8 RightCorners = 6;
	constexpr uint8 BottomCorners = 12;

	// --- Palette (sRGB picks, stored linear) --------------------------------------
	FLinearColor Cyan();
	FLinearColor CyanDeep();
	FLinearColor Orange();
	FLinearColor Amber();
	FLinearColor Red();
	FLinearColor Magenta();
	/** Panel glass: near-black blue, translucent. */
	FLinearColor Glass();
	/** Empty bar track. */
	FLinearColor Track();

	// --- Paint helpers (local units) -------------------------------------------------
	/** Outline of a box with the given corners cut at 45 degrees, clockwise from the top-left. */
	void ChamferPoints(const FVector2f& Pos, const FVector2f& Size, float Chamfer, uint8 Corners, TArray<FVector2f>& OutPoints);
	void PaintPolyline(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, bool bClosed);
	/** Neon line: soft halo passes (Glow 0..1 scales them), the line, and a whitened hot core. */
	void PaintGlowPolyline(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, float Glow, bool bClosed);
	/** Solid fill of a chamfered box (a few strips per cut corner). */
	void PaintChamferFill(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, float Chamfer, uint8 Corners, const FLinearColor& Color);
	/** Even-odd scanline fill of any polygon: rows RowStep apart, RowHeight tall (a gap between them reads as hologram scanlines). */
	void PaintPolygonFill(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Points, const FLinearColor& Color, float RowStep, float RowHeight);
	/** Glass fill + glowing outline (+ bright cuts on the chamfers when Accent has alpha). Uses Layer and Layer + 1. */
	void PaintPanel(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, float Chamfer, uint8 Corners,
		const FLinearColor& Line, const FLinearColor& Fill, float Glow, const FLinearColor& Accent);
	/**
	 * Parallelogram bar (top edge shifted right by Slant), split into Segments with Gap between them and filled to Fraction
	 * with a From -> To gradient. Ghost > Fraction paints the recently lost part in GhostColor.
	 */
	void PaintSlantBar(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, float Slant,
		float Fraction, const FLinearColor& From, const FLinearColor& To, int32 Segments, float Gap, const FLinearColor& TrackColor,
		float Ghost = -1.f, const FLinearColor& GhostColor = FLinearColor(1.f, 1.f, 1.f, 0.5f));
	/** Corners of that parallelogram, filled to Fraction (1 = the whole bar). */
	void SlantBarPoints(const FVector2f& Pos, const FVector2f& Size, float Slant, float Fraction, TArray<FVector2f>& OutPoints);

	/** "Andrew Hale" -> "AH", "ghost" -> "GH", "" -> "OP". */
	FString Initials(const FString& Name);
}

/** A chamfered glass frame with a glowing outline around its content. */
class SAirsoftNeonPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftNeonPanel)
		: _LineColor(AirsoftNeon::Cyan())
		, _FillColor(AirsoftNeon::Glass())
		, _AccentColor(FLinearColor(0.f, 0.f, 0.f, 0.f))
		, _Chamfer(12.f)
		, _Corners(AirsoftNeon::Diagonal)
		, _Glow(1.f)
		, _Padding(FMargin(14.f, 10.f))
	{}
		SLATE_DEFAULT_SLOT(FArguments, Content)
		SLATE_ATTRIBUTE(FLinearColor, LineColor)
		SLATE_ATTRIBUTE(FLinearColor, FillColor)
		/** Bright cut along each chamfer (alpha 0 = none). */
		SLATE_ATTRIBUTE(FLinearColor, AccentColor)
		SLATE_ARGUMENT(float, Chamfer)
		SLATE_ARGUMENT(uint8, Corners)
		SLATE_ARGUMENT(float, Glow)
		SLATE_ARGUMENT(FMargin, Padding)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;

private:
	TAttribute<FLinearColor> LineColor;
	TAttribute<FLinearColor> FillColor;
	TAttribute<FLinearColor> AccentColor;
	float Chamfer = 12.f;
	uint8 Corners = AirsoftNeon::Diagonal;
	float Glow = 1.f;
};

/** Slanted, optionally segmented gradient bar with a glowing fill; Trail keeps a fading "just lost" chunk. */
class SAirsoftNeonBar : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftNeonBar)
		: _Fraction(0.f)
		, _FromColor(AirsoftNeon::Red())
		, _ToColor(AirsoftNeon::Orange())
		, _Width(240.f)
		, _Height(10.f)
		, _Slant(6.f)
		, _Segments(1)
		, _Gap(3.f)
		, _Trail(false)
		, _Frame(true)
		, _Glow(1.f)
	{}
		SLATE_ATTRIBUTE(float, Fraction)
		SLATE_ATTRIBUTE(FLinearColor, FromColor)
		SLATE_ATTRIBUTE(FLinearColor, ToColor)
		SLATE_ARGUMENT(float, Width)
		SLATE_ARGUMENT(float, Height)
		SLATE_ARGUMENT(float, Slant)
		SLATE_ARGUMENT(int32, Segments)
		SLATE_ARGUMENT(float, Gap)
		SLATE_ARGUMENT(bool, Trail)
		SLATE_ARGUMENT(bool, Frame)
		SLATE_ARGUMENT(float, Glow)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	TAttribute<float> Fraction;
	TAttribute<FLinearColor> FromColor;
	TAttribute<FLinearColor> ToColor;
	float Width = 240.f;
	float Height = 10.f;
	float Slant = 6.f;
	int32 Segments = 1;
	float Gap = 3.f;
	bool bTrail = false;
	bool bFrame = true;
	float Glow = 1.f;

	// Trail state (paint-time animation).
	mutable float Ghost = -1.f;
	mutable float LastFraction = -1.f;
	mutable double GhostHoldUntil = 0.0;
	mutable double LastPaintTime = 0.0;
};

/** Octagonal crest with the player's call-sign initials (an original emblem, no portraits). */
class SAirsoftNeonEmblem : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftNeonEmblem)
		: _Color(AirsoftNeon::Cyan())
		, _Size(64.f)
	{}
		SLATE_ATTRIBUTE(FString, Text)
		SLATE_ATTRIBUTE(FLinearColor, Color)
		SLATE_ARGUMENT(float, Size)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	TAttribute<FString> Text;
	TAttribute<FLinearColor> Color;
	float Size = 64.f;
};

/** Side-on silhouette of the current weapon class (Rifle, DMR, Sniper, LMG, SMG, Shotgun, Pistol), muzzle to the right. */
class SAirsoftWeaponGlyph : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftWeaponGlyph)
		: _Color(AirsoftNeon::Cyan())
		, _Width(124.f)
		, _Height(40.f)
	{}
		SLATE_ATTRIBUTE(FString, WeaponClass)
		SLATE_ATTRIBUTE(FLinearColor, Color)
		SLATE_ARGUMENT(float, Width)
		SLATE_ARGUMENT(float, Height)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

	/** Outline polygons in a 100 x 40 design box (y down). */
	static void GetShapes(const FString& WeaponClass, TArray<TArray<FVector2f>>& OutShapes);

private:
	TAttribute<FString> WeaponClass;
	TAttribute<FLinearColor> Color;
	float Width = 124.f;
	float Height = 40.f;
};

/** One pip per round (grouped above 50 rounds): cyan loaded, orange when low, dim when spent. */
class SAirsoftMagPips : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftMagPips)
		: _Mag(0)
		, _MagSize(30)
		, _Width(220.f)
		, _Height(7.f)
	{}
		SLATE_ATTRIBUTE(int32, Mag)
		SLATE_ATTRIBUTE(int32, MagSize)
		SLATE_ARGUMENT(float, Width)
		SLATE_ARGUMENT(float, Height)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	TAttribute<int32> Mag;
	TAttribute<int32> MagSize;
	float Width = 220.f;
	float Height = 7.f;
};

/** Small painted icon in a neon tile: a target reticle (objective) or a medical cross. */
class SAirsoftNeonIcon : public SLeafWidget
{
public:
	enum class EKind : uint8
	{
		Target,
		Cross
	};

	SLATE_BEGIN_ARGS(SAirsoftNeonIcon)
		: _Kind(EKind::Target)
		, _Color(AirsoftNeon::Cyan())
		, _Size(44.f)
	{}
		SLATE_ARGUMENT(EKind, Kind)
		SLATE_ATTRIBUTE(FLinearColor, Color)
		SLATE_ARGUMENT(float, Size)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	EKind Kind = EKind::Target;
	TAttribute<FLinearColor> Color;
	float Size = 44.f;
};
