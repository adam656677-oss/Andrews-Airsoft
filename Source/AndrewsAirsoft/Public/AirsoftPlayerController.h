// Andrew's Airsoft - local input (Enhanced Input, built in code), menus,
// HUD feed (kill feed, announcements, XP, chat), the team camera for players
// out for the round, and the client/server messages between a player and the host.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "InputActionValue.h"
#include "AirsoftTypes.h"
#include "AirsoftPlayerController.generated.h"

class UInputAction;
class UInputMappingContext;
class AAirsoftCharacter;
class AAirsoftArmoryDisplay;
class AAirsoftGameState;
class AAirsoftPlayerState;
class ACameraActor;
class UAudioComponent;
class SWidget;

/** Which full-screen UI is open. */
enum class EAirsoftMenu : uint8
{
	None,
	MainMenu,
	GameMenu,
	Armory,
	Settings
};

struct FAirsoftKillFeedEntry
{
	FString Shooter;
	EAirsoftTeam ShooterTeam = EAirsoftTeam::None;
	FString Victim;
	EAirsoftTeam VictimTeam = EAirsoftTeam::None;
	FName WeaponId;
	double Time = 0.0;
	bool bInvolvesMe = false;
};

struct FAirsoftAnnouncement
{
	FString Title;
	FString Sub;
	FLinearColor Color = FLinearColor::White;
	double Time = -100.0;
	float Duration = 0.f;
};

struct FAirsoftXPPopup
{
	int32 Amount = 0;
	FString Reason;
	double Time = 0.0;
};

/** One line in the chat box. */
struct FAirsoftChatEntry
{
	FString Sender;
	EAirsoftTeam SenderTeam = EAirsoftTeam::None;
	FString Text;
	EAirsoftChatKind Kind = EAirsoftChatKind::All;
	/** Real time it arrived (same clock as the rest of the HUD feed). */
	double Time = 0.0;
};

/** Everything the after-action screen shows. */
struct FAirsoftMatchSummary
{
	bool bValid = false;
	EAirsoftTeam Winner = EAirsoftTeam::None;
	EAirsoftTeam MyTeam = EAirsoftTeam::None;
	/** Free-for-all winner (empty = draw or team mode). */
	FString WinnerName;
	/** This player won (their team, or them in a free-for-all). */
	bool bWon = false;
	TArray<FAirsoftSummaryRow> Rows;
	FAirsoftFinalTag FinalTag;
	int32 XPEarned = 0;
	int32 RankBefore = 1;
	int32 RankAfter = 1;
	double Time = 0.0;
};

