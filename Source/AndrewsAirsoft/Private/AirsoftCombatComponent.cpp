#include "AirsoftCombatComponent.h"

#include "AirsoftAssets.h"
#include "AirsoftBallistics.h"
#include "AirsoftCharacter.h"
#include "AirsoftEffects.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameMode.h"
#include "AirsoftGameState.h"
#include "AirsoftGunVisual.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftPracticeTarget.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

namespace
{
	float Ease(float T)
	{
		T = FMath::Clamp(T, 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}

	float Window(float T, float A, float B)
	{
		return Ease((T - A) / FMath::Max(B - A, UE_KINDA_SMALL_NUMBER));
	}

	const FName KindDraw(TEXT("Draw"));
	const FName KindReload(TEXT("Reload"));
	const FName KindInspect(TEXT("Inspect"));
	const FName KindCycle(TEXT("Cycle"));
	const FName KindMelee(TEXT("Melee"));

	/** Semi-implicit spring toward Target, sub-stepped so a long frame can't blow it up. DampingRatio 1 = no overshoot. */
	void SpringStep(float& Value, float& Velocity, float Target, float Stiffness, float DampingRatio, float DeltaTime)
	{
		const float Omega = FMath::Sqrt(FMath::Max(Stiffness, 1.f));
		const int32 Steps = FMath::Clamp(FMath::CeilToInt(DeltaTime * 240.f), 1, 16);
		const float Dt = DeltaTime / Steps;
		for (int32 i = 0; i < Steps; ++i)
		{
			Velocity += (Stiffness * (Target - Value) - 2.f * DampingRatio * Omega * Velocity) * Dt;
			Value += Velocity * Dt;
		}
	}

	/** Reload choreography at time T (0..1), shared by the viewmodel and the third-person gun. */
	struct FReloadPose
	{
		/** 0..1: the gun tilts and dips toward the support hand, then comes back up. */
		float Tilt = 0.f;
		/** 0..1..0: the fresh mag slapped home (or a shell thumbed in) jolts the gun. */
		float Seat = 0.f;
		FTransform Mag = FTransform::Identity;
		FTransform Bolt = FTransform::Identity;
		/** Support hand travel in gun space, added to the gun's LeftHandLocal. */
		FVector Hand = FVector::ZeroVector;
		/** Pistols on an empty reload: slide position (1 = locked back); -1 leaves the slide alone. */
		float SlideBack = -1.f;
		/** 0..1..0: the slide slamming home after the slide stop is dropped. */
		float Release = 0.f;
	};

	FReloadPose ReloadPose(float T, bool bEmpty, bool bPistol, bool bTubeFed, const UAirsoftGunVisual* Gun)
	{
		FReloadPose P;
		P.Tilt = Window(T, 0.f, 0.18f) - Window(T, 0.82f, 1.f);
		if (bTubeFed)
		{
			// Shells (or the VSR's mag) thumbed in one at a time: the gun rocks with each push.
			P.Seat = (Window(T, 0.27f, 0.31f) - Window(T, 0.31f, 0.4f)) + (Window(T, 0.52f, 0.56f) - Window(T, 0.56f, 0.65f));
			return P;
		}
		// Mag drops out, fresh mag comes up and seats.
		const float Drop = Window(T, 0.18f, 0.4f);
		const float Insert = Window(T, 0.45f, 0.7f);
		if (T < 0.42f)
		{
			P.Mag = FTransform(FRotator(-10.f * Drop, 0.f, 25.f * Drop), FVector(-3.f * Drop, 0.f, -40.f * Drop * Drop));
		}
		else
		{
			const FTransform From(FRotator(0.f, 0.f, 20.f), FVector(-10.f, -6.f, -32.f));
			P.Mag.Blend(From, FTransform::Identity, Insert);
		}
		// Support hand leaves the handguard, strips the mag, fetches a fresh one and returns.
		const float Reach = Window(T, 0.08f, 0.2f) - Window(T, 0.72f, 0.86f);
		const FVector ToWell = Gun ? Gun->MagWellLocal - Gun->LeftHandLocal + FVector(0.f, -2.f, -10.f) : FVector(-16.f, -2.f, -12.f);
		P.Hand = ToWell * Reach + P.Mag.GetTranslation() * Reach;
		P.Seat = Window(T, 0.66f, 0.7f) - Window(T, 0.7f, 0.8f);
		if (bEmpty)
		{
			if (bPistol)
			{
				// Slide stop: the slide stays back until the thumb drops it, then slams home.
				P.SlideBack = 1.f - Window(T, 0.8f, 0.83f);
				P.Release = Window(T, 0.8f, 0.83f) - Window(T, 0.83f, 0.93f);
			}
			else
			{
				const float Charge = Window(T, 0.74f, 0.82f) - Window(T, 0.82f, 0.9f);
				P.Bolt.SetTranslation(FVector(-6.f * Charge, 0.f, 0.f));
			}
		}
		return P;
	}

	/** Sound cues of a reload, fired once each as T passes them. */
	template <typename FCueFn>
	void ReloadCues(float T, bool bTubeFed, bool bEmpty, bool bPistol, FCueFn&& Cue)
	{
		if (bTubeFed)
		{
			Cue(TEXT("Click1"), 0.3f, TEXT("MagIn"), 1.4f);
			Cue(TEXT("Click2"), 0.55f, TEXT("MagIn"), 1.3f);
			return;
		}
		Cue(TEXT("Out"), 0.2f, TEXT("MagOut"), 1.f);
		Cue(TEXT("In"), 0.68f, TEXT("MagIn"), 1.f);
		if (bEmpty)
		{
			Cue(TEXT("Charge"), 0.8f, TEXT("BoltCycle"), bPistol ? 1.35f : 1.1f);
		}
	}

	/** Melee at time T: wind-up, then the blow (contact at ~40%), then recovery. Camera / aim space: X forward, Y right, Z up. */
	void MeleePose(float T, bool bPistol, FVector& Loc, FRotator& Rot)
	{
		const float Wind = Window(T, 0.f, 0.3f) - Window(T, 0.3f, 0.45f);
		const float Strike = Window(T, 0.3f, 0.45f) - Window(T, 0.6f, 1.f);
		if (bPistol)
		{
			// Pistol whip: cock the gun up and out, then chop down and across with the frame.
			Loc += FVector(-3.f, 5.f, 7.f) * Wind + FVector(12.f, -8.f, -5.f) * Strike;
			Rot += FRotator(28.f, 12.f, -55.f) * Wind + FRotator(-30.f, -25.f, -85.f) * Strike;
		}
		else
		{
			// Rifle butt-stroke: the muzzle swings right as the stock comes round, then drives forward-left.
			Loc += FVector(-5.f, 7.f, -1.f) * Wind + FVector(15.f, -13.f, 4.f) * Strike;
			Rot += FRotator(-8.f, 30.f, 18.f) * Wind + FRotator(-12.f, 78.f, -30.f) * Strike;
		}
	}

	bool IsTubeFed(const FAirsoftWeaponDef& W)
	{
		return W.Id == TEXT("M870") || W.Id == TEXT("VSR");
	}

	constexpr float MaxOriginOffset = 250.f;   // cm between eyes and reported shot origin
	constexpr float HitTolerance = 160.f;      // cm between reported hit and victim
	constexpr float AngleToleranceDeg = 14.f;  // BB arc + latency
	constexpr double ShotHistory = 5.0;
	constexpr float FarGunfireDistance = 4000.f; // cm; beyond this remote shots use the distant variant

	/** Gunfire key for this listener: cinematic (default) or airsoft set, distant variant when far away. */
	FName GunSoundKey(const UObject* Context, FName Base, bool bFar)
	{
		bool bCinematic = true;
		if (const UWorld* World = Context ? Context->GetWorld() : nullptr)
		{
			if (UAirsoftGameInstance* GI = World->GetGameInstance<UAirsoftGameInstance>())
			{
				bCinematic = GI->GetUserSettings().bCinematicGunSounds;
			}
		}
		if (!bCinematic)
		{
			const FName Airsoft(*(Base.ToString() + TEXT("_Airsoft")));
			return AirsoftAssets::Sound(Airsoft) ? Airsoft : Base;
		}
		if (bFar)
		{
			const FName Far(*(Base.ToString() + TEXT("_Far")));
			return AirsoftAssets::Sound(Far) ? Far : Base;
		}
		return Base;
	}
}

UAirsoftCombatComponent::UAirsoftCombatComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.TickGroup = TG_PostPhysics;
	SetIsReplicatedByDefault(true);
	Rng.GenerateNewSeed();
}

void UAirsoftCombatComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(UAirsoftCombatComponent, Loadout);
	DOREPLIFETIME(UAirsoftCombatComponent, ActiveSlot);
	DOREPLIFETIME(UAirsoftCombatComponent, Grenades);
	DOREPLIFETIME_CONDITION(UAirsoftCombatComponent, bAiming, COND_SkipOwner);
	DOREPLIFETIME(UAirsoftCombatComponent, bLightOn);
}

void UAirsoftCombatComponent::BeginPlay()
{
	Super::BeginPlay();
	Resolved[0] = AirsoftWeapons::Resolve(Loadout.Primary);
	Resolved[1] = AirsoftWeapons::Resolve(Loadout.Secondary);
}

AAirsoftCharacter* UAirsoftCombatComponent::GetCharacter() const
{
	return Cast<AAirsoftCharacter>(GetOwner());
}

bool UAirsoftCombatComponent::IsLocal() const
{
	const APawn* Pawn = Cast<APawn>(GetOwner());
	return Pawn && Pawn->IsLocallyControlled();
}

bool UAirsoftCombatComponent::IsLocalHuman() const
{
	const AAirsoftCharacter* C = GetCharacter();
	return C && C->IsLocalHuman();
}

bool UAirsoftCombatComponent::IsBotAuthority() const
{
	// Bots only exist on the server, where their pawn counts as locally controlled.
	const AActor* OwnerActor = GetOwner();
	return OwnerActor && OwnerActor->HasAuthority() && IsLocal() && !IsLocalHuman();
}

bool UAirsoftCombatComponent::CanAct() const
{
	const AAirsoftCharacter* C = GetCharacter();
	if (!C || C->IsOut() || C->IsFrozen())
	{
		return false;
	}
	if (const AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(C->GetController()))
	{
		if (PC->IsMenuOpen())
		{
			return false;
		}
	}
	return true;
}

const FAirsoftCustomization& UAirsoftCombatComponent::CustomizationFor(EAirsoftSlot Slot) const
{
	return Slot == EAirsoftSlot::Secondary ? Loadout.Secondary : Loadout.Primary;
}

const FAirsoftWeaponDef& UAirsoftCombatComponent::Current() const
{
	return Resolved[SlotIndex(ActiveSlot)];
}

const FAirsoftCustomization& UAirsoftCombatComponent::CurrentCustomization() const
{
	return CustomizationFor(ActiveSlot);
}

int32 UAirsoftCombatComponent::GetLocalMag() const { return LocalMag[SlotIndex(ActiveSlot)]; }
int32 UAirsoftCombatComponent::GetLocalReserve() const { return LocalReserve[SlotIndex(ActiveSlot)]; }

EAirsoftFireMode UAirsoftCombatComponent::GetFireMode() const
{
	const FAirsoftWeaponDef& W = Current();
	if (W.FireModes.Num() == 0)
	{
		return EAirsoftFireMode::Semi;
	}
	return W.FireModes[FMath::Clamp(FireModeIndex[SlotIndex(ActiveSlot)], 0, W.FireModes.Num() - 1)];
}

float UAirsoftCombatComponent::GetReloadProgress() const
{
	if (!bLocalReloading || ReloadDuration <= 0.f)
	{
		return 0.f;
	}
	return FMath::Clamp(static_cast<float>((GetWorld()->GetTimeSeconds() - ReloadStart) / ReloadDuration), 0.f, 1.f);
}

bool UAirsoftCombatComponent::IsScoped() const
{
	return Current().bScopeOverlay && AimAlpha > 0.92f;
}

float UAirsoftCombatComponent::GetTargetFOV(float BaseFOV) const
{
	const float AimFOV = BaseFOV * (Current().AimFOV / 75.f);
	const float Eased = 1.f - FMath::Square(1.f - AimAlpha);
	return FMath::Lerp(BaseFOV, AimFOV, Eased);
}

// ---------------------------------------------------------------------------
// Loadout and visuals
// ---------------------------------------------------------------------------

void UAirsoftCombatComponent::ServerInitLoadout(const FAirsoftLoadout& InLoadout)
{
	check(GetOwner()->HasAuthority());
	Loadout.Primary = AirsoftWeapons::Clean(InLoadout.Primary);
	Loadout.Secondary = AirsoftWeapons::Clean(InLoadout.Secondary);
	if (!AirsoftWeapons::Find(Loadout.Primary.WeaponId) || !AirsoftWeapons::Find(Loadout.Secondary.WeaponId))
	{
		Loadout = AirsoftWeapons::DefaultLoadout();
	}
	Resolved[0] = AirsoftWeapons::Resolve(Loadout.Primary);
	Resolved[1] = AirsoftWeapons::Resolve(Loadout.Secondary);
	for (int32 i = 0; i < 2; ++i)
	{
		ServerMag[i] = Resolved[i].MagSize;
		ServerReserve[i] = Resolved[i].Reserve;
		bServerReloading[i] = false;
		LocalMag[i] = ServerMag[i];
		LocalReserve[i] = ServerReserve[i];
		ClientAmmo(i == 0 ? EAirsoftSlot::Primary : EAirsoftSlot::Secondary, ServerMag[i], ServerReserve[i]);
	}
	Grenades = AirsoftWeapons::GrenadesPerLife;
	ActiveSlot = EAirsoftSlot::Primary;
	ServerShots.Reset();
	RefreshVisuals();
}

void UAirsoftCombatComponent::ServerGiveAmmo(float Mags)
{
	if (!GetOwner()->HasAuthority() || Mags <= 0.f)
	{
		return;
	}
	for (int32 i = 0; i < 2; ++i)
	{
		const int32 Add = FMath::Max(1, FMath::RoundToInt(Resolved[i].MagSize * Mags));
		// Never more than the gun's full starting reserve.
		ServerReserve[i] = FMath::Min(ServerReserve[i] + Add, FMath::Max(Resolved[i].Reserve, Resolved[i].MagSize));
		ClientAmmo(i == 0 ? EAirsoftSlot::Primary : EAirsoftSlot::Secondary, ServerMag[i], ServerReserve[i]);
	}
}

void UAirsoftCombatComponent::OnRep_Loadout()
{
	Resolved[0] = AirsoftWeapons::Resolve(Loadout.Primary);
	Resolved[1] = AirsoftWeapons::Resolve(Loadout.Secondary);
	RefreshVisuals();
}

void UAirsoftCombatComponent::OnRep_ActiveSlot()
{
	RefreshVisuals();
}

void UAirsoftCombatComponent::OnRep_Light()
{
	if (AAirsoftCharacter* C = GetCharacter())
	{
		C->GetFPGun()->SetLightOn(bLightOn);
		C->GetTPGun()->SetLightOn(bLightOn);
	}
}

void UAirsoftCombatComponent::RefreshVisuals()
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || ActiveSlot == EAirsoftSlot::Grenade)
	{
		return;
	}
	const FLinearColor Accent = AirsoftColors::Team(C->GetTeam());
	const FAirsoftCustomization& Custom = CustomizationFor(ActiveSlot);
	if (GetNetMode() != NM_DedicatedServer)
	{
		C->GetFPGun()->Build(Custom, Accent, true, false);
		C->GetTPGun()->Build(Custom, Accent, false, true);
		C->GetFPGun()->SetLightOn(bLightOn);
		C->GetTPGun()->SetLightOn(bLightOn);
	}
	if (IsLocal())
	{
		bSlideLocked = Resolved[SlotIndex(ActiveSlot)].Class == TEXT("Pistol") && LocalMag[SlotIndex(ActiveSlot)] <= 0;
		PlayAnim(KindDraw, 0.38f);
	}
}

// ---------------------------------------------------------------------------
// Local input
// ---------------------------------------------------------------------------

void UAirsoftCombatComponent::StartFire()
{
	bTriggerHeld = true;
	bFireQueued = true;
	TryFire();
}

void UAirsoftCombatComponent::StopFire()
{
	bTriggerHeld = false;
}

void UAirsoftCombatComponent::SetAimHeld(bool bHeld)
{
	bAimHeld = bHeld;
}

void UAirsoftCombatComponent::ToggleAim()
{
	bAimHeld = !bAimHeld;
}

void UAirsoftCombatComponent::CancelActions()
{
	bTriggerHeld = false;
	bAimHeld = false;
	BurstLeft = 0;
}

void UAirsoftCombatComponent::CycleFireMode()
{
	const FAirsoftWeaponDef& W = Current();
	if (W.FireModes.Num() < 2)
	{
		return;
	}
	const int32 Idx = SlotIndex(ActiveSlot);
	FireModeIndex[Idx] = (FireModeIndex[Idx] + 1) % W.FireModes.Num();
	BurstLeft = 0;
	AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.4f, 1.3f);
}

