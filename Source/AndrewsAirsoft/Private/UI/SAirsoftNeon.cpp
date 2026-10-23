// Andrew's Airsoft - neon HUD kit (see SAirsoftNeon.h).

#include "SAirsoftNeon.h"

#include "AirsoftUIStyle.h"
#include "HAL/PlatformTime.h"
#include "Rendering/DrawElements.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftNeon
{
	// --- Palette -------------------------------------------------------------------

	FLinearColor Cyan() { return FLinearColor(FColor(0, 229, 255)); }
	FLinearColor CyanDeep() { return FLinearColor(FColor(0, 120, 190)); }
	FLinearColor Orange() { return FLinearColor(FColor(255, 128, 32)); }
	FLinearColor Amber() { return FLinearColor(FColor(255, 196, 64)); }
	FLinearColor Red() { return FLinearColor(FColor(255, 40, 72)); }
	FLinearColor Magenta() { return FLinearColor(FColor(255, 48, 170)); }
	FLinearColor Glass() { return FLinearColor(0.0015f, 0.004f, 0.009f, 0.62f); }
	FLinearColor Track() { return FLinearColor(0.35f, 0.75f, 1.f, 0.08f); }

	// --- Paint helpers ---------------------------------------------------------------

	void ChamferPoints(const FVector2f& Pos, const FVector2f& Size, float Chamfer, uint8 Corners, TArray<FVector2f>& OutPoints)
	{
		OutPoints.Reset();
		const float C = FMath::Clamp(Chamfer, 0.f, FMath::Min(Size.X, Size.Y) * 0.5f);
		const float X0 = Pos.X;
		const float Y0 = Pos.Y;
		const float X1 = Pos.X + Size.X;
		const float Y1 = Pos.Y + Size.Y;
		if ((Corners & CornerTL) && C > 0.f)
		{
			OutPoints.Add(FVector2f(X0, Y0 + C));
			OutPoints.Add(FVector2f(X0 + C, Y0));
		}
		else
		{
			OutPoints.Add(FVector2f(X0, Y0));
		}
		if ((Corners & CornerTR) && C > 0.f)
		{
			OutPoints.Add(FVector2f(X1 - C, Y0));
			OutPoints.Add(FVector2f(X1, Y0 + C));
		}
		else
		{
			OutPoints.Add(FVector2f(X1, Y0));
		}
		if ((Corners & CornerBR) && C > 0.f)
		{
			OutPoints.Add(FVector2f(X1, Y1 - C));
			OutPoints.Add(FVector2f(X1 - C, Y1));
		}
		else
		{
			OutPoints.Add(FVector2f(X1, Y1));
		}
		if ((Corners & CornerBL) && C > 0.f)
		{
			OutPoints.Add(FVector2f(X0 + C, Y1));
			OutPoints.Add(FVector2f(X0, Y1 - C));
		}
		else
		{
			OutPoints.Add(FVector2f(X0, Y1));
		}
	}

	void PaintPolyline(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, bool bClosed)
	{
		if (Points.Num() < 2 || Color.A <= 0.f)
		{
			return;
		}
		TArray<FVector2f> Line = Points;
		if (bClosed)
		{
			Line.Add(Points[0]);
		}
		FSlateDrawElement::MakeLines(Out, Layer, Geo.ToPaintGeometry(), MoveTemp(Line), ESlateDrawEffect::None, Color, true, Thickness);
	}

	void PaintGlowPolyline(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Points, const FLinearColor& Color, float Thickness, float Glow, bool bClosed)
	{
		if (Glow > 0.f)
		{
			PaintPolyline(Out, Layer, Geo, Points, AUI::WithAlpha(Color, 0.06f * Glow), Thickness + 12.f, bClosed);
			PaintPolyline(Out, Layer, Geo, Points, AUI::WithAlpha(Color, 0.13f * Glow), Thickness + 6.f, bClosed);
			PaintPolyline(Out, Layer, Geo, Points, AUI::WithAlpha(Color, 0.3f * Glow), Thickness + 2.5f, bClosed);
		}
		PaintPolyline(Out, Layer, Geo, Points, Color, Thickness, bClosed);
		// Hot core: the middle of a neon tube reads almost white.
		FLinearColor Core = FMath::Lerp(Color, FLinearColor::White, 0.5f);
		Core.A = Color.A * 0.8f;
		PaintPolyline(Out, Layer, Geo, Points, Core, FMath::Max(Thickness * 0.45f, 0.6f), bClosed);
	}

	void PaintChamferFill(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, float Chamfer, uint8 Corners, const FLinearColor& Color)
	{
		if (Color.A <= 0.f || Size.X <= 0.f || Size.Y <= 0.f)
		{
			return;
		}
		const float C = FMath::Clamp(Chamfer, 0.f, FMath::Min(Size.X, Size.Y) * 0.5f);
		if (C < 1.f)
		{
			AUI::PaintRect(Out, Layer, Geo, Pos, Size, Color);
			return;
		}
		const int32 Steps = FMath::Clamp(FMath::CeilToInt(C / 2.f), 1, 12);
		const float StepH = C / Steps;
		for (int32 i = 0; i < Steps; ++i)
		{
			// Inset of the cut at the middle of this strip (strip i counted in from the edge).
			const float Inset = C - (i + 0.5f) * StepH;
			const float TL = (Corners & CornerTL) ? Inset : 0.f;
			const float TR = (Corners & CornerTR) ? Inset : 0.f;
			const float BL = (Corners & CornerBL) ? Inset : 0.f;
			const float BR = (Corners & CornerBR) ? Inset : 0.f;
			AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X + TL, Pos.Y + i * StepH), FVector2f(Size.X - TL - TR, StepH), Color);
			AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X + BL, Pos.Y + Size.Y - (i + 1) * StepH), FVector2f(Size.X - BL - BR, StepH), Color);
		}
		AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X, Pos.Y + C), FVector2f(Size.X, Size.Y - 2.f * C), Color);
	}

	void PaintPolygonFill(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Points, const FLinearColor& Color, float RowStep, float RowHeight)
	{
		if (Points.Num() < 3 || Color.A <= 0.f)
		{
			return;
		}
		const float Step = FMath::Max(RowStep, 0.5f);
		const float RowH = FMath::Clamp(RowHeight, 0.25f, Step);
		float MinY = Points[0].Y;
		float MaxY = Points[0].Y;
		for (const FVector2f& P : Points)
		{
			MinY = FMath::Min(MinY, P.Y);
			MaxY = FMath::Max(MaxY, P.Y);
		}
		if (MaxY - MinY > 2000.f)
		{
			return; // not meant for anything this big
		}
		TArray<float, TInlineAllocator<16>> Xs;
		const int32 Num = Points.Num();
		for (float Y = MinY; Y < MaxY; Y += Step)
		{
			const float Yc = Y + RowH * 0.5f;
			Xs.Reset();
			for (int32 i = 0; i < Num; ++i)
			{
				const FVector2f& A = Points[i];
				const FVector2f& B = Points[(i + 1) % Num];
				if ((A.Y <= Yc && B.Y > Yc) || (B.Y <= Yc && A.Y > Yc))
				{
					const float T = (Yc - A.Y) / (B.Y - A.Y);
					Xs.Add(A.X + T * (B.X - A.X));
				}
			}
			Xs.Sort();
			for (int32 k = 0; k + 1 < Xs.Num(); k += 2)
			{
				AUI::PaintRect(Out, Layer, Geo, FVector2f(Xs[k], Y), FVector2f(Xs[k + 1] - Xs[k], FMath::Min(RowH, MaxY - Y)), Color);
			}
		}
	}

	void PaintPanel(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, float Chamfer, uint8 Corners,
		const FLinearColor& Line, const FLinearColor& Fill, float Glow, const FLinearColor& Accent)
	{
		PaintChamferFill(Out, Layer, Geo, Pos, Size, Chamfer, Corners, Fill);
		// A faint sheen along the top: the glass catches the neon.
		AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X + Chamfer, Pos.Y + 1.f), FVector2f(FMath::Max(0.f, Size.X - 2.f * Chamfer), FMath::Min(Size.Y * 0.35f, 18.f)),
			AUI::WithAlpha(Line, 0.035f));

		TArray<FVector2f> Pts;
		ChamferPoints(Pos + FVector2f(0.5f, 0.5f), Size - FVector2f(1.f, 1.f), Chamfer, Corners, Pts);
		PaintGlowPolyline(Out, Layer + 1, Geo, Pts, Line, 1.25f, Glow, true);

		if (Accent.A > 0.f && Chamfer >= 4.f)
		{
			const float C = FMath::Min(Chamfer, FMath::Min(Size.X, Size.Y) * 0.5f);
			const float X0 = Pos.X + 0.5f;
			const float Y0 = Pos.Y + 0.5f;
			const float X1 = Pos.X + Size.X - 0.5f;
			const float Y1 = Pos.Y + Size.Y - 0.5f;
			auto Cut = [&](const FVector2f& A, const FVector2f& B)
			{
				TArray<FVector2f> Seg;
				Seg.Add(A);
				Seg.Add(B);
				PaintGlowPolyline(Out, Layer + 1, Geo, Seg, Accent, 3.f, Glow, false);
			};
			if (Corners & CornerTL) { Cut(FVector2f(X0, Y0 + C), FVector2f(X0 + C, Y0)); }
			if (Corners & CornerTR) { Cut(FVector2f(X1 - C, Y0), FVector2f(X1, Y0 + C)); }
			if (Corners & CornerBR) { Cut(FVector2f(X1, Y1 - C), FVector2f(X1 - C, Y1)); }
			if (Corners & CornerBL) { Cut(FVector2f(X0 + C, Y1), FVector2f(X0, Y1 - C)); }
		}
	}

	void SlantBarPoints(const FVector2f& Pos, const FVector2f& Size, float Slant, float Fraction, TArray<FVector2f>& OutPoints)
	{
		OutPoints.Reset();
		const float S = FMath::Clamp(Slant, 0.f, Size.X * 0.5f);
		const float L = (Size.X - S) * FMath::Clamp(Fraction, 0.f, 1.f);
		OutPoints.Add(FVector2f(Pos.X + S, Pos.Y));
		OutPoints.Add(FVector2f(Pos.X + S + L, Pos.Y));
		OutPoints.Add(FVector2f(Pos.X + L, Pos.Y + Size.Y));
		OutPoints.Add(FVector2f(Pos.X, Pos.Y + Size.Y));
	}

	void PaintSlantBar(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, float Slant,
		float Fraction, const FLinearColor& From, const FLinearColor& To, int32 Segments, float Gap, const FLinearColor& TrackColor,
		float Ghost, const FLinearColor& GhostColor)
	{
		if (Size.X <= 1.f || Size.Y <= 0.f)
		{
			return;
		}
		const float S = FMath::Clamp(Slant, 0.f, Size.X * 0.5f);
		const float Base = Size.X - S;
		const int32 N = FMath::Clamp(Segments, 1, 64);
		const float G = N > 1 ? FMath::Max(Gap, 0.f) : 0.f;
		const float SegW = (Base - G * (N - 1)) / N;
		if (SegW <= 0.f)
		{
			return;
		}
		// A continuous bar is cut into thin slices so its gradient is smooth; segments take one colour each.
		const int32 Sub = N == 1 ? 24 : 1;
		const float SliceW = SegW / Sub;
		const int32 Rows = FMath::Clamp(FMath::CeilToInt(Size.Y), 1, 16);
		const float RowH = Size.Y / Rows;
		const float FillEnd = Base * FMath::Clamp(Fraction, 0.f, 1.f);
		const float GhostEnd = Ghost > Fraction ? Base * FMath::Clamp(Ghost, 0.f, 1.f) : FillEnd;

		for (int32 r = 0; r < Rows; ++r)
		{
			const float Yc = (r + 0.5f) * RowH;
			const float Shift = S * (1.f - Yc / Size.Y);
			const float Y = Pos.Y + r * RowH;
			for (int32 k = 0; k < N; ++k)
			{
				for (int32 j = 0; j < Sub; ++j)
				{
					const float A0 = k * (SegW + G) + j * SliceW;
					const float A1 = A0 + SliceW;
					const float T = FMath::Clamp((A0 + A1) * 0.5f / Base, 0.f, 1.f);
					const FLinearColor Col = FMath::Lerp(From, To, T);
					const float F1 = FMath::Min(A1, FillEnd);
					if (F1 > A0)
					{
						AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X + Shift + A0, Y), FVector2f(F1 - A0, RowH), Col);
					}
					const float G0 = FMath::Max(A0, FillEnd);
					const float G1 = FMath::Min(A1, GhostEnd);
					if (G1 > G0)
					{
						AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X + Shift + G0, Y), FVector2f(G1 - G0, RowH), GhostColor);
					}
					const float T0 = FMath::Max(A0, FMath::Max(FillEnd, GhostEnd));
					if (A1 > T0)
					{
						AUI::PaintRect(Out, Layer, Geo, FVector2f(Pos.X + Shift + T0, Y), FVector2f(A1 - T0, RowH), TrackColor);
					}
				}
			}
		}
	}

	FString Initials(const FString& Name)
	{
		TArray<FString> Words;
		FString Clean = Name.TrimStartAndEnd();
		Clean.ReplaceInline(TEXT("_"), TEXT(" "));
		Clean.ReplaceInline(TEXT("-"), TEXT(" "));
		Clean.ParseIntoArrayWS(Words);
		FString Out;
		if (Words.Num() >= 2)
		{
			Out.AppendChar(Words[0][0]);
			Out.AppendChar(Words[1][0]);
		}
		else if (Words.Num() == 1)
		{
			Out = Words[0].Left(2);
		}
		if (Out.IsEmpty())
		{
			Out = TEXT("OP");
		}
		return Out.ToUpper();
	}
}

