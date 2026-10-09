// Andrew's Airsoft - painted HUD layer: crosshair, hit marker, scope, team-mate
// name tags, XP popups, Domination capture bar, final-tag letterbox, and the
// A/B/C objective badges.

#include "SAirsoftHUD.h"

#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameState.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftUIStyle.h"
#include "AirsoftWeaponData.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Rendering/DrawElements.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftHUDCanvasLocal
{
	/** How far the scope mask's black ring reaches beyond the lens (1080p units). Covers any aspect ratio up to ~6:1. */
	constexpr float ScopeMaskBorder = 3200.f;
	constexpr int32 NumRings = 4;
	const float RingWidths[NumRings] = { 90.f, 44.f, 18.f, 6.f };
	const float RingAlphas[NumRings] = { 0.1f, 0.14f, 0.2f, 0.42f };

	/** Rounded box whose radius is half its height (a circle when square) with a transparent middle. */
	FSlateBrush MakeRingBrush(const FLinearColor& RingColor, float RingWidth)
	{
		FSlateBrush Brush = FSlateRoundedBoxBrush(FLinearColor(0.f, 0.f, 0.f, 0.001f), 0.f, RingColor, RingWidth);
		Brush.OutlineSettings.RoundingType = ESlateBrushRoundingType::HalfHeightRadius;
		return Brush;
	}
}

namespace AirsoftHUDShared
{
	bool IsGameplayHidden(const AAirsoftPlayerController* PC)
	{
		if (!PC || PC->IsMainMenu())
		{
			return true;
		}
		return PC->IsMenuOpen() || PC->IsSummaryVisible() || PC->GetReplayTime() >= 0.f;
	}
}

// ---------------------------------------------------------------------------
// SAirsoftHUDCanvas
// ---------------------------------------------------------------------------

void SAirsoftHUDCanvas::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	using namespace AirsoftHUDCanvasLocal;
	WeakPC = InPC;
	SetCanTick(false);
	ForceVolatile(true);

	ScopeMask = MakeRingBrush(FLinearColor::Black, ScopeMaskBorder);
	for (int32 i = 0; i < NumRings; ++i)
	{
		ScopeRings[i] = MakeRingBrush(FLinearColor(0.f, 0.f, 0.f, RingAlphas[i]), RingWidths[i]);
	}
}

FVector2D SAirsoftHUDCanvas::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(8.f, 8.f);
}

int32 SAirsoftHUDCanvas::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	AAirsoftPlayerController* PC = WeakPC.Get();
	if (!PC)
	{
		return LayerId;
	}
	const FVector2f Size(AllottedGeometry.GetLocalSize());
	if (Size.X < 1.f || Size.Y < 1.f)
	{
		return LayerId;
	}

	if (!AirsoftHUDShared::IsGameplayHidden(PC))
	{
		const AAirsoftCharacter* Character = AUI::GetCharacter(PC);
		const UAirsoftCombatComponent* Combat = Character ? Character->GetCombat() : nullptr;
		const bool bOut = Character && Character->IsOut();

		if (Combat && Combat->IsScoped() && !bOut)
		{
			PaintScope(OutDrawElements, LayerId, AllottedGeometry, Size);
		}
		if (bOut)
		{
			PaintTaggedShade(OutDrawElements, LayerId, AllottedGeometry, Size);
		}
		PaintNameTags(PC, OutDrawElements, LayerId, AllottedGeometry, Size);
		PaintCaptureBar(PC, OutDrawElements, LayerId, AllottedGeometry, Size);
		PaintCrosshair(PC, OutDrawElements, LayerId, AllottedGeometry, Size);
		PaintHitMarker(PC, OutDrawElements, LayerId, AllottedGeometry, Size);
		PaintXPPopups(PC, OutDrawElements, LayerId, AllottedGeometry, Size);
	}
	PaintReplay(PC, OutDrawElements, LayerId, AllottedGeometry, Size);

	// Layers used: +0 shapes, +1 lines, +2 text.
	return LayerId + 2;
}

