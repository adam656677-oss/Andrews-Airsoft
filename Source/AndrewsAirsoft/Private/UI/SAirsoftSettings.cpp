// Andrew's Airsoft - settings: controls, video, audio. Changes apply through
// UAirsoftGameInstance::SetUserSettings when a slider is released, a choice is
// clicked, or (keyboard/gamepad nudges) shortly after the last change.

#include "AirsoftGameInstance.h"
#include "AirsoftPlayerController.h"
#include "AirsoftSaveGame.h"
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

protected:
	virtual void HandleBack() override;

private:
	TSharedRef<SWidget> Row(const FString& Label, const FString& Note, const TSharedRef<SWidget>& Control, const TAttribute<FText>& Value);
	TSharedRef<SWidget> SliderRow(const FString& Label, const FString& Note, float FAirsoftUserSettings::* Field,
		float Min, float Max, float Snap, TFunction<FString(float)> Format);
	TSharedRef<SWidget> ChoiceRow(const FString& Label, const FString& Note, const TArray<FString>& Options,
		TFunction<int32()> Get, TFunction<void(int32)> Set);
	TSharedRef<SWidget> Section(const FString& Title);

	void MarkDirty();
	/** Push the edited fields to the game instance (keeps fields this screen doesn't edit, e.g. call sign). */
	void Apply();
	bool AnySliderDragging() const;

	FAirsoftUserSettings Working;
	bool bDirty = false;
	double LastChange = 0.0;
	TArray<TSharedPtr<SAirsoftSlider>> Sliders;
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
	Settings.Quality = Working.Quality;
	Settings.RenderScale = Working.RenderScale;
	Settings.MasterVolume = Working.MasterVolume;
	Settings.bCinematicGunSounds = Working.bCinematicGunSounds;
	GI->SetUserSettings(Settings);
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
	return Row(Label, Note, SNew(SBox).WidthOverride(360.f).HAlign(HAlign_Left)[Box], TAttribute<FText>());
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

	Rows->AddSlot().AutoHeight()[Section(TEXT("VIDEO"))];
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
