// Andrew's Airsoft - shared Slate look.

#include "AirsoftUIStyle.h"

#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftWeaponData.h"
#include "Brushes/SlateColorBrush.h"
#include "Brushes/SlateNoResource.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Engine/World.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformTime.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

namespace AirsoftUIStyle
{
	// --- Colours -------------------------------------------------------------------

	FLinearColor Accent() { return AirsoftColors::Accent(); }
	FLinearColor AccentDeep() { return FLinearColor(0.42f, 0.2f, 0.015f); }
	FLinearColor Ink() { return FLinearColor(0.004f, 0.004f, 0.005f); }
	FLinearColor TextColor() { return FLinearColor(0.9f, 0.88f, 0.85f); }
	FLinearColor TextDim() { return FLinearColor(0.42f, 0.41f, 0.4f); }
	FLinearColor TextMuted() { return FLinearColor(0.16f, 0.16f, 0.16f); }
	FLinearColor Hairline() { return FLinearColor(1.f, 1.f, 1.f, 0.09f); }
	FLinearColor Danger() { return FLinearColor(1.f, 0.16f, 0.1f); }

	FLinearColor TeamColor(EAirsoftTeam Team)
	{
		return Team == EAirsoftTeam::None ? TextColor() : AirsoftColors::Team(Team);
	}

	FLinearColor WithAlpha(const FLinearColor& Color, float Alpha)
	{
		return FLinearColor(Color.R, Color.G, Color.B, Color.A * FMath::Clamp(Alpha, 0.f, 1.f));
	}

	// --- Type ----------------------------------------------------------------------

	FSlateFontInfo Font(EFontWeight Weight, int32 Size, int32 LetterSpacing)
	{
		const TCHAR* Face = Weight == EFontWeight::Bold ? TEXT("Bold") : (Weight == EFontWeight::Light ? TEXT("Light") : TEXT("Regular"));
		FSlateFontInfo Info = FCoreStyle::GetDefaultFontStyle(FName(Face), Size);
		Info.LetterSpacing = LetterSpacing;
		return Info;
	}

	FSlateFontInfo Heading(int32 Size)
	{
		return Font(EFontWeight::Bold, Size, 260);
	}

	FSlateFontInfo Caption(int32 Size)
	{
		return Font(EFontWeight::Regular, Size, 220);
	}

	// --- Brushes -------------------------------------------------------------------

	const FSlateBrush* WhiteBrush()
	{
		static const FSlateColorBrush Brush(FLinearColor::White);
		return &Brush;
	}

	const FSlateBrush* NoBrush()
	{
		static const FSlateNoResource Brush;
		return &Brush;
	}

	const FSlateBrush* PanelBrush()
	{
		static const FSlateRoundedBoxBrush Brush(FLinearColor(0.003f, 0.003f, 0.004f, 0.8f), 2.f, FLinearColor(1.f, 1.f, 1.f, 0.07f), 1.f);
		return &Brush;
	}

	const FSlateBrush* PanelSolidBrush()
	{
		static const FSlateRoundedBoxBrush Brush(FLinearColor(0.002f, 0.002f, 0.0025f, 0.94f), 2.f, FLinearColor(1.f, 1.f, 1.f, 0.06f), 1.f);
		return &Brush;
	}

	const FSlateBrush* RoundedBrush()
	{
		static const FSlateRoundedBoxBrush Brush(FLinearColor::White, 2.f);
		return &Brush;
	}

	const FSlateBrush* OutlineBrush()
	{
		static const FSlateRoundedBoxBrush Brush(FLinearColor(1.f, 1.f, 1.f, 0.f), 2.f, FLinearColor::White, 1.f);
		return &Brush;
	}

	const FButtonStyle& ClearButtonStyle()
	{
		static const FButtonStyle Style = FButtonStyle()
			.SetNormal(FSlateNoResource())
			.SetHovered(FSlateNoResource())
			.SetPressed(FSlateNoResource())
			.SetDisabled(FSlateNoResource())
			.SetNormalPadding(FMargin(0.f))
			.SetPressedPadding(FMargin(0.f));
		return Style;
	}

