// Andrew's Airsoft - computer-controlled players ("bots"). Server only.
//
// A bot is an AIController driving an ordinary AAirsoftCharacter. On the host a
// bot's pawn is locally controlled, so it fires through exactly the same
// UAirsoftCombatComponent path as the listen-server player: local BB flight,
// ServerFire validation, hit claims, HandleTag, scoring, the dead-rag walk-off
// and respawn all run unchanged, and clients see it like any other player.
//
// The brain is a small state machine ticked by the controller:
//   Idle (frozen / round not live)
//   Advance (to a roam point or objective) <-> Hold (on a point, scanning)
//   Investigate (last seen / heard enemy) <-> Engage (visible enemy)
//   WalkOff (tagged: rag up, back toward spawn until the respawn - or, in the
//            one-life modes, until the next round respawns everyone)
// Who counts as an enemy comes from AAirsoftGameState::AreHostile (Gun Game:
// everyone). Goals per mode: TDM / Elimination / Gun Game roam, Domination
// takes points, VIP escorts or hunts the VIP.
// Tactical bots (story enemies; SetTactical) fight from cover instead of in the
// open: they pick a spot that hides them crouched but lets them shoot standing
// or from a step to the side, then cycle hide (reload) / peek (shoot). One bot
// per team works round the side of the fight (flank). Cover is re-picked every
// few seconds, a little closer each time for the bolder difficulties.
// Numbers per difficulty live in UAirsoftSettings (Project Settings > Game > Airsoft > Bots);
// how hard they push comes from AirsoftDifficulty::Aggression.

#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "AirsoftTypes.h"
#include "AirsoftBotController.generated.h"

class AAirsoftCharacter;
class AAirsoftObjective;
class UAirsoftCombatComponent;

/**
 * The single difficulty setting (Easy, Normal, Hard, Expert) shared by story enemies and skirmish bots. Stored in the
 * profile as FAirsoftUserSettings::BotSkill (0..3); the menus read and write that field.
 */
namespace AirsoftDifficulty
{
	/** The difficulty in effect for this world (Normal without a profile). */
	ANDREWSAIRSOFT_API EAirsoftBotSkill Get(const UObject* WorldContext);
	/** "EASY", "NORMAL", "HARD", "EXPERT". */
	ANDREWSAIRSOFT_API FString Label(EAirsoftBotSkill Skill);
	/** One line for the menu: what the setting changes. */
	ANDREWSAIRSOFT_API FString Blurb(EAirsoftBotSkill Skill);
	/** 0..1: how hard enemies push - shorter hides behind cover, longer peeks, more flanking, less backing off. */
	ANDREWSAIRSOFT_API float Aggression(EAirsoftBotSkill Skill);
	/** Story missions: share of an enemy hit's damage the player takes (the player has health there; matches are one-tag-out). */
	ANDREWSAIRSOFT_API float PlayerDamageScale(EAirsoftBotSkill Skill);
}

enum class EAirsoftBotState : uint8
{
	Idle,
	Advance,
	Hold,
	Investigate,
	Engage,
	WalkOff
};

