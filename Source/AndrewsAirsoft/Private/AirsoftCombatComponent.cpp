#include "AirsoftCombatComponent.h"

#include "AirsoftAssets.h"
#include "AirsoftBallistics.h"
#include "AirsoftCharacter.h"
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

void UAirsoftCombatComponent::Reload()
{
	if (!CanAct() || bLocalReloading || bThrowing)
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
	AAirsoftCharacter* C = GetCharacter();
	if (!C || !CanAct() || bThrowing || Grenades <= 0)
	{
		return;
	}
	const AAirsoftGameState* GS = GetWorld()->GetGameState<AAirsoftGameState>();
	if (GS && GS->Phase != EAirsoftPhase::Live)
	{
		return;
	}
	bThrowing = true;
	PlayAnim(KindInspect, 0.6f);
	const FVector Origin = C->GetCamera()->GetComponentLocation();
	const FVector Dir = (C->GetControlRotation().Vector() + FVector(0.f, 0.f, 0.15f)).GetSafeNormal();
	FTimerHandle Handle;
	GetWorld()->GetTimerManager().SetTimer(Handle, FTimerDelegate::CreateWeakLambda(this, [this, Origin, Dir]()
	{
		ServerThrowGrenade(Origin, Dir);
		AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.5f, 0.6f);
		bThrowing = false;
	}), 0.3f, false);
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
	if (AnimKind == KindCycle)
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
	if (LocalMag[Idx] <= 0)
	{
		AirsoftAssets::Play2D(this, TEXT("DryFire"), 0.5f, 1.2f);
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

	const FVector Origin = C->GetCamera()->GetComponentLocation();
	const FVector Look = C->GetCamera()->GetForwardVector();
	TArray<FVector_NetQuantizeNormal> Dirs;
	for (int32 i = 0; i < W.Pellets; ++i)
	{
		Dirs.Add(AirsoftBallistics::Spread(Look, CurrentSpread, Rng));
	}
	ServerFire(ActiveSlot, ShotId, Origin, Dirs);

	if (UAirsoftBBSubsystem* BBs = GetWorld()->GetSubsystem<UAirsoftBBSubsystem>())
	{
		const FVector Muzzle = C->GetFPGun()->GetMuzzleWorld();
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

	AirsoftAssets::Play2D(this, GunSoundKey(this, W.Sound, false), W.bQuiet ? 0.45f : 0.75f, Rng.FRandRange(0.96f, 1.05f));
	Kick = FMath::Min(Kick + W.RecoilUp * 0.35f, 1.5f);
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
		if (Me && Victim != Me && !Victim->IsOut() && (Victim->GetTeam() != Me->GetTeam() || UAirsoftSettings::Get()->bFriendlyFire))
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
		if (GM->HandleTag(Me->GetController(), Victim->GetController(), W.Id))
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
	AirsoftAssets::Play2D(this, TEXT("HitMarker"), 0.7f, 1.2f);
	if (AAirsoftCharacter* C = GetCharacter())
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(C->GetController()))
		{
			PC->ShowHitMarker(true);
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
	const bool bWantsAim = bAlive && bAimHeld && !C->IsSprinting() && !bLocalReloading && !bThrowing && CanAct();
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
	UpdateViewmodel(DeltaTime);
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
	const bool bPistol = W.Class == TEXT("Pistol");

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
	Kick = FMath::Max(Kick - DeltaTime * 9.f, 0.f);
	SlideKick = FMath::Max(SlideKick - DeltaTime / 0.07f, 0.f);

	// Hip and aimed placements (camera space: X forward, Y right, Z up).
	const FVector Hip = bPistol ? FVector(30.f, 10.f, -12.f) : FVector(20.f, 11.f, -15.f);
	const FVector Aimed = -Gun->AimPointLocal;
	const float Eased = 1.f - FMath::Square(1.f - AimAlpha);
	FVector Loc = FMath::Lerp(Hip, Aimed, Eased);
	FRotator Rot = FRotator::ZeroRotator;

	// Sprint and slide poses.
	Loc += FVector(-2.f, 3.f, -5.f) * SprintAlpha;
	Rot += FRotator(-18.f, 35.f, 12.f) * SprintAlpha;
	Loc += FVector(0.f, -2.f, 1.f) * SlideAlpha;
	Rot += FRotator(0.f, 0.f, -22.f) * SlideAlpha;

	// Recoil kick.
	Loc += FVector(-Kick * 3.5f, 0.f, 0.f);
	Rot += FRotator(Kick * 5.f, 0.f, 0.f);

	// Sway and bob.
	const float SwayScale = 1.f - AimAlpha * 0.7f;
	Rot += FRotator(Sway.Y * SwayScale, Sway.X * SwayScale, 0.f);
	Loc += Bob;

	// Procedural animations.
	FTransform MagOffset = FTransform::Identity;
	FTransform SlideOffset = FTransform::Identity;
	FTransform BoltOffset = FTransform::Identity;
	FTransform PumpOffset = FTransform::Identity;
	FTransform HandOffset = FTransform::Identity;
	const float SlideBack = bSlideLocked ? 1.f : SlideKick;
	if (SlideBack > 0.f)
	{
		SlideOffset.SetTranslation(FVector(-3.5f * SlideBack, 0.f, 0.f));
	}

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
			const float Tilt = Window(T, 0.f, 0.18f) - Window(T, 0.82f, 1.f);
			Loc += FVector(1.f, -1.f, -2.5f) * Tilt;
			Rot += FRotator(14.f, -8.f, -32.f) * Tilt;
			if (W.Id == TEXT("M870") || W.Id == TEXT("VSR"))
			{
				Cue(TEXT("Click1"), 0.3f, TEXT("MagIn"), 1.4f);
				Cue(TEXT("Click2"), 0.55f, TEXT("MagIn"), 1.3f);
			}
			else
			{
				// Mag drops out, fresh mag comes up and seats.
				const float Drop = Window(T, 0.18f, 0.4f);
				const float Insert = Window(T, 0.45f, 0.7f);
				// Support hand leaves the handguard, strips the mag, fetches a fresh one and returns.
				const float Reach = Window(T, 0.08f, 0.2f) - Window(T, 0.72f, 0.86f);
				const FVector ToWell = Gun->MagWellLocal - Gun->LeftHandLocal + FVector(0.f, -2.f, -10.f);
				if (T < 0.42f)
				{
					MagOffset = FTransform(FRotator(-10.f * Drop, 0.f, 25.f * Drop), FVector(-3.f * Drop, 0.f, -40.f * Drop * Drop));
				}
				else
				{
					const FTransform From(FRotator(0.f, 0.f, 20.f), FVector(-10.f, -6.f, -32.f));
					FTransform Blend;
					Blend.Blend(From, FTransform::Identity, Insert);
					MagOffset = Blend;
				}
				HandOffset.SetTranslation(ToWell * Reach + MagOffset.GetTranslation() * Reach);
				Cue(TEXT("Out"), 0.2f, TEXT("MagOut"), 1.f);
				Cue(TEXT("In"), 0.68f, TEXT("MagIn"), 1.f);
				if (bAnimEmpty)
				{
					const float Charge = Window(T, 0.74f, 0.82f) - Window(T, 0.82f, 0.9f);
					BoltOffset.SetTranslation(FVector(-6.f * Charge, 0.f, 0.f));
					Cue(TEXT("Charge"), 0.8f, TEXT("BoltCycle"), 1.1f);
				}
			}
		}
		else if (AnimKind == KindInspect)
		{
			const float Side = Window(T, 0.05f, 0.25f) - Window(T, 0.42f, 0.55f);
			const float Flip = Window(T, 0.5f, 0.65f) - Window(T, 0.85f, 1.f);
			Loc += FVector(8.f, -8.f, 4.f) * (Side + Flip);
			Rot += FRotator(10.f * Side, 60.f * Side - 50.f * Flip, 25.f * Side - 70.f * Flip);
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
	}

	Gun->SetRelativeLocationAndRotation(Loc, Rot);
	Gun->SetPartOffsets(MagOffset, SlideOffset, BoltOffset, PumpOffset, HandOffset);
	Gun->SetOpticFade(AimAlpha);
	Gun->SetVisibility(!IsScoped() && !C->IsOut(), true);
}
