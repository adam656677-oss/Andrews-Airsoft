#include "AirsoftCharacter.h"

#include "AirsoftAssets.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGunVisual.h"
#include "AirsoftMovementComponent.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"

namespace
{
	constexpr float CapsuleRadius = 36.f;
	constexpr float CapsuleHalfHeight = 92.f;
	constexpr float StandEye = 164.f;
	constexpr float CrouchEye = 102.f;
	constexpr float SlideEye = 84.f;
	constexpr float LeanOffset = 32.f;
	constexpr float LeanRoll = 11.f;

	void MakeBBTarget(UPrimitiveComponent* Comp)
	{
		Comp->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		Comp->SetCollisionResponseToAllChannels(ECR_Ignore);
		Comp->SetCollisionResponseToChannel(ECC_BB, ECR_Block);
		Comp->SetGenerateOverlapEvents(false);
	}

	void MakeCosmetic(UPrimitiveComponent* Comp)
	{
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetGenerateOverlapEvents(false);
		Comp->SetCastShadow(false);
	}
}

AAirsoftCharacter::AAirsoftCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UAirsoftMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = true;
	bUseControllerRotationYaw = true;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;
	BaseEyeHeight = StandEye - CapsuleHalfHeight;
	CrouchedEyeHeight = CrouchEye - 58.f;

	UCapsuleComponent* Capsule = GetCapsuleComponent();
	Capsule->InitCapsuleSize(CapsuleRadius, CapsuleHalfHeight);
	// BBs hit the actual body (mannequin physics asset or stand-in), not the movement capsule.
	Capsule->SetCollisionResponseToChannel(ECC_BB, ECR_Ignore);

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(Capsule);
	Camera->SetRelativeLocation(FVector(0.f, 0.f, StandEye - CapsuleHalfHeight));
	Camera->bUsePawnControlRotation = true;
	Camera->SetFieldOfView(90.f);

	ViewRoot = CreateDefaultSubobject<USceneComponent>(TEXT("ViewRoot"));
	ViewRoot->SetupAttachment(Camera);

	FPGun = CreateDefaultSubobject<UAirsoftGunVisual>(TEXT("FPGun"));
	FPGun->SetupAttachment(ViewRoot);

	TPAimRoot = CreateDefaultSubobject<USceneComponent>(TEXT("TPAimRoot"));
	TPAimRoot->SetupAttachment(Capsule);
	TPAimRoot->SetRelativeLocation(FVector(0.f, 0.f, 46.f));

	TPGun = CreateDefaultSubobject<UAirsoftGunVisual>(TEXT("TPGun"));
	TPGun->SetupAttachment(TPAimRoot);
	TPGun->SetRelativeLocation(FVector(16.f, 17.f, -9.f));

	Combat = CreateDefaultSubobject<UAirsoftCombatComponent>(TEXT("Combat"));

	FallbackBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FallbackBody"));
	FallbackBody->SetupAttachment(Capsule);
	FallbackBody->SetRelativeLocation(FVector(0.f, 0.f, -26.f));
	FallbackBody->SetRelativeScale3D(FVector(0.56f, 0.42f, 1.3f));
	FallbackBody->SetOwnerNoSee(true);
	FallbackBody->bCastHiddenShadow = true;

	FallbackHead = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FallbackHead"));
	FallbackHead->SetupAttachment(Capsule);
	FallbackHead->SetRelativeLocation(FVector(0.f, 0.f, 64.f));
	FallbackHead->SetRelativeScale3D(FVector(0.27f));
	FallbackHead->SetOwnerNoSee(true);
	FallbackHead->bCastHiddenShadow = true;

	TeamBand = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("TeamBand"));
	TeamBand->SetupAttachment(Capsule);
	TeamBand->SetRelativeLocation(FVector(0.f, -24.f, 30.f));
	TeamBand->SetRelativeScale3D(FVector(0.14f, 0.14f, 0.07f));
	TeamBand->SetOwnerNoSee(true);

	DeadRag = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DeadRag"));
	DeadRag->SetupAttachment(Capsule);
	DeadRag->SetRelativeLocation(FVector(0.f, 0.f, 108.f));
	DeadRag->SetRelativeScale3D(FVector(0.02f, 0.3f, 0.2f));
	DeadRag->SetOwnerNoSee(true);
	DeadRag->SetHiddenInGame(false);
	DeadRag->SetVisibility(false);

	HitCall = CreateDefaultSubobject<UTextRenderComponent>(TEXT("HitCall"));
	HitCall->SetupAttachment(Capsule);
	HitCall->SetRelativeLocation(FVector(0.f, 0.f, 140.f));
	HitCall->SetHorizontalAlignment(EHTA_Center);
	HitCall->SetVerticalAlignment(EVRTA_TextCenter);
	HitCall->SetWorldSize(34.f);
	HitCall->SetText(FText::FromString(TEXT("HIT!")));
	HitCall->SetTextRenderColor(FColor(255, 120, 20));
	HitCall->SetOwnerNoSee(true);
	HitCall->SetVisibility(false);

	PoseMesh = CreateDefaultSubobject<UPoseableMeshComponent>(TEXT("PoseMesh"));
	PoseMesh->SetupAttachment(GetMesh());
	PoseMesh->SetOwnerNoSee(true);
	PoseMesh->bCastHiddenShadow = true;
	PoseMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	PoseMesh->SetVisibility(false);

	MakeBBTarget(FallbackBody);
	MakeBBTarget(FallbackHead);
	MakeCosmetic(TeamBand);
	MakeCosmetic(DeadRag);

	GetMesh()->SetOwnerNoSee(true);
	GetMesh()->bCastHiddenShadow = true;
	GetMesh()->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -CapsuleHalfHeight), FRotator(0.f, -90.f, 0.f));
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;

	SetNetUpdateFrequency(60.f);
	SetMinNetUpdateFrequency(20.f);
}

void AAirsoftCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(AAirsoftCharacter, bIsOutReplicated);
	DOREPLIFETIME(AAirsoftCharacter, bFrozen);
	DOREPLIFETIME_CONDITION(AAirsoftCharacter, bSprinting, COND_SkipOwner);
	DOREPLIFETIME_CONDITION(AAirsoftCharacter, bSliding, COND_SkipOwner);
	DOREPLIFETIME_CONDITION(AAirsoftCharacter, LeanAmount, COND_SkipOwner);
	DOREPLIFETIME(AAirsoftCharacter, TaggedByName);
}

UAirsoftMovementComponent* AAirsoftCharacter::GetAirsoftMovement() const
{
	return Cast<UAirsoftMovementComponent>(GetCharacterMovement());
}

AAirsoftPlayerState* AAirsoftCharacter::GetAirsoftPlayerState() const
{
	return GetPlayerState<AAirsoftPlayerState>();
}

EAirsoftTeam AAirsoftCharacter::GetTeam() const
{
	const AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	return PS ? PS->Team : EAirsoftTeam::None;
}

FString AAirsoftCharacter::GetDisplayName() const
{
	const AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	return PS ? PS->GetPlayerName() : FString(TEXT("Player"));
}

bool AAirsoftCharacter::IsSprinting() const
{
	if (IsLocallyControlled() || HasAuthority())
	{
		const UAirsoftMovementComponent* Move = GetAirsoftMovement();
		return Move && Move->IsSprintingNow();
	}
	return bSprinting;
}