	namespace
	{
		FEditableTextBoxStyle BuildTextBoxStyle()
		{
			FEditableTextBoxStyle Style = FCoreStyle::Get().GetWidgetStyle<FEditableTextBoxStyle>(TEXT("NormalEditableTextBox"));
			const FSlateRoundedBoxBrush Normal(FLinearColor(0.f, 0.f, 0.f, 0.55f), 2.f, FLinearColor(1.f, 1.f, 1.f, 0.12f), 1.f);
			const FSlateRoundedBoxBrush Hovered(FLinearColor(0.f, 0.f, 0.f, 0.6f), 2.f, FLinearColor(1.f, 1.f, 1.f, 0.25f), 1.f);
			const FSlateRoundedBoxBrush Focused(FLinearColor(0.f, 0.f, 0.f, 0.7f), 2.f, AirsoftColors::Accent(), 1.f);
			Style.SetBackgroundImageNormal(Normal);
			Style.SetBackgroundImageHovered(Hovered);
			Style.SetBackgroundImageFocused(Focused);
			Style.SetBackgroundImageReadOnly(Normal);
			Style.SetPadding(FMargin(12.f, 9.f));
			return Style;
		}
	}

	const FEditableTextBoxStyle& TextBoxStyle()
	{
		static const FEditableTextBoxStyle Style = BuildTextBoxStyle();
		return Style;
	}

	// --- Strings -------------------------------------------------------------------

	FText Txt(const FString& S)
	{
		return FText::FromString(S);
	}

	FText Upper(const FString& S)
	{
		return FText::FromString(S.ToUpper());
	}

	FString TimeString(float Seconds)
	{
		const int32 Total = FMath::Max(0, FMath::CeilToInt(Seconds));
		return FString::Printf(TEXT("%02d:%02d"), Total / 60, Total % 60);
	}

	FString RankName(int32 RankIndex)
	{
		const TArray<FAirsoftRankDef>& Ranks = AirsoftWeapons::Ranks();
		if (Ranks.Num() == 0)
		{
			return FString();
		}
		return Ranks[FMath::Clamp(RankIndex - 1, 0, Ranks.Num() - 1)].Name;
	}

	FString WeaponName(FName WeaponId)
	{
		const FAirsoftWeaponDef* Def = AirsoftWeapons::Find(WeaponId);
		return Def ? Def->Name : WeaponId.ToString();
	}

	float RankProgress(int32 XP)
	{
		const TArray<FAirsoftRankDef>& Ranks = AirsoftWeapons::Ranks();
		const int32 Index = AirsoftWeapons::RankIndexForXP(XP); // 1-based; Ranks[Index] is the next rank
		if (Ranks.Num() == 0 || !Ranks.IsValidIndex(Index) || !Ranks.IsValidIndex(Index - 1))
		{
			return 1.f;
		}
		const int32 Lo = Ranks[Index - 1].XP;
		const int32 Hi = Ranks[Index].XP;
		return Hi > Lo ? FMath::Clamp(static_cast<float>(XP - Lo) / static_cast<float>(Hi - Lo), 0.f, 1.f) : 1.f;
	}

	int32 NextRankXP(int32 XP)
	{
		const TArray<FAirsoftRankDef>& Ranks = AirsoftWeapons::Ranks();
		const int32 Index = AirsoftWeapons::RankIndexForXP(XP);
		return Ranks.IsValidIndex(Index) ? Ranks[Index].XP : -1;
	}

	// --- Game access ---------------------------------------------------------------

	double HudNow(const AAirsoftPlayerController* PC)
	{
		// Must match AAirsoftPlayerController, which stamps its feed with real time
		// (unaffected by pause and the slow-motion replay).
		const UWorld* World = PC ? PC->GetWorld() : nullptr;
		return World ? World->GetRealTimeSeconds() : 0.0;
	}

	AAirsoftGameState* GetGameState(const AAirsoftPlayerController* PC)
	{
		const UWorld* World = PC ? PC->GetWorld() : nullptr;
		return World ? World->GetGameState<AAirsoftGameState>() : nullptr;
	}

	AAirsoftPlayerState* GetPlayerState(const AAirsoftPlayerController* PC)
	{
		return PC ? PC->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	}

