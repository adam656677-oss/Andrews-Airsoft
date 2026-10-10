#include "AirsoftPlayerController.h"

#include "AirsoftArmoryDisplay.h"
#include "AirsoftAssets.h"
#include "AirsoftBallistics.h"
#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameMode.h"
#include "AirsoftGameState.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftWeaponData.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/AudioComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/GameViewportClient.h"
#include "Engine/HitResult.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "InputAction.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "Kismet/GameplayStatics.h"
#include "TimerManager.h"
#include "UI/AirsoftUI.h"

namespace
{
	constexpr float MouseDegreesPerCount = 0.07f;
	constexpr float StickYawRate = 210.f;
	constexpr float StickPitchRate = 150.f;
	constexpr double ReplayLength = 4.6;
	constexpr double ReplayFireAt = 0.6;
	constexpr double ReplayFlight = 2.0;

	const FName IA_Move(TEXT("IA_Move"));
	const FName IA_LookMouse(TEXT("IA_LookMouse"));
	const FName IA_LookStick(TEXT("IA_LookStick"));
	const FName IA_Jump(TEXT("IA_Jump"));
	const FName IA_Sprint(TEXT("IA_Sprint"));
	const FName IA_SprintToggle(TEXT("IA_SprintToggle"));
	const FName IA_Crouch(TEXT("IA_Crouch"));
	const FName IA_CrouchHold(TEXT("IA_CrouchHold"));
	const FName IA_Fire(TEXT("IA_Fire"));
	const FName IA_Aim(TEXT("IA_Aim"));
	const FName IA_Reload(TEXT("IA_Reload"));
	const FName IA_Swap(TEXT("IA_Swap"));
	const FName IA_Primary(TEXT("IA_Primary"));
	const FName IA_Secondary(TEXT("IA_Secondary"));
	const FName IA_Grenade(TEXT("IA_Grenade"));
	const FName IA_FireMode(TEXT("IA_FireMode"));
	const FName IA_Light(TEXT("IA_Light"));
	const FName IA_Inspect(TEXT("IA_Inspect"));
	const FName IA_Interact(TEXT("IA_Interact"));
	const FName IA_LeanLeft(TEXT("IA_LeanLeft"));
	const FName IA_LeanRight(TEXT("IA_LeanRight"));
	const FName IA_Scoreboard(TEXT("IA_Scoreboard"));
	const FName IA_Menu(TEXT("IA_Menu"));
	const FName IA_Loadout(TEXT("IA_Loadout"));
	const FName IA_Vote1(TEXT("IA_Vote1"));
	const FName IA_Vote2(TEXT("IA_Vote2"));
	const FName IA_Vote3(TEXT("IA_Vote3"));
	const FName IA_Vote4(TEXT("IA_Vote4"));

	float StickCurve(float V)
	{
		return FMath::Sign(V) * FMath::Pow(FMath::Abs(V), 1.8f);
	}
}

AAirsoftPlayerController::AAirsoftPlayerController()
{
	bShowMouseCursor = false;
}

AAirsoftCharacter* AAirsoftPlayerController::GetAirsoftCharacter() const
{
	return Cast<AAirsoftCharacter>(GetPawn());
}

AAirsoftGameState* AAirsoftPlayerController::GetAirsoftGameState() const
{
	return GetWorld() ? GetWorld()->GetGameState<AAirsoftGameState>() : nullptr;
}

AAirsoftPlayerState* AAirsoftPlayerController::GetAirsoftPlayerState() const
{
	return GetPlayerState<AAirsoftPlayerState>();
}

bool AAirsoftPlayerController::IsHost() const
{
	return IsLocalController() && GetNetMode() != NM_Client;
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::BeginPlay()
{
	Super::BeginPlay();
	if (!IsLocalController())
	{
		return;
	}
	BuildInput();
	AddMappingContext();
	UIWorld = GetWorld();
	RebuildUI();
}

void AAirsoftPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (IsLocalController())
	{
		StopReplay();
		HideWidget(MenuWidget);
		HideWidget(ScoreboardWidget);
		HideWidget(SummaryWidget);
		HideWidget(HUDWidget);
	}
	Super::EndPlay(EndPlayReason);
}

void AAirsoftPlayerController::RebuildUI()
{
	HideWidget(MenuWidget);
	HideWidget(ScoreboardWidget);
	HideWidget(SummaryWidget);
	HideWidget(HUDWidget);
	OpenMenu = EAirsoftMenu::None;
	bScoreboard = false;
	InteractTarget.Reset();
	StopReplay();

	bMainMenu = GetWorld() && GetWorld()->GetAuthGameMode<AAirsoftMenuGameMode>() != nullptr;
	if (bMainMenu)
	{
		ShowMenu(EAirsoftMenu::MainMenu);
	}
	else
	{
		ShowWidget(HUDWidget, AirsoftUI::MakeHUD(this), 10);
		SendProfile();
	}
	RefreshInputMode();
}

void AAirsoftPlayerController::SendProfile()
{
	UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>();
	if (!GI)
	{
		return;
	}
	UAirsoftSaveGame* Profile = GI->GetProfile();
	ServerSetProfile(GI->GetPlayerName(), Profile ? Profile->XP : 0, Profile ? Profile->Loadout : AirsoftWeapons::DefaultLoadout());
}

void AAirsoftPlayerController::PushLoadoutToServer()
{
	if (!IsLocalController())
	{
		return;
	}
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		if (UAirsoftSaveGame* Profile = GI->GetProfile())
		{
			ServerSetLoadout(Profile->Loadout);
		}
	}
}

