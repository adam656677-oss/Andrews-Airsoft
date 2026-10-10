// Andrew's Airsoft - everything a player does with a gun: firing, aiming,
// recoil, reloads, fire modes, grenades, weapon light, and the first-person
// viewmodel animation. The server validates every shot and hit claim.

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "Engine/NetSerialization.h"
#include "TimerManager.h"
#include "AirsoftTypes.h"
#include "AirsoftWeaponData.h"
#include "AirsoftCombatComponent.generated.h"

class AAirsoftCharacter;
class UAirsoftGunVisual;
struct FHitResult;

UCLASS(ClassGroup = (Airsoft), meta = (BlueprintSpawnableComponent))
class ANDREWSAIRSOFT_API UAirsoftCombatComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UAirsoftCombatComponent();

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Server: hand out a loadout and fill the mags. */
	void ServerInitLoadout(const FAirsoftLoadout& InLoadout);

	// --- Local input -------------------------------------------------------
	void StartFire();
	void StopFire();
	void SetAimHeld(bool bHeld);
	void ToggleAim();
	void Reload();
	void CycleFireMode();
	void EquipSlot(EAirsoftSlot Slot);
	void CycleWeapon();
	void ThrowGrenade();
	void ToggleLight();
	void Inspect();
	void CancelActions();

	// --- Bot input (server only) --------------------------------------------
	// A bot's pawn is locally controlled on the host, so these drive the same
	// predicted firing / reload / aim path as the listen-server player: the shot
	// still goes through ServerFire validation, hit claims and HandleTag.
	/** One trigger press: a single shot (semi / bolt / pump), a 3-round burst, or full auto until released. */
	void BotPullTrigger();
	void BotReleaseTrigger();
	void BotSetAim(bool bAim);
	/** Starts a reload if the mag isn't full and there is reserve; true if it started. */
	bool BotReload();
	/** Switches weapon slot (primary / secondary). */
	void BotEquip(EAirsoftSlot Slot);
	/** Selects a fire mode the current gun has (no UI click). */
	void BotSetFireMode(EAirsoftFireMode Mode);
	/** Throws the grenade from the eyes along Direction; true if the throw started. */
	bool BotThrowGrenade(const FVector& Direction);

	// --- State for HUD / character ----------------------------------------
	const FAirsoftWeaponDef& Current() const;
	const FAirsoftCustomization& CurrentCustomization() const;
	EAirsoftSlot GetActiveSlot() const { return ActiveSlot; }
	int32 GetLocalMag() const;
	int32 GetLocalReserve() const;
	EAirsoftFireMode GetFireMode() const;
	float GetAimAlpha() const { return AimAlpha; }
	float GetSpread() const { return CurrentSpread; }
	bool IsReloading() const { return bLocalReloading; }
	float GetReloadProgress() const;
	bool IsScoped() const;
	bool IsAiming() const { return bAiming; }
	int32 GetGrenades() const { return Grenades; }
	bool IsLightOn() const { return bLightOn; }
	float GetTargetFOV(float BaseFOV) const;
	bool IsThrowing() const { return bThrowing; }
	bool HasFireMode(EAirsoftFireMode Mode) const { return Current().FireModes.Contains(Mode); }
	int32 GetLocalMagFor(EAirsoftSlot Slot) const { return LocalMag[SlotIndex(Slot)]; }
	int32 GetLocalReserveFor(EAirsoftSlot Slot) const { return LocalReserve[SlotIndex(Slot)]; }
	/** World time of the last shot this machine fired. */
	double GetLastShotTime() const { return LastShotTime; }

	UPROPERTY(ReplicatedUsing = OnRep_Loadout) FAirsoftLoadout Loadout;
	UPROPERTY(ReplicatedUsing = OnRep_ActiveSlot) EAirsoftSlot ActiveSlot = EAirsoftSlot::Primary;
	UPROPERTY(Replicated) int32 Grenades = 1;
	UPROPERTY(Replicated) bool bAiming = false;
	UPROPERTY(ReplicatedUsing = OnRep_Light) bool bLightOn = false;

	/** Rebuild first/third person gun visuals (team colour or loadout changed). */
	void RefreshVisuals();

	// --- RPCs ----------------------------------------------------------------
	UFUNCTION(Server, Reliable)
	void ServerFire(EAirsoftSlot Slot, int32 ShotId, FVector_NetQuantize Origin, const TArray<FVector_NetQuantizeNormal>& Directions);

	UFUNCTION(Server, Reliable)
	void ServerReportHit(int32 ShotId, uint8 Pellet, AActor* HitActor, FVector_NetQuantize HitLocation);

	UFUNCTION(Server, Reliable)
	void ServerReload(EAirsoftSlot Slot);

	UFUNCTION(Server, Reliable)
	void ServerEquip(EAirsoftSlot Slot);

	UFUNCTION(Server, Reliable)
	void ServerThrowGrenade(FVector_NetQuantize Origin, FVector_NetQuantizeNormal Direction);

	UFUNCTION(Server, Unreliable)
	void ServerSetAiming(bool bNewAiming);

	UFUNCTION(Server, Reliable)
	void ServerSetLight(bool bOn);

	UFUNCTION(NetMulticast, Unreliable)
	void MulticastShot(FVector_NetQuantize Origin, const TArray<FVector_NetQuantizeNormal>& Directions, float Speed, float Hop, float Drag, float Range, FName SoundKey, bool bQuiet);

	UFUNCTION(Client, Reliable)
	void ClientAmmo(EAirsoftSlot Slot, int32 Mag, int32 Reserve);

	UFUNCTION(Client, Reliable)
	void ClientHitConfirm();

