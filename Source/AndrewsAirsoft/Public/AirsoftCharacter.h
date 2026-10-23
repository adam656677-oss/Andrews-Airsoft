// Andrew's Airsoft - the player: first-person camera, movement (sprint,
// crouch, slide, lean), gear, guns and the airsoft "hit, walk off" state.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AirsoftTypes.h"
#include "AirsoftCharacter.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UAirsoftCombatComponent;
class UAirsoftGunVisual;
class UAirsoftMovementComponent;
class UStaticMeshComponent;
class UTextRenderComponent;
class UMaterialInstanceDynamic;
class UPoseableMeshComponent;
class UAirsoftTeamGearComponent;
class AAirsoftPlayerState;

/**
 * Third person: where a shot goes. The crosshair ray comes from the over-the-shoulder camera, but the BB
 * leaves the gun, so a camera that sees round a corner can't shoot round it (the shoulder-peek exploit).
 */
struct FAirsoftShoulderAim
{
	/** Where the crosshair ray from the camera lands (or its end at the gun's range). */
	FVector AimPoint = FVector::ZeroVector;
	/** Where the BB starts: the third-person muzzle, or the eyes if the barrel is inside a wall. */
	FVector Origin = FVector::ZeroVector;
	FVector Direction = FVector::ForwardVector;
	/** The muzzle can't see the aim point: the BB would stop here first. */
	FVector BlockPoint = FVector::ZeroVector;
	bool bBlocked = false;
	bool bValid = false;
};

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	AAirsoftCharacter(const FObjectInitializer& ObjectInitializer);

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void OnRep_PlayerState() override;
	virtual void Landed(const FHitResult& Hit) override;
	/** The view: the eye camera, blended toward the over-the-shoulder camera in third person. */
	virtual void CalcCamera(float DeltaTime, FMinimalViewInfo& OutResult) override;

	/** The eye camera. Shots, grenades and the server's origin check use it in both views (it never leaves the head). */
	UCameraComponent* GetCamera() const { return Camera; }
	UAirsoftCombatComponent* GetCombat() const { return Combat; }
	UAirsoftGunVisual* GetFPGun() const { return FPGun; }
	UAirsoftGunVisual* GetTPGun() const { return TPGun; }
	UAirsoftMovementComponent* GetAirsoftMovement() const;

	AAirsoftPlayerState* GetAirsoftPlayerState() const;
	EAirsoftTeam GetTeam() const;
	FString GetDisplayName() const;
	bool IsOut() const { return bIsOutReplicated; }
	bool IsFrozen() const { return bFrozen; }
	bool IsSprinting() const;
	bool IsSliding() const;
	float GetLean() const { return LeanAmount; }
	/** cm the eye camera is dipped by the last landing (springs back to 0). */
	float GetLandDip() const { return LandDip; }
	/**
	 * Controlled by a person on this machine. Bots are "locally controlled" on the host too
	 * (their AIController lives there), so first-person-only work - 2D sounds, the viewmodel,
	 * hiding your own body - checks this instead of IsLocallyControlled().
	 */
	bool IsLocalHuman() const;

	// --- Local input (called by AAirsoftPlayerController) -------------------
	void MoveInput(const FVector2D& Axis);
	/** Look by a number of degrees (the controller applies sensitivity). */
	void LookInput(float YawDegrees, float PitchDegrees);
	void SetSprintHeld(bool bHeld);
	void ToggleSprint();
	/** Firing/aiming interrupts sprint until sprint is pressed again. */
	void CancelSprint();
	void ToggleCrouchInput();
	void SetCrouchHeld(bool bHeld);
	void SetLeanInput(float Direction);
	void JumpInput();

	// --- Camera: first / third person (local only; nothing here is replicated) ---------
	/** F5: flips the saved camera setting for this kind of game (story or airsoft match). */
	void ToggleCameraMode();
	/** X: over the right or the left shoulder (saved). */
	void SwapShoulder();
	/** This machine's player wants the over-the-shoulder camera here (settings: matches / story). */
	bool WantsThirdPerson() const;
	/**
	 * The owner is looking at their own body right now. False in first person and while aiming down
	 * sights from third person (ADS goes to the real sights; see UpdateThirdPersonCamera).
	 */
	bool IsThirdPersonView() const { return bOwnerSeesBody; }
	/** 0 = eye view, 1 = fully over the shoulder. */
	float GetThirdPersonBlend() const { return TPBlend; }
	/** Third person: aim point from the camera, BB origin and direction from the muzzle, muzzle line of sight. */
	FAirsoftShoulderAim ComputeShoulderAim(float MaxRange) const;
	/** Last frame's ComputeShoulderAim (for the HUD's blocked-shot marker); bValid false in first person. */
	const FAirsoftShoulderAim& GetShoulderAim() const { return ShoulderAim; }
	/** Where the over-the-shoulder camera sits right now (e.g. for a cinematic to end on). False if not in use. */
	bool GetOverShoulderView(FVector& OutLocation, FRotator& OutRotation) const;

	// --- Server ---------------------------------------------------------------
	/** Called by the game mode when this player is tagged. */
	void ServerMarkOut(const FString& TaggedBy);

	// --- Story campaign: health --------------------------------------------------
	/**
	 * Server: takes damage (campaign only). FromLocation is where the shot came from (damage direction).
	 * Returns true if this hit killed. A kill marks the character out, which on a campaign map
	 * means dead: a ragdoll, not the airsoft hit rag.
	 */
	bool ServerApplyDamage(float Amount, const FString& From, const FVector& FromLocation);
	float GetHealth() const { return Health; }
	float GetMaxHealth() const { return MaxHealth; }
	/** 0 (fine) .. 1 (nearly dead): drives the red damage overlay. */
	float GetHurtAlpha() const;
	/** Seconds since the last damage taken (regeneration starts after RegenDelay). */
	float TimeSinceDamage() const;

	UPROPERTY(ReplicatedUsing = OnRep_Health) float Health = 100.f;
	UPROPERTY(EditAnywhere, Category = "Campaign") float MaxHealth = 100.f;
	/** Call of Duty style: no damage for this long, then health climbs back at RegenRate per second. */
	UPROPERTY(EditAnywhere, Category = "Campaign") float RegenDelay = 4.f;
	UPROPERTY(EditAnywhere, Category = "Campaign") float RegenRate = 40.f;
	void ServerSetFrozen(bool bInFrozen);

	/** Recolours armband, body and guns for the current team. */
	void ApplyTeamLook();

	/** Third person: copy the animated pose and bend both arms onto the gun (called after animation each frame). */
	void UpdateThirdPersonPose();

	// --- Effects --------------------------------------------------------------
	/** Shakes this player's own view (Strength 0..1) with an optional upward flinch; local human only, honours the screen-shake option. */
	void AddViewShake(float Strength, float KickDegrees = 0.f);

	UPROPERTY(ReplicatedUsing = OnRep_Out) bool bIsOutReplicated = false;
	UPROPERTY(ReplicatedUsing = OnRep_Frozen) bool bFrozen = false;
	UPROPERTY(Replicated) bool bSprinting = false;
	UPROPERTY(Replicated) bool bSliding = false;
	UPROPERTY(Replicated) float LeanAmount = 0.f;
	UPROPERTY(Replicated) FString TaggedByName;

	UFUNCTION(Server, Unreliable) void ServerSetLean(float NewLean);