void AAirsoftPlayerController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);
}

void AAirsoftPlayerController::OnRep_Pawn()
{
	Super::OnRep_Pawn();
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::BuildInput()
{
	if (Mapping)
	{
		return;
	}
	Mapping = NewObject<UInputMappingContext>(this, TEXT("IMC_Airsoft"));

	auto MakeAction = [this](FName Name, EInputActionValueType Type)
	{
		UInputAction* Action = NewObject<UInputAction>(this, Name);
		Action->ValueType = Type;
		Actions.Add(Name, Action);
		return Action;
	};
	auto Map = [this](UInputAction* Action, const FKey& Key, TArray<UInputModifier*> Modifiers = {})
	{
		FEnhancedActionKeyMapping& M = Mapping->MapKey(Action, Key);
		for (UInputModifier* Modifier : Modifiers)
		{
			M.Modifiers.Add(Modifier);
		}
	};
	auto Negate = [this]()
	{
		return NewObject<UInputModifierNegate>(this);
	};
	auto ToY = [this]()
	{
		UInputModifierSwizzleAxis* Swizzle = NewObject<UInputModifierSwizzleAxis>(this);
		Swizzle->Order = EInputAxisSwizzle::YXZ;
		return Swizzle;
	};
	auto DeadZone = [this]()
	{
		UInputModifierDeadZone* Zone = NewObject<UInputModifierDeadZone>(this);
		Zone->LowerThreshold = 0.18f;
		Zone->UpperThreshold = 1.f;
		Zone->Type = EDeadZoneType::Radial;
		return Zone;
	};

	UInputAction* Move = MakeAction(IA_Move, EInputActionValueType::Axis2D);
	Map(Move, EKeys::W, { ToY() });
	Map(Move, EKeys::S, { ToY(), Negate() });
	Map(Move, EKeys::A, { Negate() });
	Map(Move, EKeys::D);
	Map(Move, EKeys::Gamepad_Left2D, { DeadZone() });

	Map(MakeAction(IA_LookMouse, EInputActionValueType::Axis2D), EKeys::Mouse2D);
	Map(MakeAction(IA_LookStick, EInputActionValueType::Axis2D), EKeys::Gamepad_Right2D, { DeadZone() });

	auto Button = [&](FName Name, std::initializer_list<FKey> Keys)
	{
		UInputAction* Action = MakeAction(Name, EInputActionValueType::Boolean);
		for (const FKey& Key : Keys)
		{
			Map(Action, Key);
		}
	};
	Button(IA_Jump, { EKeys::SpaceBar, EKeys::Gamepad_FaceButton_Bottom });
	Button(IA_Sprint, { EKeys::LeftShift });
	Button(IA_SprintToggle, { EKeys::Gamepad_LeftThumbstick });
	Button(IA_Crouch, { EKeys::C, EKeys::Gamepad_FaceButton_Right });
	Button(IA_CrouchHold, { EKeys::LeftControl });
	Button(IA_Fire, { EKeys::LeftMouseButton, EKeys::Gamepad_RightTrigger });
	Button(IA_Aim, { EKeys::RightMouseButton, EKeys::Gamepad_LeftTrigger });
	Button(IA_Reload, { EKeys::R, EKeys::Gamepad_FaceButton_Left });
	Button(IA_Swap, { EKeys::MouseScrollUp, EKeys::MouseScrollDown, EKeys::Gamepad_FaceButton_Top });
	Button(IA_Primary, { EKeys::One });
	Button(IA_Secondary, { EKeys::Two });
	Button(IA_Grenade, { EKeys::G, EKeys::Gamepad_RightShoulder });
	Button(IA_FireMode, { EKeys::B, EKeys::Gamepad_DPad_Down });
	Button(IA_Light, { EKeys::T, EKeys::Gamepad_DPad_Up });
	Button(IA_Inspect, { EKeys::V, EKeys::Gamepad_DPad_Left });
	Button(IA_Interact, { EKeys::F, EKeys::Gamepad_DPad_Right });
	Button(IA_LeanLeft, { EKeys::Q });
	Button(IA_LeanRight, { EKeys::E });
	Button(IA_Scoreboard, { EKeys::Tab, EKeys::Gamepad_Special_Left });
	// Escape stops Play-In-Editor, so P opens the menu too.
	Button(IA_Menu, { EKeys::Escape, EKeys::P, EKeys::Gamepad_Special_Right });
	Button(IA_Loadout, { EKeys::L });
	Button(IA_Vote1, { EKeys::F1 });
	Button(IA_Vote2, { EKeys::F2 });
	Button(IA_Vote3, { EKeys::F3 });
	Button(IA_Vote4, { EKeys::F4 });
}

void AAirsoftPlayerController::AddMappingContext()
{
	if (ULocalPlayer* LP = GetLocalPlayer())
	{
		if (UEnhancedInputLocalPlayerSubsystem* Input = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
		{
			if (Mapping && !Input->HasMappingContext(Mapping))
			{
				Input->AddMappingContext(Mapping, 0);
			}
		}
	}
}

void AAirsoftPlayerController::SetupInputComponent()
{
	Super::SetupInputComponent();
	BuildInput();
	UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(InputComponent);
	if (!EIC)
	{
		UE_LOG(LogTemp, Error, TEXT("Airsoft: Enhanced Input is not the default input component class (check DefaultInput.ini)."));
		return;
	}
	auto Get = [this](FName Name) { return Actions.FindRef(Name).Get(); };

	EIC->BindAction(Get(IA_Move), ETriggerEvent::Triggered, this, &AAirsoftPlayerController::OnMove);
	EIC->BindAction(Get(IA_LookMouse), ETriggerEvent::Triggered, this, &AAirsoftPlayerController::OnLookMouse);
	EIC->BindAction(Get(IA_LookStick), ETriggerEvent::Triggered, this, &AAirsoftPlayerController::OnLookStick);
	EIC->BindAction(Get(IA_Jump), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnJump);
	EIC->BindAction(Get(IA_Sprint), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnSprintPressed);
	EIC->BindAction(Get(IA_Sprint), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnSprintReleased);
	EIC->BindAction(Get(IA_SprintToggle), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnSprintToggle);
	EIC->BindAction(Get(IA_Crouch), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnCrouchToggle);
	EIC->BindAction(Get(IA_CrouchHold), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnCrouchHoldPressed);
	EIC->BindAction(Get(IA_CrouchHold), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnCrouchHoldReleased);
	EIC->BindAction(Get(IA_Fire), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnFirePressed);
	EIC->BindAction(Get(IA_Fire), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnFireReleased);
	EIC->BindAction(Get(IA_Aim), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnAimPressed);
	EIC->BindAction(Get(IA_Aim), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnAimReleased);
	EIC->BindAction(Get(IA_Reload), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnReload);
	EIC->BindAction(Get(IA_Swap), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnSwapWeapon);
	EIC->BindAction(Get(IA_Primary), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnPrimary);
	EIC->BindAction(Get(IA_Secondary), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnSecondary);
	EIC->BindAction(Get(IA_Grenade), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnGrenade);
	EIC->BindAction(Get(IA_FireMode), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnFireMode);
	EIC->BindAction(Get(IA_Light), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnLight);
	EIC->BindAction(Get(IA_Inspect), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnInspect);
	EIC->BindAction(Get(IA_Interact), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnInteract);
	EIC->BindAction(Get(IA_LeanLeft), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnLeanLeftPressed);
	EIC->BindAction(Get(IA_LeanLeft), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnLeanLeftReleased);
	EIC->BindAction(Get(IA_LeanRight), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnLeanRightPressed);
	EIC->BindAction(Get(IA_LeanRight), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnLeanRightReleased);
	EIC->BindAction(Get(IA_Scoreboard), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnScoreboardPressed);
	EIC->BindAction(Get(IA_Scoreboard), ETriggerEvent::Completed, this, &AAirsoftPlayerController::OnScoreboardReleased);
	EIC->BindAction(Get(IA_Menu), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnMenu);
	EIC->BindAction(Get(IA_Loadout), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnLoadout);
	EIC->BindAction(Get(IA_Vote1), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnVote1);
	EIC->BindAction(Get(IA_Vote2), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnVote2);
	EIC->BindAction(Get(IA_Vote3), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnVote3);
	EIC->BindAction(Get(IA_Vote4), ETriggerEvent::Started, this, &AAirsoftPlayerController::OnVote4);
}

bool AAirsoftPlayerController::CanControlPawn() const
{
	return !IsMenuOpen() && ReplayStart < 0.0 && GetAirsoftCharacter() != nullptr;
}

void AAirsoftPlayerController::OnMove(const FInputActionValue& Value)
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->MoveInput(Value.Get<FVector2D>());
	}
}