// ---------------------------------------------------------------------------
// SAirsoftNeonPanel
// ---------------------------------------------------------------------------

void SAirsoftNeonPanel::Construct(const FArguments& InArgs)
{
	LineColor = InArgs._LineColor;
	FillColor = InArgs._FillColor;
	AccentColor = InArgs._AccentColor;
	Chamfer = InArgs._Chamfer;
	Corners = InArgs._Corners;
	Glow = InArgs._Glow;
	ChildSlot
	.Padding(InArgs._Padding)
	[
		InArgs._Content.Widget
	];
}

int32 SAirsoftNeonPanel::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	if (Size.X > 1.f && Size.Y > 1.f)
	{
		AirsoftNeon::PaintPanel(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Size, Chamfer, Corners,
			LineColor.Get() * Tint, FillColor.Get() * Tint, Glow, AccentColor.Get() * Tint);
	}
	return SCompoundWidget::OnPaint(Args, AllottedGeometry, MyCullingRect, OutDrawElements, LayerId + 2, InWidgetStyle, bParentEnabled);
}

// ---------------------------------------------------------------------------
// SAirsoftNeonBar
// ---------------------------------------------------------------------------

void SAirsoftNeonBar::Construct(const FArguments& InArgs)
{
	Fraction = InArgs._Fraction;
	FromColor = InArgs._FromColor;
	ToColor = InArgs._ToColor;
	Width = InArgs._Width;
	Height = InArgs._Height;
	Slant = InArgs._Slant;
	Segments = InArgs._Segments;
	Gap = InArgs._Gap;
	bTrail = InArgs._Trail;
	bFrame = InArgs._Frame;
	Glow = InArgs._Glow;
	SetCanTick(false);
}