protected:
	virtual void BeginPlay() override;

	UFUNCTION() void OnRep_Loadout();
	UFUNCTION() void OnRep_ActiveSlot();
	UFUNCTION() void OnRep_Light();

private:
	AAirsoftCharacter* GetCharacter() const;
	bool IsLocal() const;
	/** Locally controlled by a person (not a bot on the host): 2D sounds, viewmodel, hit markers. */
	bool IsLocalHuman() const;
	bool IsBotAuthority() const;
	bool CanAct() const;
	bool BeginThrow(const FVector& Direction);
	/** Positional gunshot (remote players and bots), distant variant when far from the local listener. */
	void PlayShotSound(const FVector& Muzzle, FName SoundKey, bool bQuiet) const;
	void TryFire();
	void FireOnce();
	void UpdateLocal(float DeltaTime);
	void UpdateViewmodel(float DeltaTime);
	void ApplyRecoil(float DeltaTime);
	void OnLocalBBHit(int32 ShotId, int32 Pellet, const FHitResult& Hit);
	void PlayAnim(FName Kind, float Duration, bool bEmpty = false);
	int32 SlotIndex(EAirsoftSlot Slot) const { return Slot == EAirsoftSlot::Secondary ? 1 : 0; }
	const FAirsoftCustomization& CustomizationFor(EAirsoftSlot Slot) const;
	void ServerFinishReload(EAirsoftSlot Slot);

	// Resolved stats per slot (attachments applied).
	FAirsoftWeaponDef Resolved[2];

	// Client-predicted ammo.
	int32 LocalMag[2] = { 0, 0 };
	int32 LocalReserve[2] = { 0, 0 };
	int32 FireModeIndex[2] = { 0, 0 };

	// Server-authoritative ammo.
	int32 ServerMag[2] = { 0, 0 };
	int32 ServerReserve[2] = { 0, 0 };
	bool bServerReloading[2] = { false, false };
	double ServerLastFire[2] = { 0.0, 0.0 };
	FTimerHandle ServerReloadTimer[2];

	struct FShotRecord
	{
		FAirsoftWeaponDef Weapon;
		FVector Origin;
		TArray<FVector> Directions;
		double Time = 0.0;
		uint32 UsedPellets = 0;
	};
	TMap<int32, FShotRecord> ServerShots;

	// Local state.
	bool bTriggerHeld = false;
	bool bFireQueued = false;
	bool bAimHeld = false;
	int32 BurstLeft = 0;
	int32 NextShotId = 0;
	double LastShotTime = 0.0;
	bool bLocalReloading = false;
	double ReloadStart = 0.0;
	float ReloadDuration = 0.f;
	FTimerHandle LocalReloadTimer;
	bool bThrowing = false;
	float AimAlpha = 0.f;
	float CurrentSpread = 0.f;
	float Bloom = 0.f;
	FVector2D RecoilOffset = FVector2D::ZeroVector;
	FVector2D RecoilTarget = FVector2D::ZeroVector;
	FRandomStream Rng;

	// Viewmodel animation.
	FName AnimKind;
	double AnimStart = 0.0;
	float AnimDuration = 0.f;
	bool bAnimEmpty = false;
	bool bSlideLocked = false;
	float SlideKick = 0.f;
	float Kick = 0.f;
	float SprintAlpha = 0.f;
	float SlideAlpha = 0.f;
	float BobTime = 0.f;
	FVector2D Sway = FVector2D::ZeroVector;
	FRotator LastControlRotation = FRotator::ZeroRotator;
	TSet<FName> FiredCues;

	// Effects: where this player's last BB struck an opponent, for the hit-confirm pop.
	FVector LastVictimHit = FVector::ZeroVector;
	double LastVictimHitTime = -100.0;
};