void SAirsoftHUDCanvas::PaintScope(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	using namespace AirsoftHUDCanvasLocal;
	const FVector2f C = Size * 0.5f;
	const float R = Size.Y * 0.45f;
	const float Outer = R + ScopeMaskBorder;

	// Black everywhere outside the lens.
	AUI::PaintBrush(Out, Layer, Geo, &ScopeMask, C - FVector2f(Outer, Outer), FVector2f(Outer * 2.f, Outer * 2.f), FLinearColor::White);
	if (C.X > Outer)
	{
		AUI::PaintRect(Out, Layer, Geo, FVector2f(0.f, 0.f), FVector2f(C.X - Outer + 1.f, Size.Y), FLinearColor::Black);
		AUI::PaintRect(Out, Layer, Geo, FVector2f(C.X + Outer - 1.f, 0.f), FVector2f(C.X - Outer + 1.f, Size.Y), FLinearColor::Black);
	}

	// Dark vignette just inside the lens edge.
	for (int32 i = 0; i < NumRings; ++i)
	{
		AUI::PaintBrush(Out, Layer, Geo, &ScopeRings[i], C - FVector2f(R, R), FVector2f(R * 2.f, R * 2.f), FLinearColor::White);
	}

	// Duplex reticle: heavy posts from the edge, fine cross in the middle, mil-dots.
	const int32 L = Layer + 1;
	const FLinearColor Ink(0.f, 0.f, 0.f, 0.94f);
	const float Thin = 1.2f;
	const float Thick = 4.f;
	const float Inner = R * 0.32f;
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Inner, C.Y - Thin * 0.5f), FVector2f(Inner * 2.f, Thin), Ink);
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Thin * 0.5f, C.Y - Inner), FVector2f(Thin, Inner * 2.f), Ink);
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X - R, C.Y - Thick * 0.5f), FVector2f(R - Inner, Thick), Ink);
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X + Inner, C.Y - Thick * 0.5f), FVector2f(R - Inner, Thick), Ink);
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Thick * 0.5f, C.Y + Inner), FVector2f(Thick, R - Inner), Ink);
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Thick * 0.5f, C.Y - R), FVector2f(Thick, R - Inner), Ink);

	const float Spacing = Inner / 5.f;
	const float Dot = 3.5f;
	for (int32 k = 1; k <= 4; ++k)
	{
		const float D = Spacing * k;
		AUI::PaintRect(Out, L, Geo, FVector2f(C.X + D - Dot * 0.5f, C.Y - Dot * 0.5f), FVector2f(Dot, Dot), Ink);
		AUI::PaintRect(Out, L, Geo, FVector2f(C.X - D - Dot * 0.5f, C.Y - Dot * 0.5f), FVector2f(Dot, Dot), Ink);
		AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Dot * 0.5f, C.Y + D - Dot * 0.5f), FVector2f(Dot, Dot), Ink);
		AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Dot * 0.5f, C.Y - D - Dot * 0.5f), FVector2f(Dot, Dot), Ink);
	}
	// A faint illuminated centre.
	AUI::PaintRect(Out, L, Geo, C - FVector2f(1.f, 1.f), FVector2f(2.f, 2.f), AUI::WithAlpha(AUI::Accent(), 0.85f));
}

void SAirsoftHUDCanvas::PaintTaggedShade(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	AUI::PaintRect(Out, Layer, Geo, FVector2f(0.f, 0.f), Size, FLinearColor(0.f, 0.f, 0.f, 0.3f));
	const int32 Rows = 12;
	const float FallH = Size.Y * 0.2f;
	for (int32 i = 0; i < Rows; ++i)
	{
		const float T = static_cast<float>(i) / Rows;
		const float Alpha = 0.35f * (1.f - AUI::Ease(T));
		const float H = FallH / Rows + 0.5f;
		AUI::PaintRect(Out, Layer, Geo, FVector2f(0.f, FallH * T), FVector2f(Size.X, H), FLinearColor(0.f, 0.f, 0.f, Alpha));
		AUI::PaintRect(Out, Layer, Geo, FVector2f(0.f, Size.Y - FallH * T - H), FVector2f(Size.X, H), FLinearColor(0.f, 0.f, 0.f, Alpha));
	}
}

