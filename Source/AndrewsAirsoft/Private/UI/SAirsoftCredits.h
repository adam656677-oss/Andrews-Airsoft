// Andrew's Airsoft - end credits for "Last Contract": the screen fades to black and the
// credits (Campaign.json "Credits") roll up from the bottom. Fires OnFinished once the last
// line has left the screen (or when Finish() is called, e.g. the player skips).

#pragma once

#include "CoreMinimal.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class SAirsoftCredits : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftCredits)
		: _ScrollSpeed(55.f)
	{}
		/** Pixels per second (layout units). */
		SLATE_ARGUMENT(float, ScrollSpeed)
		SLATE_EVENT(FSimpleDelegate, OnFinished)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;

	/** Ends the roll now (fires OnFinished once). */
	void Finish();

private:
	TSharedRef<SWidget> BuildContent() const;

	TSharedPtr<SWidget> Content;
	FSimpleDelegate OnFinished;
	float ScrollSpeed = 55.f;
	float Elapsed = 0.f;
	float Offset = -1.f;
	bool bFinished = false;
};
