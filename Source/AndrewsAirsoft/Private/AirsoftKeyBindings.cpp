#include "AirsoftKeyBindings.h"

#include "AirsoftGameInstance.h"
#include "AirsoftSaveGame.h"
#include "Engine/LocalPlayer.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/PlayerController.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "InputTriggers.h"

namespace AirsoftKeyBindingsLocal
{
	using AirsoftKeyBindings::FSlot;

	FSlot Make(const TCHAR* Id, const TCHAR* Action, const TCHAR* Label, const TCHAR* Group, const FKey& Default, uint8 MoveDirection = 0)
	{
		FSlot Slot;
		Slot.Id = FName(Id);
		Slot.Action = FName(Action);
		Slot.Label = Label;
		Slot.Group = Group;
		Slot.Default = Default;
		Slot.MoveDirection = MoveDirection;
		return Slot;
	}

	/** Which way a keyboard Move mapping pushes, from its modifiers (BuildInput: W swizzle, S swizzle+negate, A negate, D none). */
	uint8 MoveDirectionOf(const FEnhancedActionKeyMapping& Mapping)
	{
		bool bSwizzle = false;
		bool bNegate = false;
		for (const TObjectPtr<UInputModifier>& Modifier : Mapping.Modifiers)
		{
			bSwizzle |= Cast<UInputModifierSwizzleAxis>(Modifier.Get()) != nullptr;
			bNegate |= Cast<UInputModifierNegate>(Modifier.Get()) != nullptr;
		}
		if (bSwizzle)
		{
			return bNegate ? 2 : 1;
		}
		return bNegate ? 3 : 4;
	}

	/** Keys other, fixed controls use (menu, lobby votes, weapon wheel). */
	bool IsReserved(const FKey& Key)
	{
		return Key == EKeys::Escape || Key == EKeys::P || Key == EKeys::F1 || Key == EKeys::F2
			|| Key == EKeys::MouseScrollUp || Key == EKeys::MouseScrollDown;
	}
}