void AAirsoftPlayerController::OnLookMouse(const FInputActionValue& Value)
{
	if (!CanControlPawn())
	{
		return;
	}
	float Sens = 1.f;
	bool bInvert = false;
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		Sens = GI->GetUserSettings().Sensitivity;
		bInvert = GI->GetUserSettings().bInvertY;
	}
	const FVector2D Delta = Value.Get<FVector2D>() * MouseDegreesPerCount * Sens;
	GetAirsoftCharacter()->LookInput(Delta.X, Delta.Y * (bInvert ? -1.f : 1.f));
}

void AAirsoftPlayerController::OnLookStick(const FInputActionValue& Value)
{
	if (!CanControlPawn())
	{
		return;
	}
	float Sens = 1.f;
	bool bInvert = false;
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		Sens = GI->GetUserSettings().Sensitivity;
		bInvert = GI->GetUserSettings().bInvertY;
	}
	const FVector2D Stick = Value.Get<FVector2D>();
	const float Dt = GetWorld()->GetDeltaSeconds();
	GetAirsoftCharacter()->LookInput(StickCurve(Stick.X) * StickYawRate * Sens * Dt, StickCurve(Stick.Y) * StickPitchRate * Sens * Dt * (bInvert ? -1.f : 1.f));
}

void AAirsoftPlayerController::OnJump()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->JumpInput();
	}
}

void AAirsoftPlayerController::OnSprintPressed()
{
	if (AAirsoftCharacter* C = GetAirsoftCharacter())
	{
		C->SetSprintHeld(CanControlPawn());
	}
}

void AAirsoftPlayerController::OnSprintReleased()
{
	if (AAirsoftCharacter* C = GetAirsoftCharacter())
	{
		C->SetSprintHeld(false);
	}
}

void AAirsoftPlayerController::OnSprintToggle()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->ToggleSprint();
	}
}

void AAirsoftPlayerController::OnCrouchToggle()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->ToggleCrouchInput();
	}
}