void UAirsoftCombatComponent::EquipSlot(EAirsoftSlot Slot)
{
	if (!CanAct() || bThrowing || Slot == ActiveSlot || Slot == EAirsoftSlot::Grenade)
	{
		return;
	}
	GetWorld()->GetTimerManager().ClearTimer(LocalReloadTimer);
	bLocalReloading = false;
	BurstLeft = 0;
	ActiveSlot = Slot; // predicted locally; server confirms
	RefreshVisuals();
	ServerEquip(Slot);
}

void UAirsoftCombatComponent::CycleWeapon()
{
	EquipSlot(ActiveSlot == EAirsoftSlot::Primary ? EAirsoftSlot::Secondary : EAirsoftSlot::Primary);
}

void UAirsoftCombatComponent::ToggleLight()
{
	if (!Current().Id.IsNone() && CurrentCustomization().Laser == TEXT("Laser"))
	{
		bLightOn = !bLightOn;
		OnRep_Light();
		ServerSetLight(bLightOn);
		AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.4f, 1.6f);
	}
}

void UAirsoftCombatComponent::Inspect()
{
	if (CanAct() && !bLocalReloading && AimAlpha < 0.1f && AnimKind.IsNone())
	{
		PlayAnim(KindInspect, 2.6f);
	}
}

bool UAirsoftCombatComponent::IsMeleeing() const
{
	return AnimKind == KindMelee;
}

void UAirsoftCombatComponent::Melee()
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || !CanAct() || bLocalReloading || bThrowing || AnimKind == KindMelee || AnimKind == KindCycle || ActiveSlot == EAirsoftSlot::Grenade)
	{
		return;
	}
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	if (GS && (GS->Phase == EAirsoftPhase::Briefing || GS->Phase == EAirsoftPhase::PostRound))
	{
		return;
	}
	const FAirsoftViewmodelTuning& VM = UAirsoftSettings::Get()->Viewmodel;
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - LastMeleeTime < VM.MeleeCooldown)
	{
		return;
	}
	LastMeleeTime = Now;
	bTriggerHeld = false;
	BurstLeft = 0;
	C->CancelSprint();
	PlayAnim(KindMelee, VM.MeleeDuration);
	if (IsLocalHuman())
	{
		AirsoftAssets::Play2D(this, TEXT("ReplayWhoosh"), 0.35f, Rng.FRandRange(1.5f, 1.7f));
	}
	// The blow lands at the end of the wind-up.
	GetWorld()->GetTimerManager().SetTimer(MeleeTimer, FTimerDelegate::CreateWeakLambda(this, [this]()
	{
		MeleeStrike();
	}), VM.MeleeDuration * 0.4f, false);
}

void UAirsoftCombatComponent::MeleeStrike()
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || C->IsOut() || !C->GetCamera())
	{
		return;
	}
	const FAirsoftViewmodelTuning& VM = UAirsoftSettings::Get()->Viewmodel;
	const FVector Eye = C->GetCamera()->GetComponentLocation();
	const FVector End = Eye + C->GetControlRotation().Vector() * VM.MeleeRange;
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftMelee), false);
	Query.AddIgnoredActor(C);

	// A fat sweep against bodies (forgiving aim at arm's length), nearest first.
	TArray<FHitResult> Hits;
	GetWorld()->SweepMultiByObjectType(Hits, Eye, End, FQuat::Identity, FCollisionObjectQueryParams(ECC_Pawn), FCollisionShape::MakeSphere(22.f), Query);
	AAirsoftCharacter* Victim = nullptr;
	FVector ImpactPoint = End;
	for (const FHitResult& Hit : Hits)
	{
		AAirsoftCharacter* Other = Cast<AAirsoftCharacter>(Hit.GetActor());
		if (Other && Other != C && !Other->IsOut() && AAirsoftGameState::CanTag(this, C->GetTeam(), Other->GetTeam()))
		{
			Victim = Other;
			ImpactPoint = Hit.ImpactPoint;
			break;
		}
	}
	if (Victim)
	{
		// The sweep can reach round a thin wall edge; if something solid is in the way, the wall takes the blow.
		FCollisionQueryParams WallQuery(SCENE_QUERY_STAT(AirsoftMeleeWall), false);
		WallQuery.AddIgnoredActor(C);
		WallQuery.AddIgnoredActor(Victim);
		FHitResult Block;
		if (GetWorld()->LineTraceSingleByChannel(Block, Eye, ImpactPoint, ECC_Visibility, WallQuery) && !Cast<APawn>(Block.GetActor()))
		{
			Victim = nullptr;
		}
	}
	const bool bHuman = IsLocalHuman();
	if (Victim)
	{
		ServerMelee(Victim);
		if (bHuman)
		{
			AirsoftAssets::Play2D(this, TEXT("Impact"), 0.85f, 0.7f);
			C->AddViewShake(0.35f, 0.6f);
		}
		else
		{
			AirsoftAssets::Play3D(this, TEXT("Impact"), ImpactPoint, 0.85f, 0.7f);
		}
		return;
	}
	// Nothing to hit: a thud if the gun meets a wall, otherwise just the swing.
	FHitResult Wall;
	if (GetWorld()->LineTraceSingleByChannel(Wall, Eye, End, ECC_Visibility, Query))
	{
		AirsoftAssets::Play3D(this, TEXT("Impact"), Wall.ImpactPoint, 0.5f, 0.55f);
		if (bHuman)
		{
			C->AddViewShake(0.2f);
		}
	}
}

void UAirsoftCombatComponent::Reload()
{
	if (!CanAct() || bLocalReloading || bThrowing || AnimKind == KindMelee)
	{
		return;
	}
	const int32 Idx = SlotIndex(ActiveSlot);
	const FAirsoftWeaponDef& W = Resolved[Idx];
	if (LocalMag[Idx] >= W.MagSize || LocalReserve[Idx] <= 0)
	{
		return;
	}
	const bool bEmpty = LocalMag[Idx] == 0;
	bLocalReloading = true;
	BurstLeft = 0;
	ReloadStart = GetWorld()->GetTimeSeconds();
	ReloadDuration = bEmpty ? W.EmptyReloadTime : W.ReloadTime;
	PlayAnim(KindReload, ReloadDuration, bEmpty);
	ServerReload(ActiveSlot);

	const EAirsoftSlot Slot = ActiveSlot;
	GetWorld()->GetTimerManager().SetTimer(LocalReloadTimer, FTimerDelegate::CreateWeakLambda(this, [this, Slot]()
	{
		bLocalReloading = false;
		const int32 I = SlotIndex(Slot);
		// Predict the result; the server's ClientAmmo corrects it if needed.
		const int32 Take = FMath::Min(Resolved[I].MagSize - LocalMag[I], LocalReserve[I]);
		LocalMag[I] += Take;
		LocalReserve[I] -= Take;
		if (LocalMag[I] > 0)
		{
			bSlideLocked = false;
		}
	}), ReloadDuration, false);
}

void UAirsoftCombatComponent::ThrowGrenade()
{
	if (const AAirsoftCharacter* C = GetCharacter())
	{
		BeginThrow((C->GetControlRotation().Vector() + FVector(0.f, 0.f, 0.15f)).GetSafeNormal());
	}
}

bool UAirsoftCombatComponent::BeginThrow(const FVector& Direction)
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || !CanAct() || bThrowing || Grenades <= 0)
	{
		return false;
	}
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	if (GS && GS->Phase != EAirsoftPhase::Live)
	{
		return false;
	}
	bThrowing = true;
	PlayAnim(KindInspect, 0.6f);
	const FVector Origin = C->GetCamera()->GetComponentLocation();
	const FVector Dir = Direction.GetSafeNormal();
	const bool bHuman = IsLocalHuman();
	FTimerHandle Handle;
	GetWorld()->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, Origin, Dir, bHuman]()
	{
		ServerThrowGrenade(Origin, Dir);
		if (bHuman)
		{
			AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.5f, 0.6f);
		}
		bThrowing = false;
	}), 0.3f, false);
	return true;
}

// ---------------------------------------------------------------------------
// Bot input (server only)
// ---------------------------------------------------------------------------

void UAirsoftCombatComponent::BotPullTrigger()
{
	if (!IsBotAuthority())
	{
		return;
	}
	if (AAirsoftCharacter* C = GetCharacter())
	{
		C->CancelSprint();
	}
	StartFire();
}

void UAirsoftCombatComponent::BotReleaseTrigger()
{
	if (IsBotAuthority())
	{
		StopFire();
	}
}

void UAirsoftCombatComponent::BotSetAim(bool bAim)
{
	if (IsBotAuthority())
	{
		SetAimHeld(bAim);
	}
}