bool AAirsoftCharacter::IsSliding() const
{
	if (IsLocallyControlled() || HasAuthority())
	{
		const UAirsoftMovementComponent* Move = GetAirsoftMovement();
		return Move && Move->IsSlidingNow();
	}
	return bSliding;
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

void AAirsoftCharacter::BeginPlay()
{
	Super::BeginPlay();

	FallbackBody->SetStaticMesh(AirsoftAssets::Cylinder());
	FallbackHead->SetStaticMesh(AirsoftAssets::Sphere());
	TeamBand->SetStaticMesh(AirsoftAssets::Cylinder());
	DeadRag->SetStaticMesh(AirsoftAssets::Cube());

	if (UMaterialInterface* Base = FallbackBody->GetMaterial(0))
	{
		BodyMID = UMaterialInstanceDynamic::Create(Base, this);
		FallbackBody->SetMaterial(0, BodyMID);
		FallbackHead->SetMaterial(0, BodyMID);
	}
	TeamMID = AirsoftAssets::MakeEmissive(this, AirsoftColors::Team(GetTeam()), 3.f);
	if (TeamMID)
	{
		TeamBand->SetMaterial(0, TeamMID);
	}
	RagMID = AirsoftAssets::MakeEmissive(this, FLinearColor(1.f, 0.25f, 0.02f), 6.f);
	if (RagMID)
	{
		DeadRag->SetMaterial(0, RagMID);
	}

	SetupThirdPersonBody();
	ApplyOutVisuals();
	ApplyTeamLook();
	EyeHeight = StandEye;
}

void AAirsoftCharacter::SetupThirdPersonBody()
{
	const UAirsoftSettings* Settings = UAirsoftSettings::Get();
	USkeletalMesh* BodyMesh = Settings->ThirdPersonMesh.IsNull() ? nullptr : Settings->ThirdPersonMesh.LoadSynchronous();
	bHasMannequin = BodyMesh != nullptr;

	if (bHasMannequin)
	{
		GetMesh()->SetSkeletalMesh(BodyMesh);
		if (UClass* AnimClass = Settings->ThirdPersonAnimClass.IsNull() ? nullptr : Settings->ThirdPersonAnimClass.LoadSynchronous())
		{
			GetMesh()->SetAnimInstanceClass(AnimClass);
		}
		GetMesh()->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
		GetMesh()->SetCollisionResponseToChannel(ECC_BB, ECR_Block);

		// Armband on the left upper arm.
		if (GetMesh()->DoesSocketExist(TEXT("upperarm_l")))
		{
			TeamBand->AttachToComponent(GetMesh(), FAttachmentTransformRules::KeepRelativeTransform, TEXT("upperarm_l"));
			TeamBand->SetRelativeLocationAndRotation(FVector(14.f, 0.f, 0.f), FRotator(90.f, 0.f, 0.f));
			TeamBand->SetRelativeScale3D(FVector(0.13f, 0.13f, 0.07f));
		}
		if (!Settings->ThirdPersonGunSocket.IsNone() && GetMesh()->DoesSocketExist(Settings->ThirdPersonGunSocket))
		{
			TPGun->AttachToComponent(GetMesh(), FAttachmentTransformRules::KeepRelativeTransform, Settings->ThirdPersonGunSocket);
			TPGun->SetRelativeTransform(Settings->ThirdPersonGunOffset);
		}

		// No rifle animations needed: the animated mesh drives a hidden pose, and a poseable copy
		// is what everyone sees, with both arms bent onto the gun each frame.
		bool bHasArmBones = true;
		for (const TCHAR* Bone : { TEXT("upperarm_r"), TEXT("lowerarm_r"), TEXT("hand_r"), TEXT("upperarm_l"), TEXT("lowerarm_l"), TEXT("hand_l") })
		{
			bHasArmBones = bHasArmBones && GetMesh()->DoesSocketExist(Bone);
		}
		bUsePoseMesh = bHasArmBones && TPGun->GetAttachParent() == TPAimRoot;
		if (bUsePoseMesh)
		{
			PoseMesh->SetSkinnedAssetAndUpdate(BodyMesh, true);
			PoseMesh->SetVisibility(true);
			GetMesh()->SetVisibility(false);
			GetMesh()->SetCastShadow(false);
			GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
			if (TeamBand->GetAttachParent() == GetMesh())
			{
				TeamBand->AttachToComponent(PoseMesh, FAttachmentTransformRules::KeepRelativeTransform, TEXT("upperarm_l"));
			}
		}
	}
	else
	{
		GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	FallbackBody->SetVisibility(!bHasMannequin);
	FallbackHead->SetVisibility(!bHasMannequin);
	FallbackBody->SetCollisionEnabled(bHasMannequin ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryOnly);
	FallbackHead->SetCollisionEnabled(bHasMannequin ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryOnly);
}

void AAirsoftCharacter::UpdateThirdPersonPose()
{
	if (!bUsePoseMesh || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	PoseMesh->CopyPoseFromSkeletalComponent(GetMesh());
	// The owner never sees their own body (only its shadow), and tagged players drop the gun pose.
	if (IsLocallyControlled() || IsOut() || !TPGun->IsVisible())
	{
		return;
	}
	const FTransform Gun = TPGun->GetComponentTransform();
	const FVector Up = GetActorUpVector();
	const FVector Right = GetActorRightVector();
	const FVector Forward = GetActorForwardVector();
	// Wrists sit a little behind/below the grip and the support-hand point.
	const FVector RightWrist = Gun.TransformPosition(FVector(-3.f, 3.f, -5.f));
	const FVector LeftWrist = Gun.TransformPosition(TPGun->LeftHandLocal + FVector(-2.f, -4.f, -6.f));
	const FVector RightShoulder = PoseMesh->GetBoneTransformByName(TEXT("upperarm_r"), EBoneSpaces::WorldSpace).GetLocation();
	const FVector LeftShoulder = PoseMesh->GetBoneTransformByName(TEXT("upperarm_l"), EBoneSpaces::WorldSpace).GetLocation();
	SolveArm(TEXT("upperarm_r"), TEXT("lowerarm_r"), TEXT("hand_r"), RightWrist, RightShoulder + Right * 25.f - Up * 45.f - Forward * 10.f);
	SolveArm(TEXT("upperarm_l"), TEXT("lowerarm_l"), TEXT("hand_l"), LeftWrist, LeftShoulder - Right * 30.f - Up * 40.f - Forward * 5.f);
}

void AAirsoftCharacter::SolveArm(FName UpperName, FName LowerName, FName HandName, const FVector& WristTargetWorld, const FVector& PoleWorld)
{
	// Analytic two-bone IK in component space; the elbow bends toward the pole.
	const FTransform ToWorld = PoseMesh->GetComponentTransform();
	const FTransform Upper = PoseMesh->GetBoneTransformByName(UpperName, EBoneSpaces::ComponentSpace);
	const FTransform Lower = PoseMesh->GetBoneTransformByName(LowerName, EBoneSpaces::ComponentSpace);
	const FTransform Hand = PoseMesh->GetBoneTransformByName(HandName, EBoneSpaces::ComponentSpace);
	const FVector Shoulder = Upper.GetLocation();
	const FVector Elbow0 = Lower.GetLocation();
	const FVector Wrist0 = Hand.GetLocation();
	const double A = FVector::Dist(Shoulder, Elbow0);
	const double B = FVector::Dist(Elbow0, Wrist0);
	if (A < 1.0 || B < 1.0)
	{
		return;
	}
	const FVector Target = ToWorld.InverseTransformPosition(WristTargetWorld);
	const FVector Pole = ToWorld.InverseTransformPosition(PoleWorld);
	const FVector ToTarget = Target - Shoulder;
	const double Length = ToTarget.Size();
	if (Length < KINDA_SMALL_NUMBER)
	{
		return;
	}
	const FVector Dir = ToTarget / Length;
	const double D = FMath::Clamp(Length, FMath::Abs(A - B) + 1.0, A + B - 0.5);
	const double CosA = FMath::Clamp((A * A + D * D - B * B) / (2.0 * A * D), -1.0, 1.0);
	const double SinA = FMath::Sqrt(FMath::Max(0.0, 1.0 - CosA * CosA));
	FVector Bend = (Pole - Shoulder) - Dir * FVector::DotProduct(Pole - Shoulder, Dir);
	if (!Bend.Normalize())
	{
		Bend = FVector::CrossProduct(Dir, FVector::RightVector).GetSafeNormal();
	}
	const FVector Elbow = Shoulder + Dir * (A * CosA) + Bend * (A * SinA);
	const FVector Wrist = Shoulder + Dir * D;

	const FQuat DeltaUpper = FQuat::FindBetweenNormals((Elbow0 - Shoulder) / A, (Elbow - Shoulder) / A);
	const FVector LowerAfter = DeltaUpper.RotateVector((Wrist0 - Elbow0) / B);
	const FQuat DeltaLower = FQuat::FindBetweenNormals(LowerAfter, (Wrist - Elbow).GetSafeNormal());

	FTransform NewUpper = Upper;
	NewUpper.SetRotation(DeltaUpper * Upper.GetRotation());
	FTransform NewLower = Lower;
	NewLower.SetLocation(Elbow);
	NewLower.SetRotation(DeltaLower * DeltaUpper * Lower.GetRotation());
	FTransform NewHand = Hand;
	NewHand.SetLocation(Wrist);
	NewHand.SetRotation(DeltaLower * DeltaUpper * Hand.GetRotation());

	PoseMesh->SetBoneTransformByName(UpperName, NewUpper, EBoneSpaces::ComponentSpace);
	PoseMesh->SetBoneTransformByName(LowerName, NewLower, EBoneSpaces::ComponentSpace);
	PoseMesh->SetBoneTransformByName(HandName, NewHand, EBoneSpaces::ComponentSpace);
}

void AAirsoftCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	ApplyTeamLook();
}

void AAirsoftCharacter::OnRep_PlayerState()
{
	Super::OnRep_PlayerState();
	ApplyTeamLook();
}

void AAirsoftCharacter::ApplyTeamLook()
{
	const EAirsoftTeam Team = GetTeam();
	AppliedTeam = Team;
	bTeamApplied = GetAirsoftPlayerState() != nullptr;
	const FLinearColor Color = AirsoftColors::Team(Team);
	if (TeamMID)
	{
		TeamMID->SetVectorParameterValue(TEXT("Color"), Color);
	}
	if (BodyMID)
	{
		// Muted team-tinted fatigues on the stand-in body.
		const FLinearColor Fatigue = FMath::Lerp(FLinearColor(0.09f, 0.1f, 0.08f), Color * 0.35f, 0.35f);
		BodyMID->SetVectorParameterValue(TEXT("Color"), Fatigue);
	}
	if (Combat)
	{
		Combat->RefreshVisuals();
	}
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

void AAirsoftCharacter::MoveInput(const FVector2D& Axis)
{
	if (!Controller)
	{
		return;
	}
	const FRotator YawRot(0.f, Controller->GetControlRotation().Yaw, 0.f);
	const FRotationMatrix M(YawRot);
	AddMovementInput(M.GetUnitAxis(EAxis::X), Axis.Y);
	AddMovementInput(M.GetUnitAxis(EAxis::Y), Axis.X);
}

void AAirsoftCharacter::LookInput(float YawDegrees, float PitchDegrees)
{
	if (!Controller)
	{
		return;
	}
	// Slow the look down while aiming in proportion to the zoom.
	float Scale = 1.f;
	if (Combat && Combat->GetAimAlpha() > 0.f)
	{
		float AimSens = 0.7f;
		float BaseFOV = 90.f;
		if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
		{
			AimSens = GI->GetUserSettings().AimSensitivity;
			BaseFOV = GI->GetUserSettings().FieldOfView;
		}
		const float Zoom = Camera->FieldOfView / FMath::Max(BaseFOV, 1.f);
		Scale = FMath::Lerp(1.f, AimSens * Zoom, Combat->GetAimAlpha());
	}
	FRotator R = Controller->GetControlRotation();
	R.Pitch = FMath::ClampAngle(static_cast<float>(FRotator::NormalizeAxis(R.Pitch)) + PitchDegrees * Scale, -88.f, 88.f);
	R.Yaw = FRotator::NormalizeAxis(R.Yaw + YawDegrees * Scale);
	R.Roll = 0.f;
	Controller->SetControlRotation(R);
}

void AAirsoftCharacter::SetSprintHeld(bool bHeld)
{
	bSprintHeld = bHeld;
	if (bHeld)
	{
		bSprintSuppressed = false;
		if (bIsCrouched && !IsSliding())
		{
			UnCrouch();
		}
		if (Combat)
		{
			Combat->SetAimHeld(false);
		}
	}
}

void AAirsoftCharacter::ToggleSprint()
{
	bSprintToggled = !bSprintToggled;
	if (bSprintToggled)
	{
		bSprintSuppressed = false;
		if (bIsCrouched && !IsSliding())
		{
			UnCrouch();
		}
		if (Combat)
		{
			Combat->SetAimHeld(false);
		}
	}
}

void AAirsoftCharacter::CancelSprint()
{
	bSprintSuppressed = true;
	bSprintToggled = false;
}

void AAirsoftCharacter::ToggleCrouchInput()
{
	if (IsOut())
	{
		return;
	}
	if (bIsCrouched)
	{
		UnCrouch();
		return;
	}
	if (IsSprinting())
	{
		SlideRequestUntil = GetWorld()->GetTimeSeconds() + 0.25;
		bSprintToggled = false;
	}
	Crouch();
}

void AAirsoftCharacter::SetCrouchHeld(bool bHeld)
{
	if (bHeld)
	{
		if (!bIsCrouched)
		{
			ToggleCrouchInput();
		}
	}
	else if (bIsCrouched)
	{
		UnCrouch();
	}
}

void AAirsoftCharacter::SetLeanInput(float Direction)
{
	LeanTarget = FMath::Clamp(Direction, -1.f, 1.f);
}

void AAirsoftCharacter::JumpInput()
{
	if (IsOut() || IsFrozen())
	{
		return;
	}
	if (bIsCrouched && !IsSliding())
	{
		UnCrouch();
		return;
	}
	Jump();
}

void AAirsoftCharacter::ServerSetLean_Implementation(float NewLean)
{
	LeanAmount = FMath::Clamp(NewLean, -1.f, 1.f);
}

// ---------------------------------------------------------------------------
// Out / frozen
// ---------------------------------------------------------------------------

void AAirsoftCharacter::ServerMarkOut(const FString& TaggedBy)
{
	if (!HasAuthority() || bIsOutReplicated)
	{
		return;
	}
	bIsOutReplicated = true;
	TaggedByName = TaggedBy;
	LeanAmount = 0.f;
	if (AAirsoftPlayerState* PS = GetAirsoftPlayerState())
	{
		PS->bOut = true;
	}
	OnRep_Out();
}

void AAirsoftCharacter::ServerSetFrozen(bool bInFrozen)
{
	if (HasAuthority())
	{
		bFrozen = bInFrozen;
		OnRep_Frozen();
	}
}

void AAirsoftCharacter::OnRep_Frozen()
{
	if (bFrozen)
	{
		GetCharacterMovement()->StopMovementImmediately();
	}
}

void AAirsoftCharacter::OnRep_Out()
{
	ApplyOutVisuals();
	if (!bIsOutReplicated)
	{
		return;
	}
	AirsoftAssets::Play3D(this, TEXT("HitCall"), GetActorLocation() + FVector(0.f, 0.f, 70.f), 0.9f, FMath::FRandRange(0.92f, 1.08f));
	if (IsLocallyControlled())
	{
		AirsoftAssets::Play2D(this, TEXT("Tagged"), 0.8f, 1.f);
		if (Combat)
		{
			Combat->CancelActions();
		}
		bSprintToggled = false;
		LeanTarget = 0.f;
		if (bIsCrouched)
		{
			UnCrouch();
		}
	}
}

void AAirsoftCharacter::ApplyOutVisuals()
{
	const bool bOut = bIsOutReplicated;
	DeadRag->SetVisibility(bOut);
	HitCall->SetVisibility(bOut);
	// Tagged players walk off through everyone and BBs pass through them.
	GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, bOut ? ECR_Ignore : ECR_Block);
	const ECollisionResponse BB = bOut ? ECR_Ignore : ECR_Block;
	GetMesh()->SetCollisionResponseToChannel(ECC_BB, bHasMannequin ? BB : ECR_Ignore);
	FallbackBody->SetCollisionResponseToChannel(ECC_BB, bHasMannequin ? ECR_Ignore : BB);
	FallbackHead->SetCollisionResponseToChannel(ECC_BB, bHasMannequin ? ECR_Ignore : BB);
}

void AAirsoftCharacter::Landed(const FHitResult& Hit)
{
	Super::Landed(Hit);
	const float FallSpeed = -GetCharacterMovement()->Velocity.Z;
	LandDip = FMath::Clamp(FallSpeed / 900.f * 7.f, 0.f, 9.f);
	AirsoftAssets::Play3D(this, TEXT("Land"), GetActorLocation() - FVector(0.f, 0.f, CapsuleHalfHeight), FMath::Clamp(FallSpeed / 700.f, 0.2f, 0.8f), FMath::FRandRange(0.9f, 1.05f));
}

// ---------------------------------------------------------------------------
// Per frame
// ---------------------------------------------------------------------------

void AAirsoftCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (!bTeamApplied || AppliedTeam != GetTeam())
	{
		if (GetAirsoftPlayerState())
		{
			ApplyTeamLook();
		}
	}

	UAirsoftMovementComponent* Move = GetAirsoftMovement();
	if (HasAuthority() && Move)
	{
		bSprinting = Move->IsSprintingNow();
		bSliding = Move->IsSlidingNow();
	}

	if (IsLocallyControlled())
	{
		if (Move)
		{
			const bool bMoving = GetVelocity().Size2D() > 40.f || !GetLastMovementInputVector().IsNearlyZero();
			if (bSprintToggled && !bMoving)
			{
				bSprintToggled = false;
			}
			Move->bWantsSprint = (bSprintHeld || bSprintToggled) && !bSprintSuppressed && !IsOut();
			Move->bWantsSlide = GetWorld()->GetTimeSeconds() < SlideRequestUntil;
			Move->bWantsAimWalk = Combat && Combat->GetAimAlpha() > 0.3f;
		}
		UpdateCamera(DeltaSeconds);
	}
	UpdateRemoteVisuals(DeltaSeconds);

	// Footsteps.
	if (Move && Move->IsMovingOnGround())
	{
		const float Speed = GetVelocity().Size2D();
		if (Speed > 80.f && !IsSliding())
		{
			StepAccum += Speed * DeltaSeconds;
			const bool bSprint = IsSprinting();
			const float Stride = bIsCrouched ? 115.f : bSprint ? 215.f : 165.f;
			if (StepAccum >= Stride)
			{
				StepAccum = 0.f;
				const float Volume = (bIsCrouched ? 0.12f : bSprint ? 0.55f : 0.32f) * (IsLocallyControlled() ? 0.6f : 1.f);
				AirsoftAssets::Play3D(this, TEXT("Footstep"), GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()), Volume, FMath::FRandRange(0.85f, 1.15f));
			}
		}
	}
}