void AAirsoftPlayerController::OnCrouchHoldPressed()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->SetCrouchHeld(true);
	}
}

void AAirsoftPlayerController::OnCrouchHoldReleased()
{
	if (AAirsoftCharacter* C = GetAirsoftCharacter())
	{
		C->SetCrouchHeld(false);
	}
}

void AAirsoftPlayerController::OnFirePressed()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->CancelSprint();
		GetAirsoftCharacter()->GetCombat()->StartFire();
	}
}

void AAirsoftPlayerController::OnFireReleased()
{
	if (AAirsoftCharacter* C = GetAirsoftCharacter())
	{
		C->GetCombat()->StopFire();
	}
}

void AAirsoftPlayerController::OnAimPressed()
{
	if (!CanControlPawn())
	{
		return;
	}
	AAirsoftCharacter* C = GetAirsoftCharacter();
	C->CancelSprint();
	UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>();
	const bool bToggle = GI && GI->GetUserSettings().bToggleAim;
	if (bToggle)
	{
		C->GetCombat()->ToggleAim();
	}
	else
	{
		C->GetCombat()->SetAimHeld(true);
	}
}

void AAirsoftPlayerController::OnAimReleased()
{
	AAirsoftCharacter* C = GetAirsoftCharacter();
	UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>();
	if (C && !(GI && GI->GetUserSettings().bToggleAim))
	{
		C->GetCombat()->SetAimHeld(false);
	}
}

void AAirsoftPlayerController::OnReload()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->Reload();
	}
}

void AAirsoftPlayerController::OnSwapWeapon()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->CycleWeapon();
	}
}

void AAirsoftPlayerController::OnPrimary()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->EquipSlot(EAirsoftSlot::Primary);
	}
}

void AAirsoftPlayerController::OnSecondary()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->EquipSlot(EAirsoftSlot::Secondary);
	}
}

void AAirsoftPlayerController::OnGrenade()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->CancelSprint();
		GetAirsoftCharacter()->GetCombat()->ThrowGrenade();
	}
}

void AAirsoftPlayerController::OnFireMode()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->CycleFireMode();
	}
}

void AAirsoftPlayerController::OnLight()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->ToggleLight();
	}
}

void AAirsoftPlayerController::OnInspect()
{
	if (CanControlPawn())
	{
		GetAirsoftCharacter()->GetCombat()->Inspect();
	}
}

void AAirsoftPlayerController::OnInteract()
{
	if (CanControlPawn() && InteractTarget.IsValid())
	{
		OpenArmory(InteractTarget->WeaponId);
	}
}

void AAirsoftPlayerController::OnLeanLeftPressed() { bLeanLeft = true; }
void AAirsoftPlayerController::OnLeanLeftReleased() { bLeanLeft = false; }
void AAirsoftPlayerController::OnLeanRightPressed() { bLeanRight = true; }
void AAirsoftPlayerController::OnLeanRightReleased() { bLeanRight = false; }

void AAirsoftPlayerController::OnScoreboardPressed()
{
	if (bMainMenu || IsMenuOpen())
	{
		return;
	}
	bScoreboard = true;
	ShowWidget(ScoreboardWidget, AirsoftUI::MakeScoreboard(this), 20);
}

void AAirsoftPlayerController::OnScoreboardReleased()
{
	bScoreboard = false;
	HideWidget(ScoreboardWidget);
}

void AAirsoftPlayerController::OnMenu()
{
	if (bMainMenu)
	{
		if (OpenMenu != EAirsoftMenu::MainMenu)
		{
			ShowMenu(EAirsoftMenu::MainMenu);
		}
		return;
	}
	ToggleGameMenu();
}

void AAirsoftPlayerController::OnLoadout()
{
	if (!IsMenuOpen())
	{
		OpenArmory();
	}
}

void AAirsoftPlayerController::OnVote1() { VoteMode(0); }
void AAirsoftPlayerController::OnVote2() { VoteMode(1); }
void AAirsoftPlayerController::OnVote3() { VoteMap(0); }
void AAirsoftPlayerController::OnVote4() { VoteMap(1); }

void AAirsoftPlayerController::VoteMode(int32 ModeIndex)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->bIsMatchMap || bMainMenu)
	{
		return;
	}
	MyModeVote = FMath::Clamp(ModeIndex, 0, 1);
	ServerVote(MyModeVote, MyMapVote);
	AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.5f, 1.1f);
}

void AAirsoftPlayerController::VoteMap(int32 MapIndex)
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || GS->bIsMatchMap || bMainMenu)
	{
		return;
	}
	MyMapVote = FMath::Clamp(MapIndex, 0, AAirsoftGameState::MapIds().Num() - 1);
	ServerVote(MyModeVote, MyMapVote);
	AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.5f, 1.1f);
}

// ---------------------------------------------------------------------------
// Menus
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::ShowWidget(TSharedPtr<SWidget>& Slot, const TSharedRef<SWidget>& Widget, int32 ZOrder)
{
	HideWidget(Slot);
	ULocalPlayer* LP = GetLocalPlayer();
	if (LP && LP->ViewportClient)
	{
		LP->ViewportClient->AddViewportWidgetForPlayer(LP, Widget, ZOrder);
		Slot = Widget;
	}
}

void AAirsoftPlayerController::HideWidget(TSharedPtr<SWidget>& Slot)
{
	if (Slot.IsValid())
	{
		ULocalPlayer* LP = GetLocalPlayer();
		if (LP && LP->ViewportClient)
		{
			LP->ViewportClient->RemoveViewportWidgetForPlayer(LP, Slot.ToSharedRef());
		}
		Slot.Reset();
	}
}