FVector2D SAirsoftNeonBar::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Width, FMath::Max(Height, 1.f));
}

int32 SAirsoftNeonBar::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace AirsoftNeon;
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	if (Size.X < 2.f || Size.Y < 1.f)
	{
		return LayerId;
	}
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	const float F = FMath::Clamp(Fraction.Get(), 0.f, 1.f);

	// Trail: a lost chunk holds for a moment, then drains down to the new value.
	const double Now = FPlatformTime::Seconds();
	const float Dt = LastPaintTime > 0.0 ? static_cast<float>(FMath::Min(Now - LastPaintTime, 0.1)) : 0.f;
	LastPaintTime = Now;
	if (!bTrail || Ghost < 0.f || F >= Ghost)
	{
		Ghost = F;
	}
	else
	{
		if (LastFraction >= 0.f && F < LastFraction - 0.001f)
		{
			GhostHoldUntil = Now + 0.45;
		}
		if (Now > GhostHoldUntil)
		{
			Ghost = FMath::Max(F, Ghost - Dt * 0.7f);
		}
	}
	LastFraction = F;

	const FLinearColor From = FromColor.Get() * Tint;
	const FLinearColor To = ToColor.Get() * Tint;
	PaintSlantBar(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Size, Slant, F, From, To, Segments, Gap,
		Track() * Tint, Ghost, FLinearColor(1.f, 0.95f, 0.9f, 0.55f) * Tint);

	TArray<FVector2f> Pts;
	if (F > 0.005f && Glow > 0.f)
	{
		// Halo around the lit part only.
		SlantBarPoints(FVector2f(0.f, 0.f), Size, Slant, F, Pts);
		FLinearColor Halo = FMath::Lerp(From, To, 0.6f);
		Halo.A *= 0.55f;
		PaintPolyline(OutDrawElements, LayerId, AllottedGeometry, Pts, AUI::WithAlpha(Halo, 0.18f * Glow), 7.f, true);
		PaintPolyline(OutDrawElements, LayerId, AllottedGeometry, Pts, AUI::WithAlpha(Halo, 0.3f * Glow), 3.f, true);
	}
	if (bFrame)
	{
		// Thin frame a little outside the track.
		SlantBarPoints(FVector2f(-3.f, -3.f), Size + FVector2f(6.f, 6.f), Slant + 3.f * Slant / FMath::Max(Size.Y, 1.f), 1.f, Pts);
		PaintPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Pts, AUI::WithAlpha(Cyan() * Tint, 0.45f), 1.f, true);
	}
	return LayerId + 1;
}

