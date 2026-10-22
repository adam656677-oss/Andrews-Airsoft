// Andrew's Airsoft - settings: controls, key bindings, gameplay, camera, video, audio,
// accessibility (and host bots when multiplayer is on). Changes apply through
// UAirsoftGameInstance::SetUserSettings when a slider is released, a choice is
// clicked, a key is bound, or (keyboard/gamepad nudges) shortly after the last change.

#include "AirsoftGameInstance.h"
#include "AirsoftKeyBindings.h"
#include "AirsoftPlayerController.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "HAL/PlatformTime.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

class SAirsoftSettings : public SAirsoftMenuBase
{
public:
	SLATE_BEGIN_ARGS(SAirsoftSettings) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;
	/** While a key binding waits for a key, the next key or mouse button goes to it (Esc cancels). */
	virtual FReply OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual FReply OnPreviewMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;

protected:
	virtual void HandleBack() override;

private:
	TSharedRef<SWidget> Row(const FString& Label, const FString& Note, const TSharedRef<SWidget>& Control, const TAttribute<FText>& Value);
	TSharedRef<SWidget> SliderRow(const FString& Label, const FString& Note, float FAirsoftUserSettings::* Field,
		float Min, float Max, float Snap, TFunction<FString(float)> Format);
	TSharedRef<SWidget> ChoiceRow(const FString& Label, const FString& Note, const TArray<FString>& Options,
		TFunction<int32()> Get, TFunction<void(int32)> Set);
	TSharedRef<SWidget> Section(const FString& Title);
	/** One rebindable control: its name, and a key cap that waits for a new key when clicked. */
	TSharedRef<SWidget> BindingRow(const AirsoftKeyBindings::FSlot& Slot);
	/** Bind the waiting slot to Key (a key another control used swaps over). */
	void FinishCapture(const FKey& Key);

	void MarkDirty();
	/** Push the edited fields to the game instance (keeps fields this screen doesn't edit, e.g. call sign). */
	void Apply();
	bool AnySliderDragging() const;

	FAirsoftUserSettings Working;
	bool bDirty = false;
	double LastChange = 0.0;
	TArray<TSharedPtr<SAirsoftSlider>> Sliders;
	/** The binding waiting for a key, or None. */
	FName CapturingSlot;
	/** Shown under the bindings after a refused key ("ESC is the menu key"). */
	FString BindingMessage;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateSettings(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftSettings, PC);
}

void SAirsoftSettings::MarkDirty()
{
	bDirty = true;
	LastChange = FPlatformTime::Seconds();
}

void SAirsoftSettings::Apply()
{
	bDirty = false;
	UAirsoftGameInstance* GI = AUI::GetGameInstance(WeakPC.Get());
	if (!GI)
	{
		return;
	}
	FAirsoftUserSettings Settings = GI->GetUserSettings();
	Settings.Sensitivity = Working.Sensitivity;
	Settings.AimSensitivity = Working.AimSensitivity;
	Settings.FieldOfView = Working.FieldOfView;
	Settings.bToggleAim = Working.bToggleAim;
	Settings.bInvertY = Working.bInvertY;
	Settings.bThirdPersonMatches = Working.bThirdPersonMatches;
	Settings.bThirdPersonStory = Working.bThirdPersonStory;
	Settings.bLeftShoulder = Working.bLeftShoulder;
	Settings.Quality = Working.Quality;
	Settings.RenderScale = Working.RenderScale;
	Settings.WindowMode = Working.WindowMode;
	Settings.MasterVolume = Working.MasterVolume;
	Settings.bCinematicGunSounds = Working.bCinematicGunSounds;
	Settings.bCinematicEffects = Working.bCinematicEffects;
	Settings.bScreenShake = Working.bScreenShake;
	Settings.bSubtitles = Working.bSubtitles;
	Settings.BotFill = Working.BotFill;
	Settings.BotSkill = Working.BotSkill;
	Settings.Difficulty = Working.Difficulty;
	Settings.ColorblindMode = Working.ColorblindMode;
	Settings.bSubtitles = Working.bSubtitles;
	Settings.KeyBindings = Working.KeyBindings;
	GI->SetUserSettings(Settings);
}