void AAirsoftPlayerController::ShowMenu(EAirsoftMenu Menu)
{
	if (!IsLocalController())
	{
		return;
	}
	HideWidget(MenuWidget);
	OpenMenu = Menu;
	TSharedPtr<SWidget> Widget;
	switch (Menu)
	{
	case EAirsoftMenu::MainMenu: Widget = AirsoftUI::MakeMainMenu(this); break;
	case EAirsoftMenu::GameMenu: Widget = AirsoftUI::MakeGameMenu(this); break;
	case EAirsoftMenu::Armory: Widget = AirsoftUI::MakeArmory(this); break;
	case EAirsoftMenu::Settings: Widget = AirsoftUI::MakeSettings(this); break;
	case EAirsoftMenu::None: break;
	}
	if (Widget.IsValid())
	{
		ShowWidget(MenuWidget, Widget.ToSharedRef(), 50);
		HideWidget(ScoreboardWidget);
		bScoreboard = false;
		if (AAirsoftCharacter* C = GetAirsoftCharacter())
		{
			C->GetCombat()->CancelActions();
			C->SetSprintHeld(false);
			C->SetLeanInput(0.f);
		}
		AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.35f, 0.9f);
	}
	RefreshInputMode();
	if (Widget.IsValid() && FSlateApplication::IsInitialized())
	{
		FSlateApplication::Get().SetKeyboardFocus(Widget, EFocusCause::SetDirectly);
	}
}

void AAirsoftPlayerController::CloseMenus()
{
	if (bMainMenu)
	{
		ShowMenu(EAirsoftMenu::MainMenu);
		return;
	}
	HideWidget(MenuWidget);
	OpenMenu = EAirsoftMenu::None;
	ArmoryFocus = NAME_None;
	RefreshInputMode();
}

void AAirsoftPlayerController::ToggleGameMenu()
{
	if (IsMenuOpen())
	{
		CloseMenus();
	}
	else
	{
		ShowMenu(EAirsoftMenu::GameMenu);
	}
}

void AAirsoftPlayerController::OpenArmory(FName FocusWeapon)
{
	ArmoryFocus = FocusWeapon;
	ShowMenu(EAirsoftMenu::Armory);
}

void AAirsoftPlayerController::RefreshInputMode()
{
	if (!IsLocalController())
	{
		return;
	}
	if (IsMenuOpen())
	{
		FInputModeGameAndUI Mode;
		Mode.SetWidgetToFocus(MenuWidget);
		Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
		Mode.SetHideCursorDuringCapture(false);
		SetInputMode(Mode);
		SetShowMouseCursor(true);
	}
	else
	{
		SetInputMode(FInputModeGameOnly());
		SetShowMouseCursor(false);
	}
}

// ---------------------------------------------------------------------------
// HUD feed
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::ShowHitMarker(bool bConfirmedTag)
{
	HitMarkerTime = GetWorld()->GetRealTimeSeconds();
	bHitMarkerTag = bConfirmedTag;
}

float AAirsoftPlayerController::GetHitMarkerAlpha() const
{
	const double Age = GetWorld()->GetRealTimeSeconds() - HitMarkerTime;
	const double Duration = bHitMarkerTag ? 0.45 : 0.22;
	return FMath::Clamp(static_cast<float>(1.0 - Age / Duration), 0.f, 1.f);
}

void AAirsoftPlayerController::Announce(const FString& Title, const FString& Sub, const FLinearColor& Color, float Duration)
{
	Announcement.Title = Title;
	Announcement.Sub = Sub;
	Announcement.Color = Color;
	Announcement.Duration = FMath::Max(Duration, 0.5f);
	Announcement.Time = GetWorld()->GetRealTimeSeconds();
	AirsoftAssets::Play2D(this, TEXT("Announce"), 0.6f, 1.f);
}

FString AAirsoftPlayerController::GetInteractPrompt() const
{
	if (const AAirsoftArmoryDisplay* Display = InteractTarget.Get())
	{
		return Display->GetPrompt();
	}
	return FString();
}

bool AAirsoftPlayerController::IsSummaryVisible() const
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	return Summary.bValid && GS && GS->Phase == EAirsoftPhase::PostRound && ReplayStart < 0.0;
}

float AAirsoftPlayerController::GetReplayTime() const
{
	return ReplayStart < 0.0 ? -1.f : static_cast<float>(GetWorld()->GetRealTimeSeconds() - ReplayStart);
}

void AAirsoftPlayerController::UpdateInteraction()
{
	InteractTarget.Reset();
	AAirsoftCharacter* C = GetAirsoftCharacter();
	if (!C || IsMenuOpen() || C->IsOut())
	{
		return;
	}
	FVector Loc;
	FRotator Rot;
	GetPlayerViewPoint(Loc, Rot);
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftInteract), false, C);
	FHitResult Hit;
	if (GetWorld()->LineTraceSingleByChannel(Hit, Loc, Loc + Rot.Vector() * 260.f, ECC_Visibility, Query))
	{
		InteractTarget = Cast<AAirsoftArmoryDisplay>(Hit.GetActor());
	}
}