// ---------------------------------------------------------------------------
// SAirsoftNeonEmblem
// ---------------------------------------------------------------------------

void SAirsoftNeonEmblem::Construct(const FArguments& InArgs)
{
	Text = InArgs._Text;
	Color = InArgs._Color;
	Size = InArgs._Size;
	SetCanTick(false);
}

FVector2D SAirsoftNeonEmblem::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Size, Size);
}

int32 SAirsoftNeonEmblem::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace AirsoftNeon;
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	const FLinearColor Col = Color.Get() * Tint;
	const FVector2f Box(Size, Size);
	const float Cut = Size * 0.29f;
	PaintChamferFill(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Box, Cut, AllCorners, FLinearColor(0.002f, 0.006f, 0.014f, 0.8f) * Tint);
	// Inner hatching: a faint scanline tint inside the crest.
	TArray<FVector2f> Pts;
	ChamferPoints(FVector2f(6.f, 6.f), Box - FVector2f(12.f, 12.f), Cut - 2.5f, AllCorners, Pts);
	PaintPolygonFill(OutDrawElements, LayerId, AllottedGeometry, Pts, AUI::WithAlpha(Col, 0.07f), 3.f, 1.f);
	PaintPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Pts, AUI::WithAlpha(Col, 0.35f), 1.f, true);
	ChamferPoints(FVector2f(0.5f, 0.5f), Box - FVector2f(1.f, 1.f), Cut, AllCorners, Pts);
	PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Pts, Col, 1.75f, 1.f, true);
	// Orange cuts on the top-left and bottom-right edges.
	const FLinearColor Hot = Orange() * Tint;
	TArray<FVector2f> Seg;
	Seg.Add(FVector2f(0.5f, Cut + 0.5f));
	Seg.Add(FVector2f(Cut + 0.5f, 0.5f));
	PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Seg, Hot, 2.5f, 0.8f, false);
	Seg[0] = FVector2f(Size - 0.5f, Size - Cut - 0.5f);
	Seg[1] = FVector2f(Size - Cut - 0.5f, Size - 0.5f);
	PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Seg, Hot, 2.5f, 0.8f, false);

	const int32 FontSize = FMath::Max(8, FMath::RoundToInt(Size * 0.27f));
	AUI::PaintTextCentered(OutDrawElements, LayerId + 2, AllottedGeometry, Text.Get(), AUI::Font(AUI::EFontWeight::Bold, FontSize, 80), Box * 0.5f,
		FMath::Lerp(Col, FLinearColor::White, 0.45f));
	return LayerId + 2;
}