FReply SAirsoftSettings::OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	if (CapturingSlot.IsNone())
	{
		return SAirsoftMenuBase::OnPreviewKeyDown(MyGeometry, InKeyEvent);
	}
	const FKey Key = InKeyEvent.GetKey();
	if (Key == EKeys::Escape || Key == EKeys::Gamepad_FaceButton_Right)
	{
		CapturingSlot = NAME_None;
		BindingMessage.Reset();
		return FReply::Handled();
	}
	FinishCapture(Key);
	return FReply::Handled();
}

FReply SAirsoftSettings::OnPreviewMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (CapturingSlot.IsNone())
	{
		return SAirsoftMenuBase::OnPreviewMouseButtonDown(MyGeometry, MouseEvent);
	}
	FinishCapture(MouseEvent.GetEffectingButton());
	return FReply::Handled();
}

void SAirsoftSettings::FinishCapture(const FKey& Key)
{
	if (Key.IsGamepadKey())
	{
		// Gamepad buttons keep their own layout; a pad press just cancels.
		CapturingSlot = NAME_None;
		BindingMessage.Reset();
		return;
	}
	if (!AirsoftKeyBindings::CanBind(Key))
	{
		BindingMessage = FString::Printf(TEXT("%s is kept for the menu or the weapon swap. Pick another key, or Esc to cancel."),
			*AirsoftKeyBindings::KeyLabel(Key));
		return;
	}
	const FName Id = CapturingSlot;
	CapturingSlot = NAME_None;
	BindingMessage.Reset();
	AirsoftKeyBindings::Rebind(Working, Id, Key);
	Apply();
}

TSharedRef<SWidget> SAirsoftSettings::BindingRow(const AirsoftKeyBindings::FSlot& Slot)
{
	const FName Id = Slot.Id;
	const FKey Default = Slot.Default;
	return Row(Slot.Label, FString(),
		SNew(SBox)
		.WidthOverride(200.f)
		.HAlign(HAlign_Left)
		[
			SNew(SAirsoftButton)
			.FontSize(11)
			.HAlign(HAlign_Center)
			.ShowEdge(false)
			.ContentPadding(FMargin(8.f, 7.f))
			.IsSelected_Lambda([this, Id]() { return CapturingSlot == Id; })
			.Text_Lambda([this, Id]()
			{
				if (CapturingSlot == Id)
				{
					return FText::FromString(TEXT("PRESS A KEY…"));
				}
				return FText::FromString(AirsoftKeyBindings::KeyLabel(AirsoftKeyBindings::KeyFor(Working, Id)));
			})
			.OnClicked_Lambda([this, Id]()
			{
				CapturingSlot = Id;
				BindingMessage.Reset();
				return FReply::Handled();
			})
		],
		TAttribute<FText>::CreateLambda([this, Id, Default]()
		{
			// A rebound control shows its default on the right.
			const FKey Now = AirsoftKeyBindings::KeyFor(Working, Id);
			return Now == Default ? FText::GetEmpty() : FText::FromString(AirsoftKeyBindings::KeyLabel(Default));
		}));
}


bool SAirsoftSettings::AnySliderDragging() const
{
	for (const TSharedPtr<SAirsoftSlider>& Slider : Sliders)
	{
		if (Slider.IsValid() && Slider->IsDragging())
		{
			return true;
		}
	}
	return false;
}

void SAirsoftSettings::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	SAirsoftMenuBase::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
	if (bDirty && FPlatformTime::Seconds() - LastChange > 0.6 && !AnySliderDragging())
	{
		Apply();
	}
}

void SAirsoftSettings::HandleBack()
{
	if (bDirty)
	{
		Apply();
	}
	ReturnToParentMenu();
}

TSharedRef<SWidget> SAirsoftSettings::Section(const FString& Title)
{
	return SNew(SBox)
		.Padding(FMargin(0.f, 22.f, 0.f, 10.f))
		[
			AirsoftUIWidgets::SectionLabel(FText::FromString(Title))
		];
}

