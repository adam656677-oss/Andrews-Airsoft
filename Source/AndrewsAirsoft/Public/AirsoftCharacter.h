// Andrew's Airsoft - the player: first-person camera, movement (sprint,
// crouch, slide, lean), gear, guns and the airsoft "hit, walk off" state.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AirsoftTypes.h"
#include "AirsoftCharacter.generated.h"

class UCameraComponent;
class UAirsoftCombatComponent;
class UAirsoftGunVisual;
class UAirsoftMovementComponent;
class UStaticMeshComponent;
class UTextRenderComponent;
class UMaterialInstanceDynamic;
class UPoseableMeshComponent;
class AAirsoftPlayerState;

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

	// --- Server ---------------------------------------------------------------
	/** Called by the game mode when this player is tagged. */
	void ServerMarkOut(const FString& TaggedBy);
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
	void UpdateCamera(float DeltaSeconds);
	void UpdateRemoteVisuals(float DeltaSeconds);
	void ApplyOutVisuals();
	void SetupThirdPersonBody();

	UPROPERTY(VisibleAnywhere) TObjectPtr<UCameraComponent> Camera;
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
};