void AAirsoftPlayerController::PlayerTick(float DeltaTime)
{
	Super::PlayerTick(DeltaTime);
	if (!IsLocalController())
	{
		return;
	}
	// The controller survives seamless travel and, on clients, may begin play before it has a
	// local player - so (re)build input and UI whenever the world changed or the UI is missing.
	const bool bUIMissing = bMainMenu ? !MenuWidget.IsValid() : !HUDWidget.IsValid();
	if (UIWorld.Get() != GetWorld() || bUIMissing)
	{
		UIWorld = GetWorld();
		BuildInput();
		AddMappingContext();
		RebuildUI();
	}

	const double Now = GetWorld()->GetRealTimeSeconds();
	XPPopups.RemoveAll([Now](const FAirsoftXPPopup& P) { return Now - P.Time > 2.0 || Now < P.Time; });
	KillFeed.RemoveAll([Now](const FAirsoftKillFeedEntry& E) { return Now - E.Time > 8.0 || Now < E.Time; });

	if (AAirsoftCharacter* C = GetAirsoftCharacter())
	{
		C->SetLeanInput(CanControlPawn() ? (bLeanRight ? 1.f : 0.f) - (bLeanLeft ? 1.f : 0.f) : 0.f);
	}

	UpdateInteraction();
	UpdateReplay(DeltaTime);
	UpdateMatchAudio();

	const bool bWantSummary = IsSummaryVisible();
	if (bWantSummary && !SummaryWidget.IsValid())
	{
		ShowWidget(SummaryWidget, AirsoftUI::MakeSummary(this), 30);
		if (!PostRoundMusic)
		{
			PostRoundMusic = UGameplayStatics::SpawnSound2D(this, AirsoftAssets::Sound(TEXT("PostRoundMusic")), 0.55f);
			if (PostRoundMusic)
			{
				PostRoundMusic->FadeIn(2.f, 0.55f);
			}
		}
		if (!bSummaryStingPlayed)
		{
			bSummaryStingPlayed = true;
			const bool bWon = Summary.Winner != EAirsoftTeam::None && Summary.Winner == Summary.MyTeam;
			AirsoftAssets::Play2D(this, bWon ? TEXT("Victory") : TEXT("Defeat"), 0.8f, 1.f);
			if (Summary.RankAfter > Summary.RankBefore)
			{
				FTimerHandle Handle;
				GetWorldTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this]()
				{
					AirsoftAssets::Play2D(this, TEXT("RankUp"), 0.8f, 1.f);
				}), 2.5f, false);
			}
		}
	}
	else if (!bWantSummary && SummaryWidget.IsValid())
	{
		HideWidget(SummaryWidget);
	}
	if (!bWantSummary && PostRoundMusic)
	{
		PostRoundMusic->FadeOut(1.5f, 0.f);
		PostRoundMusic = nullptr;
	}
}

void AAirsoftPlayerController::UpdateMatchAudio()
{
	const AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS || bMainMenu)
	{
		return;
	}
	if (GS->Phase != LastPhase)
	{
		if (GS->bIsMatchMap && GS->Phase == EAirsoftPhase::Live && LastPhase == EAirsoftPhase::Briefing)
		{
			AirsoftAssets::Play2D(this, TEXT("RoundStart"), 0.8f, 1.f);
		}
		LastPhase = GS->Phase;
	}
	if (GS->Phase != EAirsoftPhase::Live)
	{
		LastObjectiveOwners.Reset();
		return;
	}

	const APawn* MyPawn = GetPawn();
	const double Now = GetWorld()->GetRealTimeSeconds();
	for (const TObjectPtr<AAirsoftObjective>& Obj : GS->Objectives)
	{
		if (!Obj || !Obj->bActive)
		{
			continue;
		}
		EAirsoftTeam& Last = LastObjectiveOwners.FindOrAdd(Obj.Get(), Obj->OwnerTeam);
		if (Last != Obj->OwnerTeam)
		{
			if (Obj->OwnerTeam != EAirsoftTeam::None)
			{
				const bool bMine = GetAirsoftPlayerState() && GetAirsoftPlayerState()->Team == Obj->OwnerTeam;
				AirsoftAssets::Play2D(this, TEXT("PointCaptured"), 0.7f, bMine ? 1.f : 0.8f);
			}
			Last = Obj->OwnerTeam;
		}
		// Ticking while we stand on a point that is changing hands.
		if (MyPawn && Obj->CapturingTeam != EAirsoftTeam::None && !Obj->bContested && Obj->IsInside(MyPawn->GetActorLocation()) && Now >= NextCaptureTick)
		{
			NextCaptureTick = Now + 0.5;
			AirsoftAssets::Play2D(this, TEXT("CaptureTick"), 0.35f, 0.9f + 0.3f * FMath::Abs(Obj->Progress));
		}
	}
}

// ---------------------------------------------------------------------------
// Final-tag replay
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::StartReplay()
{
	StopReplay();
	const FAirsoftFinalTag& Tag = Summary.FinalTag;
	if (!Tag.bValid || FVector::Dist(Tag.From, Tag.To) < 50.f)
	{
		return;
	}
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ReplayCamera = GetWorld()->SpawnActor<ACameraActor>(ACameraActor::StaticClass(), Tag.From, (Tag.To - Tag.From).Rotation(), Params);
	if (!ReplayCamera)
	{
		return;
	}
	ReplayCamera->GetCameraComponent()->SetFieldOfView(55.f);
	ReplayCamera->GetCameraComponent()->bConstrainAspectRatio = false;
	ReplayStart = GetWorld()->GetRealTimeSeconds();
	bReplayFired = false;
	bReplayHitPlayed = false;
	SetViewTargetWithBlend(ReplayCamera, 0.4f, VTBlend_EaseInOut, 2.f);
	AirsoftAssets::Play2D(this, TEXT("ReplayWhoosh"), 0.8f, 1.f);
	UpdateReplay(0.f);
}

