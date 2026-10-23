// Andrew's Airsoft - keyboard and mouse rebinding. The player controller builds its
// Enhanced Input mapping in code (AAirsoftPlayerController::BuildInput); Apply() then
// moves each rebound slot's keyboard/mouse key to the player's choice. Gamepad keys
// are never touched. Choices live in FAirsoftUserSettings::KeyBindings.

#pragma once

#include "CoreMinimal.h"
#include "InputCoreTypes.h"

class APlayerController;
struct FAirsoftUserSettings;

namespace AirsoftKeyBindings
{
	/** One rebindable control. Move is one Axis2D action with four keys, told apart by its modifiers. */
	struct FSlot
	{
		/** Saved name, e.g. "MoveForward". */
		FName Id;
		/** The controller's input action, e.g. "IA_Move". */
		FName Action;
		/** Shown in Settings. */
		FString Label;
		/** Settings section ("MOVEMENT", "COMBAT", "OTHER"). */
		FString Group;
		FKey Default;
		/** Move only: 1 forward, 2 back, 3 left, 4 right; 0 for a button. */
		uint8 MoveDirection = 0;
	};

	ANDREWSAIRSOFT_API const TArray<FSlot>& Slots();
	ANDREWSAIRSOFT_API const FSlot* FindSlot(FName Id);

	/** The key a slot uses with these settings (its override, else the default). */
	ANDREWSAIRSOFT_API FKey KeyFor(const FAirsoftUserSettings& Settings, FName Id);

	/** Keys a player may not bind: Escape opens the menu, and gamepad keys keep their own layout. */
	ANDREWSAIRSOFT_API bool CanBind(const FKey& Key);

	/**
	 * Bind Id to Key in Settings. A slot that already used Key takes Id's old key (a swap),
	 * so no two controls ever share a key. A key equal to the default clears the override.
	 */
	ANDREWSAIRSOFT_API void Rebind(FAirsoftUserSettings& Settings, FName Id, const FKey& Key);

	/** Short name for a key cap: "LMB", "SPACE", "F5". */
	ANDREWSAIRSOFT_API FString KeyLabel(const FKey& Key);

	/**
	 * Point the controller's IMC_Airsoft at the saved keys and rebuild the live mappings.
	 * Safe to call any time after the controller built its input; cheap when nothing changed.
	 */
	ANDREWSAIRSOFT_API void Apply(APlayerController* PC);
}