namespace AirsoftKeyBindings
{
	const TArray<FSlot>& Slots()
	{
		using AirsoftKeyBindingsLocal::Make;
		static const TArray<FSlot> List = {
			Make(TEXT("MoveForward"), TEXT("IA_Move"), TEXT("Move forward"), TEXT("MOVEMENT"), EKeys::W, 1),
			Make(TEXT("MoveBack"), TEXT("IA_Move"), TEXT("Move back"), TEXT("MOVEMENT"), EKeys::S, 2),
			Make(TEXT("MoveLeft"), TEXT("IA_Move"), TEXT("Move left"), TEXT("MOVEMENT"), EKeys::A, 3),
			Make(TEXT("MoveRight"), TEXT("IA_Move"), TEXT("Move right"), TEXT("MOVEMENT"), EKeys::D, 4),
			Make(TEXT("Jump"), TEXT("IA_Jump"), TEXT("Jump / vault"), TEXT("MOVEMENT"), EKeys::SpaceBar),
			Make(TEXT("Sprint"), TEXT("IA_Sprint"), TEXT("Sprint (hold)"), TEXT("MOVEMENT"), EKeys::LeftShift),
			Make(TEXT("Crouch"), TEXT("IA_Crouch"), TEXT("Crouch / slide (toggle)"), TEXT("MOVEMENT"), EKeys::C),
			Make(TEXT("CrouchHold"), TEXT("IA_CrouchHold"), TEXT("Crouch (hold)"), TEXT("MOVEMENT"), EKeys::LeftControl),
			Make(TEXT("LeanLeft"), TEXT("IA_LeanLeft"), TEXT("Lean left"), TEXT("MOVEMENT"), EKeys::Q),
			Make(TEXT("LeanRight"), TEXT("IA_LeanRight"), TEXT("Lean right"), TEXT("MOVEMENT"), EKeys::E),
			Make(TEXT("Fire"), TEXT("IA_Fire"), TEXT("Fire"), TEXT("COMBAT"), EKeys::LeftMouseButton),
			Make(TEXT("Aim"), TEXT("IA_Aim"), TEXT("Aim down sights"), TEXT("COMBAT"), EKeys::RightMouseButton),
			Make(TEXT("Reload"), TEXT("IA_Reload"), TEXT("Reload"), TEXT("COMBAT"), EKeys::R),
			Make(TEXT("Primary"), TEXT("IA_Primary"), TEXT("Primary weapon"), TEXT("COMBAT"), EKeys::One),
			Make(TEXT("Secondary"), TEXT("IA_Secondary"), TEXT("Sidearm"), TEXT("COMBAT"), EKeys::Two),
			Make(TEXT("Grenade"), TEXT("IA_Grenade"), TEXT("Throw grenade"), TEXT("COMBAT"), EKeys::G),
			Make(TEXT("FireMode"), TEXT("IA_FireMode"), TEXT("Fire mode"), TEXT("COMBAT"), EKeys::B),
			Make(TEXT("Light"), TEXT("IA_Light"), TEXT("Weapon light"), TEXT("COMBAT"), EKeys::T),
			Make(TEXT("Inspect"), TEXT("IA_Inspect"), TEXT("Inspect weapon"), TEXT("COMBAT"), EKeys::V),
			Make(TEXT("Interact"), TEXT("IA_Interact"), TEXT("Interact"), TEXT("OTHER"), EKeys::F),
			Make(TEXT("CameraView"), TEXT("IA_CameraView"), TEXT("First / third person"), TEXT("OTHER"), EKeys::F5),
			Make(TEXT("Shoulder"), TEXT("IA_Shoulder"), TEXT("Swap shoulder"), TEXT("OTHER"), EKeys::X),
			Make(TEXT("Scoreboard"), TEXT("IA_Scoreboard"), TEXT("Scoreboard (hold)"), TEXT("OTHER"), EKeys::Tab),
			Make(TEXT("Loadout"), TEXT("IA_Loadout"), TEXT("Armory"), TEXT("OTHER"), EKeys::L),
		};
		return List;
	}

	const FSlot* FindSlot(FName Id)
	{
		return Slots().FindByPredicate([Id](const FSlot& Slot) { return Slot.Id == Id; });
	}

	FKey KeyFor(const FAirsoftUserSettings& Settings, FName Id)
	{
		if (const FKey* Override = Settings.KeyBindings.Find(Id))
		{
			if (CanBind(*Override))
			{
				return *Override;
			}
		}
		const FSlot* Slot = FindSlot(Id);
		return Slot ? Slot->Default : EKeys::Invalid;
	}

	bool CanBind(const FKey& Key)
	{
		return Key.IsValid() && !Key.IsGamepadKey() && !Key.IsTouch() && !Key.IsAxis1D() && !Key.IsAxis2D() && !Key.IsAxis3D()
			&& !AirsoftKeyBindingsLocal::IsReserved(Key);
	}

	void Rebind(FAirsoftUserSettings& Settings, FName Id, const FKey& Key)
	{
		const FSlot* Slot = FindSlot(Id);
		if (!Slot || !CanBind(Key))
		{
			return;
		}
		const FKey Old = KeyFor(Settings, Id);
		if (Old == Key)
		{
			return;
		}
		auto Store = [&Settings](const FSlot& Target, const FKey& NewKey)
		{
			if (NewKey == Target.Default)
			{
				Settings.KeyBindings.Remove(Target.Id);
			}
			else
			{
				Settings.KeyBindings.Add(Target.Id, NewKey);
			}
		};
		// Whoever had the key takes this slot's old one.
		for (const FSlot& Other : Slots())
		{
			if (Other.Id != Id && KeyFor(Settings, Other.Id) == Key)
			{
				Store(Other, Old);
			}
		}
		Store(*Slot, Key);
	}