void SAirsoftHUDCanvas::PaintNameTags(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	const AAirsoftPlayerState* MyPS = AUI::GetPlayerState(PC);
	UWorld* World = PC->GetWorld();
	if (!MyPS || !World || MyPS->Team == EAirsoftTeam::None || !PC->PlayerCameraManager)
	{
		return;
	}
	const FVector CamLoc = PC->PlayerCameraManager->GetCameraLocation();
	const float Scale = Geo.Scale > 0.f ? Geo.Scale : 1.f;
	const FSlateFontInfo NameFont = AUI::Font(AUI::EFontWeight::Bold, 9, 80);
	const FSlateFontInfo OutFont = AUI::Caption(7);
	const APawn* MyPawn = PC->GetPawn();
	const FLinearColor TeamCol = AUI::TeamColor(MyPS->Team);

	for (TActorIterator<AAirsoftCharacter> It(World); It; ++It)
	{
		const AAirsoftCharacter* Other = *It;
		if (!IsValid(Other) || Other == MyPawn)
		{
			continue;
		}
		const AAirsoftPlayerState* OtherPS = Other->GetAirsoftPlayerState();
		if (!OtherPS || OtherPS->Team != MyPS->Team)
		{
			continue;
		}
		float HalfHeight = 90.f;
		if (const UCapsuleComponent* Capsule = Other->GetCapsuleComponent())
		{
			HalfHeight = Capsule->GetScaledCapsuleHalfHeight();
		}
		const FVector Head = Other->GetActorLocation() + FVector(0.0, 0.0, HalfHeight + 28.0);
		const float Dist = static_cast<float>(FVector::Dist(CamLoc, Head));
		if (Dist > 6000.f)
		{
			continue;
		}
		FVector2D Screen;
		if (!PC->ProjectWorldLocationToScreen(Head, Screen, true))
		{
			continue;
		}
		const FVector2f P(static_cast<float>(Screen.X) / Scale, static_cast<float>(Screen.Y) / Scale);
		if (P.X < -60.f || P.X > Size.X + 60.f || P.Y < -60.f || P.Y > Size.Y + 60.f)
		{
			continue;
		}

		const float Alpha = FMath::Lerp(1.f, 0.4f, FMath::Clamp((Dist - 1500.f) / 4500.f, 0.f, 1.f));
		const bool bOtherOut = Other->IsOut();
		const FLinearColor NameCol = bOtherOut ? AUI::WithAlpha(AUI::TextDim(), Alpha) : AUI::WithAlpha(TeamCol, Alpha);
		const FVector2f NameSize = AUI::PaintTextCentered(Out, Layer + 2, Geo, OtherPS->GetPlayerName(), NameFont, P, NameCol);
		AUI::PaintRect(Out, Layer, Geo, FVector2f(P.X - 9.f, P.Y + NameSize.Y * 0.5f + 2.f), FVector2f(18.f, 2.f), AUI::WithAlpha(bOtherOut ? AUI::TextDim() : TeamCol, Alpha * 0.8f));
		if (bOtherOut)
		{
			AUI::PaintTextCentered(Out, Layer + 2, Geo, TEXT("OUT"), OutFont, FVector2f(P.X, P.Y - NameSize.Y * 0.5f - 7.f), AUI::WithAlpha(AUI::Danger(), Alpha));
		}
	}
}

