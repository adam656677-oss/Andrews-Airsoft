#include "AirsoftCharacter.h"

#include "AirsoftAssets.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftEffects.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftGunVisual.h"
#include "AirsoftMovementComponent.h"
#include "AirsoftPlayerState.h"
#include "AirsoftTeamGearComponent.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Engine/HitResult.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Net/UnrealNetwork.h"

// Named (not anonymous): unity builds merge .cpp files.
namespace AirsoftCharacterLocal
{
	/** True once a step sound (or its _01.._06 variations) is imported; checked once per key. */
	bool HasStepSound(FName Key)
	{
		static TMap<FName, bool> Known;
		if (const bool* Found = Known.Find(Key))
		{
			return *Found;
		}
		const bool bHas = AirsoftAssets::Sound(FName(*(Key.ToString() + TEXT("_01")))) != nullptr || AirsoftAssets::Sound(Key) != nullptr;
		Known.Add(Key, bHas);
		return bHas;
	}

	/**
	 * The step sound for the ground under the foot (Tools/Audio foley.py: Footstep* keys), and how it sits next to
	 * the gravel default. Falls back to gravel when a surface set has not been imported yet.
	 */
	FName FootstepFor(EAirsoftSurface Surface, float& OutVolume, float& OutPitch)
	{
		static const FName Gravel(TEXT("Footstep")), Grass(TEXT("FootstepGrass")), Concrete(TEXT("FootstepConcrete")),
			Metal(TEXT("FootstepMetal")), Wet(TEXT("FootstepWet"));
		OutVolume = 1.f;
		OutPitch = 1.f;
		FName Key = Gravel;
		switch (Surface)
		{
		case EAirsoftSurface::Foliage: Key = Grass; OutVolume = 0.8f; break;
		case EAirsoftSurface::Stone: Key = Concrete; break;
		case EAirsoftSurface::Wood: Key = Concrete; OutPitch = 0.82f; OutVolume = 0.85f; break;  // boards: a duller knock
		case EAirsoftSurface::Soft: Key = Concrete; OutPitch = 0.75f; OutVolume = 0.35f; break;  // carpet, velvet: muffled
		case EAirsoftSurface::Metal:
		case EAirsoftSurface::Steel: Key = Metal; OutVolume = 0.6f; break;                      // the plate ring carries
		case EAirsoftSurface::Water: Key = Wet; break;
		default: break;                                                                          // dirt, gravel, unknown
		}
		if (Key != Gravel && !HasStepSound(Key))
		{
			OutVolume = 1.f;
			OutPitch = 1.f;
			return Gravel;
		}
		return Key;
	}
}

namespace
{
	constexpr float CapsuleRadius = 36.f;
	constexpr float CapsuleHalfHeight = 92.f;
	constexpr float StandEye = 164.f;
	constexpr float CrouchEye = 102.f;
	constexpr float SlideEye = 84.f;
	constexpr float LeanOffset = 32.f;
	constexpr float LeanRoll = 11.f;
	// Third person: boom pivot a little below the eyes, camera 2 m back and over the shoulder,
	// so the character stands left (or right) of the crosshair, rifle low in frame.
	constexpr float TPPivotDrop = 12.f;
	constexpr float TPArmLength = 200.f;
	constexpr float TPShoulderOffset = 60.f;
	constexpr float TPRise = 14.f;
	/** The owner's body shows once the camera is this far out from the eyes (0..1). */
	constexpr float TPBodyFrom = 0.3f;

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

	// Third person: a boom from the shoulders with a collision probe and a little lag. Its camera only
	// drives the view through CalcCamera; the eye camera above stays the gameplay camera.
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(Capsule);
	CameraBoom->SetRelativeLocation(FVector(0.f, 0.f, StandEye - CapsuleHalfHeight - TPPivotDrop));
	CameraBoom->TargetArmLength = TPArmLength;
	CameraBoom->SocketOffset = FVector(0.f, TPShoulderOffset, TPRise);
	CameraBoom->bUsePawnControlRotation = true;
	CameraBoom->bInheritRoll = false;
	CameraBoom->bDoCollisionTest = true;
	CameraBoom->ProbeSize = 14.f;
	CameraBoom->ProbeChannel = ECC_Camera;
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 14.f;
	CameraBoom->CameraLagMaxDistance = 45.f;
	CameraBoom->bEnableCameraRotationLag = false;
	CameraBoom->PrimaryComponentTick.bStartWithTickEnabled = false;

	ShoulderCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("ShoulderCamera"));
	ShoulderCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	ShoulderCamera->bUsePawnControlRotation = false;
	ShoulderCamera->SetFieldOfView(86.f);
	ShoulderCamera->SetAutoActivate(false);

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
	TeamGear = CreateDefaultSubobject<UAirsoftTeamGearComponent>(TEXT("TeamGear"));

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
	DOREPLIFETIME(AAirsoftCharacter, Health);
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

bool AAirsoftCharacter::IsLocalHuman() const
{
	const AController* MyController = GetController();
	return MyController && MyController->IsLocalPlayerController();
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
			// The dead rag is held up in the left hand.
			DeadRag->AttachToComponent(PoseMesh, FAttachmentTransformRules::KeepRelativeTransform, TEXT("hand_l"));
			DeadRag->SetRelativeLocation(FVector::ZeroVector);
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
	// In first person the owner never sees their own body, only its shadow (bots on the host are seen by everyone).
	if ((IsLocalHuman() && !bOwnerSeesBody) || !TPGun->IsVisible())
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
	if (IsOut())
	{
		// Airsoft etiquette: hand (and dead rag) up while walking off, gun pointed at the ground.
		SolveArm(TEXT("upperarm_l"), TEXT("lowerarm_l"), TEXT("hand_l"), LeftShoulder + Up * 62.f + Forward * 6.f + Right * 4.f, LeftShoulder - Right * 40.f + Forward * 10.f);
	}
	else
	{
		SolveArm(TEXT("upperarm_l"), TEXT("lowerarm_l"), TEXT("hand_l"), LeftWrist, LeftShoulder - Right * 30.f - Up * 40.f - Forward * 5.f);
	}
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
	if (Length < UE_KINDA_SMALL_NUMBER)
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
	if (TeamGear)
	{
		// Same player id on every machine, so everyone sees the same helmet/cap and colourway.
		const AAirsoftPlayerState* GearPS = GetAirsoftPlayerState();
		const int32 GearSeed = GearPS ? GearPS->GetPlayerId() : 0;
		if (bHasMannequin)
		{
			USkinnedMeshComponent* GearBody = bUsePoseMesh ? static_cast<USkinnedMeshComponent*>(PoseMesh.Get()) : GetMesh();
			TeamGear->ApplyTo(GearBody, Team, GearSeed);
		}
		else
		{
			TeamGear->ApplyToFallbackHead(FallbackHead, Team, GearSeed);
		}
		if (TeamBand)
		{
			TeamBand->SetVisibility(!TeamGear->HasArmband()); // the glowing band only when the gear isn't imported
		}
	}
	if (AAirsoftGameState::IsCampaign(this))
	{
		ApplyCampaignWardrobe();
	}
	if (Combat)
	{
		Combat->RefreshVisuals();
	}
}