	FString KeyLabel(const FKey& Key)
	{
		if (Key == EKeys::LeftMouseButton) return TEXT("LMB");
		if (Key == EKeys::RightMouseButton) return TEXT("RMB");
		if (Key == EKeys::MiddleMouseButton) return TEXT("MMB");
		if (Key == EKeys::ThumbMouseButton) return TEXT("MOUSE 4");
		if (Key == EKeys::ThumbMouseButton2) return TEXT("MOUSE 5");
		if (Key == EKeys::SpaceBar) return TEXT("SPACE");
		if (Key == EKeys::LeftShift) return TEXT("L-SHIFT");
		if (Key == EKeys::RightShift) return TEXT("R-SHIFT");
		if (Key == EKeys::LeftControl) return TEXT("L-CTRL");
		if (Key == EKeys::RightControl) return TEXT("R-CTRL");
		if (Key == EKeys::LeftAlt) return TEXT("L-ALT");
		if (Key == EKeys::RightAlt) return TEXT("R-ALT");
		if (!Key.IsValid()) return TEXT("-");
		return Key.GetDisplayName(false).ToString().ToUpper();
	}

	void Apply(APlayerController* PC)
	{
		if (!PC || !PC->IsLocalController())
		{
			return;
		}
		UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(PC->GetGameInstance());
		UInputMappingContext* Mapping = FindObject<UInputMappingContext>(PC, TEXT("IMC_Airsoft"));
		if (!GI || !Mapping)
		{
			return;
		}
		const FAirsoftUserSettings& Settings = GI->GetUserSettings();

		// Gather every slot whose key changed first, unmap all their old keys, then map the new ones:
		// the four Move keys share one action, so a swap done one slot at a time would unmap its partner.
		struct FChange
		{
			const UInputAction* Action = nullptr;
			FKey Old;
			FKey Want;
			TArray<TObjectPtr<UInputModifier>> Modifiers;
			TArray<TObjectPtr<UInputTrigger>> Triggers;
		};
		TArray<FChange> Changes;
		const TArray<FEnhancedActionKeyMapping>& Mappings = Mapping->GetMappings();
		for (const FSlot& Slot : Slots())
		{
			const UInputAction* Action = FindObject<UInputAction>(PC, *Slot.Action.ToString());
			if (!Action)
			{
				continue;
			}
			// This slot's current keyboard/mouse mapping (gamepad mappings stay as built).
			const FEnhancedActionKeyMapping* Current = Mappings.FindByPredicate([Action, &Slot](const FEnhancedActionKeyMapping& M)
			{
				return M.Action == Action && !M.Key.IsGamepadKey()
					&& (Slot.MoveDirection == 0 || AirsoftKeyBindingsLocal::MoveDirectionOf(M) == Slot.MoveDirection);
			});
			const FKey Want = KeyFor(Settings, Slot.Id);
			if (!Current || Current->Key == Want)
			{
				continue;
			}
			FChange& Change = Changes.AddDefaulted_GetRef();
			Change.Action = Action;
			Change.Old = Current->Key;
			Change.Want = Want;
			Change.Modifiers = Current->Modifiers;
			Change.Triggers = Current->Triggers;
		}
		if (Changes.Num() == 0)
		{
			return;
		}
		for (const FChange& Change : Changes)
		{
			Mapping->UnmapKey(Change.Action, Change.Old);
		}
		for (const FChange& Change : Changes)
		{
			FEnhancedActionKeyMapping& New = Mapping->MapKey(Change.Action, Change.Want);
			New.Modifiers = Change.Modifiers;
			New.Triggers = Change.Triggers;
		}
		if (ULocalPlayer* LP = PC->GetLocalPlayer())
		{
			if (UEnhancedInputLocalPlayerSubsystem* Input = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
			{
				Input->RequestRebuildControlMappings();
			}
		}
	}
}