void SAirsoftHUDCanvas::PaintCrosshair(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	const AAirsoftCharacter* Character = AUI::GetCharacter(PC);
	const UAirsoftCombatComponent* Combat = Character ? Character->GetCombat() : nullptr;
	if (!Character || !Combat || Character->IsOut() || Character->IsSprinting() || Combat->IsScoped())
	{
		return;
	}
	const float Aim = Combat->GetAimAlpha();
	if (Aim > 0.6f)
	{
		return;
	}
	const float Alpha = 1.f - FMath::Clamp((Aim - 0.25f) / 0.35f, 0.f, 1.f);
	const float FOV = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetFOVAngle() : 90.f;
	const float HalfTan = FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(FOV, 5.f, 170.f) * 0.5f));
	const float SpreadTan = FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(Combat->GetSpread(), 0.f, 45.f)));
	const float Gap = FMath::Clamp(SpreadTan / FMath::Max(HalfTan, 0.01f) * Size.X * 0.5f, 4.f, Size.X * 0.2f);

	const FVector2f C = Size * 0.5f;
	const float Len = 9.f;
	const float Thick = 2.f;
	const FLinearColor Col(1.f, 1.f, 1.f, 0.92f * Alpha);
	const FLinearColor Shadow(0.f, 0.f, 0.f, 0.45f * Alpha);
	const int32 L = Layer + 1;
	auto Bar = [&](const FVector2f& Pos, const FVector2f& BarSize)
	{
		AUI::PaintRect(Out, L, Geo, Pos - FVector2f(1.f, 1.f), BarSize + FVector2f(2.f, 2.f), Shadow);
		AUI::PaintRect(Out, L, Geo, Pos, BarSize, Col);
	};
	Bar(FVector2f(C.X - Gap - Len, C.Y - Thick * 0.5f), FVector2f(Len, Thick));
	Bar(FVector2f(C.X + Gap, C.Y - Thick * 0.5f), FVector2f(Len, Thick));
	Bar(FVector2f(C.X - Thick * 0.5f, C.Y - Gap - Len), FVector2f(Thick, Len));
	Bar(FVector2f(C.X - Thick * 0.5f, C.Y + Gap), FVector2f(Thick, Len));
	Bar(C - FVector2f(1.f, 1.f), FVector2f(2.f, 2.f));
}

void SAirsoftHUDCanvas::PaintHitMarker(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	const float A = FMath::Clamp(PC->GetHitMarkerAlpha(), 0.f, 1.f);
	if (A <= 0.01f)
	{
		return;
	}
	const bool bTag = PC->WasHitMarkerTag();
	const float Grow = 0.85f + 0.25f * A;
	const float Inner = (bTag ? 9.f : 6.f) * Grow;
	const float OuterR = (bTag ? 22.f : 13.f) * Grow;
	const float Thick = bTag ? 2.6f : 1.8f;
	const FLinearColor Col = AUI::WithAlpha(bTag ? AUI::Accent() : FLinearColor::White, A);
	const FLinearColor Shadow(0.f, 0.f, 0.f, 0.5f * A);
	const FVector2f C = Size * 0.5f;
	const int32 L = Layer + 1;
	const float K = 0.70710678f;
	const FVector2f Dirs[4] = { FVector2f(K, K), FVector2f(-K, K), FVector2f(K, -K), FVector2f(-K, -K) };
	for (const FVector2f& D : Dirs)
	{
		AUI::PaintLine(Out, L, Geo, C + D * Inner, C + D * OuterR, Shadow, Thick + 2.f);
	}
	for (const FVector2f& D : Dirs)
	{
		AUI::PaintLine(Out, L, Geo, C + D * Inner, C + D * OuterR, Col, Thick);
	}
}

