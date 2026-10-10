// Andrew's Airsoft - text chat: the fading message box the HUD shows bottom
// left, and the typing line that opens with Enter (everyone) or Y (team).
// While the line is open the controller switches to UI-only input, so nothing
// typed reaches gameplay; Enter sends, Tab flips everyone/team, Esc cancels.

#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSettings.h"
#include "AirsoftUIScreens.h"
#include "AirsoftUIStyle.h"
#include "AirsoftUIWidgets.h"
#include "Input/Events.h"
#include "Input/Reply.h"
#include "InputCoreTypes.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Text/STextBlock.h"

namespace AUI = AirsoftUIStyle;

namespace AirsoftChatLocal
{
	constexpr int32 BoxRows = 8;
	/** Seconds a line stays fully visible, then fades over LineFade (always visible while typing). */
	constexpr float LineLife = 10.f;
	constexpr float LineFade = 1.5f;
	constexpr float BoxWidth = 520.f;
}

// ---------------------------------------------------------------------------
// The typing line
// ---------------------------------------------------------------------------

class SAirsoftChatInput : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftChatInput) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnFocusReceived(const FGeometry& MyGeometry, const FFocusEvent& InFocusEvent) override;
	/** Escape and Tab are caught here, before the text box sees them. */
	virtual FReply OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;

private:
	bool IsTeam() const;

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
	TSharedPtr<SEditableTextBox> TextBox;
	int32 MaxLength = 120;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateChatInput(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftChatInput, PC);
}

bool SAirsoftChatInput::IsTeam() const
{
	const AAirsoftPlayerController* PC = WeakPC.Get();
	return PC && PC->IsTeamChat();
}

void SAirsoftChatInput::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	MaxLength = FMath::Max(UAirsoftSettings::Get()->ChatMaxLength, 8);

	ChildSlot
	.HAlign(HAlign_Left)
	.VAlign(VAlign_Bottom)
	.Padding(FMargin(32.f, 0.f, 0.f, 150.f))
	[
		SNew(SBox)
		.WidthOverride(AirsoftChatLocal::BoxWidth + 40.f)
		[
			SNew(SBorder)
			.BorderImage(AUI::PanelSolidBrush())
			.Padding(FMargin(8.f, 6.f))
			[
				SNew(SHorizontalBox)
				// Channel chip: ALL in amber, TEAM in the team colour.
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.f, 0.f, 8.f, 0.f))
				[
					SNew(SBorder)
					.BorderImage(AUI::RoundedBrush())
					.Padding(FMargin(8.f, 3.f))
					.BorderBackgroundColor_Lambda([this]() -> FSlateColor
					{
						if (IsTeam())
						{
							const AAirsoftPlayerState* PS = AUI::GetPlayerState(WeakPC.Get());
							return PS && PS->Team != EAirsoftTeam::None ? AUI::TeamColor(PS->Team) : AUI::Accent();
						}
						return AUI::Accent();
					})
					[
						SNew(STextBlock)
						.Font(AUI::Font(AUI::EFontWeight::Bold, 9, 200))
						.ColorAndOpacity(FLinearColor(0.02f, 0.02f, 0.02f))
						.Text_Lambda([this]() { return FText::FromString(IsTeam() ? TEXT("TEAM") : TEXT("ALL")); })
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.f)
				.VAlign(VAlign_Center)
				[
					SAssignNew(TextBox, SEditableTextBox)
					.Style(&AUI::TextBoxStyle())
					.Font(AUI::Font(AUI::EFontWeight::Regular, 12, 20))
					.ForegroundColor(AUI::TextColor())
					.BackgroundColor(FLinearColor::White)
					.HintText(FText::FromString(TEXT("Say something   ·   Enter send   ·   Tab team / all   ·   Esc cancel")))
					.SelectAllTextWhenFocused(false)
					.ClearKeyboardFocusOnCommit(false)
					.OnTextChanged_Lambda([this](const FText& NewText)
					{
						// Keep the line within what the host accepts.
						const FString Current = NewText.ToString();
						if (Current.Len() > MaxLength && TextBox.IsValid())
						{
							TextBox->SetText(FText::FromString(Current.Left(MaxLength)));
						}
					})
					.OnTextCommitted_Lambda([this](const FText& NewText, ETextCommit::Type CommitType)
					{
						AAirsoftPlayerController* PC = WeakPC.Get();
						if (!PC)
						{
							return;
						}
						if (CommitType == ETextCommit::OnEnter)
						{
							PC->SubmitChat(NewText.ToString());
						}
						else if (CommitType == ETextCommit::OnCleared)
						{
							PC->CloseChat();
						}
						// OnUserMovedFocus: the controller puts focus straight back on the line.
					})
				]
			]
		]
	];
}

FReply SAirsoftChatInput::OnFocusReceived(const FGeometry& MyGeometry, const FFocusEvent& InFocusEvent)
{
	if (TextBox.IsValid())
	{
		return FReply::Handled().SetUserFocus(TextBox.ToSharedRef(), EFocusCause::SetDirectly);
	}
	return SCompoundWidget::OnFocusReceived(MyGeometry, InFocusEvent);
}

FReply SAirsoftChatInput::OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	const FKey Key = InKeyEvent.GetKey();
	if (Key == EKeys::Escape)
	{
		if (AAirsoftPlayerController* PC = WeakPC.Get())
		{
			PC->CloseChat();
		}
		return FReply::Handled();
	}
	if (Key == EKeys::Tab)
	{
		if (AAirsoftPlayerController* PC = WeakPC.Get())
		{
			PC->ToggleChatChannel();
		}
		return FReply::Handled();
	}
	return SCompoundWidget::OnPreviewKeyDown(MyGeometry, InKeyEvent);
}

