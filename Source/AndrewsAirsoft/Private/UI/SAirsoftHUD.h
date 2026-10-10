// Andrew's Airsoft - in-game HUD widgets.
//   SAirsoftHUD          layout of all text panels (STextBlocks bound to live lambdas)
//   SAirsoftHUDCanvas    everything that is simpler to paint: crosshair, hit marker,
//                        scope, name tags, XP popups, capture bar, letterbox
//   SAirsoftObjectiveBadge  one Domination point (A/B/C) under the timer

#pragma once

#include "CoreMinimal.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "Styling/SlateBrush.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SLeafWidget.h"

class AAirsoftPlayerController;
class AAirsoftObjective;
struct FAirsoftKillFeedEntry;

namespace AirsoftHUDShared
{
	/** True when gameplay HUD elements should hide: main menu map, a menu or the summary is open, or the final-tag replay runs. */
	bool IsGameplayHidden(const AAirsoftPlayerController* PC);
}

class SAirsoftHUDCanvas : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftHUDCanvas) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	void PaintScope(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintTaggedShade(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintNameTags(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintCrosshair(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintHitMarker(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintXPPopups(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintCaptureBar(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	/** VIP: the marker over the VIP (teammates always, enemies when in sight), the extraction marker and its progress bar. */
	void PaintVIP(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;
	void PaintReplay(AAirsoftPlayerController* PC, FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Size) const;

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;

	/** Circle-with-a-hole masks for the sniper scope (rounded boxes, radius = half height). */
	FSlateBrush ScopeMask;
	FSlateBrush ScopeRings[4];
};

class SAirsoftObjectiveBadge : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftObjectiveBadge) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC, int32 InIndex);

	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
		FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

	/** The objective this badge shows, if it exists and is active in Domination. */
	AAirsoftObjective* GetObjective() const;

private:
	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
	int32 Index = 0;
};

class SAirsoftHUD : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftHUD) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

private:
	TSharedRef<SWidget> BuildTopCenter();
	TSharedRef<SWidget> BuildTeamScore(uint8 TeamValue);
	/** Gun Game: "YOU" (level) or "LEADER" (name, level) box in place of a team score. */
	TSharedRef<SWidget> BuildFreeForAllBox(bool bLeader);
	TSharedRef<SWidget> BuildKillFeed();
	TSharedRef<SWidget> BuildKillFeedRow(int32 Row);
	TSharedRef<SWidget> BuildWeaponPanel();
	TSharedRef<SWidget> BuildAnnouncement();
	TSharedRef<SWidget> BuildTaggedOverlay();
	TSharedRef<SWidget> BuildBottomCenter();
	TSharedRef<SWidget> BuildVotePanel();
	TSharedRef<SWidget> BuildVoteRow(const FText& Label, const FText& Detail, TFunction<int32()> Count, TFunction<bool()> IsMine,
		TFunction<bool()> IsLeading, TFunction<bool()> IsDimmed);

	/** True when gameplay HUD elements should be hidden (menu, summary, replay, main menu map). */
	bool IsHidden() const;
	bool IsOut() const;
	/** Caption under the timer ("FIRST TO 40", "ROUND 3 · FIRST TO 5", "LEVEL 4 / 13"...). */
	FText PhaseCaption() const;
	/** Mode-specific line under the mode / map ("VIP: X · ESCORT TO EXTRACT", "NEXT GUN: ..."), empty for none. */
	FString ModeLine() const;
	float AnnouncementAlpha() const;
	const FAirsoftKillFeedEntry* FeedEntry(int32 Row) const;
	float FeedAlpha(int32 Row) const;

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
};