void SAirsoftHUDCanvas::PaintXPPopups(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	const TArray<FAirsoftXPPopup>& Pops = PC->GetXPPopups();
	if (Pops.Num() == 0)
	{
		return;
	}
	const double Now = AUI::HudNow(PC);
	const FSlateFontInfo AmountFont = AUI::Font(AUI::EFontWeight::Bold, 13, 40);
	const FSlateFontInfo ReasonFont = AUI::Caption(9);
	const FVector2f C = Size * 0.5f;
	int32 Slot = 0;
	for (int32 i = Pops.Num() - 1; i >= 0 && Slot < 5; --i)
	{
		const FAirsoftXPPopup& Pop = Pops[i];
		const float Age = static_cast<float>(Now - Pop.Time);
		if (Age < 0.f || Age > 1.5f)
		{
			continue;
		}
		const float Alpha = AUI::Ease(Age / 0.12f) * (1.f - AUI::Ease((Age - 1.f) / 0.5f));
		const float Rise = 20.f * AUI::Ease(Age / 1.5f);
		const float Y = C.Y + 64.f + Slot * 22.f - Rise;
		const FString Amount = FString::Printf(TEXT("+%d"), Pop.Amount);
		const FString Reason = Pop.Reason.ToUpper();
		const FVector2f AmountSize = AUI::MeasureText(Amount, AmountFont);
		const FVector2f ReasonSize = AUI::MeasureText(Reason, ReasonFont);
		const float Gap = Reason.IsEmpty() ? 0.f : 8.f;
		const float X = C.X - (AmountSize.X + Gap + ReasonSize.X) * 0.5f;
		AUI::PaintText(Out, Layer + 2, Geo, Amount, AmountFont, FVector2f(X, Y - AmountSize.Y * 0.5f), AUI::WithAlpha(AUI::Accent(), Alpha));
		if (!Reason.IsEmpty())
		{
			AUI::PaintText(Out, Layer + 2, Geo, Reason, ReasonFont, FVector2f(X + AmountSize.X + Gap, Y - ReasonSize.Y * 0.5f), AUI::WithAlpha(AUI::TextColor(), Alpha));
		}
		++Slot;
	}
}