void AAirsoftPlayerController::StopReplay()
{
	const bool bWasPlaying = ReplayStart >= 0.0;
	ReplayStart = -1.0;
	if (ReplayCamera)
	{
		ReplayCamera->Destroy();
		ReplayCamera = nullptr;
	}
	if (bWasPlaying && GetPawn())
	{
		SetViewTargetWithBlend(GetPawn(), 0.5f, VTBlend_EaseInOut, 2.f);
	}
}

void AAirsoftPlayerController::UpdateReplay(float DeltaTime)
{
	if (ReplayStart < 0.0 || !ReplayCamera)
	{
		return;
	}
	const FAirsoftFinalTag& Tag = Summary.FinalTag;
	const double T = GetWorld()->GetRealTimeSeconds() - ReplayStart;
	const FVector Dir = (Tag.To - Tag.From).GetSafeNormal();
	const FVector Side = FVector::CrossProduct(FVector::UpVector, Dir).GetSafeNormal();
	const float Dist = FVector::Dist(Tag.From, Tag.To);

	if (!bReplayFired && T >= ReplayFireAt)
	{
		bReplayFired = true;
		if (UAirsoftBBSubsystem* BBs = GetWorld()->GetSubsystem<UAirsoftBBSubsystem>())
		{
			FAirsoftBBParams P;
			P.Origin = Tag.From + Dir * 30.f;
			P.Direction = Dir;
			P.Speed = Dist / ReplayFlight;
			P.Hop = 1.f;
			P.Drag = 0.f;
			P.MaxRange = Dist + 60.f;
			P.Color = AirsoftColors::Team(Tag.ShooterTeam);
			BBs->Fire(MoveTemp(P));
		}
		AirsoftAssets::Play2D(this, TEXT("FireRifle"), 0.5f, 0.55f);
		AirsoftAssets::Play2D(this, TEXT("SlowMoHeartbeat"), 0.6f, 1.f);
	}
	if (!bReplayHitPlayed && T >= ReplayFireAt + ReplayFlight)
	{
		bReplayHitPlayed = true;
		AirsoftAssets::Play2D(this, TEXT("ReplayImpact"), 0.9f, 1.f);
		AirsoftAssets::Play2D(this, TEXT("HitCall"), 0.7f, 0.9f);
	}

	FVector CamLoc;
	FVector LookAt;
	if (T < ReplayFireAt)
	{
		// Over the shooter's shoulder.
		CamLoc = Tag.From - Dir * 70.f + Side * 30.f + FVector(0.f, 0.f, 8.f);
		LookAt = Tag.To;
	}
	else if (T < ReplayFireAt + ReplayFlight)
	{
		// Chase the BB.
		const float Alpha = FMath::Clamp(static_cast<float>((T - ReplayFireAt) / ReplayFlight), 0.f, 1.f);
		const FVector BB = FMath::Lerp(Tag.From, Tag.To, Alpha);
		CamLoc = BB - Dir * 110.f + Side * 40.f + FVector(0.f, 0.f, 14.f);
		LookAt = BB + Dir * 250.f;
	}
	else
	{
		// Slow orbit on the tagged player.
		const float Orbit = static_cast<float>(T - (ReplayFireAt + ReplayFlight)) * 18.f;
		const FVector Offset = (-Dir * 220.f + Side * 120.f).RotateAngleAxis(Orbit, FVector::UpVector) + FVector(0.f, 0.f, 50.f);
		CamLoc = Tag.To + Offset;
		LookAt = Tag.To;
	}
	ReplayCamera->SetActorLocationAndRotation(CamLoc, (LookAt - CamLoc).Rotation());

	if (T >= ReplayLength)
	{
		StopReplay();
	}
}

// ---------------------------------------------------------------------------
// Server RPCs
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::ApplyLoadout(const FAirsoftLoadout& InLoadout)
{
	AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	if (!PS)
	{
		return;
	}
	FAirsoftLoadout Clean;
	Clean.Primary = AirsoftWeapons::Clean(InLoadout.Primary);
	Clean.Secondary = AirsoftWeapons::Clean(InLoadout.Secondary);
	const FAirsoftWeaponDef* Primary = AirsoftWeapons::Find(Clean.Primary.WeaponId);
	const FAirsoftWeaponDef* Secondary = AirsoftWeapons::Find(Clean.Secondary.WeaponId);
	const FAirsoftLoadout Defaults = AirsoftWeapons::DefaultLoadout();
	if (!Primary || !Primary->IsPrimary())
	{
		Clean.Primary = Defaults.Primary;
	}
	if (!Secondary || !Secondary->IsSecondary())
	{
		Clean.Secondary = Defaults.Secondary;
	}
	// Finishes are earned: fall back to the default finish if the rank isn't there yet.
	const int32 Rank = PS->RankIndex();
	for (FAirsoftCustomization* Custom : { &Clean.Primary, &Clean.Secondary })
	{
		if (AirsoftWeapons::FindSkin(Custom->Skin).UnlockRank > Rank)
		{
			Custom->Skin = TEXT("Black");
		}
	}
	PS->Loadout = Clean;
	PS->bLoadoutReceived = true;
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		GM->OnLoadoutChanged(this);
	}
}