UCLASS()
class ANDREWSAIRSOFT_API AAirsoftPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AAirsoftPlayerController();

	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void SetupInputComponent() override;
	virtual void PlayerTick(float DeltaTime) override;
	virtual void OnPossess(APawn* InPawn) override;
	virtual void OnRep_Pawn() override;

	AAirsoftCharacter* GetAirsoftCharacter() const;
	AAirsoftGameState* GetAirsoftGameState() const;
	AAirsoftPlayerState* GetAirsoftPlayerState() const;

	// --- Menus (local) ----------------------------------------------------------
	bool IsMainMenu() const { return bMainMenu; }
	bool IsMenuOpen() const { return OpenMenu != EAirsoftMenu::None; }
	EAirsoftMenu GetOpenMenu() const { return OpenMenu; }
	void ShowMenu(EAirsoftMenu Menu);
	void CloseMenus();
	void ToggleGameMenu();
	/** Opens the armory, optionally on a specific weapon (from a display rack). */
	void OpenArmory(FName FocusWeapon = NAME_None);
	FName GetArmoryFocus() const { return ArmoryFocus; }
	bool IsScoreboardVisible() const { return bScoreboard; }
	/** True when this player is the host (listen server) and may force-start matches. */
	bool IsHost() const;

	// --- HUD feed (local) -------------------------------------------------------
	void ShowHitMarker(bool bConfirmedTag);
	float GetHitMarkerAlpha() const;
	bool WasHitMarkerTag() const { return bHitMarkerTag; }
	const TArray<FAirsoftKillFeedEntry>& GetKillFeed() const { return KillFeed; }
	const FAirsoftAnnouncement& GetAnnouncement() const { return Announcement; }
	const TArray<FAirsoftXPPopup>& GetXPPopups() const { return XPPopups; }
	const FAirsoftMatchSummary& GetSummary() const { return Summary; }
	bool IsSummaryVisible() const;
	FString GetInteractPrompt() const;
	/** Seconds the final-tag replay has been playing, or -1. */
	float GetReplayTime() const;
	/** The tag the replay shows (end of a round or of the match). */
	const FAirsoftFinalTag& GetReplayTag() const { return ReplayTag; }
	/** "FINAL TAG" or "ROUND 3  -  FINAL TAG". */
	const FString& GetReplayCaption() const { return ReplayCaption; }
	/** Announce locally (no network). */
	void Announce(const FString& Title, const FString& Sub, const FLinearColor& Color, float Duration = 3.f);

	// --- Lobby vote (local) ------------------------------------------------------
	/** F1 / F2: move this player's vote to the next mode / map in the list (wraps around). */
	void CycleModeVote(int32 Step = 1);
	void CycleMapVote(int32 Step = 1);
	/** Vote for an entry directly (menu buttons). Index into the mode list / AirsoftRules::Maps(). */
	void VoteMode(int32 ModeIndex);
	void VoteMap(int32 MapIndex);
	int32 GetMyModeVote() const { return MyModeVote; }
	int32 GetMyMapVote() const { return MyMapVote; }
	/** The lobby vote is open (staging, waiting or intermission). */
	bool CanVote() const;

	// --- Chat (local) ------------------------------------------------------------
	bool IsChatOpen() const { return ChatWidget.IsValid(); }
	bool IsTeamChat() const { return bChatTeam; }
	/** Enter (everyone) / Y (team): opens the chat line; gameplay input stops while typing. */
	void OpenChat(bool bTeam);
	void CloseChat();
	/** Sends the typed line (empty = just closes). */
	void SubmitChat(const FString& Text);
	/** Tab in the chat line: everyone <-> team. */
	void ToggleChatChannel();
	const TArray<FAirsoftChatEntry>& GetChatLog() const { return ChatLog; }

	// --- Team camera (local): out for the round in Elimination / VIP ------------
	bool IsTeamCamActive() const { return TeamCamera != nullptr; }
	/** Call sign of the teammate being watched. */
	FString GetTeamCamName() const;
	/** Fire / jump while watching: the next standing teammate. */
	void CycleTeamCam();

	// --- Profile / loadout ------------------------------------------------------
	/** Sends the saved profile loadout to the host and equips it (if allowed right now). */
	void PushLoadoutToServer();

	// --- Server RPCs ------------------------------------------------------------
	UFUNCTION(Server, Reliable) void ServerSetProfile(const FString& InName, int32 InCareerXP, const FAirsoftLoadout& InLoadout);
	UFUNCTION(Server, Reliable) void ServerSetLoadout(const FAirsoftLoadout& InLoadout);
	UFUNCTION(Server, Reliable) void ServerVote(int32 ModeIndex, int32 MapIndex);
	UFUNCTION(Server, Reliable) void ServerForceStart();
	UFUNCTION(Server, Reliable) void ServerSwitchTeam();
	/** A chat line (the host cleans, caps and rate-limits it). */
	UFUNCTION(Server, Reliable) void ServerSendChat(const FString& Text, bool bTeam);

	// --- Client RPCs ------------------------------------------------------------
	UFUNCTION(Client, Reliable) void ClientAnnounce(const FString& Title, const FString& Sub, FLinearColor Color, float Duration);
	UFUNCTION(Client, Reliable) void ClientKillFeed(const FString& Shooter, EAirsoftTeam ShooterTeam, const FString& Victim, EAirsoftTeam VictimTeam, FName WeaponId);
	UFUNCTION(Client, Reliable) void ClientXP(int32 Amount, const FString& Reason);
	UFUNCTION(Client, Reliable) void ClientMatchEnded(EAirsoftTeam Winner, const FString& WinnerName, bool bWon, const TArray<FAirsoftSummaryRow>& Rows, const FAirsoftFinalTag& FinalTag, int32 XPEarned, int32 Captures);
	/** Round-based modes: a round (not the match) ended - replay its last tag. */
	UFUNCTION(Client, Reliable) void ClientRoundEnded(EAirsoftTeam RoundWinner, const FString& Reason, const FAirsoftFinalTag& FinalTag);
	UFUNCTION(Client, Reliable) void ClientResetForNewRound();
	UFUNCTION(Client, Reliable) void ClientReceiveChat(const FString& Sender, EAirsoftTeam SenderTeam, const FString& Text, EAirsoftChatKind Kind);