void SAirsoftHUDCanvas::PaintCaptureBar(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	const AAirsoftGameState* GS = AUI::GetGameState(PC);
	const AAirsoftCharacter* Character = AUI::GetCharacter(PC);
	if (!GS || !Character || Character->IsOut() || GS->Mode != EAirsoftMode::Domination)
	{
		return;
	}
	const FVector PawnLoc = Character->GetActorLocation();
	const AAirsoftObjective* Inside = nullptr;
	for (const TObjectPtr<AAirsoftObjective>& ObjPtr : GS->Objectives)
	{
		const AAirsoftObjective* Obj = ObjPtr.Get();
		if (Obj && Obj->bActive && Obj->IsInside(PawnLoc))
		{
			Inside = Obj;
			break;
		}
	}
	if (!Inside)
	{
		return;
	}

	const AAirsoftPlayerState* PS = AUI::GetPlayerState(PC);
	const EAirsoftTeam MyTeam = PS ? PS->Team : EAirsoftTeam::None;
	const FString Letter = Inside->Letter.ToUpper();
	FString Label = FString::Printf(TEXT("POINT %s"), *Letter);
	FLinearColor LabelColor = AUI::TextColor();
	if (Inside->bContested)
	{
		Label = FString::Printf(TEXT("%s CONTESTED"), *Letter);
		LabelColor = FLinearColor::LerpUsingHSV(AUI::Accent(), FLinearColor::White, AUI::Pulse(2.f) * 0.5f);
	}
	else if (Inside->CapturingTeam != EAirsoftTeam::None)
	{
		Label = (Inside->CapturingTeam == MyTeam ? FString(TEXT("CAPTURING ")) : FString(TEXT("LOSING "))) + Letter;
		LabelColor = AUI::TeamColor(Inside->CapturingTeam);
	}
	else if (Inside->OwnerTeam != EAirsoftTeam::None)
	{
		Label = Letter + (Inside->OwnerTeam == MyTeam ? FString(TEXT(" SECURED")) : FString(TEXT(" HELD BY ENEMY")));
		LabelColor = AUI::TeamColor(Inside->OwnerTeam);
	}

	const float W = 340.f;
	const float H = 6.f;
	const FVector2f C(Size.X * 0.5f, Size.Y * 0.5f + 160.f);
	AUI::PaintBrush(Out, Layer, Geo, AUI::PanelBrush(), FVector2f(C.X - W * 0.5f - 18.f, C.Y - 34.f), FVector2f(W + 36.f, 56.f), FLinearColor::White);
	AUI::PaintTextCentered(Out, Layer + 2, Geo, Label, AUI::Font(AUI::EFontWeight::Bold, 11, 260), FVector2f(C.X, C.Y - 15.f), LabelColor);

	const int32 L = Layer + 1;
	const float Left = C.X - W * 0.5f;
	const float Y = C.Y + 4.f;
	AUI::PaintRect(Out, L, Geo, FVector2f(Left, Y), FVector2f(W, H), FLinearColor(1.f, 1.f, 1.f, 0.1f));
	const float P = FMath::Clamp(Inside->Progress, -1.f, 1.f);
	if (P < 0.f)
	{
		const float Len = -P * W * 0.5f;
		AUI::PaintRect(Out, L, Geo, FVector2f(C.X - Len, Y), FVector2f(Len, H), AUI::TeamColor(EAirsoftTeam::Blue));
	}
	else if (P > 0.f)
	{
		AUI::PaintRect(Out, L, Geo, FVector2f(C.X, Y), FVector2f(P * W * 0.5f, H), AUI::TeamColor(EAirsoftTeam::Red));
	}
	AUI::PaintRect(Out, L, Geo, FVector2f(C.X - 0.75f, Y - 4.f), FVector2f(1.5f, H + 8.f), FLinearColor(1.f, 1.f, 1.f, 0.7f));
	AUI::PaintRect(Out, L, Geo, FVector2f(Left - 1.f, Y - 2.f), FVector2f(2.f, H + 4.f), AUI::TeamColor(EAirsoftTeam::Blue));
	AUI::PaintRect(Out, L, Geo, FVector2f(Left + W - 1.f, Y - 2.f), FVector2f(2.f, H + 4.f), AUI::TeamColor(EAirsoftTeam::Red));
	if (Inside->bContested)
	{
		AUI::PaintFrame(Out, L, Geo, FVector2f(Left - 4.f, Y - 4.f), FVector2f(W + 8.f, H + 8.f), AUI::WithAlpha(AUI::Accent(), 0.3f + 0.6f * AUI::Pulse(2.f)), 1.f);
	}
}

