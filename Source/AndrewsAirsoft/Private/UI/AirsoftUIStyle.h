// Andrew's Airsoft - shared look for every Slate screen: colours, type, brushes
// and a few low-level paint helpers. Neo-noir: near-black glass, thin amber
// lines, uppercase letter-spaced headings. Designed in 1080p units (the DPI
// curve scales everything for 4K).

#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "Layout/Geometry.h"
#include "Styling/SlateBrush.h"
#include "Styling/SlateTypes.h"
#include "AirsoftTypes.h"

class FSlateWindowElementList;
class AAirsoftPlayerController;
class AAirsoftGameState;
class AAirsoftPlayerState;
class AAirsoftCharacter;
class UAirsoftCombatComponent;
class UAirsoftGameInstance;
class UAirsoftSaveGame;

namespace AirsoftUIStyle
{
	enum class EFontWeight : uint8
	{
		Light,
		Regular,
		Bold
	};

	// --- Colours ---------------------------------------------------------------
	FLinearColor Accent();
	FLinearColor AccentDeep();
	FLinearColor Ink();
	FLinearColor TextColor();
	FLinearColor TextDim();
	FLinearColor TextMuted();
	FLinearColor Hairline();
	FLinearColor Danger();
	FLinearColor TeamColor(EAirsoftTeam Team);
	FLinearColor WithAlpha(const FLinearColor& Color, float Alpha);

	// --- Type ------------------------------------------------------------------
	/** Roboto from the engine's core style. LetterSpacing is in 1/1000 em. */
	FSlateFontInfo Font(EFontWeight Weight, int32 Size, int32 LetterSpacing = 0);
	/** Bold, wide letter spacing: section titles and big headings. */
	FSlateFontInfo Heading(int32 Size);
	/** Small uppercase captions ("FIRST TO 40", "TAGS"). */
	FSlateFontInfo Caption(int32 Size);

	// --- Brushes (static, live for the whole program) ----------------------------
	const FSlateBrush* WhiteBrush();
	const FSlateBrush* NoBrush();
	/** Near-black translucent glass with a faint hairline edge. */
	const FSlateBrush* PanelBrush();
	/** Darker, almost opaque glass for full-screen menus. */
	const FSlateBrush* PanelSolidBrush();
	/** White rounded box (tint it with a colour). */
	const FSlateBrush* RoundedBrush();
	/** Transparent box with a 1px white outline (tint it with a colour). */
	const FSlateBrush* OutlineBrush();
	/** Button style with no images; SAirsoftButton draws its own look. */
	const FButtonStyle& ClearButtonStyle();
	const FEditableTextBoxStyle& TextBoxStyle();

	// --- Strings ---------------------------------------------------------------
	FText Txt(const FString& S);
	FText Upper(const FString& S);
	/** "04:32". */
	FString TimeString(float Seconds);
	/** Rank name for a 1-based rank index. */
	FString RankName(int32 RankIndex);
	FString WeaponName(FName WeaponId);
	/** 0..1 progress from the start of the rank that XP falls in to the next one (1 at max rank). */
	float RankProgress(int32 XP);
	/** XP needed for the next rank, or -1 at max rank. */
	int32 NextRankXP(int32 XP);

	// --- Game access (all null-safe) --------------------------------------------
	/** Clock used by the controller's HUD feed (kill feed, announcements, XP popups, summary). */
	double HudNow(const AAirsoftPlayerController* PC);
	AAirsoftGameState* GetGameState(const AAirsoftPlayerController* PC);
	AAirsoftPlayerState* GetPlayerState(const AAirsoftPlayerController* PC);
	AAirsoftCharacter* GetCharacter(const AAirsoftPlayerController* PC);
	UAirsoftCombatComponent* GetCombat(const AAirsoftPlayerController* PC);
	UAirsoftGameInstance* GetGameInstance(const AAirsoftPlayerController* PC);
	UAirsoftSaveGame* GetProfile(const AAirsoftPlayerController* PC);

	// --- Paint helpers (local 1080p units) ----------------------------------------
	void PaintRect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color);
	void PaintBrush(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FSlateBrush* Brush, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color);
	/** Rectangle outline of the given thickness. */
	void PaintFrame(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color, float Thickness);
	void PaintLine(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& A, const FVector2f& B, const FLinearColor& Color, float Thickness);
	FVector2f MeasureText(const FString& Text, const FSlateFontInfo& Font);
	/** Draws text with its top-left corner at Pos. Returns the text size. */
	FVector2f PaintText(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FString& Text, const FSlateFontInfo& Font, const FVector2f& Pos, const FLinearColor& Color, bool bShadow = true);
	/** Draws text centred on Center. Returns the text size. */
	FVector2f PaintTextCentered(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FString& Text, const FSlateFontInfo& Font, const FVector2f& Center, const FLinearColor& Color, bool bShadow = true);

	// --- Animation helpers --------------------------------------------------------
	/** Smooth 0..1 ramp. */
	float Ease(float T);
	/** 0..1 pulse at the given frequency (Hz), from the platform clock. */
	float Pulse(float Hz);
}
