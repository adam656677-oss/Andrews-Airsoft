#include "AirsoftMovementComponent.h"

#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "GameFramework/Character.h"

namespace
{
	/** Saved move that carries the sprint/slide/aim wishes so the server replays them exactly. */
	class FSavedMove_Airsoft : public FSavedMove_Character
	{
	public:
		using Super = FSavedMove_Character;

		uint8 bSavedSprint : 1;
		uint8 bSavedSlide : 1;
		uint8 bSavedAim : 1;

		FSavedMove_Airsoft()
			: bSavedSprint(0), bSavedSlide(0), bSavedAim(0)
		{
		}

		virtual void Clear() override
		{
			Super::Clear();
			bSavedSprint = 0;
			bSavedSlide = 0;
			bSavedAim = 0;
		}

		virtual uint8 GetCompressedFlags() const override
		{
			uint8 Result = Super::GetCompressedFlags();
			if (bSavedSprint) Result |= FLAG_Custom_0;
			if (bSavedSlide) Result |= FLAG_Custom_1;
			if (bSavedAim) Result |= FLAG_Custom_2;
			return Result;
		}

		virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const override
		{
			const FSavedMove_Airsoft* Other = static_cast<const FSavedMove_Airsoft*>(NewMove.Get());
			if (bSavedSprint != Other->bSavedSprint || bSavedSlide != Other->bSavedSlide || bSavedAim != Other->bSavedAim)
			{
				return false;
			}
			return Super::CanCombineWith(NewMove, InCharacter, MaxDelta);
		}

		virtual void SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData) override
		{
			Super::SetMoveFor(C, InDeltaTime, NewAccel, ClientData);
			if (const UAirsoftMovementComponent* Move = Cast<UAirsoftMovementComponent>(C->GetCharacterMovement()))
			{
				bSavedSprint = Move->bWantsSprint;
				bSavedSlide = Move->bWantsSlide;
				bSavedAim = Move->bWantsAimWalk;
			}
		}

		virtual void PrepMoveFor(ACharacter* C) override
		{
			Super::PrepMoveFor(C);
			if (UAirsoftMovementComponent* Move = Cast<UAirsoftMovementComponent>(C->GetCharacterMovement()))
			{
				Move->bWantsSprint = bSavedSprint;
				Move->bWantsSlide = bSavedSlide;
				Move->bWantsAimWalk = bSavedAim;
			}
		}
	};

	class FNetworkPredictionData_Client_Airsoft : public FNetworkPredictionData_Client_Character
	{
	public:
		using Super = FNetworkPredictionData_Client_Character;

		explicit FNetworkPredictionData_Client_Airsoft(const UCharacterMovementComponent& ClientMovement)
			: Super(ClientMovement)
		{
		}

		virtual FSavedMovePtr AllocateNewMove() override
		{
			return FSavedMovePtr(new FSavedMove_Airsoft());
		}
	};
}

UAirsoftMovementComponent::UAirsoftMovementComponent()
{
	MaxWalkSpeed = WalkSpeed;
	MaxWalkSpeedCrouched = CrouchSpeed;
	MaxAcceleration = 2600.f;
	BrakingDecelerationWalking = 1900.f;
	GroundFriction = 8.f;
	JumpZVelocity = 470.f;
	AirControl = 0.3f;
	GravityScale = 1.15f;
	SetCrouchedHalfHeight(58.f);
	bCanWalkOffLedgesWhenCrouching = true;
	NavAgentProps.bCanCrouch = true;
	NavAgentProps.bCanJump = true;
	bOrientRotationToMovement = false;
	PerchRadiusThreshold = 12.f;
}

FNetworkPredictionData_Client* UAirsoftMovementComponent::GetPredictionData_Client() const
{
	if (!ClientPredictionData)
	{
		UAirsoftMovementComponent* Mutable = const_cast<UAirsoftMovementComponent*>(this);
		Mutable->ClientPredictionData = new FNetworkPredictionData_Client_Airsoft(*this);
	}
	return ClientPredictionData;
}

void UAirsoftMovementComponent::UpdateFromCompressedFlags(uint8 Flags)
{
	Super::UpdateFromCompressedFlags(Flags);
	bWantsSprint = (Flags & FSavedMove_Character::FLAG_Custom_0) != 0;
	bWantsSlide = (Flags & FSavedMove_Character::FLAG_Custom_1) != 0;
	bWantsAimWalk = (Flags & FSavedMove_Character::FLAG_Custom_2) != 0;
}