void SAirsoftHUDCanvas::PaintReplay(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const
{
	const float T = PC->GetReplayTime();
	if (T < 0.f)
	{
		return;
	}
	const float BarH = Size.Y * 0.11f * AUI::Ease(T / 0.45f);
	AUI::PaintRect(Out, Layer, Geo, FVector2f(0.f, 0.f), FVector2f(Size.X, BarH), FLinearColor::Black);
	AUI::PaintRect(Out, Layer, Geo, FVector2f(0.f, Size.Y - BarH), FVector2f(Size.X, BarH), FLinearColor::Black);
	AUI::PaintRect(Out, Layer + 1, Geo, FVector2f(0.f, Size.Y - BarH), FVector2f(Size.X, 1.f), AUI::WithAlpha(AUI::Accent(), 0.35f));

	const float A = AUI::Ease((T - 0.3f) / 0.4f);
	if (A <= 0.f)
	{
		return;
	}
	const int32 TextLayer = Layer + 2;

	// "REC"-style replay tag in the top bar.
	const float DotA = A * (0.35f + 0.65f * AUI::Pulse(1.2f));
	AUI::PaintRect(Out, Layer + 1, Geo, FVector2f(48.f, BarH * 0.5f - 4.f), FVector2f(8.f, 8.f), AUI::WithAlpha(AUI::Danger(), DotA));
	const FSlateFontInfo SmallCaps = AUI::Caption(9);
	const FVector2f ReplaySize = AUI::MeasureText(TEXT("REPLAY"), SmallCaps);
	AUI::PaintText(Out, TextLayer, Geo, TEXT("REPLAY"), SmallCaps, FVector2f(66.f, BarH * 0.5f - ReplaySize.Y * 0.5f), AUI::WithAlpha(AUI::TextColor(), A));

	const FAirsoftFinalTag& FinalTag = PC->GetSummary().FinalTag;
	const float BottomTop = Size.Y - BarH;
	AUI::PaintTextCentered(Out, TextLayer, Geo, TEXT("FINAL TAG"), AUI::Heading(12), FVector2f(Size.X * 0.5f, BottomTop + BarH * 0.32f), AUI::WithAlpha(AUI::Accent(), A));
	if (FinalTag.bValid)
	{
		const FSlateFontInfo NameFont = AUI::Font(AUI::EFontWeight::Bold, 17, 120);
		const FString Verb = TEXT("TAGGED");
		const FVector2f ShooterSize = AUI::MeasureText(FinalTag.Shooter, NameFont);
		const FVector2f VerbSize = AUI::MeasureText(Verb, SmallCaps);
		const FVector2f VictimSize = AUI::MeasureText(FinalTag.Victim, NameFont);
		const float Gap = 18.f;
		const float Total = ShooterSize.X + Gap + VerbSize.X + Gap + VictimSize.X;
		const float Y = BottomTop + BarH * 0.66f;
		float X = Size.X * 0.5f - Total * 0.5f;
		AUI::PaintText(Out, TextLayer, Geo, FinalTag.Shooter, NameFont, FVector2f(X, Y - ShooterSize.Y * 0.5f), AUI::WithAlpha(AUI::TeamColor(FinalTag.ShooterTeam), A));
		X += ShooterSize.X + Gap;
		AUI::PaintText(Out, TextLayer, Geo, Verb, SmallCaps, FVector2f(X, Y - VerbSize.Y * 0.5f), AUI::WithAlpha(AUI::TextDim(), A));
		X += VerbSize.X + Gap;
		AUI::PaintText(Out, TextLayer, Geo, FinalTag.Victim, NameFont, FVector2f(X, Y - VictimSize.Y * 0.5f), AUI::WithAlpha(AUI::TeamColor(FinalTag.VictimTeam), A));

		if (const FAirsoftWeaponDef* Weapon = AirsoftWeapons::Find(FinalTag.WeaponId))
		{
			const FString WeaponText = Weapon->Name.ToUpper();
			const FVector2f WeaponSize = AUI::MeasureText(WeaponText, SmallCaps);
			AUI::PaintText(Out, TextLayer, Geo, WeaponText, SmallCaps, FVector2f(Size.X - 48.f - WeaponSize.X, Y - WeaponSize.Y * 0.5f), AUI::WithAlpha(AUI::TextDim(), A));
		}
	}
}

// ---------------------------------------------------------------------------
// SAirsoftObjectiveBadge
// ---------------------------------------------------------------------------

void SAirsoftObjectiveBadge::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC, int32 InIndex)
{
	WeakPC = InPC;
	Index = InIndex;
	SetCanTick(false);
}

AAirsoftObjective* SAirsoftObjectiveBadge::GetObjective() const
{
	const AAirsoftGameState* GS = AUI::GetGameState(WeakPC.Get());
	if (!GS || GS->Mode != EAirsoftMode::Domination || !GS->Objectives.IsValidIndex(Index))
	{
		return nullptr;
	}
	AAirsoftObjective* Obj = GS->Objectives[Index].Get();
	return (Obj && Obj->bActive) ? Obj : nullptr;
}

FVector2D SAirsoftObjectiveBadge::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(42.f, 50.f);
}