// ---------------------------------------------------------------------------
// SAirsoftWeaponGlyph
// ---------------------------------------------------------------------------

namespace AirsoftGlyphLocal
{
	void Add(TArray<TArray<FVector2f>>& Shapes, std::initializer_list<float> XY)
	{
		TArray<FVector2f>& Shape = Shapes.AddDefaulted_GetRef();
		const float* P = XY.begin();
		for (size_t i = 0; i + 1 < XY.size(); i += 2)
		{
			Shape.Add(FVector2f(P[i], P[i + 1]));
		}
	}
}

void SAirsoftWeaponGlyph::GetShapes(const FString& WeaponClass, TArray<TArray<FVector2f>>& OutShapes)
{
	using AirsoftGlyphLocal::Add;
	OutShapes.Reset();
	// Design box 100 x 40, y down, muzzle to the right. Keep in step with Tools/HUD/hud_mockup.py.
	if (WeaponClass == TEXT("Pistol"))
	{
		Add(OutShapes, { 24,11, 84,11, 84,19, 56,19, 54,24, 47,24, 46,21, 43,34, 32,34, 35,20, 24,19 });
	}
	else if (WeaponClass == TEXT("SMG"))
	{
		Add(OutShapes, { 6,12, 18,12, 20,10, 60,10, 62,12, 76,12, 76,14, 90,14, 90,17, 76,17, 76,19, 58,19, 58,33, 51,33, 51,19,
			42,19, 38,30, 32,30, 34,19, 20,19, 18,21, 6,22 });
	}
	else if (WeaponClass == TEXT("Shotgun"))
	{
		Add(OutShapes, { 0,14, 16,12, 26,14, 34,13, 98,13, 98,16.5f, 74,16.5f, 74,20, 54,20, 54,17, 40,17, 34,19, 31,28, 25,28, 27,19, 18,19, 0,24 });
	}
	else if (WeaponClass == TEXT("Sniper") || WeaponClass == TEXT("DMR"))
	{
		Add(OutShapes, { 0,15, 14,13, 28,15, 32,14, 66,14, 66,16, 99,16, 99,18.5f, 66,18.5f, 64,20, 47,20, 45,28, 40,28, 40,20,
			35,20, 32,30, 27,30, 29,20, 16,21, 0,26 });
		Add(OutShapes, { 30,8, 34,6, 58,6, 62,8, 62,11, 58,12.5f, 34,12.5f, 30,11 });
	}
	else if (WeaponClass == TEXT("LMG"))
	{
		Add(OutShapes, { 2,13, 16,11, 24,13, 30,13, 31,9, 60,9, 61,11, 84,11, 84,13.5f, 98,13.5f, 98,16.5f, 84,16.5f, 84,19,
			38,19, 35,30, 30,30, 32,19, 24,19, 16,23, 2,25 });
		Add(OutShapes, { 42,19, 58,19, 58,31, 42,31 });
	}
	else if (WeaponClass == TEXT("Grenade"))
	{
		Add(OutShapes, { 44,12, 56,12, 62,18, 62,30, 56,36, 44,36, 38,30, 38,18 });
		Add(OutShapes, { 46,6, 54,6, 54,12, 46,12 });
	}
	else
	{
		// Rifle (M4 / AK / carbines) and anything unknown.
		Add(OutShapes, { 2,13, 16,11, 24,13, 30,13, 31,9, 58,9, 59,11, 82,11, 82,13.5f, 97,13.5f, 97,16.5f, 82,16.5f, 82,19, 58,19,
			56,20, 52,20, 50,33, 43,32, 45,20, 38,20, 35,30, 30,30, 32,20, 24,20, 16,23, 2,25 });
	}
}