void AAirsoftCharacter::UpdateCamera(float DeltaSeconds)
{
	const bool bSlidingNow = IsSliding();
	const float EyeTarget = bSlidingNow ? SlideEye : bIsCrouched ? CrouchEye : StandEye;
	EyeHeight = FMath::FInterpTo(EyeHeight, EyeTarget, DeltaSeconds, 11.f);
	LandDip = FMath::FInterpTo(LandDip, 0.f, DeltaSeconds, 7.f);

	// Lean, stopped short by walls.
	const bool bCanLean = !IsSprinting() && !bSlidingNow && !IsOut();
	float Wanted = bCanLean ? LeanTarget : 0.f;
	const float HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
	if (!FMath::IsNearlyZero(Wanted))
	{
		const FVector Eye = GetActorLocation() + FVector(0.f, 0.f, EyeHeight - HalfHeight);
		const FVector Side = GetActorRightVector() * FMath::Sign(Wanted) * (LeanOffset + 12.f);
		FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftLean), false, this);
		FHitResult Hit;
		if (GetWorld()->SweepSingleByChannel(Hit, Eye, Eye + Side, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(10.f), Query))
		{
			Wanted *= Hit.Time;
		}
	}
	LeanAmount = FMath::FInterpTo(LeanAmount, Wanted, DeltaSeconds, 9.f);
	if (FMath::Abs(LeanAmount - LeanSent) > 0.04f || (FMath::IsNearlyZero(Wanted) && !FMath::IsNearlyZero(LeanSent) && FMath::Abs(LeanAmount) < 0.02f))
	{
		LeanSent = FMath::Abs(LeanAmount) < 0.02f ? 0.f : LeanAmount;
		if (!HasAuthority())
		{
			ServerSetLean(LeanSent);
		}
	}

	const float SlideRoll = bSlidingNow ? -4.f : 0.f;
	const float Roll = LeanAmount * LeanRoll + SlideRoll;
	Camera->SetRelativeLocation(FVector(0.f, LeanAmount * LeanOffset, EyeHeight - HalfHeight - LandDip));
	Camera->ClearAdditiveOffset();
	Camera->AddAdditiveOffset(FTransform(FRotator(0.f, 0.f, Roll)), 0.f);
	ViewRoot->SetRelativeRotation(FRotator(0.f, 0.f, Roll));

	// Field of view: user setting, zoomed by the gun's optic, widened slightly when sprinting.
	float BaseFOV = 90.f;
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		BaseFOV = FMath::Clamp(GI->GetUserSettings().FieldOfView, 70.f, 110.f);
	}
	const float Extra = IsSprinting() ? 6.f : bSlidingNow ? 9.f : 0.f;
	const float TargetFOV = (Combat ? Combat->GetTargetFOV(BaseFOV) : BaseFOV) + Extra;
	Camera->SetFieldOfView(FMath::FInterpTo(Camera->FieldOfView, TargetFOV, DeltaSeconds, 14.f));

	// Tagged: the world drains of colour until respawn.
	OutFade = FMath::FInterpTo(OutFade, IsOut() ? 1.f : 0.f, DeltaSeconds, 3.f);
	FPostProcessSettings& PP = Camera->PostProcessSettings;
	PP.bOverride_ColorSaturation = true;
	PP.ColorSaturation = FVector4(1.f, 1.f, 1.f, 1.f - 0.75f * OutFade);
	PP.bOverride_VignetteIntensity = true;
	PP.VignetteIntensity = 0.4f + 0.6f * OutFade;
	Camera->PostProcessBlendWeight = 1.f;
}