bool UAirsoftCombatComponent::BotReload()
{
	if (!IsBotAuthority() || bLocalReloading)
	{
		return false;
	}
	Reload();
	return bLocalReloading;
}

void UAirsoftCombatComponent::BotEquip(EAirsoftSlot Slot)
{
	if (IsBotAuthority())
	{
		EquipSlot(Slot);
	}
}

void UAirsoftCombatComponent::BotSetFireMode(EAirsoftFireMode Mode)
{
	if (!IsBotAuthority())
	{
		return;
	}
	const int32 Index = Current().FireModes.IndexOfByKey(Mode);
	const int32 Slot = SlotIndex(ActiveSlot);
	if (Index != INDEX_NONE && FireModeIndex[Slot] != Index)
	{
		FireModeIndex[Slot] = Index;
		BurstLeft = 0;
	}
}

bool UAirsoftCombatComponent::BotThrowGrenade(const FVector& Direction)
{
	return IsBotAuthority() && BeginThrow(Direction);
}

// ---------------------------------------------------------------------------
// Firing
// ---------------------------------------------------------------------------

void UAirsoftCombatComponent::TryFire()
{
	if (!CanAct() || bLocalReloading || bThrowing || ActiveSlot == EAirsoftSlot::Grenade)
	{
		return;
	}
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	if (GS && (GS->Phase == EAirsoftPhase::Briefing || GS->Phase == EAirsoftPhase::PostRound))
	{
		return;
	}
	const AAirsoftCharacter* C = GetCharacter();
	if (C && C->IsSprinting())
	{
		return;
	}
	const FAirsoftWeaponDef& W = Current();
	if (GetWorld()->GetTimeSeconds() - LastShotTime < W.FireInterval)
	{
		return;
	}
	if (AnimKind == KindCycle || AnimKind == KindMelee)
	{
		return;
	}
	const EAirsoftFireMode Mode = GetFireMode();
	if (Mode == EAirsoftFireMode::Burst)
	{
		if (BurstLeft <= 0)
		{
			if (!bFireQueued)
			{
				return;
			}
			bFireQueued = false;
			BurstLeft = 3;
		}
		--BurstLeft;
	}
	else if (Mode != EAirsoftFireMode::Auto)
	{
		if (!bFireQueued)
		{
			return;
		}
		bFireQueued = false;
	}
	FireOnce();
}

void UAirsoftCombatComponent::FireOnce()
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C)
	{
		return;
	}
	const int32 Idx = SlotIndex(ActiveSlot);
	const FAirsoftWeaponDef& W = Resolved[Idx];
	const bool bHuman = IsLocalHuman();
	if (LocalMag[Idx] <= 0)
	{
		if (bHuman)
		{
			AirsoftAssets::Play2D(this, TEXT("DryFire"), 0.5f, 1.2f);
		}
		bTriggerHeld = false;
		BurstLeft = 0;
		if (LocalReserve[Idx] > 0)
		{
			Reload();
		}
		return;
	}

	LastShotTime = GetWorld()->GetTimeSeconds();
	--LocalMag[Idx];
	const int32 ShotId = ++NextShotId;

	FVector Origin = C->GetCamera()->GetComponentLocation();
	// A bot's camera is never anyone's view target, so it never picks up the control rotation:
	// bots shoot along their control rotation directly (the same thing the camera shows a human).
	FVector Look = bHuman ? C->GetCamera()->GetForwardVector() : C->GetControlRotation().Vector();
	// Third person (hip fire; aiming goes to the eye): the crosshair point comes from the over-the-shoulder view,
	// but the BB leaves the third-person muzzle toward it, so the camera can't shoot round a corner the gun can't see.
	// The origin stays within the server's MaxOriginOffset of the eyes; ServerFire's checks are unchanged.
	const bool bShoulder = bHuman && C->IsThirdPersonView();
	if (bShoulder)
	{
		const FAirsoftShoulderAim Aim = C->ComputeShoulderAim(W.MaxRange);
		if (Aim.bValid)
		{
			Origin = Aim.Origin;
			Look = Aim.Direction;
		}
	}
	TArray<FVector_NetQuantizeNormal> Dirs;
	for (int32 i = 0; i < W.Pellets; ++i)
	{
		Dirs.Add(AirsoftBallistics::Spread(Look, CurrentSpread, Rng));
	}
	ServerFire(ActiveSlot, ShotId, Origin, Dirs);

	// Everyone else sees a bot's third-person gun, so its tracers start there (and so do yours in third person).
	const bool bViewmodel = bHuman && !bShoulder;
	const FVector Muzzle = bViewmodel ? C->GetFPGun()->GetMuzzleWorld() : C->GetTPGun()->GetMuzzleWorld();
	// Effects: muzzle puff on the viewmodel (none while the scope overlay hides it) or the third-person gun.
	if (UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this))
	{
		if (!bViewmodel || !IsScoped())
		{
			const UAirsoftGunVisual* Gun = bViewmodel ? C->GetFPGun() : C->GetTPGun();
			FX->MuzzlePuff(Muzzle, Gun->GetForwardVector(), W, W.bQuiet, bViewmodel, AimAlpha);
		}
	}
	if (UAirsoftBBSubsystem* BBs = GetWorld()->GetSubsystem<UAirsoftBBSubsystem>())
	{
		const FLinearColor Color = AirsoftColors::Team(C->GetTeam());
		for (int32 i = 0; i < Dirs.Num(); ++i)
		{
			FAirsoftBBParams P;
			P.Origin = Origin;
			P.Direction = Dirs[i];
			P.Speed = W.MuzzleVelocity;
			P.Hop = W.Hop;
			P.Drag = W.Drag;
			P.MaxRange = W.MaxRange;
			P.VisualStart = Muzzle;
			P.bHasVisualStart = true;
			P.Color = Color;
			P.IgnoreActors.Add(C);
			TWeakObjectPtr<UAirsoftCombatComponent> WeakThis(this);
			const int32 Pellet = i;
			P.OnHit = [WeakThis, ShotId, Pellet](const FHitResult& Hit)
			{
				if (WeakThis.IsValid())
				{
					WeakThis->OnLocalBBHit(ShotId, Pellet, Hit);
				}
			};
			BBs->Fire(MoveTemp(P));
		}
	}

	if (bHuman)
	{
		AirsoftAssets::Play2D(this, GunSoundKey(this, W.Sound, false), W.bQuiet ? 0.45f : 0.75f, Rng.FRandRange(0.96f, 1.05f));
	}
	else
	{
		// A bot on the host: the host hears it like any other player's gun (the multicast skips this machine).
		PlayShotSound(Muzzle, W.Sound, W.bQuiet);
	}
	{
		// Recoil springs (viewmodel and third-person gun): an impulse per shot, so bursts stack and each shot settles back.
		const FAirsoftViewmodelTuning& VM = UAirsoftSettings::Get()->Viewmodel;
		const float Impulse = W.RecoilUp * 0.35f * FMath::Sqrt(FMath::Max(VM.RecoilSpringStiffness, 1.f)) * 2.f;
		if (bHuman)
		{
			KickVel += Impulse;
		}
		TPKickVel += Impulse;
		KickRollSide = Rng.FRand() < 0.5f ? -1.f : 1.f;
	}
	SlideKick = 1.f;
	if (AnimKind == KindInspect)
	{
		AnimKind = NAME_None;
	}
	const float RecoilScale = (1.f - AimAlpha * 0.35f) * (C->bIsCrouched ? 0.8f : 1.f);
	RecoilTarget += FVector2D(W.RecoilUp * RecoilScale, Rng.FRandRange(-W.RecoilSide, W.RecoilSide) * RecoilScale);
	Bloom = FMath::Min(Bloom + W.HipSpread * 0.12f, 2.5f);

	if (W.FireModes.Num() > 0 && (W.FireModes[0] == EAirsoftFireMode::Bolt || W.FireModes[0] == EAirsoftFireMode::Pump))
	{
		PlayAnim(KindCycle, W.FireInterval * 0.85f);
	}
	if (W.Class == TEXT("Pistol") && LocalMag[Idx] <= 0)
	{
		bSlideLocked = true;
	}
	if (LocalMag[Idx] <= 0 && LocalReserve[Idx] > 0)
	{
		FTimerHandle Handle;
		GetWorld()->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this]()
		{
			if (GetLocalMag() <= 0)
			{
				Reload();
			}
		}), 0.25f, false);
	}
}