void AAirsoftCharacter::ApplyCampaignWardrobe()
{
	// Story missions: tailored suits, not airsoft kit. No helmets, plate carriers or armbands.
	if (TeamBand)
	{
		TeamBand->SetVisibility(false);
	}
	const AAirsoftPlayerState* PS = GetAirsoftPlayerState();
	const bool bAndrew = GetTeam() == EAirsoftTeam::Blue;
	const AAirsoftGameState* GS = GetWorld() ? GetWorld()->GetGameState<AAirsoftGameState>() : nullptr;
	const bool bBoss = !bAndrew && PS && GS && !GS->BossName.IsEmpty() && PS->GetPlayerName() == GS->BossName;
	// The suit kit (jacket, shirt and tie, trousers, shoes, hair) on the mannequin; the dark body tint below
	// still covers the joints and hands. Falls back to the tint alone when the suit isn't imported.
	const FName Colorway = bAndrew ? FName(TEXT("Charcoal")) : (bBoss ? FName(TEXT("Oxblood")) : FName(TEXT("MidnightNavy")));
	if (TeamGear)
	{
		bool bSuited = false;
		if (bHasMannequin)
		{
			USkinnedMeshComponent* SuitBody = bUsePoseMesh ? static_cast<USkinnedMeshComponent*>(PoseMesh.Get()) : GetMesh();
			bSuited = TeamGear->ApplySuit(SuitBody, UAirsoftTeamGearComponent::SuitColor(Colorway), PS ? PS->GetPlayerId() : 0,
				bAndrew ? FName(TEXT("Black")) : NAME_None);
		}
		if (!bSuited)
		{
			TeamGear->Clear();
		}
	}
	// Andrew: charcoal. The Ledger's crews: midnight navy. Bosses: oxblood.
	const FLinearColor Suit = bAndrew ? FLinearColor(0.011f, 0.011f, 0.013f)
		: (bBoss ? FLinearColor(0.07f, 0.008f, 0.012f) : FLinearColor(0.012f, 0.016f, 0.03f));
	if (BodyMID)
	{
		BodyMID->SetVectorParameterValue(TEXT("Color"), Suit);
	}
	if (!bHasMannequin)
	{
		return;
	}
	for (UMeshComponent* Body : { static_cast<UMeshComponent*>(GetMesh()), static_cast<UMeshComponent*>(PoseMesh.Get()) })
	{
		if (!Body)
		{
			continue;
		}
		for (int32 Slot = 0; Slot < Body->GetNumMaterials(); ++Slot)
		{
			if (UMaterialInstanceDynamic* MID = Body->CreateDynamicMaterialInstance(Slot))
			{
				MID->SetVectorParameterValue(TEXT("Paint Tint"), Suit);
				MID->SetScalarParameterValue(TEXT("MetalPaintMetallic"), 0.f);
				MID->SetScalarParameterValue(TEXT("MetalPaintRoughness"), 0.72f);
				MID->SetScalarParameterValue(TEXT("EmissivePower"), 0.f);
			}
		}
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

// ---------------------------------------------------------------------------
// Story campaign: health, damage, death
// ---------------------------------------------------------------------------

bool AAirsoftCharacter::ServerApplyDamage(float Amount, const FString& From, const FVector& FromLocation)
{
	if (!HasAuthority() || bIsOutReplicated || Amount <= 0.f)
	{
		return false;
	}
	const float Old = Health;
	Health = FMath::Max(0.f, Health - Amount);
	LastDamageTime = GetWorld()->GetTimeSeconds();
	// OnRep doesn't fire on the server or in standalone: the local player's own feedback is played here.
	if (IsLocalHuman())
	{
		PlayDamageFeedback(Old - Health);
	}
	if (Health <= 0.f)
	{
		ServerMarkOut(From);
		return true;
	}
	return false;
}

float AAirsoftCharacter::GetHurtAlpha() const
{
	return MaxHealth > 0.f ? FMath::Clamp(1.f - Health / MaxHealth, 0.f, 1.f) : 0.f;
}

float AAirsoftCharacter::TimeSinceDamage() const
{
	return static_cast<float>(GetWorld()->GetTimeSeconds() - LastDamageTime);
}

void AAirsoftCharacter::OnRep_Health(float OldHealth)
{
	if (Health < OldHealth)
	{
		LastDamageTime = GetWorld()->GetTimeSeconds();
		if (IsLocalHuman())
		{
			PlayDamageFeedback(OldHealth - Health);
		}
	}
}

void AAirsoftCharacter::PlayDamageFeedback(float Amount)
{
	const float Strength = FMath::Clamp(Amount / 40.f, 0.15f, 1.f);
	HitPulse = FMath::Max(HitPulse, 0.4f + 0.6f * Strength);
	AddViewShake(0.25f + 0.35f * Strength, 1.f + 2.f * Strength);
	AirsoftAssets::Play2D(this, TEXT("Tagged"), 0.35f + 0.4f * Strength, FMath::FRandRange(0.85f, 1.f));
}

void AAirsoftCharacter::ApplyCampaignDeath()
{
	if (bRagdolled)
	{
		return;
	}
	bRagdolled = true;
	DeadRag->SetVisibility(false);
	HitCall->SetVisibility(false);
	GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	GetCharacterMovement()->DisableMovement();
	GetCharacterMovement()->StopMovementImmediately();
	TPGun->SetVisibility(false, true);
	if (!bHasMannequin)
	{
		// Stand-in body: topple it over.
		FallbackBody->SetRelativeLocationAndRotation(FVector(0.f, 0.f, -70.f), FRotator(90.f, 0.f, 0.f));
		FallbackHead->SetRelativeLocation(FVector(70.f, 0.f, -80.f));
		return;
	}
	USkeletalMeshComponent* Body = GetMesh();
	if (bUsePoseMesh)
	{
		// The posed copy can't simulate: show the real mesh (already in the same suit) instead.
		PoseMesh->SetVisibility(false);
		Body->SetVisibility(true);
		Body->SetCastShadow(true);
	}
	Body->SetCollisionProfileName(TEXT("Ragdoll"));
	Body->SetCollisionResponseToChannel(ECC_BB, ECR_Ignore);
	Body->SetAllBodiesSimulatePhysics(true);
	Body->SetSimulatePhysics(true);
	Body->WakeAllRigidBodies();
	Body->bBlendPhysics = true;
	// A little shove away from the last shot so the fall reads.
	Body->AddImpulse(GetActorForwardVector() * -2500.f + FVector(0.f, 0.f, 600.f), NAME_None, true);
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
	if (AAirsoftGameState::IsCampaign(this))
	{
		ApplyCampaignDeath();
		if (IsLocallyControlled() && Combat)
		{
			Combat->CancelActions();
		}
		return;
	}
	AirsoftAssets::Play3D(this, TEXT("HitCall"), GetActorLocation() + FVector(0.f, 0.f, 70.f), 0.9f, FMath::FRandRange(0.92f, 1.08f));
	// Effects: everyone watching sees an orange pop where the BB struck (not on join-in-progress replication).
	if (!IsLocalHuman() && GetGameTimeSinceCreation() > 0.5f)
	{
		if (UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this))
		{
			FX->TagPop(this);
		}
	}
	if (IsLocallyControlled())
	{
		if (IsLocalHuman())
		{
			AirsoftAssets::Play2D(this, TEXT("Tagged"), 0.8f, 1.f);
			// Effects: the victim's view pulses (desaturate + vignette) and flinches.
			HitPulse = 1.f;
			AddViewShake(0.45f, 2.5f);
		}
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
	// On a story mission "out" means dead (ragdoll, see ApplyCampaignDeath): no airsoft hit rag.
	const bool bAirsoftOut = bOut && !AAirsoftGameState::IsCampaign(this);
	DeadRag->SetVisibility(bAirsoftOut);
	HitCall->SetVisibility(bAirsoftOut);
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
	// Effects: dust off the ground on a hard landing.
	if (FallSpeed > 350.f)
	{
		if (UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this))
		{
			FX->LandingDust(Hit, FMath::Clamp((FallSpeed - 350.f) / 700.f, 0.f, 1.f));
		}
	}
}

void AAirsoftCharacter::AddViewShake(float Strength, float KickDegrees)
{
	if (!IsLocalHuman() || !AirsoftEffects::ScreenShakeEnabled(this))
	{
		return;
	}
	const float Scale = UAirsoftEffectsSettings::Get()->ShakeScale;
	if (ViewShake <= 0.f)
	{
		ViewShakeTime = FMath::FRandRange(0.f, 100.f); // a fresh stretch of noise each time
	}
	ViewShake = FMath::Clamp(FMath::Max(ViewShake, Strength * Scale), 0.f, 1.f);
	ViewKick = FMath::Clamp(FMath::Max(ViewKick, KickDegrees * Scale), 0.f, 6.f);
}

void AAirsoftCharacter::UpdateViewEffects(float DeltaSeconds, FRotator& OutShakeRotation, FVector& OutShakeOffset)
{
	OutShakeRotation = FRotator::ZeroRotator;
	OutShakeOffset = FVector::ZeroVector;
	HitPulse = FMath::Max(0.f, HitPulse - DeltaSeconds / 0.5f);
	// Flinch: snaps up, eases back down.
	ViewKick = FMath::FInterpTo(ViewKick, 0.f, DeltaSeconds, 9.f);
	OutShakeRotation.Pitch = ViewKick;
	if (ViewShake <= 0.f)
	{
		return;
	}
	ViewShakeTime += DeltaSeconds;
	ViewShake = FMath::Max(0.f, ViewShake - DeltaSeconds * 2.f); // a full-strength shake settles in half a second
	const float Amount = ViewShake * ViewShake;
	const float T = ViewShakeTime * 24.f;
	OutShakeRotation.Pitch += FMath::PerlinNoise1D(T) * 2.4f * Amount;
	OutShakeRotation.Yaw = FMath::PerlinNoise1D(T + 31.7f) * 1.6f * Amount;
	OutShakeRotation.Roll = FMath::PerlinNoise1D(T + 67.3f) * 2.8f * Amount;
	OutShakeOffset = FVector(0.f, FMath::PerlinNoise1D(T + 11.1f) * 1.4f * Amount, FMath::PerlinNoise1D(T + 47.9f) * 1.4f * Amount);
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
	// Campaign: health comes back once you've been out of fire for a few seconds.
	if (HasAuthority() && !bIsOutReplicated && Health < MaxHealth && TimeSinceDamage() > RegenDelay && AAirsoftGameState::IsCampaign(this))
	{
		Health = FMath::Min(MaxHealth, Health + RegenRate * DeltaSeconds);
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
				const float Volume = (bIsCrouched ? 0.12f : bSprint ? 0.55f : 0.32f) * (IsLocalHuman() ? 0.6f : 1.f);
				const FVector Foot = GetActorLocation() - FVector(0.f, 0.f, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
				UAirsoftEffectsSubsystem* FX = UAirsoftEffectsSubsystem::Get(this);
				// The step sounds like what's underfoot: grass, concrete, steel, wet street (else gravel).
				EAirsoftSurface Surface = EAirsoftSurface::Default;
				if (FX)
				{
					FHitResult Ground;
					FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftFootstep), false, this);
					if (GetWorld()->LineTraceSingleByChannel(Ground, Foot + FVector(0.f, 0.f, 10.f), Foot - FVector(0.f, 0.f, 40.f), ECC_Visibility, Query))
					{
						Surface = FX->SurfaceOf(Ground);
					}
				}
				float SurfaceVolume = 1.f;
				float SurfacePitch = 1.f;
				const FName StepKey = AirsoftCharacterLocal::FootstepFor(Surface, SurfaceVolume, SurfacePitch);
				AirsoftAssets::Play3D(this, StepKey, Foot, Volume * SurfaceVolume, SurfacePitch * FMath::FRandRange(0.85f, 1.15f));
				// Effects: dust kicked up on dusty ground (others only: your own feet are out of view).
				if (FX && !bIsCrouched && !IsLocalHuman())
				{
					FX->FootDust(this, Foot, bSprint ? 1.f : 0.4f);
				}
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
	// Shake and flinch ride on the same additive offset as lean roll; the viewmodel follows so the gun stays glued to the view.
	FRotator ShakeRotation;
	FVector ShakeOffset;
	UpdateViewEffects(DeltaSeconds, ShakeRotation, ShakeOffset);
	const FRotator ViewRotation(ShakeRotation.Pitch, ShakeRotation.Yaw, Roll + ShakeRotation.Roll);
	Camera->SetRelativeLocation(FVector(0.f, LeanAmount * LeanOffset, EyeHeight - HalfHeight - LandDip));
	Camera->ClearAdditiveOffset();
	Camera->AddAdditiveOffset(FTransform(ViewRotation, ShakeOffset), 0.f);
	ViewRoot->SetRelativeLocationAndRotation(ShakeOffset, ViewRotation);

	// Field of view: user setting, zoomed by the gun's optic, widened slightly when sprinting.
	float BaseFOV = 90.f;
	if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
	{
		BaseFOV = FMath::Clamp(GI->GetUserSettings().FieldOfView, 70.f, 110.f);
	}
	const float Extra = IsSprinting() ? 6.f : bSlidingNow ? 9.f : 0.f;
	const float TargetFOV = (Combat ? Combat->GetTargetFOV(BaseFOV) : BaseFOV) + Extra;
	Camera->SetFieldOfView(FMath::FInterpTo(Camera->FieldOfView, TargetFOV, DeltaSeconds, 14.f));

	UpdateThirdPersonCamera(DeltaSeconds, ShakeRotation, ShakeOffset);

	// Tagged: the world drains of colour until respawn. The moment of the hit lands as a short,
	// sharp pulse on top: deeper desaturation, a vignette punch, a warm tint and (cinematic) fringing.
	OutFade = FMath::FInterpTo(OutFade, IsOut() ? 1.f : 0.f, DeltaSeconds, 3.f);
	const float Pulse = HitPulse * HitPulse;
	const bool bPulsing = Pulse > 0.001f;
	FPostProcessSettings& PP = Camera->PostProcessSettings;
	PP.bOverride_ColorSaturation = true;
	PP.ColorSaturation = FVector4(1.f, 1.f, 1.f, FMath::Max(0.f, 1.f - 0.75f * OutFade - 0.6f * Pulse));
	PP.bOverride_VignetteIntensity = true;
	PP.VignetteIntensity = 0.4f + 0.6f * OutFade + 0.6f * Pulse;
	// Only override these while pulsing so the map's own grading and chromatic aberration stay in charge.
	PP.bOverride_ColorGain = bPulsing;
	PP.ColorGain = FVector4(1.f + 0.12f * Pulse, 1.f - 0.04f * Pulse, 1.f - 0.14f * Pulse, 1.f);
	PP.bOverride_SceneFringeIntensity = bPulsing && AirsoftEffects::CinematicEnabled(this);
	PP.SceneFringeIntensity = 0.1f + 3.f * Pulse;
	Camera->PostProcessBlendWeight = 1.f;
}

void AAirsoftCharacter::UpdateRemoteVisuals(float DeltaSeconds)
{
	// Third-person gun follows where the player is looking.
	if (TPGun->GetAttachParent() == TPAimRoot)
	{
		const float Pitch = IsOut() ? -55.f : static_cast<float>(FRotator::NormalizeAxis(GetBaseAimRotation().Pitch));
		const float CrouchDrop = bIsCrouched ? -24.f : 0.f;
		TPAimRoot->SetRelativeLocationAndRotation(FVector(0.f, LeanVisual * 22.f, 46.f + CrouchDrop), FRotator(Pitch, 0.f, LeanVisual * 12.f));
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

// ---------------------------------------------------------------------------
// Third-person camera (local only)
//
// The eye camera (Camera) never moves off the head: it is what the shots, grenades and the server's
// origin check use in both views. Third person is purely a different view: CalcCamera blends from the
// eye view to the boom camera, and the owner is shown their own body, gear and third-person gun.
// Aiming down sights from third person goes to the eye (real sights and scopes), see below.
// ---------------------------------------------------------------------------

void AAirsoftCharacter::CalcCamera(float DeltaTime, FMinimalViewInfo& OutResult)
{
	if (!Camera)
	{
		Super::CalcCamera(DeltaTime, OutResult);
		return;
	}
	// Always the eye camera first: GetCameraView also keeps it on the control rotation, which the shots use.
	Camera->GetCameraView(DeltaTime, OutResult);
	if (TPBlend <= 0.001f || !ShoulderCamera)
	{
		return;
	}
	FMinimalViewInfo Shoulder;
	ShoulderCamera->GetCameraView(DeltaTime, Shoulder);
	// Eased, so the move spends little time close to the head.
	const float A = TPBlend * TPBlend * (3.f - 2.f * TPBlend);
	OutResult.Location = FMath::Lerp(OutResult.Location, Shoulder.Location, A);
	OutResult.Rotation = OutResult.Rotation + (Shoulder.Rotation - OutResult.Rotation).GetNormalized() * A;
	OutResult.FOV = FMath::Lerp(OutResult.FOV, Shoulder.FOV, A);
	// Post-process (tagged fade, hit pulse) stays the eye camera's.
}

bool AAirsoftCharacter::WantsThirdPerson() const
{
	if (!IsLocalHuman())
	{
		return false;
	}
	UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>();
	if (!GI)
	{
		return false;
	}
	const FAirsoftUserSettings& S = GI->GetUserSettings();
	return AAirsoftGameState::IsCampaign(this) ? S.bThirdPersonStory : S.bThirdPersonMatches;
}

void AAirsoftCharacter::ToggleCameraMode()
{
	UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>();
	UAirsoftSaveGame* Profile = GI ? GI->GetProfile() : nullptr;
	if (!Profile || !IsLocalHuman())
	{
		return;
	}
	// Straight into the profile: SetUserSettings would re-apply the video settings (a hitch mid-fight).
	bool& bThird = AAirsoftGameState::IsCampaign(this) ? Profile->Settings.bThirdPersonStory : Profile->Settings.bThirdPersonMatches;
	bThird = !bThird;
	GI->SaveProfile();
	AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.35f, bThird ? 1.1f : 0.9f);
}

void AAirsoftCharacter::SwapShoulder()
{
	UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>();
	UAirsoftSaveGame* Profile = GI ? GI->GetProfile() : nullptr;
	if (!Profile || !IsLocalHuman())
	{
		return;
	}
	Profile->Settings.bLeftShoulder = !Profile->Settings.bLeftShoulder;
	GI->SaveProfile();
	if (bOwnerSeesBody)
	{
		AirsoftAssets::Play2D(this, TEXT("UIClick"), 0.25f, 1.3f);
	}
}

bool AAirsoftCharacter::GetOverShoulderView(FVector& OutLocation, FRotator& OutRotation) const
{
	if (!ShoulderCamera || !WantsThirdPerson())
	{
		return false;
	}
	OutLocation = ShoulderCamera->GetComponentLocation();
	OutRotation = GetControlRotation();
	return true;
}

void AAirsoftCharacter::UpdateThirdPersonCamera(float DeltaSeconds, const FRotator& ShakeRotation, const FVector& ShakeOffset)
{
	const bool bHuman = IsLocalHuman();
	const bool bWant = bHuman && WantsThirdPerson();
	// ADS from third person goes to the real sights (first person). With BB ballistics the arc, the hop and
	// the scope picture only read from the eye, and a precise shot never comes from a camera that sees
	// round corners. Hip fire stays over the shoulder; the move is tied to the aim so it takes the gun's aim time.
	const float Aim = Combat ? Combat->GetAimAlpha() : 0.f;
	const float Target = bWant ? 1.f - FMath::Clamp(Aim * 1.6f, 0.f, 1.f) : 0.f;
	TPBlend = FMath::FInterpTo(TPBlend, Target, DeltaSeconds, 16.f);
	if (FMath::Abs(TPBlend - Target) < 0.002f)
	{
		TPBlend = Target;
	}

	const bool bBoomActive = bHuman && (bWant || TPBlend > 0.f);
	if (CameraBoom->IsComponentTickEnabled() != bBoomActive)
	{
		CameraBoom->SetComponentTickEnabled(bBoomActive);
	}
	if (bBoomActive)
	{
		bool bLeft = false;
		if (UAirsoftGameInstance* GI = GetGameInstance<UAirsoftGameInstance>())
		{
			bLeft = GI->GetUserSettings().bLeftShoulder;
		}
		ShoulderSide = FMath::FInterpTo(ShoulderSide, bLeft ? -1.f : 1.f, DeltaSeconds, 9.f);
		const float HalfHeight = GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
		// Follows the eye height (crouch, slide, landing dip); the boom's lag smooths the steps.
		CameraBoom->SetRelativeLocation(FVector(0.f, 0.f, EyeHeight - HalfHeight - TPPivotDrop - LandDip));
		const float ArmTarget = TPArmLength + (IsSprinting() ? 30.f : 0.f) - (bIsCrouched ? 30.f : 0.f);
		CameraBoom->TargetArmLength = FMath::FInterpTo(CameraBoom->TargetArmLength, ArmTarget, DeltaSeconds, 6.f);
		// Leaning slides the camera out with the body.
		CameraBoom->SocketOffset = FVector(0.f, ShoulderSide * TPShoulderOffset + LeanAmount * 38.f, TPRise);
		ShoulderCamera->SetFieldOfView(FMath::Max(60.f, Camera->FieldOfView - 4.f));
		// Same shake and flinch as the eye view, without the lean roll.
		ShoulderCamera->ClearAdditiveOffset();
		ShoulderCamera->AddAdditiveOffset(FTransform(FRotator(ShakeRotation.Pitch, ShakeRotation.Yaw, ShakeRotation.Roll * 0.5f), ShakeOffset), 0.f);
	}

	// The body appears once the camera is well clear of the head; the arms and viewmodel go at the same moment.
	bOwnerSeesBody = bHuman && TPBlend > TPBodyFrom;
	if (bHuman)
	{
		ApplyOwnerView(bOwnerSeesBody);
	}
	ShoulderAim = (bOwnerSeesBody && Combat) ? ComputeShoulderAim(Combat->Current().MaxRange) : FAirsoftShoulderAim();
}

void AAirsoftCharacter::ApplyOwnerView(bool bSeeBody)
{
	const bool bTransition = bSeeBody != bOwnerViewApplied;
	// First person is the constructor's state: only the switch back needs work. In third person the guns
	// and gear are rebuilt now and then (weapon swap, team look), so their new parts are caught every frame.
	if (!bTransition && !bSeeBody)
	{
		return;
	}
	bOwnerViewApplied = bSeeBody;
	const bool bNoSee = !bSeeBody;

	if (bTransition)
	{
		PoseMesh->SetOwnerNoSee(bNoSee);
		GetMesh()->SetOwnerNoSee(bNoSee);
		FallbackBody->SetOwnerNoSee(bNoSee);
		FallbackHead->SetOwnerNoSee(bNoSee);
		TeamBand->SetOwnerNoSee(bNoSee);
		DeadRag->SetOwnerNoSee(bNoSee);
	}

	// Third-person gun: OwnerNoSee on every part. First-person gun, gloves and its light: hidden.
	TArray<USceneComponent*> Parts;
	TPGun->GetChildrenComponents(true, Parts);
	for (USceneComponent* Part : Parts)
	{
		if (UPrimitiveComponent* Prim = Cast<UPrimitiveComponent>(Part))
		{
			Prim->SetOwnerNoSee(bNoSee);
		}
	}
	Parts.Reset();
	FPGun->GetChildrenComponents(true, Parts);
	for (USceneComponent* Part : Parts)
	{
		if (Part)
		{
			Part->SetHiddenInGame(bSeeBody); // no-op when unchanged
		}
	}

	// Team gear pieces (UAirsoftTeamGearComponent names them TeamGear_*). That component also hides them
	// while their owner views through this pawn; in third person they have to show.
	TInlineComponentArray<UStaticMeshComponent*> Meshes(this);
	for (UStaticMeshComponent* Mesh : Meshes)
	{
		if (Mesh && Mesh->GetName().StartsWith(TEXT("TeamGear_")))
		{
			Mesh->SetOwnerNoSee(bNoSee);
			if (bSeeBody && !Mesh->IsVisible())
			{
				Mesh->SetVisibility(true);
			}
		}
	}
	if (bTransition && !bSeeBody && TeamGear)
	{
		TeamGear->RefreshVisibility();
	}
}

FAirsoftShoulderAim AAirsoftCharacter::ComputeShoulderAim(float MaxRange) const
{
	FAirsoftShoulderAim Aim;
	UWorld* World = GetWorld();
	if (!World || !Camera)
	{
		return Aim;
	}
	const FVector Eye = Camera->GetComponentLocation();
	FVector ViewLoc = ShoulderCamera ? ShoulderCamera->GetComponentLocation() : Eye;
	FRotator ViewRot = GetControlRotation();
	// The real view (blend, lag, shake included): its centre is exactly where the crosshair is drawn.
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		if (PC->PlayerCameraManager)
		{
			ViewLoc = PC->PlayerCameraManager->GetCameraLocation();
			ViewRot = PC->PlayerCameraManager->GetCameraRotation();
		}
	}
	const FVector Forward = ViewRot.Vector();
	FCollisionQueryParams Query(SCENE_QUERY_STAT(AirsoftShoulderAim), false, this);

	// 1) The crosshair ray, started level with the shooter: whatever is between the camera and the body can't be aimed at.
	const double Behind = FMath::Max(0.0, FVector::DotProduct(Eye - ViewLoc, Forward));
	const FVector Start = ViewLoc + Forward * Behind;
	const FVector End = Start + Forward * FMath::Max(MaxRange, 1000.f);
	FHitResult Hit;
	Aim.AimPoint = World->LineTraceSingleByChannel(Hit, Start, End, ECC_BB, Query) ? FVector(Hit.ImpactPoint) : End;

	// 2) The BB leaves the third-person muzzle, unless the barrel pokes through a wall: then the eyes.
	FVector Origin = TPGun ? TPGun->GetMuzzleWorld() : Eye;
	FHitResult Wall;
	if (FVector::DistSquared(Origin, Eye) > FMath::Square(150.0) || World->LineTraceSingleByChannel(Wall, Eye, Origin, ECC_BB, Query))
	{
		Origin = Eye;
	}
	Aim.Origin = Origin;
	const FVector ToAim = Aim.AimPoint - Origin;
	// A point right beside the gun gives no usable direction: shoot along the view.
	Aim.Direction = ToAim.SizeSquared() > FMath::Square(60.0) ? ToAim.GetSafeNormal() : Forward;

	// 3) Shoulder-peek guard: can the muzzle see the aim point? If not the BB stops on the way (the HUD marks where).
	const double Reach = FMath::Max(0.0, ToAim.Size() - 25.0);
	FHitResult Block;
	if (Reach > 1.0 && World->LineTraceSingleByChannel(Block, Origin, Origin + Aim.Direction * Reach, ECC_BB, Query))
	{
		Aim.bBlocked = true;
		Aim.BlockPoint = Block.ImpactPoint;
	}
	Aim.bValid = true;
	return Aim;
}