	AAirsoftCharacter* GetCharacter(const AAirsoftPlayerController* PC)
	{
		return PC ? Cast<AAirsoftCharacter>(PC->GetPawn()) : nullptr;
	}

	UAirsoftCombatComponent* GetCombat(const AAirsoftPlayerController* PC)
	{
		const AAirsoftCharacter* Character = GetCharacter(PC);
		return Character ? Character->GetCombat() : nullptr;
	}

	UAirsoftGameInstance* GetGameInstance(const AAirsoftPlayerController* PC)
	{
		return PC ? PC->GetGameInstance<UAirsoftGameInstance>() : nullptr;
	}

	UAirsoftSaveGame* GetProfile(const AAirsoftPlayerController* PC)
	{
		UAirsoftGameInstance* GI = GetGameInstance(PC);
		return GI ? GI->GetProfile() : nullptr;
	}

	// --- Paint helpers -------------------------------------------------------------

	void PaintRect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
	{
		PaintBrush(Out, Layer, Geo, WhiteBrush(), Pos, Size, Color);
	}

	void PaintBrush(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FSlateBrush* Brush, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
	{
		if (!Brush || Color.A <= 0.f || Size.X <= 0.f || Size.Y <= 0.f)
		{
			return;
		}
		FSlateDrawElement::MakeBox(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), Brush, ESlateDrawEffect::None, Color);
	}

	void PaintFrame(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color, float Thickness)
	{
		PaintRect(Out, Layer, Geo, Pos, FVector2f(Size.X, Thickness), Color);
		PaintRect(Out, Layer, Geo, FVector2f(Pos.X, Pos.Y + Size.Y - Thickness), FVector2f(Size.X, Thickness), Color);
		PaintRect(Out, Layer, Geo, FVector2f(Pos.X, Pos.Y + Thickness), FVector2f(Thickness, Size.Y - 2.f * Thickness), Color);
		PaintRect(Out, Layer, Geo, FVector2f(Pos.X + Size.X - Thickness, Pos.Y + Thickness), FVector2f(Thickness, Size.Y - 2.f * Thickness), Color);
	}

	void PaintLine(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& A, const FVector2f& B, const FLinearColor& Color, float Thickness)
	{
		if (Color.A <= 0.f)
		{
			return;
		}
		TArray<FVector2f> Points;
		Points.Add(A);
		Points.Add(B);
		FSlateDrawElement::MakeLines(Out, Layer, Geo.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color, true, Thickness);
	}

	FVector2f MeasureText(const FString& Text, const FSlateFontInfo& InFont)
	{
		if (Text.IsEmpty() || !FSlateApplication::IsInitialized() || !FSlateApplication::Get().GetRenderer())
		{
			return FVector2f(0.f, 0.f);
		}
		const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		return FVector2f(Measure->Measure(Text, InFont));
	}

	FVector2f PaintText(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FString& Text, const FSlateFontInfo& InFont, const FVector2f& Pos, const FLinearColor& Color, bool bShadow)
	{
		const FVector2f Size = MeasureText(Text, InFont);
		if (Text.IsEmpty() || Color.A <= 0.f)
		{
			return Size;
		}
		if (bShadow)
		{
			FSlateDrawElement::MakeText(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos + FVector2f(1.f, 1.f))), Text, InFont,
				ESlateDrawEffect::None, FLinearColor(0.f, 0.f, 0.f, 0.75f * Color.A));
		}
		FSlateDrawElement::MakeText(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), Text, InFont, ESlateDrawEffect::None, Color);
		return Size;
	}

	FVector2f PaintTextCentered(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FString& Text, const FSlateFontInfo& InFont, const FVector2f& Center, const FLinearColor& Color, bool bShadow)
	{
		const FVector2f Size = MeasureText(Text, InFont);
		return PaintText(Out, Layer, Geo, Text, InFont, Center - Size * 0.5f, Color, bShadow);
	}

	// --- Animation -----------------------------------------------------------------

	float Ease(float T)
	{
		const float X = FMath::Clamp(T, 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}

	float Pulse(float Hz)
	{
		const double Phase = FPlatformTime::Seconds() * Hz * 2.0 * PI;
		return 0.5f + 0.5f * static_cast<float>(FMath::Sin(Phase));
	}
}