bool UAirsoftMovementComponent::IsOwnerOut() const
{
	const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(CharacterOwner);
	return C && C->IsOut();
}

bool UAirsoftMovementComponent::IsOwnerFrozen() const
{
	const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(CharacterOwner);
	return C && C->IsFrozen();
}

float UAirsoftMovementComponent::SpeedMultiplier() const
{
	const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(CharacterOwner);
	if (C && C->GetCombat())
	{
		return FMath::Clamp(C->GetCombat()->Current().SpeedMultiplier, 0.5f, 1.5f);
	}
	return 1.f;
}

bool UAirsoftMovementComponent::CanSprint() const
{
	if (!bWantsSprint || bWantsAimWalk || IsCrouching() || !IsMovingOnGround() || IsOwnerOut() || IsOwnerFrozen() || !CharacterOwner)
	{
		return false;
	}
	// Only sprint forwards (or diagonally forwards).
	const FVector Wish = Acceleration.GetSafeNormal2D();
	return !Wish.IsNearlyZero() && FVector::DotProduct(Wish, CharacterOwner->GetActorForwardVector().GetSafeNormal2D()) > 0.5f;
}

void UAirsoftMovementComponent::UpdateCharacterStateBeforeMovement(float DeltaSeconds)
{
	SlideCooldownLeft = FMath::Max(0.f, SlideCooldownLeft - DeltaSeconds);

	if (!bSlidingNow && bWantsSlide && SlideCooldownLeft <= 0.f && IsMovingOnGround() && !IsOwnerOut() && !IsOwnerFrozen()
		&& Velocity.Size2D() >= SlideMinSpeed)
	{
		bSlidingNow = true;
		SlideTime = 0.f;
		bWantsToCrouch = true;
		Velocity += Velocity.GetSafeNormal2D() * SlideBoost;
	}

	if (bSlidingNow)
	{
		SlideTime += DeltaSeconds;
		const bool bTooSlow = SlideTime > 0.15f && Velocity.Size2D() < SlideEndSpeed;
		if (SlideTime > SlideMaxTime || bTooSlow || !bWantsToCrouch || IsOwnerOut() || IsFalling())
		{
			bSlidingNow = false;
			SlideCooldownLeft = SlideCooldown;
		}
	}

	bSprintingNow = !bSlidingNow && CanSprint();
	Super::UpdateCharacterStateBeforeMovement(DeltaSeconds);
}

void UAirsoftMovementComponent::CalcVelocity(float DeltaTime, float Friction, bool bFluid, float BrakingDeceleration)
{
	if (bSlidingNow && IsMovingOnGround())
	{
		// Momentum carries the slide; input can't add speed, only low friction slows it.
		const FVector SavedAccel = Acceleration;
		Acceleration = FVector::ZeroVector;
		Super::CalcVelocity(DeltaTime, SlideFriction, bFluid, SlideBraking);
		Acceleration = SavedAccel;
		return;
	}
	Super::CalcVelocity(DeltaTime, Friction, bFluid, BrakingDeceleration);
}

float UAirsoftMovementComponent::GetMaxSpeed() const
{
	if (IsOwnerFrozen())
	{
		return 0.f;
	}
	if (MovementMode != MOVE_Walking && MovementMode != MOVE_NavWalking && MovementMode != MOVE_Falling)
	{
		return Super::GetMaxSpeed();
	}
	if (bSlidingNow)
	{
		return SprintSpeed + SlideBoost + 120.f;
	}
	if (IsOwnerOut())
	{
		return OutSpeed;
	}
	float Speed = WalkSpeed;
	if (IsCrouching())
	{
		Speed = CrouchSpeed;
	}
	else if (bSprintingNow)
	{
		Speed = SprintSpeed;
	}
	else if (bWantsAimWalk)
	{
		Speed = AimWalkSpeed;
	}
	return Speed * SpeedMultiplier();
}

float UAirsoftMovementComponent::GetMaxBrakingDeceleration() const
{
	return bSlidingNow ? SlideBraking : Super::GetMaxBrakingDeceleration();
}

bool UAirsoftMovementComponent::CanAttemptJump() const
{
	return !bSlidingNow && !IsOwnerFrozen() && !IsOwnerOut() && Super::CanAttemptJump();
}