void AAirsoftPlayerController::ServerSetProfile_Implementation(const FString& InName, int32 InCareerXP, const FAirsoftLoadout& InLoadout)
{
	AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	if (!PS)
	{
		return;
	}
	const FString Name = InName.Left(20).TrimStartAndEnd();
	if (!Name.IsEmpty() && Name != PS->GetPlayerName())
	{
		if (AGameModeBase* GM = GetWorld()->GetAuthGameMode())
		{
			GM->ChangeName(this, Name, false);
		}
	}
	PS->CareerXP = FMath::Clamp(InCareerXP, 0, 50000000);
	ApplyLoadout(InLoadout);
}

void AAirsoftPlayerController::ServerSetLoadout_Implementation(const FAirsoftLoadout& InLoadout)
{
	ApplyLoadout(InLoadout);
}

void AAirsoftPlayerController::ServerVote_Implementation(int32 ModeIndex, int32 MapIndex)
{
	AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	if (!PS)
	{
		return;
	}
	PS->ModeVote = FMath::Clamp(ModeIndex, -1, 1);
	PS->MapVote = FMath::Clamp(MapIndex, -1, AAirsoftGameState::MapIds().Num() - 1);
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		GM->OnVotesChanged();
	}
}

void AAirsoftPlayerController::ServerForceStart_Implementation()
{
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		GM->ForceStart(this);
	}
}

void AAirsoftPlayerController::ServerSwitchTeam_Implementation()
{
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		GM->SwitchTeam(this);
	}
}

// ---------------------------------------------------------------------------
// Client RPCs
// ---------------------------------------------------------------------------

void AAirsoftPlayerController::ClientAnnounce_Implementation(const FString& Title, const FString& Sub, FLinearColor Color, float Duration)
{
	Announce(Title, Sub, Color, Duration);
}

void AAirsoftPlayerController::ClientKillFeed_Implementation(const FString& Shooter, EAirsoftTeam ShooterTeam, const FString& Victim, EAirsoftTeam VictimTeam, FName WeaponId)
{
	FAirsoftKillFeedEntry Entry;
	Entry.Shooter = Shooter;
	Entry.ShooterTeam = ShooterTeam;
	Entry.Victim = Victim;
	Entry.VictimTeam = VictimTeam;
	Entry.WeaponId = WeaponId;
	Entry.Time = GetWorld()->GetRealTimeSeconds();
	const AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	Entry.bInvolvesMe = PS && (PS->GetPlayerName() == Shooter || PS->GetPlayerName() == Victim);
	KillFeed.Add(Entry);
	while (KillFeed.Num() > 6)
	{
		KillFeed.RemoveAt(0);
	}
	if (PS && PS->GetPlayerName() == Victim)
	{
		Announce(TEXT("HIT"), FString::Printf(TEXT("Tagged by %s"), *Shooter), FLinearColor(1.f, 0.25f, 0.05f), 2.f);
	}
}

void AAirsoftPlayerController::ClientXP_Implementation(int32 Amount, const FString& Reason)
{
	FAirsoftXPPopup Popup;
	Popup.Amount = Amount;
	Popup.Reason = Reason;
	Popup.Time = GetWorld()->GetRealTimeSeconds();
	XPPopups.Add(Popup);
}

void AAirsoftPlayerController::ClientMatchEnded_Implementation(EAirsoftTeam Winner, const TArray<FAirsoftSummaryRow>& Rows, const FAirsoftFinalTag& FinalTag, int32 XPEarned, int32 Captures)
{
	const AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	Summary = FAirsoftMatchSummary();
	Summary.bValid = true;
	Summary.Winner = Winner;
	Summary.MyTeam = PS ? PS->Team : EAirsoftTeam::None;
	Summary.Rows = Rows;
	Summary.FinalTag = FinalTag;
	Summary.XPEarned = XPEarned;
	Summary.Time = GetWorld()->GetRealTimeSeconds();
	bSummaryStingPlayed = false;

	// The profile lives on each player's own PC.
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		if (UAirsoftSaveGame* Profile = GI->GetProfile())
		{
			Summary.RankBefore = AirsoftWeapons::RankIndexForXP(Profile->XP);
			Profile->XP += FMath::Max(XPEarned, 0);
			Profile->Matches++;
			Profile->Captures += Captures;
			if (Winner != EAirsoftTeam::None && Winner == Summary.MyTeam)
			{
				Profile->Wins++;
			}
			const FString MyName = PS ? PS->GetPlayerName() : FString();
			for (const FAirsoftSummaryRow& Row : Rows)
			{
				if (Row.Name == MyName)
				{
					Profile->Tags += Row.Stats.Tags;
					Profile->Outs += Row.Stats.Outs;
					Profile->BestStreak = FMath::Max(Profile->BestStreak, Row.Stats.Streak);
					break;
				}
			}
			Summary.RankAfter = AirsoftWeapons::RankIndexForXP(Profile->XP);
			GI->SaveProfile();
		}
	}

	if (AAirsoftCharacter* C = GetAirsoftCharacter())
	{
		C->GetCombat()->CancelActions();
	}
	if (IsMenuOpen())
	{
		CloseMenus();
	}
	StartReplay();
}

void AAirsoftPlayerController::ClientResetForNewRound_Implementation()
{
	Summary = FAirsoftMatchSummary();
	bSummaryStingPlayed = false;
	KillFeed.Reset();
	XPPopups.Reset();
	StopReplay();
	HideWidget(SummaryWidget);
}