void AAirsoftCharacter::UpdateRemoteVisuals(float DeltaSeconds)
{
	// Third-person gun follows where the player is looking.
	if (TPGun->GetAttachParent() == TPAimRoot)
	{
		const float Pitch = FRotator::NormalizeAxis(GetBaseAimRotation().Pitch);
		const float Crouch = bIsCrouched ? -24.f : 0.f;
		TPAimRoot->SetRelativeLocationAndRotation(FVector(0.f, LeanVisual * 22.f, 46.f + Crouch), FRotator(Pitch, 0.f, LeanVisual * 12.f));
		// Rifles tucked into the shoulder, pistols pushed out at arm's length.
		const bool bPistol = Combat && Combat->Current().Class == TEXT("Pistol");
		TPGun->SetRelativeLocation(bPistol ? FVector(38.f, 6.f, -2.f) : FVector(16.f, 17.f, -9.f));
	}

	if (!IsLocallyControlled())
	{
		LeanVisual = FMath::FInterpTo(LeanVisual, LeanAmount, DeltaSeconds, 10.f);
	}
	else
	{
		LeanVisual = LeanAmount;
	}

	if (bHasMannequin)
	{
		const FQuat Lean(FVector::ForwardVector, FMath::DegreesToRadians(LeanVisual * 10.f));
		GetMesh()->SetRelativeRotation(Lean * FQuat(FRotator(0.f, -90.f, 0.f)));
	}
	else
	{
		FallbackBody->SetRelativeRotation(FRotator(0.f, 0.f, LeanVisual * 10.f));
		FallbackHead->SetRelativeLocation(FVector(0.f, LeanVisual * 18.f, bIsCrouched ? 30.f : 64.f));
	}

	// "HIT!" call and rag always face the local camera.
	if (HitCall->IsVisible())
	{
		if (const APlayerController* PC = GetWorld()->GetFirstPlayerController())
		{
			if (PC->PlayerCameraManager)
			{
				const FVector CamLoc = PC->PlayerCameraManager->GetCameraLocation();
				const FRotator Face = (CamLoc - HitCall->GetComponentLocation()).Rotation();
				HitCall->SetWorldRotation(FRotator(0.f, Face.Yaw, 0.f));
				DeadRag->SetWorldRotation(FRotator(0.f, Face.Yaw, FMath::Sin(GetWorld()->GetTimeSeconds() * 6.f) * 8.f));
			}
		}
	}
}