void SAirsoftWeaponGlyph::Construct(const FArguments& InArgs)
{
	WeaponClass = InArgs._WeaponClass;
	Color = InArgs._Color;
	Width = InArgs._Width;
	Height = InArgs._Height;
	SetCanTick(false);
}

FVector2D SAirsoftWeaponGlyph::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Width, Height);
}

int32 SAirsoftWeaponGlyph::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace AirsoftNeon;
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	TArray<TArray<FVector2f>> Shapes;
	GetShapes(WeaponClass.Get(), Shapes);
	// Fit the silhouette's own bounds (a grenade is tall, a rifle long) into the widget, centred.
	FVector2f Min(TNumericLimits<float>::Max(), TNumericLimits<float>::Max());
	FVector2f Max(-TNumericLimits<float>::Max(), -TNumericLimits<float>::Max());
	for (const TArray<FVector2f>& Shape : Shapes)
	{
		for (const FVector2f& P : Shape)
		{
			Min = FVector2f(FMath::Min(Min.X, P.X), FMath::Min(Min.Y, P.Y));
			Max = FVector2f(FMath::Max(Max.X, P.X), FMath::Max(Max.Y, P.Y));
		}
	}
	const FVector2f Extent = Max - Min;
	if (Extent.X <= 0.f || Extent.Y <= 0.f)
	{
		return LayerId;
	}
	const float Scale = FMath::Min(Size.X / Extent.X, Size.Y / Extent.Y);
	const FVector2f Offset = (Size - Extent * Scale) * 0.5f - Min * Scale;
	const FLinearColor Col = Color.Get() * InWidgetStyle.GetColorAndOpacityTint();
	for (TArray<FVector2f>& Shape : Shapes)
	{
		for (FVector2f& P : Shape)
		{
			P = Offset + P * Scale;
		}
		PaintPolygonFill(OutDrawElements, LayerId, AllottedGeometry, Shape, AUI::WithAlpha(Col, 0.55f), 2.f, 1.3f);
		PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Shape, Col, 1.2f, 0.9f, true);
	}
	return LayerId + 1;
}