int32 SAirsoftObjectiveBadge::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	const AAirsoftObjective* Obj = GetObjective();
	if (!Obj)
	{
		return LayerId;
	}
	const FLinearColor Tint = InWidgetStyle.GetColorAndOpacityTint();
	const float Box = 34.f;
	const FVector2f Pos(4.f, 0.f);
	const FLinearColor OwnerCol = Obj->OwnerTeam != EAirsoftTeam::None ? AUI::TeamColor(Obj->OwnerTeam) : FLinearColor(1.f, 1.f, 1.f, 0.3f);
	const float P = FMath::Clamp(Obj->Progress, -1.f, 1.f);

	AUI::PaintBrush(OutDrawElements, LayerId, AllottedGeometry, AUI::RoundedBrush(), Pos, FVector2f(Box, Box), FLinearColor(0.f, 0.f, 0.f, 0.6f) * Tint);
	// Capture fill rising from the bottom in the colour of whoever the progress favours.
	if (FMath::Abs(P) > 0.01f && Obj->OwnerTeam == EAirsoftTeam::None)
	{
		const float FillH = (Box - 2.f) * FMath::Abs(P);
		const FLinearColor FillCol = AUI::WithAlpha(AUI::TeamColor(P < 0.f ? EAirsoftTeam::Blue : EAirsoftTeam::Red), 0.35f);
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, FVector2f(Pos.X + 1.f, Pos.Y + Box - 1.f - FillH), FVector2f(Box - 2.f, FillH), FillCol * Tint);
	}
	else if (Obj->OwnerTeam != EAirsoftTeam::None)
	{
		AUI::PaintRect(OutDrawElements, LayerId, AllottedGeometry, Pos + FVector2f(1.f, 1.f), FVector2f(Box - 2.f, Box - 2.f), AUI::WithAlpha(OwnerCol, 0.22f) * Tint);
	}

	const int32 L = LayerId + 1;
	FLinearColor FrameCol = OwnerCol;
	if (Obj->bContested)
	{
		FrameCol = AUI::WithAlpha(AUI::Accent(), 0.35f + 0.65f * AUI::Pulse(2.f));
	}
	AUI::PaintFrame(OutDrawElements, L, AllottedGeometry, Pos, FVector2f(Box, Box), FrameCol * Tint, Obj->bContested ? 2.f : 1.5f);

	const FLinearColor LetterCol = Obj->OwnerTeam != EAirsoftTeam::None ? OwnerCol : AUI::TextColor();
	AUI::PaintTextCentered(OutDrawElements, LayerId + 2, AllottedGeometry, Obj->Letter.ToUpper(), AUI::Font(AUI::EFontWeight::Bold, 14), Pos + FVector2f(Box * 0.5f, Box * 0.5f), LetterCol * Tint, false);

	// Bipolar progress bar: blue grows left of centre, red grows right.
	const float BarY = Box + 5.f;
	AUI::PaintRect(OutDrawElements, L, AllottedGeometry, FVector2f(Pos.X, BarY), FVector2f(Box, 3.f), FLinearColor(1.f, 1.f, 1.f, 0.12f) * Tint);
	const float Mid = Pos.X + Box * 0.5f;
	if (P < 0.f)
	{
		AUI::PaintRect(OutDrawElements, L, AllottedGeometry, FVector2f(Mid + P * Box * 0.5f, BarY), FVector2f(-P * Box * 0.5f, 3.f), AUI::TeamColor(EAirsoftTeam::Blue) * Tint);
	}
	else if (P > 0.f)
	{
		AUI::PaintRect(OutDrawElements, L, AllottedGeometry, FVector2f(Mid, BarY), FVector2f(P * Box * 0.5f, 3.f), AUI::TeamColor(EAirsoftTeam::Red) * Tint);
	}

	// Marker when the local player stands inside this point.
	const AAirsoftCharacter* Character = AUI::GetCharacter(WeakPC.Get());
	if (Character && !Character->IsOut() && Obj->IsInside(Character->GetActorLocation()))
	{
		AUI::PaintRect(OutDrawElements, L, AllottedGeometry, FVector2f(Mid - 4.f, BarY + 7.f), FVector2f(8.f, 2.f), AUI::Accent() * Tint);
	}
	return LayerId + 2;
}
