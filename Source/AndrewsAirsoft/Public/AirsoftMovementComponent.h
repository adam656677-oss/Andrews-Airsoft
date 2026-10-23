// Andrew's Airsoft - character movement with client-predicted sprint, slide
// and aim-walk (sent with each move, so there are no rubber-band corrections).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "AirsoftMovementComponent.generated.h"

UCLASS()
class ANDREWSAIRSOFT_API UAirsoftMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UAirsoftMovementComponent();

	// Tuning (cm/s).
	UPROPERTY(EditAnywhere, Category = "Airsoft") float WalkSpeed = 430.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float AimWalkSpeed = 250.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SprintSpeed = 660.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float CrouchSpeed = 200.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float OutSpeed = 230.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideMinSpeed = 480.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideBoost = 260.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideEndSpeed = 260.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideMaxTime = 1.1f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideFriction = 0.25f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideBraking = 380.f;
	UPROPERTY(EditAnywhere, Category = "Airsoft") float SlideCooldown = 0.7f;

	/** Input wishes, set by the owning character each frame and sent with every saved move. */
	bool bWantsSprint = false;
	bool bWantsSlide = false;
	bool bWantsAimWalk = false;

	bool IsSprintingNow() const { return bSprintingNow; }
	bool IsSlidingNow() const { return bSlidingNow; }

	virtual float GetMaxSpeed() const override;
	virtual float GetMaxBrakingDeceleration() const override;
	virtual bool CanAttemptJump() const override;
	virtual void UpdateFromCompressedFlags(uint8 Flags) override;
	virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;
	virtual void UpdateCharacterStateBeforeMovement(float DeltaSeconds) override;
	virtual void CalcVelocity(float DeltaTime, float Friction, bool bFluid, float BrakingDeceleration) override;

private:
	bool CanSprint() const;
	float SpeedMultiplier() const;
	bool IsOwnerOut() const;
	bool IsOwnerFrozen() const;

	bool bSprintingNow = false;
	bool bSlidingNow = false;
	float SlideTime = 0.f;
	float SlideCooldownLeft = 0.f;
};