void UAirsoftCombatComponent::OnLocalBBHit(int32 ShotId, int32 Pellet, const FHitResult& Hit)
{
	AActor* HitActor = Hit.GetActor();
	AAirsoftCharacter* Me = GetCharacter();
	if (AAirsoftCharacter* Victim = Cast<AAirsoftCharacter>(HitActor))
	{
		LastVictimHit = Hit.ImpactPoint;
		LastVictimHitTime = GetWorld()->GetTimeSeconds();
		if (Me && Victim != Me && !Victim->IsOut() && AAirsoftGameState::CanTag(this, Me->GetTeam(), Victim->GetTeam()))
		{
			ServerReportHit(ShotId, static_cast<uint8>(Pellet), Victim, Hit.ImpactPoint);
		}
		return;
	}
	if (AAirsoftPracticeTarget* Target = Cast<AAirsoftPracticeTarget>(HitActor))
	{
		Target->Ding(Hit.ImpactPoint);
		if (AAirsoftPlayerController* PC = Me ? Cast<AAirsoftPlayerController>(Me->GetController()) : nullptr)
		{
			PC->ShowHitMarker(false);
		}
		return;
	}
	AirsoftAssets::Play3D(this, TEXT("Impact"), Hit.ImpactPoint, 0.35f, Rng.FRandRange(0.9f, 1.2f));
}

void UAirsoftCombatComponent::ServerFire_Implementation(EAirsoftSlot Slot, int32 ShotId, FVector_NetQuantize Origin, const TArray<FVector_NetQuantizeNormal>& Directions)
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || C->IsOut() || C->IsFrozen() || Slot == EAirsoftSlot::Grenade)
	{
		return;
	}
	const int32 Idx = SlotIndex(Slot);
	const FAirsoftWeaponDef& W = Resolved[Idx];
	if (Slot != ActiveSlot || Directions.Num() != W.Pellets || Directions.Num() == 0)
	{
		return;
	}
	if (FVector::Dist(C->GetCamera()->GetComponentLocation(), Origin) > MaxOriginOffset)
	{
		return;
	}
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - ServerLastFire[Idx] < W.FireInterval * 0.7)
	{
		return;
	}
	if (ServerMag[Idx] <= 0 || bServerReloading[Idx])
	{
		ClientAmmo(Slot, ServerMag[Idx], ServerReserve[Idx]);
		return;
	}
	--ServerMag[Idx];
	ServerLastFire[Idx] = Now;

	if (AAirsoftPlayerState* PS = C->GetAirsoftPlayerState())
	{
		PS->ProtectedUntil = 0.f; // firing ends spawn protection
	}

	for (auto It = ServerShots.CreateIterator(); It; ++It)
	{
		if (Now - It.Value().Time > ShotHistory)
		{
			It.RemoveCurrent();
		}
	}
	FShotRecord& Rec = ServerShots.Add(ShotId);
	Rec.Weapon = W;
	Rec.Origin = Origin;
	Rec.Time = Now;
	for (const FVector_NetQuantizeNormal& D : Directions)
	{
		Rec.Directions.Add(FVector(D).GetSafeNormal());
	}

	MulticastShot(Origin, Directions, W.MuzzleVelocity, W.Hop, W.Drag, W.MaxRange, W.Sound, W.bQuiet);

	// Bots hear the shot (and notice BBs passing close by).
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		GM->NotifyShotFired(C, Origin, Rec.Directions[0], W.bQuiet);
	}
}

void UAirsoftCombatComponent::ServerReportHit_Implementation(int32 ShotId, uint8 Pellet, AActor* HitActor, FVector_NetQuantize HitLocation)
{
	FShotRecord* Shot = ServerShots.Find(ShotId);
	AAirsoftCharacter* Victim = Cast<AAirsoftCharacter>(HitActor);
	AAirsoftCharacter* Me = GetCharacter();
	if (!Shot || !Victim || !Me || Victim == Me || Pellet >= Shot->Directions.Num() || (Shot->UsedPellets & (1u << Pellet)))
	{
		return;
	}
	const FAirsoftWeaponDef& W = Shot->Weapon;
	const double Elapsed = GetWorld()->GetTimeSeconds() - Shot->Time;
	if (Elapsed > AirsoftBallistics::MaxFlightTime(W.MuzzleVelocity, W.MaxRange) + 0.6)
	{
		return;
	}
	const FVector ToHit = FVector(HitLocation) - Shot->Origin;
	const float Distance = ToHit.Size();
	if (Distance > W.MaxRange + 200.f)
	{
		return;
	}
	if (FVector::Dist(Victim->GetActorLocation(), HitLocation) > HitTolerance)
	{
		return;
	}
	if (Distance > 150.f)
	{
		const float AngleDeg = static_cast<float>(FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(ToHit / Distance, Shot->Directions[Pellet]), -1.0, 1.0))));
		if (AngleDeg > AngleToleranceDeg + W.HipSpread)
		{
			return;
		}
	}
	// Line of sight: nothing solid on the first 85% of the straight line (BBs arc).
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftHitCheck), false);
	Query.AddIgnoredActor(Me);
	Query.AddIgnoredActor(Victim);
	FHitResult Block;
	if (GetWorld()->LineTraceSingleByChannel(Block, Shot->Origin, Shot->Origin + ToHit * 0.85f, ECC_Visibility, Query))
	{
		if (!Cast<APawn>(Block.GetActor()))
		{
			return;
		}
	}
	Shot->UsedPellets |= (1u << Pellet);
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		if (GM->HandleHit(Me->GetController(), Victim->GetController(), W.Id, FVector(HitLocation)))
		{
			ClientHitConfirm();
		}
	}
}

void UAirsoftCombatComponent::ServerReload_Implementation(EAirsoftSlot Slot)
{
	if (Slot == EAirsoftSlot::Grenade)
	{
		return;
	}
	const int32 Idx = SlotIndex(Slot);
	const FAirsoftWeaponDef& W = Resolved[Idx];
	if (bServerReloading[Idx] || ServerMag[Idx] >= W.MagSize || ServerReserve[Idx] <= 0)
	{
		ClientAmmo(Slot, ServerMag[Idx], ServerReserve[Idx]);
		return;
	}
	bServerReloading[Idx] = true;
	const float Duration = (ServerMag[Idx] == 0 ? W.EmptyReloadTime : W.ReloadTime) * 0.9f;
	GetWorld()->GetTimerManager().SetTimer(ServerReloadTimer[Idx], FTimerDelegate::CreateWeakLambda(this, [this, Slot]()
	{
		ServerFinishReload(Slot);
	}), Duration, false);
}

void UAirsoftCombatComponent::ServerFinishReload(EAirsoftSlot Slot)
{
	const int32 Idx = SlotIndex(Slot);
	bServerReloading[Idx] = false;
	const int32 Take = FMath::Min(Resolved[Idx].MagSize - ServerMag[Idx], ServerReserve[Idx]);
	ServerMag[Idx] += Take;
	ServerReserve[Idx] -= Take;
	ClientAmmo(Slot, ServerMag[Idx], ServerReserve[Idx]);
}

void UAirsoftCombatComponent::ServerEquip_Implementation(EAirsoftSlot Slot)
{
	if (Slot == EAirsoftSlot::Grenade || Slot == ActiveSlot)
	{
		return;
	}
	ActiveSlot = Slot;
	RefreshVisuals();
}

void UAirsoftCombatComponent::ServerThrowGrenade_Implementation(FVector_NetQuantize Origin, FVector_NetQuantizeNormal Direction)
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || C->IsOut() || C->IsFrozen() || Grenades <= 0)
	{
		return;
	}
	if (FVector::Dist(C->GetCamera()->GetComponentLocation(), Origin) > MaxOriginOffset)
	{
		return;
	}
	--Grenades;
	if (AAirsoftPlayerState* PS = C->GetAirsoftPlayerState())
	{
		PS->ProtectedUntil = 0.f;
	}
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		GM->SpawnGrenade(C->GetController(), Origin, Direction);
	}
}

void UAirsoftCombatComponent::ServerSetAiming_Implementation(bool bNewAiming)
{
	bAiming = bNewAiming;
}

