// Andrew's Airsoft - story subtitles: the last two spoken campaign lines, bottom centre,
// "SPEAKER  line" on a dark band so they read over rain and neon.
//
// The campaign referee pushes lines with AirsoftSubtitles::Show() as it plays each voice line.
// The story is single-player (referee and HUD share one process), so the lines live in a small
// process-wide queue rather than being replicated. Hidden when the player turns subtitles off
// (FAirsoftUserSettings::bSubtitles).

#pragma once

#include "CoreMinimal.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class APlayerController;

namespace AirsoftSubtitles
{
	/** Shows Text for Duration seconds (real time). Speaker may be empty (the narrator). */
	void Show(const FString& Speaker, const FString& Text, const FLinearColor& SpeakerColor, float Duration);
	/** Drops every line (map change, ending). */
	void Clear();
}

class SAirsoftSubtitles : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftSubtitles) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, APlayerController* InPC);

private:
	TSharedRef<SWidget> BuildRow(int32 Row);
	bool IsEnabled() const;

	TWeakObjectPtr<APlayerController> WeakPC;
};