// ---------------------------------------------------------------------------
// SAirsoftMagPips
// ---------------------------------------------------------------------------

void SAirsoftMagPips::Construct(const FArguments& InArgs)
{
	Mag = InArgs._Mag;
	MagSize = InArgs._MagSize;
	Width = InArgs._Width;
	Height = InArgs._Height;
	SetCanTick(false);
}

FVector2D SAirsoftMagPips::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Width, Height);
}

int32 SAirsoftMagPips::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace AirsoftNeon;
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	const int32 Capacity = FMath::Max(1, MagSize.Get());
	const int32 Rounds = FMath::Clamp(Mag.Get(), 0, Capacity);
	// Above 50 rounds (drums, the SAW) one pip stands for several.
	const int32 PerPip = FMath::DivideAndRoundUp(Capacity, 50);
	const int32 Pips = FMath::DivideAndRoundUp(Capacity, PerPip);
	const int32 Lit = FMath::DivideAndRoundUp(Rounds, PerPip);
	const float Gap = Pips > 30 ? 1.5f : 2.5f;
	const float PipW = (Size.X - Gap * (Pips - 1)) / Pips;
	if (PipW <= 0.5f)
	{
		return LayerId;
	}
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	const bool bLow = Rounds * 4 <= Capacity;
	const FLinearColor On = (Rounds <= 0 ? Red() : (bLow ? Orange() : Cyan())) * Tint;
	const FLinearColor Off = FLinearColor(0.35f, 0.75f, 1.f, 0.12f) * Tint;
	for (int32 i = 0; i < Pips; ++i)
	{
		const float X = i * (PipW + Gap);
		// Rounds feed from the right: the lit pips are the ones still in the mag.
		const bool bOn = i >= Pips - Lit;
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(X, 0.f), FVector2f(PipW, Size.Y), bOn ? On : Off);
	}
	if (Lit > 0)
	{
		const float X0 = (Pips - Lit) * (PipW + Gap);
		TArray<FVector2f> Halo;
		Halo.Add(FVector2f(X0, Size.Y * 0.5f));
		Halo.Add(FVector2f(Size.X, Size.Y * 0.5f));
		PaintPolyline(OutDrawElements, LayerId, AllottedGeometry, Halo, AUI::WithAlpha(On, 0.14f), Size.Y + 6.f, false);
	}
	return LayerId;
}