void UAirsoftCombatComponent::ServerMelee_Implementation(AActor* Target)
{
	AAirsoftCharacter* Me = GetCharacter();
	AAirsoftCharacter* Victim = Cast<AAirsoftCharacter>(Target);
	if (!Me || !Victim || Victim == Me || Me->IsOut() || Me->IsFrozen() || Victim->IsOut())
	{
		return;
	}
	const FAirsoftViewmodelTuning& VM = UAirsoftSettings::Get()->Viewmodel;
	const double Now = GetWorld()->GetTimeSeconds();
	if (Now - ServerLastMeleeTime < VM.MeleeCooldown * 0.8f || !AAirsoftGameState::CanTag(this, Me->GetTeam(), Victim->GetTeam()))
	{
		return;
	}
	// Reach: the eyes to the nearest point of the victim's body line, with room for their capsule and latency.
	const FVector Eye = Me->GetPawnViewLocation();
	const FVector Body = Victim->GetActorLocation();
	const float HalfHeight = Victim->GetSimpleCollisionHalfHeight();
	const FVector Closest(Body.X, Body.Y, FMath::Clamp(Eye.Z, Body.Z - HalfHeight, Body.Z + HalfHeight));
	const FVector ToVictim = Closest - Eye;
	if (ToVictim.Size() > VM.MeleeRange + Victim->GetSimpleCollisionRadius() + 60.f)
	{
		return;
	}
	// Roughly in front: a wide cone, because up close the angle swings fast.
	if (FVector::DotProduct(Me->GetBaseAimRotation().Vector(), ToVictim.GetSafeNormal()) < 0.35f)
	{
		return;
	}
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftMeleeCheck), false);
	Query.AddIgnoredActor(Me);
	Query.AddIgnoredActor(Victim);
	FHitResult Block;
	if (GetWorld()->LineTraceSingleByChannel(Block, Eye, Closest, ECC_Visibility, Query) && !Cast<APawn>(Block.GetActor()))
	{
		return;
	}
	ServerLastMeleeTime = Now;
	if (AAirsoftGameMode* GM = GetWorld()->GetAuthGameMode<AAirsoftGameMode>())
	{
		// The body's centre as the hit point: a strike is never a headshot.
		if (GM->HandleHit(Me->GetController(), Victim->GetController(), TEXT("Melee"), Body))
		{
			ClientHitConfirm();
		}
	}
}

void UAirsoftCombatComponent::ServerSetLight_Implementation(bool bOn)
{
	bLightOn = bOn;
	OnRep_Light();
}

void UAirsoftCombatComponent::MulticastShot_Implementation(FVector_NetQuantize Origin, const TArray<FVector_NetQuantizeNormal>& Directions, float Speed, float Hop, float Drag, float Range, FName SoundKey, bool bQuiet)
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C || C->IsLocallyControlled() || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	const FVector Muzzle = C->GetTPGun()->GetMuzzleWorld();
	// Effects: muzzle puff on their third-person gun (gun type from their replicated loadout).
	if (UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this))
	{
		FX->MuzzlePuff(Muzzle, C->GetTPGun()->GetForwardVector(), Current(), bQuiet, false);
	}
	if (UAirsoftBBSubsystem* BBs = GetWorld()->GetSubsystem<UAirsoftBBSubsystem>())
	{
		for (const FVector_NetQuantizeNormal& D : Directions)
		{
			FAirsoftBBParams P;
			P.Origin = Origin;
			P.Direction = D;
			P.Speed = Speed;
			P.Hop = Hop;
			P.Drag = Drag;
			P.MaxRange = Range;
			P.VisualStart = Muzzle;
			P.bHasVisualStart = true;
			P.Color = AirsoftColors::Team(C->GetTeam());
			P.IgnoreActors.Add(C);
			BBs->Fire(MoveTemp(P));
		}
	}
	PlayShotSound(Muzzle, SoundKey, bQuiet);
}

void UAirsoftCombatComponent::PlayShotSound(const FVector& Muzzle, FName SoundKey, bool bQuiet) const
{
	if (GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	bool bFar = false;
	if (const APlayerController* Listener = GetWorld()->GetFirstPlayerController())
	{
		if (Listener->PlayerCameraManager)
		{
			bFar = FVector::Dist(Listener->PlayerCameraManager->GetCameraLocation(), Muzzle) > FarGunfireDistance;
		}
	}
	AirsoftAssets::Play3D(this, GunSoundKey(this, SoundKey, bFar), Muzzle, bQuiet ? 0.35f : 0.9f, FMath::FRandRange(0.96f, 1.05f));
}

void UAirsoftCombatComponent::ClientAmmo_Implementation(EAirsoftSlot Slot, int32 Mag, int32 Reserve)
{
	const int32 Idx = SlotIndex(Slot);
	LocalMag[Idx] = Mag;
	LocalReserve[Idx] = Reserve;
}

void UAirsoftCombatComponent::ClientHitConfirm_Implementation()
{
	// A bot's pawn has no owning connection, so its "client" RPCs run on the host: not for the host's ears.
	if (!IsLocalHuman())
	{
		return;
	}
	AirsoftAssets::Play2D(this, TEXT("HitMarker"), 0.7f, 1.2f);
	if (AAirsoftCharacter* C = GetCharacter())
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(C->GetController()))
		{
			PC->ShowHitMarker(true);
		}
	}
	// Effects: a small white pop on the spot the confirmed BB struck.
	if (GetWorld()->GetTimeSeconds() - LastVictimHitTime < 1.5)
	{
		if (UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this))
		{
			FX->HitConfirmPop(LastVictimHit);
		}
	}
}

// ---------------------------------------------------------------------------
// Per-frame (local player)
// ---------------------------------------------------------------------------

void UAirsoftCombatComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
	if (IsLocal())
	{
		UpdateLocal(DeltaTime);
	}
	// Runs after physics, so this frame's animation pose is ready to copy.
	if (AAirsoftCharacter* C = GetCharacter())
	{
		C->UpdateThirdPersonPose();
	}
}

void UAirsoftCombatComponent::UpdateLocal(float DeltaTime)
{
	AAirsoftCharacter* C = GetCharacter();
	if (!C)
	{
		return;
	}
	if (bTriggerHeld || BurstLeft > 0)
	{
		TryFire();
	}

	const FAirsoftWeaponDef& W = Current();
	const bool bAlive = !C->IsOut();
	const bool bWantsAim = bAlive && bAimHeld && !C->IsSprinting() && !bLocalReloading && !bThrowing && AnimKind != KindMelee && CanAct();
	const float Step = DeltaTime / FMath::Max(W.AimTime, 0.05f);
	AimAlpha = FMath::Clamp(AimAlpha + (bWantsAim ? Step : -Step), 0.f, 1.f);
	const bool bNowAiming = AimAlpha > 0.5f;
	if (bNowAiming != bAiming)
	{
		bAiming = bNowAiming;
		ServerSetAiming(bAiming);
	}

	// Spread: base lerp, movement, air, crouch, bloom.
	float Spread = FMath::Lerp(W.HipSpread, W.AimSpread, AimAlpha);
	const float Speed = C->GetVelocity().Size2D();
	Spread += FMath::Min(Speed / 400.f, 1.4f) * 1.3f * (1.f - AimAlpha * 0.6f);
	if (C->GetCharacterMovement() && C->GetCharacterMovement()->IsFalling())
	{
		Spread += 3.f;
	}
	if (C->bIsCrouched)
	{
		Spread *= 0.75f;
	}
	Spread += Bloom * (1.f - AimAlpha * 0.5f);
	CurrentSpread = Spread;
	Bloom = FMath::Max(Bloom - DeltaTime * 3.f, 0.f);

	ApplyRecoil(DeltaTime);
	UpdateThirdPersonAnim(DeltaTime);
	if (IsLocalHuman())
	{
		UpdateViewmodel(DeltaTime);
	}
	else if (!AnimKind.IsNone() && GetWorld()->GetTimeSeconds() - AnimStart >= AnimDuration)
	{
		// Bots have no viewmodel, but a bolt / pump cycle still has to finish before the next shot.
		AnimKind = NAME_None;
	}
}

void UAirsoftCombatComponent::ApplyRecoil(float DeltaTime)
{
	AAirsoftCharacter* C = GetCharacter();
	AController* Controller = C ? C->GetController() : nullptr;
	if (!Controller)
	{
		return;
	}
	RecoilTarget = FMath::Vector2DInterpTo(RecoilTarget, FVector2D::ZeroVector, DeltaTime, 5.f);
	const FVector2D NewOffset = FMath::Vector2DInterpTo(RecoilOffset, RecoilTarget, DeltaTime, 28.f);
	const FVector2D Delta = NewOffset - RecoilOffset;
	RecoilOffset = NewOffset;
	if (!Delta.IsNearlyZero(0.0001f))
	{
		FRotator Rot = Controller->GetControlRotation();
		Rot.Pitch = FMath::ClampAngle(static_cast<float>(FRotator::NormalizeAxis(Rot.Pitch) + Delta.X), -85.f, 85.f);
		Rot.Yaw += Delta.Y;
		Controller->SetControlRotation(Rot);
	}
}

void UAirsoftCombatComponent::PlayAnim(FName Kind, float Duration, bool bEmpty)
{
	AnimKind = Kind;
	AnimStart = GetWorld()->GetTimeSeconds();
	AnimDuration = FMath::Max(Duration, 0.05f);
	bAnimEmpty = bEmpty;
	FiredCues.Reset();
}