protected:
	void BuildInput();
	void AddMappingContext();
	/** (Re)creates the HUD/menus for the current world (the controller survives seamless travel). */
	void RebuildUI();
	void SendProfile();
	void ApplyLoadout(const FAirsoftLoadout& InLoadout);
	void RefreshInputMode();
	void ShowWidget(TSharedPtr<SWidget>& Slot, const TSharedRef<SWidget>& Widget, int32 ZOrder);
	void HideWidget(TSharedPtr<SWidget>& Slot);
	void UpdateInteraction();
	/** Phase changes, objective captures and capture ticks -> stings. */
	void UpdateMatchAudio();
	void UpdateReplay(float DeltaTime);
	void StartReplay(const FAirsoftFinalTag& Tag, const FString& Caption);
	void StopReplay();
	/** Stops the character doing anything (menu or chat opened). */
	void HaltPawnActions();
	void UpdateChatFocus();
	void UpdateTeamCam(float DeltaTime);
	void StopTeamCam();
	/** Standing teammates to watch, in a stable order. */
	void GetWatchableTeammates(TArray<AAirsoftCharacter*>& Out) const;

	// Input handlers.
	void OnMove(const FInputActionValue& Value);
	void OnLookMouse(const FInputActionValue& Value);
	void OnLookStick(const FInputActionValue& Value);
	void OnJump();
	void OnSprintPressed();
	void OnSprintReleased();
	void OnSprintToggle();
	void OnCrouchToggle();
	void OnCrouchHoldPressed();
	void OnCrouchHoldReleased();
	void OnFirePressed();
	void OnFireReleased();
	void OnAimPressed();
	void OnAimReleased();
	void OnReload();
	void OnSwapWeapon();
	void OnPrimary();
	void OnSecondary();
	void OnGrenade();
	void OnFireMode();
	void OnLight();
	void OnInspect();
	void OnInteract();
	void OnLeanLeftPressed();
	void OnLeanLeftReleased();
	void OnLeanRightPressed();
	void OnLeanRightReleased();
	void OnScoreboardPressed();
	void OnScoreboardReleased();
	void OnMenu();
	void OnLoadout();
	void OnVoteModeKey();
	void OnVoteMapKey();
	void OnChatKey();
	void OnTeamChatKey();

	bool CanControlPawn() const;

	UPROPERTY() TObjectPtr<UInputMappingContext> Mapping;
	UPROPERTY() TMap<FName, TObjectPtr<UInputAction>> Actions;

	UPROPERTY() TObjectPtr<ACameraActor> ReplayCamera;
	/** Follows a standing teammate while this player is out for the round. */
	UPROPERTY() TObjectPtr<ACameraActor> TeamCamera;
	/** Music bed under the after-action report. */
	UPROPERTY() TObjectPtr<UAudioComponent> PostRoundMusic;

	EAirsoftMenu OpenMenu = EAirsoftMenu::None;
	bool bMainMenu = false;
	bool bScoreboard = false;
	bool bLeanLeft = false;
	bool bLeanRight = false;
	FName ArmoryFocus;
	int32 MyModeVote = -1;
	int32 MyMapVote = -1;
	bool bProfileSent = false;

	TSharedPtr<SWidget> HUDWidget;
	TSharedPtr<SWidget> MenuWidget;
	TSharedPtr<SWidget> ScoreboardWidget;
	TSharedPtr<SWidget> SummaryWidget;
	TSharedPtr<SWidget> ChatWidget;

	double HitMarkerTime = -100.0;
	bool bHitMarkerTag = false;
	TArray<FAirsoftKillFeedEntry> KillFeed;
	FAirsoftAnnouncement Announcement;
	TArray<FAirsoftXPPopup> XPPopups;
	FAirsoftMatchSummary Summary;
	TArray<FAirsoftChatEntry> ChatLog;
	bool bChatTeam = false;

	TWeakObjectPtr<AAirsoftArmoryDisplay> InteractTarget;
	TWeakObjectPtr<UWorld> UIWorld;
	double ReplayStart = -1.0;
	bool bReplayFired = false;
	bool bReplayHitPlayed = false;
	FAirsoftFinalTag ReplayTag;
	FString ReplayCaption;
	EAirsoftPhase LastPhase = EAirsoftPhase::Waiting;
	TMap<TWeakObjectPtr<AActor>, EAirsoftTeam> LastObjectiveOwners;
	double NextCaptureTick = 0.0;
	bool bSummaryStingPlayed = false;

	// Team camera.
	TWeakObjectPtr<AAirsoftCharacter> TeamCamTarget;
	/** Real time this player was first seen out (or pawnless) during a live one-life round; < 0 = not out. */
	double OutSince = -1.0;

	// Server only: chat rate limit (token bucket on the platform clock, which survives map changes).
	float ChatTokens = 0.f;
	double ChatTokensAt = -1000.0;
};