/** How a bot holds itself in a fight, re-picked every second or two. */
enum class EAirsoftBotCombatMove : uint8
{
	Stand,
	Crouch,
	Strafe
};

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftBotController : public AAIController
{
	GENERATED_BODY()

public:
	AAirsoftBotController(const FObjectInitializer& ObjectInitializer);

	virtual void Tick(float DeltaSeconds) override;
	/** Bots turn toward their own aim point (with human-like error and a turn-speed limit), not the AI focus. */
	virtual void UpdateControlRotation(float DeltaTime, bool bUpdatePawn = true) override;
	virtual void OnMoveCompleted(FAIRequestID RequestID, const FPathFollowingResult& Result) override;

	void SetSkill(EAirsoftBotSkill InSkill);
	EAirsoftBotSkill GetSkill() const { return Skill; }
	EAirsoftTeam GetBotTeam() const;
	EAirsoftBotState GetBotState() const { return State; }

	/** The objective this bot is taking or holding (Domination), so teammates spread out. */
	const AAirsoftObjective* GetGoalObjective() const { return GoalObjective.Get(); }

	/** Server: a validated shot was fired somewhere on the map (hearing; BBs passing close by). */
	void HearShot(AAirsoftCharacter* Shooter, const FVector& Origin, const FVector& Direction, bool bQuiet);

	/**
	 * Squad tactics: fight from cover (duck, reload, peek out to shoot), and one bot per team flanks.
	 * On by default for story enemies (the campaign game mode); call this to force it either way.
	 */
	void SetTactical(bool bInTactical);
	bool IsTactical() const { return bTactical; }
	/** True while this bot is the one working round the side of the fight. */
	bool IsFlanking() const { return bFlanker; }
	/** True while this bot has a cover spot (other bots keep clear of it). */
	bool HasCoverPoint(FVector& OutPoint) const;

protected:
	virtual void OnPossess(APawn* InPawn) override;
	virtual void OnUnPossess() override;

private:
	struct FBotMemory
	{
		TWeakObjectPtr<AAirsoftCharacter> Enemy;
		FVector LastKnown = FVector::ZeroVector;
		FVector Velocity = FVector::ZeroVector;
		double LastSeen = -100.0;
		double LastHeard = -100.0;
		/** When the bot reacts to the current sighting, and when it may take its first shot. */
		double NoticeAt = 0.0;
		double FireReadyAt = 0.0;
		/** Height above the capsule centre to aim at: centre mass, or the head when only that shows over cover. */
		float AimZ = 12.f;
		bool bVisible = false;
	};

	AAirsoftCharacter* GetBotCharacter() const;
	UAirsoftCombatComponent* GetBotCombat() const;
	FVector GetEyeLocation() const;
	double WorldTime() const;

	void ResetBrain();
	void CacheSpawns(const AAirsoftCharacter* Me);
	void UpdateBrain(float DeltaSeconds);
	void TickIdle(AAirsoftCharacter* Me);
	void TickWalkOff(AAirsoftCharacter* Me);
	void TickLive(AAirsoftCharacter* Me, float DeltaSeconds);

	// Perception
	void UpdateSight(AAirsoftCharacter* Me);
	bool CanSee(const FVector& Eye, const AAirsoftCharacter* Other, float& OutAimZ) const;
	bool CanSeeFrom(const FVector& Eye, const AAirsoftCharacter* Other) const;
	FBotMemory& Remember(AAirsoftCharacter* Enemy);
	FBotMemory* FindMemory(const AAirsoftCharacter* Enemy);
	void ForgetStale();
	const FBotMemory* FreshestUnseen(const FVector& From, float MaxDistance) const;

	// Combat
	void ChooseTarget(AAirsoftCharacter* Me);
	void Engage(AAirsoftCharacter* Me, float DeltaSeconds);
	void SelectFireMode(UAirsoftCombatComponent* Combat, float Distance);
	void UpdateTrigger(UAirsoftCombatComponent* Combat, float Distance, bool bCanStart, bool bCanContinue);
	void ReleaseTrigger();
	void PickCombatMove(AAirsoftCharacter* Me, const AAirsoftCharacter* Enemy, float Distance);
	void ManageWeapon(AAirsoftCharacter* Me);
	bool TryGrenade(AAirsoftCharacter* Me);

	// Goals and movement
	void Think(AAirsoftCharacter* Me);
	void ThinkTDM(AAirsoftCharacter* Me);
	void ThinkDomination(AAirsoftCharacter* Me);
	/** VIP: the VIP heads for extraction, escorts shadow the VIP, defenders guard extraction or push out to meet them. */
	void ThinkVIP(AAirsoftCharacter* Me);
	/** Walks to a random spot near Center, then holds a few seconds watching (shared by the VIP roles). */
	void MoveNearThenHold(AAirsoftCharacter* Me, const FVector& Center, float Radius, bool bSprint);
	float ScoreObjective(const AAirsoftCharacter* Me, const AAirsoftObjective* Obj) const;
	void StartInvestigate(const FVector& Point);
	bool MoveToPoint(const FVector& Dest, float Acceptance, bool bSprint);
	bool RandomPointNear(const FVector& Origin, float Radius, FVector& Out) const;
	bool ProjectToNav(const FVector& Point, FVector& Out) const;
	bool IsMoving() const;
	void UpdateMovement(AAirsoftCharacter* Me);
	void UpdateLook(AAirsoftCharacter* Me);
	void LookAtPoint(const FVector& Point);
	FVector ThreatPointFor(const AAirsoftCharacter* Me) const;

	// Tactics (cover, peeking, flanking)
	/** Drives stance and movement in a fight; false = no usable cover or too close, fight in the open. */
	bool UpdateTactics(AAirsoftCharacter* Me, AAirsoftCharacter* Enemy, const FBotMemory& M, float Distance, bool bVisible);
	/** Behind cover with the enemy out of sight: keep the cover cycle going instead of chasing. */
	void HoldCoverBlind(AAirsoftCharacter* Me, AAirsoftCharacter* Enemy, const FBotMemory& M);
	bool FindCover(const AAirsoftCharacter* Me, const FVector& Threat, float PreferredRange, FVector& OutCover, FVector& OutPeek, bool& bOutPeekStand) const;
	bool FindFlankPoint(const AAirsoftCharacter* Me, const FVector& Threat, FVector& Out) const;
	bool IsCoverTaken(const FVector& Point) const;
	bool TryStartFlank(AAirsoftCharacter* Me, const FVector& Threat);
	bool IsHiddenAt(const FVector& Floor, const FVector& Threat, const AAirsoftCharacter* Enemy) const;
	bool CanShootFrom(const FVector& Floor, float EyeHeight, const FVector& Threat, const AAirsoftCharacter* Enemy) const;
	void ClearTactics();

	bool bTactical = false;
	bool bTacticalSet = false;
	/** 0..1 from the difficulty, with a per-bot spread. */
	float Aggression = 0.45f;
	bool bFlanker = false;
	FVector FlankPoint = FVector::ZeroVector;
	double FlankUntil = 0.0;
	double NextFlankAt = 0.0;
	bool bHasCover = false;
	/** Where the bot hides (crouched) and where it shoots from (the same spot standing, or a step to the side). */
	FVector CoverPoint = FVector::ZeroVector;
	FVector PeekPoint = FVector::ZeroVector;
	bool bPeekStand = true;
	bool bAtCover = false;
	bool bPeeking = false;
	bool bPeekCutShort = false;
	double CoverPhaseStart = 0.0;
	double CoverPhaseUntil = 0.0;
	double CoverExpiresAt = 0.0;
	double NextCoverSearchAt = 0.0;
	/** Each move to fresh cover may close in a little (aggressive bots advance by bounds). */
	float CoverRange = 0.f;

	EAirsoftBotSkill Skill = EAirsoftBotSkill::Normal;
	bool bSkillSet = false;
	FAirsoftBotTuning Tune;
	/** Per-bot spread so a squad doesn't react and aim as one. */
	float PersonalityReaction = 1.f;
	float PersonalityAim = 1.f;
	FRandomStream Rng;

	EAirsoftBotState State = EAirsoftBotState::Idle;
	TArray<FBotMemory> Memory;
	TWeakObjectPtr<AAirsoftCharacter> Target;
	TWeakObjectPtr<AAirsoftObjective> GoalObjective;

	// Aim
	FRotator DesiredRotation = FRotator::ZeroRotator;
	bool bHasDesiredRotation = false;
	/** 1 = full turn speed (fighting), lower while looking around. */
	float TurnScale = 1.f;
	float AimError = 0.f;
	float AimErrorAngle = 0.f;
	float HomeYaw = 0.f;

	// Trigger
	bool bTriggerHeld = false;
	int32 BurstLength = 0;
	int32 BurstStartMag = 0;
	double NextTriggerAt = 0.0;

	// Movement
	FVector MoveGoal = FVector::ZeroVector;
	bool bHasMoveGoal = false;
	bool bWantSprint = false;
	bool bSprinting = false;
	bool bWalkingOff = false;
	/** Crouched on purpose while holding a spot (otherwise bots stand up when not fighting). */
	bool bHoldCrouch = false;
	FVector ProgressFrom = FVector::ZeroVector;
	double ProgressCheckAt = 0.0;
	int32 StuckStrikes = 0;
	int32 MoveFailures = 0;
	EAirsoftBotCombatMove CombatMove = EAirsoftBotCombatMove::Stand;

	// Map knowledge (cached on possess)
	FVector HomeSpawn = FVector::ZeroVector;
	FVector EnemySpawn = FVector::ZeroVector;
	bool bHaveSpawns = false;
	bool bDefender = false;
	float ObjectiveBias[3] = { 0.f, 0.f, 0.f };
	int32 LastLandmark = INDEX_NONE;

	// Timers (world seconds)
	double NextSightAt = 0.0;
	double NextThinkAt = 0.0;
	double NextGoalAt = 0.0;
	double NextCombatMoveAt = 0.0;
	double NextGrenadeAt = 0.0;
	double NextScanAt = 0.0;
	double HoldUntil = 0.0;
	double GoalExpiresAt = 0.0;
	double InvestigateUntil = 0.0;
	/** Time stamp of the last memory we went to check, so the same sighting isn't chased twice. */
	double InvestigatedStamp = -1.0;
	double LastCombatAt = -100.0;
	double UnderFireUntil = 0.0;
	FVector InvestigatePoint = FVector::ZeroVector;
	FVector ThreatPoint = FVector::ZeroVector;
};