TSharedRef<SWidget> SAirsoftSettings::Row(const FString& Label, const FString& Note, const TSharedRef<SWidget>& Control, const TAttribute<FText>& Value)
{
	return SNew(SBorder)
		.BorderImage(AUI::RoundedBrush())
		.BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.38f))
		.Padding(FMargin(18.f, 11.f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(300.f)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(AUI::Upper(Label))
						.Font(AUI::Font(AUI::EFontWeight::Bold, 12, 160))
						.ColorAndOpacity(AUI::TextColor())
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.f, 3.f, 12.f, 0.f))
					[
						SNew(STextBlock)
						.Visibility(Note.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible)
						.AutoWrapText(true)
						.Text(FText::FromString(Note))
						.Font(AUI::Font(AUI::EFontWeight::Regular, 9, 20))
						.ColorAndOpacity(AUI::TextDim())
					]
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.f)
			.VAlign(VAlign_Center)
			.Padding(FMargin(20.f, 0.f))
			[
				Control
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(80.f)
				.Visibility(Value.IsSet() ? EVisibility::HitTestInvisible : EVisibility::Collapsed)
				[
					SNew(STextBlock)
					.Text(Value)
					.Justification(ETextJustify::Right)
					.Font(AUI::Font(AUI::EFontWeight::Bold, 13, 40))
					.ColorAndOpacity(AUI::Accent())
				]
			]
		];
}

TSharedRef<SWidget> SAirsoftSettings::SliderRow(const FString& Label, const FString& Note, float FAirsoftUserSettings::* Field,
	float Min, float Max, float Snap, TFunction<FString(float)> Format)
{
	const float Range = FMath::Max(Max - Min, 0.0001f);
	TSharedPtr<SAirsoftSlider> Slider;
	TSharedRef<SWidget> Control = SAssignNew(Slider, SAirsoftSlider)
		.Width(360.f)
		.Step(Snap / Range)
		.Value_Lambda([this, Field, Min, Range]()
		{
			return FMath::Clamp((Working.*Field - Min) / Range, 0.f, 1.f);
		})
		.OnValueChanged_Lambda([this, Field, Min, Max, Range, Snap](float Normalized)
		{
			const float Raw = Min + FMath::Clamp(Normalized, 0.f, 1.f) * Range;
			Working.*Field = FMath::Clamp(FMath::GridSnap(Raw, Snap), Min, Max);
			MarkDirty();
		})
		.OnCommit_Lambda([this]()
		{
			Apply();
		});
	Sliders.Add(Slider);
	if (!InitialFocus.IsValid())
	{
		SetInitialFocusWidget(Slider);
	}
	return Row(Label, Note, Control, TAttribute<FText>::CreateLambda([this, Field, Format]()
	{
		return FText::FromString(Format(Working.*Field));
	}));
}

TSharedRef<SWidget> SAirsoftSettings::ChoiceRow(const FString& Label, const FString& Note, const TArray<FString>& Options,
	TFunction<int32()> Get, TFunction<void(int32)> Set)
{
	TSharedRef<SHorizontalBox> Box = SNew(SHorizontalBox);
	for (int32 i = 0; i < Options.Num(); ++i)
	{
		Box->AddSlot()
		.FillWidth(1.f)
		.Padding(FMargin(i > 0 ? 4.f : 0.f, 0.f, 0.f, 0.f))
		[
			SNew(SAirsoftButton)
			.Text(FText::FromString(Options[i]))
			.FontSize(11)
			.HAlign(HAlign_Center)
			.ShowEdge(false)
			.ContentPadding(FMargin(8.f, 7.f))
			.IsSelected_Lambda([Get, i]() { return Get() == i; })
			.OnClicked_Lambda([this, Set, i]()
			{
				Set(i);
				Apply();
				return FReply::Handled();
			})
		];
	}
	// Spread the choices over the whole control column: sized to their text they clipped the last letters.
	return Row(Label, Note, SNew(SBox).MinDesiredWidth(360.f)[Box], TAttribute<FText>());
}