// ---------------------------------------------------------------------------
// SAirsoftNeonIcon
// ---------------------------------------------------------------------------

void SAirsoftNeonIcon::Construct(const FArguments& InArgs)
{
	Kind = InArgs._Kind;
	Color = InArgs._Color;
	Size = InArgs._Size;
	SetCanTick(false);
}

FVector2D SAirsoftNeonIcon::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Size, Size);
}

int32 SAirsoftNeonIcon::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	using namespace AirsoftNeon;
	const FLinearColor Col = Color.Get() * InWidgetStyle.GetColorAndOpacityTint();
	const FVector2f Box(Size, Size);
	PaintPanel(OutDrawElements, LayerId, AllottedGeometry, FVector2f(0.f, 0.f), Box, Size * 0.22f, Diagonal, Col, Glass(), 0.8f, FLinearColor(0.f, 0.f, 0.f, 0.f));
	const FVector2f C = Box * 0.5f;
	const float R = Size * 0.26f;
	TArray<FVector2f> Line;
	if (Kind == EKind::Cross)
	{
		const float T = Size * 0.09f;
		TArray<FVector2f> Plus;
		for (const FVector2f& P : { FVector2f(-T, -R), FVector2f(T, -R), FVector2f(T, -T), FVector2f(R, -T), FVector2f(R, T), FVector2f(T, T),
			FVector2f(T, R), FVector2f(-T, R), FVector2f(-T, T), FVector2f(-R, T), FVector2f(-R, -T), FVector2f(-T, -T) })
		{
			Plus.Add(C + P);
		}
		PaintPolygonFill(OutDrawElements, LayerId + 1, AllottedGeometry, Plus, AUI::WithAlpha(Col, 0.6f), 1.f, 1.f);
		PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Plus, Col, 1.25f, 0.8f, true);
		return LayerId + 1;
	}
	// Target: a ring (octagon) with four ticks and a centre dot.
	TArray<FVector2f> Ring;
	for (int32 i = 0; i < 12; ++i)
	{
		const float A = 2.f * UE_PI * i / 12.f;
		Ring.Add(C + FVector2f(FMath::Cos(A), FMath::Sin(A)) * R);
	}
	PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Ring, Col, 1.25f, 0.8f, true);
	const FVector2f Dirs[4] = { FVector2f(1.f, 0.f), FVector2f(-1.f, 0.f), FVector2f(0.f, 1.f), FVector2f(0.f, -1.f) };
	for (const FVector2f& D : Dirs)
	{
		Line.Reset();
		Line.Add(C + D * (R * 0.55f));
		Line.Add(C + D * (R * 1.45f));
		PaintGlowPolyline(OutDrawElements, LayerId + 1, AllottedGeometry, Line, Col, 1.25f, 0.6f, false);
	}
	AUI::PaintRect(OutDrawElements, LayerId + 1, AllottedGeometry, C - FVector2f(1.5f, 1.5f), FVector2f(3.f, 3.f), Orange() * InWidgetStyle.GetColorAndOpacityTint());
	return LayerId + 1;
}