// ---------------------------------------------------------------------------
// The message box (part of the HUD)
// ---------------------------------------------------------------------------

class SAirsoftChatBox : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SAirsoftChatBox) {}
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC);

private:
	/** Row 0 is the oldest line shown, BoxRows - 1 the newest. */
	const FAirsoftChatEntry* EntryForRow(int32 Row) const;
	float RowAlpha(int32 Row) const;
	TSharedRef<SWidget> BuildRow(int32 Row);

	TWeakObjectPtr<AAirsoftPlayerController> WeakPC;
};

TSharedRef<SWidget> AirsoftUIScreens::CreateChatBox(AAirsoftPlayerController* PC)
{
	return SNew(SAirsoftChatBox, PC);
}

const FAirsoftChatEntry* SAirsoftChatBox::EntryForRow(int32 Row) const
{
	const AAirsoftPlayerController* PC = WeakPC.Get();
	if (!PC)
	{
		return nullptr;
	}
	const TArray<FAirsoftChatEntry>& Log = PC->GetChatLog();
	const int32 Index = Log.Num() - AirsoftChatLocal::BoxRows + Row;
	return Log.IsValidIndex(Index) ? &Log[Index] : nullptr;
}

float SAirsoftChatBox::RowAlpha(int32 Row) const
{
	const AAirsoftPlayerController* PC = WeakPC.Get();
	const FAirsoftChatEntry* Entry = EntryForRow(Row);
	if (!PC || !Entry)
	{
		return 0.f;
	}
	if (PC->IsChatOpen())
	{
		return 1.f;
	}
	const float Age = static_cast<float>(AUI::HudNow(PC) - Entry->Time);
	return 1.f - AUI::Ease((Age - AirsoftChatLocal::LineLife) / AirsoftChatLocal::LineFade);
}

TSharedRef<SWidget> SAirsoftChatBox::BuildRow(int32 Row)
{
	return SNew(SBorder)
		.BorderImage(AUI::RoundedBrush())
		.Padding(FMargin(8.f, 3.f))
		.Visibility_Lambda([this, Row]() -> EVisibility { return RowAlpha(Row) > 0.01f ? EVisibility::HitTestInvisible : EVisibility::Collapsed; })
		.BorderBackgroundColor_Lambda([this, Row]() -> FSlateColor { return FLinearColor(0.f, 0.f, 0.f, 0.45f * RowAlpha(Row)); })
		.ColorAndOpacity_Lambda([this, Row]() -> FLinearColor { return FLinearColor(1.f, 1.f, 1.f, RowAlpha(Row)); })
		[
			SNew(SHorizontalBox)
			// "[TEAM] Call Sign: " in the sender's team colour (system lines have no sender).
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			[
				SNew(STextBlock)
				.Font(AUI::Font(AUI::EFontWeight::Bold, 10, 40))
				.Visibility_Lambda([this, Row]() -> EVisibility
				{
					const FAirsoftChatEntry* Entry = EntryForRow(Row);
					return (Entry && Entry->Kind != EAirsoftChatKind::System) ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
				})
				.Text_Lambda([this, Row]()
				{
					const FAirsoftChatEntry* Entry = EntryForRow(Row);
					if (!Entry)
					{
						return FText::GetEmpty();
					}
					return FText::FromString(FString::Printf(TEXT("%s%s: "), Entry->Kind == EAirsoftChatKind::Team ? TEXT("[TEAM] ") : TEXT(""), *Entry->Sender));
				})
				.ColorAndOpacity_Lambda([this, Row]() -> FSlateColor
				{
					const FAirsoftChatEntry* Entry = EntryForRow(Row);
					return Entry ? AUI::TeamColor(Entry->SenderTeam) : AUI::TextColor();
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			[
				SNew(STextBlock)
				.WrapTextAt(AirsoftChatLocal::BoxWidth - 120.f)
				.Font(AUI::Font(AUI::EFontWeight::Regular, 10, 20))
				.Text_Lambda([this, Row]()
				{
					const FAirsoftChatEntry* Entry = EntryForRow(Row);
					if (!Entry)
					{
						return FText::GetEmpty();
					}
					return FText::FromString(Entry->Kind == EAirsoftChatKind::System ? TEXT("· ") + Entry->Text : Entry->Text);
				})
				.ColorAndOpacity_Lambda([this, Row]() -> FSlateColor
				{
					const FAirsoftChatEntry* Entry = EntryForRow(Row);
					return (Entry && Entry->Kind == EAirsoftChatKind::System) ? AUI::Accent() : AUI::TextColor();
				})
			]
		];
}

void SAirsoftChatBox::Construct(const FArguments& InArgs, AAirsoftPlayerController* InPC)
{
	WeakPC = InPC;
	SetVisibility(EVisibility::HitTestInvisible);

	TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
	for (int32 Row = 0; Row < AirsoftChatLocal::BoxRows; ++Row)
	{
		Rows->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Left)
		.Padding(FMargin(0.f, 0.f, 0.f, 2.f))
		[
			BuildRow(Row)
		];
	}

	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(AirsoftChatLocal::BoxWidth)
		.Visibility_Lambda([this]() -> EVisibility
		{
			const AAirsoftPlayerController* PC = WeakPC.Get();
			const bool bShow = PC && !PC->IsMainMenu() && !PC->IsMenuOpen();
			return bShow ? EVisibility::HitTestInvisible : EVisibility::Collapsed;
		})
		[
			Rows
		]
	];
}