void UAirsoftCombatComponent::UpdateViewmodel(float DeltaTime)
{
	AAirsoftCharacter* C = GetCharacter();
	UAirsoftGunVisual* Gun = C ? C->GetFPGun() : nullptr;
	if (!Gun)
	{
		return;
	}
	const FAirsoftWeaponDef& W = Current();
	const FAirsoftViewmodelTuning& VM = UAirsoftSettings::Get()->Viewmodel;
	const bool bPistol = W.Class == TEXT("Pistol");
	const bool bTubeFed = IsTubeFed(W);

	// Sway lags behind look input.
	const FRotator ControlRot = C->GetControlRotation();
	const FRotator RotDelta = (ControlRot - LastControlRotation).GetNormalized();
	LastControlRotation = ControlRot;
	const FVector2D TargetSway(FMath::Clamp(static_cast<float>(-RotDelta.Yaw) * 0.6f, -4.f, 4.f), FMath::Clamp(static_cast<float>(RotDelta.Pitch) * 0.6f, -4.f, 4.f));
	Sway = FMath::Vector2DInterpTo(Sway, TargetSway, DeltaTime, 10.f);

	const float Speed = C->GetVelocity().Size2D();
	if (Speed > 30.f)
	{
		BobTime += DeltaTime * (Speed / 400.f) * 9.f;
	}
	const float BobAmount = FMath::Min(Speed / 400.f, 1.5f) * (1.f - AimAlpha * 0.85f) * (C->IsSliding() ? 0.2f : 1.f);
	const FVector Bob(0.f, FMath::Sin(BobTime) * 0.6f * BobAmount, FMath::Abs(FMath::Cos(BobTime)) * 0.7f * BobAmount);

	SprintAlpha = FMath::FInterpTo(SprintAlpha, C->IsSprinting() ? 1.f : 0.f, DeltaTime, 8.f);
	SlideAlpha = FMath::FInterpTo(SlideAlpha, C->IsSliding() ? 1.f : 0.f, DeltaTime, 10.f);
	const bool bFalling = C->GetCharacterMovement() && C->GetCharacterMovement()->IsFalling();
	AirAlpha = FMath::FInterpTo(AirAlpha, bFalling ? 1.f : 0.f, DeltaTime, 6.f);
	SlideKick = FMath::Max(SlideKick - DeltaTime / 0.07f, 0.f);

	// Recoil spring: Kick is its position, each shot adds velocity (FireOnce).
	SpringStep(Kick, KickVel, 0.f, VM.RecoilSpringStiffness, VM.RecoilSpringDamping, DeltaTime);
	Kick = FMath::Clamp(Kick, -0.6f, 1.6f);

	// Aim settle: arriving at the sights (or leaving them) the gun swings a touch past and springs back.
	const float AimOmega = FMath::Sqrt(FMath::Max(VM.AimSpringStiffness, 1.f));
	if (AimAlpha >= 1.f && PrevAimAlpha < 1.f)
	{
		AimSettleVel += VM.AimOvershoot * AimOmega * 1.8f;
	}
	else if (AimAlpha <= 0.f && PrevAimAlpha > 0.f)
	{
		AimSettleVel -= VM.AimOvershoot * AimOmega * 1.2f;
	}
	PrevAimAlpha = AimAlpha;
	SpringStep(AimSettle, AimSettleVel, 0.f, VM.AimSpringStiffness, VM.AimSpringDamping, DeltaTime);

	// Breathing: a slow figure-eight drift, mostly gone while aiming and while sprinting.
	BreathTime = FMath::Fmod(BreathTime + DeltaTime * VM.BreathRate * UE_TWO_PI, UE_TWO_PI * 4.f);
	const float Breath = VM.BreathDegrees * FMath::Lerp(1.f, VM.BreathAimScale, AimAlpha) * (1.f - SprintAlpha);

	// Strafing rolls the gun into the move.
	const float Strafe = static_cast<float>(FVector::DotProduct(C->GetVelocity(), C->GetActorRightVector())) / 400.f;
	StrafeRoll = FMath::FInterpTo(StrafeRoll, FMath::Clamp(Strafe, -1.2f, 1.2f), DeltaTime, 6.f);

	// Hip and aimed placements (camera space: X forward, Y right, Z up).
	// Shooter-style hip carry: the gun sits low in the right third of the screen, not filling it.
	const FVector Hip = bPistol ? FVector(36.f, 12.f, -15.f) : FVector(30.f, 14.f, -20.f);
	const FVector Aimed = -Gun->AimPointLocal;
	const float Eased = 1.f - FMath::Square(1.f - AimAlpha);
	FVector Loc = FMath::Lerp(Hip, Aimed, Eased);
	FRotator Rot = FRotator::ZeroRotator;
	Loc += (Aimed - Hip) * AimSettle;
	Rot += FRotator(-AimSettle * 12.f, 0.f, 0.f);

	// Sprint and slide poses.
	Loc += FVector(-2.f, 3.f, -5.f) * SprintAlpha;
	Rot += FRotator(-18.f, 35.f, 12.f) * SprintAlpha;
	Loc += FVector(0.f, -2.f, 1.f) * SlideAlpha;
	Rot += FRotator(0.f, 0.f, -22.f) * SlideAlpha;

	// In the air the gun tips up a little; landing dips it (the camera dips too, this adds weight).
	const float AirScale = 1.f - AimAlpha * 0.7f;
	Loc += FVector(0.f, 0.f, -1.5f) * AirAlpha * AirScale;
	Rot += FRotator(4.f, 0.f, 0.f) * AirAlpha * AirScale;
	const float Land = C->GetLandDip() * VM.LandDipScale * (1.f - AimAlpha * 0.6f);
	Loc.Z -= Land;
	Rot.Pitch -= Land * 0.8f;

	// Leaning and strafing roll the gun.
	Rot.Roll += C->GetLean() * VM.LeanRollDegrees * (1.f - AimAlpha * 0.5f) + StrafeRoll * VM.StrafeRollDegrees * (1.f - AimAlpha * 0.8f);

	// Recoil kick: back, up and a random roll; aimed shots stay tighter.
	const float KickScale = 1.f - AimAlpha * 0.4f;
	Loc += FVector(-Kick * VM.RecoilKickBack, 0.f, Kick * 0.3f) * KickScale;
	Rot += FRotator(Kick * VM.RecoilKickPitch, 0.f, Kick * VM.RecoilKickRoll * KickRollSide) * KickScale;

	// Sway, breathing and bob.
	const float SwayScale = 1.f - AimAlpha * 0.7f;
	Rot += FRotator(Sway.Y * SwayScale, Sway.X * SwayScale, 0.f);
	Rot += FRotator(FMath::Sin(BreathTime) * Breath * 0.6f, FMath::Sin(BreathTime * 0.5f + 1.3f) * Breath, 0.f);
	Loc += Bob;

	// Procedural animations.
	FTransform MagOffset = FTransform::Identity;
	FTransform SlideOffset = FTransform::Identity;
	FTransform BoltOffset = FTransform::Identity;
	FTransform PumpOffset = FTransform::Identity;
	FTransform HandOffset = FTransform::Identity;
	float SlideBack = bSlideLocked ? 1.f : SlideKick;

	if (!AnimKind.IsNone())
	{
		const float T = static_cast<float>((GetWorld()->GetTimeSeconds() - AnimStart) / AnimDuration);
		auto Cue = [this, T](FName Name, float At, FName Sound, float Pitch)
		{
			if (T >= At && !FiredCues.Contains(Name))
			{
				FiredCues.Add(Name);
				AirsoftAssets::Play2D(this, Sound, 0.5f, Pitch);
			}
		};
		if (T >= 1.f)
		{
			if (AnimKind == KindReload && bAnimEmpty && bPistol)
			{
				// The slide already went home at the slide-stop drop; don't let it flick back for a frame.
				bSlideLocked = false;
				SlideBack = SlideKick;
			}
			AnimKind = NAME_None;
		}
		else if (AnimKind == KindDraw)
		{
			const float K = 1.f - Ease(T);
			Loc += FVector(-6.f, 4.f, -22.f) * K;
			Rot += FRotator(-50.f, 20.f, -25.f) * K;
		}
		else if (AnimKind == KindReload)
		{
			const FReloadPose P = ReloadPose(T, bAnimEmpty, bPistol, bTubeFed, Gun);
			Loc += FVector(1.f, -1.f, -2.5f) * P.Tilt;
			Rot += FRotator(14.f, -8.f, -32.f) * P.Tilt;
			if (bTubeFed)
			{
				Rot += FRotator(-3.f, 0.f, 4.f) * P.Seat;
			}
			else
			{
				// The fresh mag slapped home bumps the gun up.
				Loc += FVector(0.f, 0.f, 0.9f) * P.Seat;
				Rot += FRotator(-3.f, 0.f, 2.f) * P.Seat;
				MagOffset = P.Mag;
				BoltOffset = P.Bolt;
				HandOffset.SetTranslation(P.Hand);
				if (P.SlideBack >= 0.f)
				{
					SlideBack = P.SlideBack;
					Rot += FRotator(3.f, 0.f, 0.f) * P.Release;
				}
			}
			ReloadCues(T, bTubeFed, bAnimEmpty, bPistol, Cue);
		}
		else if (AnimKind == KindInspect)
		{
			const float Side = Window(T, 0.05f, 0.25f) - Window(T, 0.42f, 0.55f);
			const float Flip = Window(T, 0.5f, 0.65f) - Window(T, 0.85f, 1.f);
			Loc += FVector(8.f, -8.f, 4.f) * (Side + Flip);
			Rot += FRotator(10.f * Side, 60.f * Side - 50.f * Flip, 25.f * Side - 70.f * Flip);
			if (!bTubeFed)
			{
				// Mag check while the gun is rolled over: pull it a little way, look, push it home.
				const float Check = Window(T, 0.6f, 0.68f) - Window(T, 0.76f, 0.84f);
				MagOffset.SetTranslation(FVector(0.f, 0.f, -6.f * Check));
				Cue(TEXT("CheckOut"), 0.64f, TEXT("MagOut"), 1.25f);
				Cue(TEXT("CheckIn"), 0.8f, TEXT("MagIn"), 1.2f);
			}
		}
		else if (AnimKind == KindCycle)
		{
			const float Back = Window(T, 0.1f, 0.45f) - Window(T, 0.55f, 0.9f);
			if (W.Id == TEXT("M870"))
			{
				PumpOffset.SetTranslation(FVector(-9.f * Back, 0.f, 0.f));
				HandOffset = PumpOffset;
				Cue(TEXT("Rack"), 0.35f, TEXT("BoltCycle"), 0.85f);
			}
			else
			{
				const float Lift = Window(T, 0.05f, 0.2f) - Window(T, 0.8f, 0.95f);
				BoltOffset = FTransform(FRotator(0.f, 0.f, 60.f * Lift), FVector(-7.f * Back, 0.f, 1.f * Lift));
				Cue(TEXT("Bolt"), 0.3f, TEXT("BoltCycle"), 1.f);
			}
			Rot += FRotator(4.f * Back, 0.f, -8.f * Back);
		}
		else if (AnimKind == KindMelee)
		{
			MeleePose(T, bPistol, Loc, Rot);
		}
	}
	if (SlideBack > 0.f)
	{
		SlideOffset.SetTranslation(FVector(-3.5f * SlideBack, 0.f, 0.f));
	}

	Gun->SetRelativeLocationAndRotation(Loc, Rot);
	Gun->SetPartOffsets(MagOffset, SlideOffset, BoltOffset, PumpOffset, HandOffset);
	Gun->SetOpticFade(AimAlpha);
	Gun->SetVisibility(!IsScoped() && !C->IsOut(), true);
}