protected:
	UFUNCTION() void OnRep_Out();
	UFUNCTION() void OnRep_Frozen();
	UFUNCTION() void OnRep_Health(float OldHealth);
	/** Local feedback for losing health: flinch, shake, hurt sound. */
	void PlayDamageFeedback(float Amount);
	/** Campaign death: the body goes limp (mannequin ragdoll) and the gun is dropped from view. */
	void ApplyCampaignDeath();
	/** Campaign: suits instead of airsoft gear (Andrew charcoal, crews navy, bosses oxblood). */
	void ApplyCampaignWardrobe();
	double LastDamageTime = -100.0;
	bool bRagdolled = false;
	void UpdateCamera(float DeltaSeconds);
	void UpdateRemoteVisuals(float DeltaSeconds);
	void ApplyOutVisuals();
	void SetupThirdPersonBody();

	UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;
	/** Third person: over-the-shoulder boom (collision probe, lag) and its camera. Ticks only for the local player in third person. */
	UPROPERTY(VisibleAnywhere) TObjectPtr<USpringArmComponent> CameraBoom;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> ShoulderCamera;
	/** Rolls with the camera when leaning so the first-person gun stays glued to the view. */
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> ViewRoot;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UAirsoftCombatComponent> Combat;
	UPROPERTY(VisibleAnywhere) TObjectPtr<USceneComponent> TPAimRoot;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UAirsoftGunVisual> FPGun;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UAirsoftGunVisual> TPGun;
	/** Stand-in body shown to others until the mannequin is available. */
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> FallbackBody;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> FallbackHead;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> TeamBand;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UStaticMeshComponent> DeadRag;
	UPROPERTY(VisibleAnywhere) TObjectPtr<UTextRenderComponent> HitCall;
	/** Visible body when the mannequin is used: a copy of the animated mesh with the arms posed onto the gun. */
	UPROPERTY(VisibleAnywhere) TObjectPtr<UPoseableMeshComponent> PoseMesh;
	/** Plate carrier, helmet or cap, goggles, mask, armband and knee pads worn by the third-person body. */
	UPROPERTY(VisibleAnywhere) TObjectPtr<UAirsoftTeamGearComponent> TeamGear;

	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> TeamMID;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> BodyMID;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> RagMID;

	bool bSprintHeld = false;
	bool bSprintToggled = false;
	bool bSprintSuppressed = false;
	bool bCrouchHeldMode = false;
	float LeanTarget = 0.f;
	float LeanSent = 0.f;
	double SlideRequestUntil = 0.0;
	float EyeHeight = 164.f;
	float LandDip = 0.f;
	float LeanVisual = 0.f;
	float OutFade = 0.f;
	float StepAccum = 0.f;
	bool bHasMannequin = false;
	bool bUsePoseMesh = false;
	void SolveArm(FName UpperName, FName LowerName, FName HandName, const FVector& WristTargetWorld, const FVector& PoleWorld);
	EAirsoftTeam AppliedTeam = EAirsoftTeam::None;
	bool bTeamApplied = false;

	// Effects: view shake, flinch and the tagged pulse (local human only; see AirsoftEffects.h).
	void UpdateViewEffects(float DeltaSeconds, FRotator& OutShakeRotation, FVector& OutShakeOffset);
	float ViewShake = 0.f;
	float ViewShakeTime = 0.f;
	float ViewKick = 0.f;
	float HitPulse = 0.f;

	// Third-person camera (local human only).
	void UpdateThirdPersonCamera(float DeltaSeconds, const FRotator& ShakeRotation, const FVector& ShakeOffset);
	/** Who sees what: body, gear, third-person gun and rag for the owner in third person; arms and viewmodel in first. */
	void ApplyOwnerView(bool bSeeBody);
	float TPBlend = 0.f;
	/** +1 right shoulder, -1 left (smoothed). */
	float ShoulderSide = 1.f;
	bool bOwnerSeesBody = false;
	bool bOwnerViewApplied = false;
	FAirsoftShoulderAim ShoulderAim;
};