void SAirsoftSettings::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	OpenTime = FPlatformTime::Seconds();
	ForceVolatile(true);
	if (UAirsoftGameInstance* GI = AUI::GetGameInstance(InPC))
	{
		Working = GI->GetUserSettings();
	}

	auto TwoDecimals = [](float V) { return FString::Printf(TEXT("%.2f"), V); };
	auto Percent = [](float V) { return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(V)); };

	TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
	Rows->AddSlot().AutoHeight()[Section(TEXT("CONTROLS"))];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		SliderRow(TEXT("Mouse sensitivity"), FString(), &FAirsoftUserSettings::Sensitivity, 0.1f, 3.f, 0.05f, TwoDecimals)
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		SliderRow(TEXT("Aim sensitivity"), TEXT("Multiplier while aiming down sights."), &FAirsoftUserSettings::AimSensitivity, 0.2f, 1.5f, 0.05f, TwoDecimals)
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		SliderRow(TEXT("Field of view"), TEXT("Horizontal, in degrees."), &FAirsoftUserSettings::FieldOfView, 70.f, 110.f, 1.f,
			[](float V) { return FString::Printf(TEXT("%d\u00B0"), FMath::RoundToInt(V)); })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Aim mode"), FString(), { TEXT("HOLD"), TEXT("TOGGLE") },
			[this]() { return Working.bToggleAim ? 1 : 0; },
			[this](int32 Index) { Working.bToggleAim = Index == 1; })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Invert Y"), FString(), { TEXT("OFF"), TEXT("ON") },
			[this]() { return Working.bInvertY ? 1 : 0; },
			[this](int32 Index) { Working.bInvertY = Index == 1; })
	];

	Rows->AddSlot().AutoHeight()[Section(TEXT("KEY BINDINGS"))];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 8.f))
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.f)
		.VAlign(VAlign_Center)
		[
			SNew(STextBlock)
			.AutoWrapText(true)
			.Text(FText::FromString(TEXT("Click a key, then press the new key or mouse button. A key another control used swaps over. Esc cancels. Gamepad buttons stay as they are.")))
			.Font(AUI::Font(AUI::EFontWeight::Regular, 9, 20))
			.ColorAndOpacity(AUI::TextDim())
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(16.f, 0.f, 0.f, 0.f))
		[
			SNew(SBox)
			.WidthOverride(200.f)
			[
				SNew(SAirsoftButton)
				.Text(FText::FromString(TEXT("RESET TO DEFAULTS")))
				.FontSize(11)
				.HAlign(HAlign_Center)
				.ShowEdge(false)
				.ContentPadding(FMargin(8.f, 7.f))
				.IsDimmed_Lambda([this]() { return Working.KeyBindings.Num() == 0; })
				.OnClicked_Lambda([this]()
				{
					CapturingSlot = NAME_None;
					BindingMessage.Reset();
					Working.KeyBindings.Empty();
					Apply();
					return FReply::Handled();
				})
			]
		]
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 8.f))
	[
		SNew(STextBlock)
		.AutoWrapText(true)
		.Visibility_Lambda([this]() { return BindingMessage.IsEmpty() ? EVisibility::Collapsed : EVisibility::HitTestInvisible; })
		.Text_Lambda([this]() { return FText::FromString(BindingMessage); })
		.Font(AUI::Font(AUI::EFontWeight::Regular, 11, 20))
		.ColorAndOpacity(AUI::Accent())
	];
	{
		FString LastGroup;
		for (const AirsoftKeyBindings::FSlot& Slot : AirsoftKeyBindings::Slots())
		{
			if (Slot.Group != LastGroup)
			{
				LastGroup = Slot.Group;
				Rows->AddSlot().AutoHeight().Padding(FMargin(2.f, 10.f, 0.f, 6.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(Slot.Group))
					.Font(AUI::Caption(8))
					.ColorAndOpacity(AUI::TextDim())
				];
			}
			Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
			[
				BindingRow(Slot)
			];
		}
	}

	Rows->AddSlot().AutoHeight()[Section(TEXT("GAMEPLAY"))];
	{
		TArray<FString> DifficultyOptions;
		for (int32 i = 0; i < AirsoftDifficulty::Num; ++i)
		{
			DifficultyOptions.Add(AirsoftDifficulty::Label(AirsoftDifficulty::FromIndex(i)));
		}
		Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
		[
			ChoiceRow(TEXT("Difficulty"), TEXT("Story and skirmish enemies: reaction time, aim and how hard they hit. Changes apply straight away."),
				DifficultyOptions,
				[this]() { return FMath::Clamp(Working.Difficulty, 0, AirsoftDifficulty::Num - 1); },
				[this](int32 Index)
				{
					Working.Difficulty = FMath::Clamp(Index, 0, AirsoftDifficulty::Num - 1);
					// The campaign referee reads the bot skill for its enemies; keep the two in step.
					Working.BotSkill = static_cast<int32>(AirsoftDifficulty::BotSkill(AirsoftDifficulty::FromIndex(Working.Difficulty)));
				})
		];
	}

	Rows->AddSlot().AutoHeight()[Section(TEXT("CAMERA"))];

	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Camera · matches"), TEXT("Airsoft matches. First person is the airsoft view; F5 switches in game."),
			{ TEXT("FIRST PERSON"), TEXT("THIRD PERSON") },
			[this]() { return Working.bThirdPersonMatches ? 1 : 0; },
			[this](int32 Index) { Working.bThirdPersonMatches = Index == 1; })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Camera · story"), TEXT("Last Contract. Aiming always goes to the sights; F5 switches in game."),
			{ TEXT("FIRST PERSON"), TEXT("THIRD PERSON") },
			[this]() { return Working.bThirdPersonStory ? 1 : 0; },
			[this](int32 Index) { Working.bThirdPersonStory = Index == 1; })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Shoulder"), TEXT("Third person: which shoulder the camera looks over. X swaps in game."),
			{ TEXT("RIGHT"), TEXT("LEFT") },
			[this]() { return Working.bLeftShoulder ? 1 : 0; },
			[this](int32 Index) { Working.bLeftShoulder = Index == 1; })
	];

	Rows->AddSlot().AutoHeight()[Section(TEXT("VIDEO"))];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Window"), TEXT("Window has a title bar to minimise or close the game. Alt+Enter switches too."),
			{ TEXT("WINDOW"), TEXT("BORDERLESS"), TEXT("FULLSCREEN") },
			[this]() { return FMath::Clamp(Working.WindowMode, 0, 2); },
			[this](int32 Index) { Working.WindowMode = FMath::Clamp(Index, 0, 2); })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Graphics quality"), TEXT("Engine scalability preset."), { TEXT("LOW"), TEXT("MEDIUM"), TEXT("HIGH"), TEXT("EPIC") },
			[this]() { return FMath::Clamp(Working.Quality, 0, 3); },
			[this](int32 Index) { Working.Quality = FMath::Clamp(Index, 0, 3); })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		SliderRow(TEXT("Render scale"), TEXT("TSR upscales to your monitor; 60 % recommended on RTX 2070 at 4K"),
			&FAirsoftUserSettings::RenderScale, 50.f, 100.f, 1.f, Percent)
	];

	Rows->AddSlot().AutoHeight()[Section(TEXT("AUDIO"))];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		SliderRow(TEXT("Master volume"), FString(), &FAirsoftUserSettings::MasterVolume, 0.f, 1.f, 0.01f,
			[](float V) { return FString::Printf(TEXT("%d%%"), FMath::RoundToInt(V * 100.f)); })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Gun sounds"), TEXT("Cinematic action-movie gunfire, or realistic airsoft mechanics."), { TEXT("CINEMATIC"), TEXT("AIRSOFT") },
			[this]() { return Working.bCinematicGunSounds ? 0 : 1; },
			[this](int32 Index) { Working.bCinematicGunSounds = Index == 0; })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Effects"), TEXT("Cinematic puffs, flashes and hit pulses, or airsoft-authentic (gas vapour only, no flashes)."), { TEXT("CINEMATIC"), TEXT("AIRSOFT") },
			[this]() { return Working.bCinematicEffects ? 0 : 1; },
			[this](int32 Index) { Working.bCinematicEffects = Index == 0; })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Screen shake"), TEXT("Camera shake from nearby grenades and when you are tagged."), { TEXT("ON"), TEXT("OFF") },
			[this]() { return Working.bScreenShake ? 0 : 1; },
			[this](int32 Index) { Working.bScreenShake = Index == 0; })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Subtitles"), TEXT("Story: the speaker and every spoken line at the bottom of the screen."), { TEXT("ON"), TEXT("OFF") },
			[this]() { return Working.bSubtitles ? 0 : 1; },
			[this](int32 Index) { Working.bSubtitles = Index == 0; })
	];

	Rows->AddSlot().AutoHeight()[Section(TEXT("ACCESSIBILITY"))];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Team colours"), TEXT("Colour-blind-safe sets: blue against yellow for red-green, red against cyan for blue-yellow. Covers the HUD, armbands, gear and objectives."),
			{ TEXT("STANDARD"), TEXT("RED-GREEN"), TEXT("BLUE-YELLOW") },
			[this]() { return FMath::Clamp(Working.ColorblindMode, 0, 2); },
			[this](int32 Index) { Working.ColorblindMode = FMath::Clamp(Index, 0, 2); })
	];
	Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
	[
		ChoiceRow(TEXT("Subtitles"), TEXT("Story voice lines with the speaker's name."), { TEXT("ON"), TEXT("OFF") },
			[this]() { return Working.bSubtitles ? 0 : 1; },
			[this](int32 Index) { Working.bSubtitles = Index == 0; })
	];

	// Host-side: only the host's choice matters (the match runs on their PC). Skirmish picks its own
	// bots, so these rows only show when multiplayer is switched on.
	const bool bMultiplayer = UAirsoftSettings::IsMultiplayerEnabled();
	TArray<FString> FillOptions;

	for (int32 i = 0; i < AirsoftBots::NumFillOptions; ++i)
	{
		FillOptions.Add(AirsoftBots::FillLabel(i));
	}
	TArray<FString> SkillOptions;
	for (int32 i = 0; i < AirsoftBots::NumSkillOptions; ++i)
	{
		SkillOptions.Add(AirsoftBots::SkillLabel(i));
	}
	if (bMultiplayer)
	{
		Rows->AddSlot().AutoHeight()[Section(TEXT("HOST  \u00B7  BOTS"))];
		Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
		[
			ChoiceRow(TEXT("Bots"), TEXT("When you host: computer players fill both teams on match maps, and step aside as friends join. Never counted for the lobby vote."),
				FillOptions,
				[this]() { return FMath::Clamp(Working.BotFill, 0, AirsoftBots::NumFillOptions - 1); },
				[this](int32 Index) { Working.BotFill = FMath::Clamp(Index, 0, AirsoftBots::NumFillOptions - 1); })
		];
		Rows->AddSlot().AutoHeight().Padding(FMargin(0.f, 0.f, 0.f, 4.f))
		[
			ChoiceRow(TEXT("Bot skill"), TEXT("Reaction time, aim and awareness. Changes apply to bots already in a match."),
				SkillOptions,
				[this]() { return FMath::Clamp(Working.BotSkill, 0, AirsoftBots::NumSkillOptions - 1); },
				[this](int32 Index) { Working.BotSkill = FMath::Clamp(Index, 0, AirsoftBots::NumSkillOptions - 1); })
		];
	}

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SAirsoftBackdrop)
			.Opacity(0.86f)
			.ColumnWidth(0.62f)
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Left)
		.Padding(FMargin(110.f, 80.f, 110.f, 50.f))
		[
			SNew(SBox)
			.WidthOverride(900.f)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					AirsoftUIWidgets::SectionLabel(FText::FromString(TEXT("SYSTEM")))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 12.f, 0.f, 4.f))
				[
					SNew(STextBlock)
					.Text(FText::FromString(TEXT("SETTINGS")))
					.Font(AUI::Font(AUI::EFontWeight::Bold, 40, 240))
					.ColorAndOpacity(FLinearColor::White)
				]
				+ SVerticalBox::Slot()
				.FillHeight(1.f)
				[
					SNew(SScrollBox)
					+ SScrollBox::Slot()
					.Padding(FMargin(0.f, 0.f, 12.f, 0.f))
					[
						Rows
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.f, 18.f, 0.f, 0.f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					[
						SNew(SBox)
						.WidthOverride(220.f)
						[
							SNew(SAirsoftButton)
							.Text(FText::FromString(TEXT("BACK")))
							.FontSize(13)
							.OnClicked_Lambda([this]()
							{
								HandleBack();
								return FReply::Handled();
							})
						]
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					.Padding(FMargin(24.f, 0.f, 0.f, 0.f))
					[
						AirsoftUIWidgets::Hint(FText::FromString(TEXT("ESC")), FText::FromString(TEXT("BACK")))
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					[
						AirsoftUIWidgets::Hint(FText::FromString(TEXT("LEFT / RIGHT")), FText::FromString(TEXT("ADJUST")))
					]
				]
			]
		]
	];
}