void UAirsoftCombatComponent::UpdateThirdPersonAnim(float DeltaTime)
{
	AAirsoftCharacter* C = GetCharacter();
	UAirsoftGunVisual* Gun = C ? C->GetTPGun() : nullptr;
	if (!Gun)
	{
		return;
	}
	const FAirsoftViewmodelTuning& VM = UAirsoftSettings::Get()->Viewmodel;
	SpringStep(TPKick, TPKickVel, 0.f, VM.RecoilSpringStiffness, VM.RecoilSpringDamping, DeltaTime);
	TPKick = FMath::Clamp(TPKick, -0.6f, 1.6f);

	const FAirsoftWeaponDef& W = Current();
	const bool bPistol = W.Class == TEXT("Pistol");
	const bool bTubeFed = IsTubeFed(W);
	FVector Loc = FVector::ZeroVector;
	FRotator Rot = FRotator::ZeroRotator;
	FTransform MagOffset = FTransform::Identity;
	FTransform SlideOffset = FTransform::Identity;
	FTransform BoltOffset = FTransform::Identity;
	FTransform PumpOffset = FTransform::Identity;
	FVector Hand = FVector::ZeroVector;
	// Pistols: the slide cycles with each shot and locks back on empty.
	float SlideBack = bSlideLocked ? 1.f : (bPistol ? FMath::Clamp(TPKick, 0.f, 1.f) : 0.f);

	if (!C->IsOut() && !AnimKind.IsNone() && AnimDuration > 0.f)
	{
		const float T = static_cast<float>((GetWorld()->GetTimeSeconds() - AnimStart) / AnimDuration);
		if (T < 1.f)
		{
			if (AnimKind == KindReload)
			{
				// The gun comes down and rolls toward the chest so the mag well faces the support hand.
				const FReloadPose P = ReloadPose(T, bAnimEmpty, bPistol, bTubeFed, Gun);
				Loc += FVector(-6.f, -5.f, -9.f) * P.Tilt;
				Rot += FRotator(22.f, -18.f, -38.f) * P.Tilt;
				if (bTubeFed)
				{
					Rot += FRotator(-3.f, 0.f, 4.f) * P.Seat;
					Hand = FVector(-8.f, 0.f, -6.f) * P.Tilt; // to the loading port
				}
				else
				{
					Loc.Z += P.Seat;
					MagOffset = P.Mag;
					BoltOffset = P.Bolt;
					Hand = P.Hand;
					if (P.SlideBack >= 0.f)
					{
						SlideBack = P.SlideBack;
					}
				}
				if (!IsLocalHuman())
				{
					// Hear an enemy reloading from where they stand (the player's own cues are 2D, in UpdateViewmodel).
					const FVector At = Gun->GetComponentLocation();
					ReloadCues(T, bTubeFed, bAnimEmpty, bPistol, [this, T, At](FName Name, float When, FName Sound, float Pitch)
					{
						if (T >= When && !FiredCues.Contains(Name))
						{
							FiredCues.Add(Name);
							AirsoftAssets::Play3D(this, Sound, At, 0.6f, Pitch);
						}
					});
				}
			}
			else if (AnimKind == KindInspect)
			{
				const float Side = Window(T, 0.05f, 0.25f) - Window(T, 0.42f, 0.55f);
				const float Flip = Window(T, 0.5f, 0.65f) - Window(T, 0.85f, 1.f);
				Loc += FVector(6.f, -6.f, 6.f) * (Side + Flip);
				Rot += FRotator(10.f * Side, 45.f * Side - 35.f * Flip, 30.f * Side - 60.f * Flip);
			}
			else if (AnimKind == KindCycle)
			{
				const float Back = Window(T, 0.1f, 0.45f) - Window(T, 0.55f, 0.9f);
				if (W.Id == TEXT("M870"))
				{
					PumpOffset.SetTranslation(FVector(-9.f * Back, 0.f, 0.f));
					Hand = FVector(-9.f * Back, 0.f, 0.f);
				}
				else
				{
					const float Lift = Window(T, 0.05f, 0.2f) - Window(T, 0.8f, 0.95f);
					BoltOffset = FTransform(FRotator(0.f, 0.f, 60.f * Lift), FVector(-7.f * Back, 0.f, 1.f * Lift));
				}
				Rot += FRotator(4.f * Back, 0.f, 0.f);
			}
			else if (AnimKind == KindMelee)
			{
				MeleePose(T, bPistol, Loc, Rot);
			}
			else if (AnimKind == KindDraw)
			{
				const float K = 1.f - Ease(T);
				Loc += FVector(-4.f, 0.f, -14.f) * K;
				Rot += FRotator(-40.f, 15.f, -20.f) * K;
			}
		}
	}

	// Recoil: the gun jumps back into the shoulder and the muzzle climbs, then springs back.
	Loc += FVector(-TPKick * VM.RecoilKickBack * 0.8f, 0.f, 0.f);
	Rot += FRotator(TPKick * VM.RecoilKickPitch * 1.2f, 0.f, TPKick * VM.RecoilKickRoll * KickRollSide);
	if (SlideBack > 0.f)
	{
		SlideOffset.SetTranslation(FVector(-3.5f * SlideBack, 0.f, 0.f));
	}
	TPGunOffset = FTransform(Rot, Loc);
	TPHandOffset = Hand;
	Gun->SetPartOffsets(MagOffset, SlideOffset, BoltOffset, PumpOffset);
}
