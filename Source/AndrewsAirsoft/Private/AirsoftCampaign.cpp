#include "AirsoftCampaign.h"

#include "AirsoftAssets.h"
#include "AirsoftBotController.h"
#include "AirsoftCharacter.h"
#include "AirsoftCombatComponent.h"
#include "AirsoftGameInstance.h"
#include "AirsoftGameState.h"
#include "AirsoftObjective.h"
#include "AirsoftPlayerController.h"
#include "AirsoftPlayerState.h"
#include "AirsoftSaveGame.h"
#include "AirsoftSettings.h"
#include "AirsoftTeamStart.h"
#include "AirsoftUnlocks.h"
#include "AirsoftWeaponData.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/LightComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/DirectionalLight.h"
#include "Engine/ExponentialHeightFog.h"
#include "Engine/GameViewportClient.h"
#include "Engine/PointLight.h"
#include "Engine/SkyLight.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/PostProcessVolume.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerStart.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/PackageName.h"
#include "Sound/SoundBase.h"
#include "TimerManager.h"
#include "UI/SAirsoftCredits.h"
#include "UI/SAirsoftSubtitles.h"

// ---------------------------------------------------------------------------
// The story (Content/Airsoft/Data/Campaign.json)
// ---------------------------------------------------------------------------

namespace AirsoftCampaign
{
	namespace
	{
		FString GetString(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field)
		{
			FString Out;
			if (Obj.IsValid())
			{
				Obj->TryGetStringField(Field, Out);
			}
			return Out;
		}

		TArray<FString> GetStrings(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field)
		{
			TArray<FString> Out;
			const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
			if (Obj.IsValid() && Obj->TryGetArrayField(Field, Values))
			{
				for (const TSharedPtr<FJsonValue>& V : *Values)
				{
					FString S;
					if (V.IsValid() && V->TryGetString(S))
					{
						Out.Add(S);
					}
				}
			}
			return Out;
		}

		int32 GetInt(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, int32 Default)
		{
			int32 Out = Default;
			if (Obj.IsValid())
			{
				Obj->TryGetNumberField(Field, Out);
			}
			return Out;
		}

		TArray<float> GetFloats(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field)
		{
			TArray<float> Out;
			const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
			if (Obj.IsValid() && Obj->TryGetArrayField(Field, Values))
			{
				for (const TSharedPtr<FJsonValue>& V : *Values)
				{
					double D = 0.0;
					if (V.IsValid() && V->TryGetNumber(D))
					{
						Out.Add(static_cast<float>(D));
					}
				}
			}
			return Out;
		}

		UAirsoftSaveGame* Profile(const UObject* WorldContext)
		{
			UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(UGameplayStatics::GetGameInstance(WorldContext));
			return GI ? GI->GetProfile() : nullptr;
		}

		/** Opens a mission's map with the campaign referee. */
		void OpenMission(const UObject* WorldContext, int32 Number, bool bFromCheckpoint)
		{
			const FMission* Mission = FindMission(Number);
			if (!Mission)
			{
				return;
			}
			AirsoftSubtitles::Clear();
			if (UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(UGameplayStatics::GetGameInstance(WorldContext)))
			{
				// Through the game instance so the loading screen shows the mission title.
				GI->StartMission(Number, bFromCheckpoint);
				return;
			}
			UGameplayStatics::OpenLevel(WorldContext, FName(*MissionMap(Number)), true, MissionOptions(Number, bFromCheckpoint));
		}
	}

	FString GameTitle()
	{
		const TSharedPtr<FJsonObject> Root = AirsoftAssets::LoadData(TEXT("Campaign.json"));
		const FString Title = GetString(Root, TEXT("Title"));
		return Title.IsEmpty() ? FString(TEXT("Last Contract")) : Title;
	}

	const TArray<FMission>& Missions()
	{
		static const TArray<FMission> List = []()
		{
			TArray<FMission> Out;
			const TSharedPtr<FJsonObject> Root = AirsoftAssets::LoadData(TEXT("Campaign.json"));
			const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
			if (!Root.IsValid() || !Root->TryGetArrayField(TEXT("Missions"), Entries))
			{
				UE_LOG(LogTemp, Error, TEXT("Campaign: Content/Airsoft/Data/Campaign.json is missing or has no Missions"));
				return Out;
			}
			for (const TSharedPtr<FJsonValue>& Entry : *Entries)
			{
				const TSharedPtr<FJsonObject> M = Entry.IsValid() ? Entry->AsObject() : nullptr;
				if (!M.IsValid())
				{
					continue;
				}
				FMission Mission;
				Mission.Title = GetString(M, TEXT("Title"));
				Mission.MapPath = GetString(M, TEXT("Map"));
				Mission.Options = GetString(M, TEXT("Options"));
				Mission.FallbackMap = GetString(M, TEXT("FallbackMap"));
				Mission.FallbackOptions = GetString(M, TEXT("FallbackOptions"));
				Mission.Intro = GetStrings(M, TEXT("Intro"));
				Mission.Objective = GetString(M, TEXT("Objective"));
				Mission.AndrewStart = GetString(M, TEXT("AndrewStart"));
				Mission.Enemies = FMath::Max(1, GetInt(M, TEXT("Enemies"), 8));
				Mission.MaxAlive = FMath::Max(1, GetInt(M, TEXT("MaxAlive"), 5));
				for (const FString& W : GetStrings(M, TEXT("EnemyWeapons")))
				{
					if (AirsoftWeapons::Find(FName(*W)))
					{
						Mission.EnemyWeapons.Add(FName(*W));
					}
				}
				const TSharedPtr<FJsonObject>* BossObj = nullptr;
				if (M->TryGetObjectField(TEXT("Boss"), BossObj) && BossObj)
				{
					Mission.Boss.Name = GetString(*BossObj, TEXT("Name"));
					Mission.Boss.Weapon = FName(*GetString(*BossObj, TEXT("Weapon")));
					Mission.Boss.Health = static_cast<float>(FMath::Max(100, GetInt(*BossObj, TEXT("Health"), 300)));
					Mission.Boss.Taunt = GetString(*BossObj, TEXT("Taunt"));
					Mission.Boss.Mid = GetString(*BossObj, TEXT("Mid"));
					Mission.Boss.Death = GetString(*BossObj, TEXT("Death"));
					Mission.Boss.AndrewReply = GetString(*BossObj, TEXT("AndrewReply"));
				}
				Mission.Outro = GetString(M, TEXT("Outro"));
				for (const float Fraction : GetFloats(M, TEXT("Checkpoints")))
				{
					if (Fraction > 0.f && Fraction < 1.f)
					{
						Mission.Checkpoints.Add(Fraction);
					}
				}
				Mission.Checkpoints.Sort();
				if (!Mission.MapPath.IsEmpty())
				{
					Out.Add(MoveTemp(Mission));
				}
			}
			return Out;
		}();
		return List;
	}

	const FMission* FindMission(int32 Number)
	{
		const TArray<FMission>& List = Missions();
		return List.IsValidIndex(Number - 1) ? &List[Number - 1] : nullptr;
	}

	float WeaponDamage(FName WeaponId, bool bHeadshot)
	{
		float Damage = 30.f;
		if (WeaponId == TEXT("Grenade"))
		{
			return 110.f;
		}
		if (WeaponId == TEXT("Melee"))
		{
			return UAirsoftSettings::Get()->Viewmodel.MeleeDamage; // rifle butt / pistol whip, never a headshot
		}
		if (const FAirsoftWeaponDef* W = AirsoftWeapons::Find(WeaponId))
		{
			if (W->Class == TEXT("Sniper")) Damage = 140.f;
			else if (W->Class == TEXT("DMR")) Damage = 60.f;
			else if (W->Class == TEXT("LMG")) Damage = 28.f;
			else if (W->Class == TEXT("SMG")) Damage = 22.f;
			else if (W->Class == TEXT("Shotgun")) Damage = 34.f;  // per pellet, three pellets a shell
			else if (W->Class == TEXT("Pistol")) Damage = WeaponId == TEXT("DEAGLE") ? 55.f : 28.f;
			else Damage = 30.f;                                   // rifles
		}
		return bHeadshot ? Damage * 2.2f : Damage;
	}

	float EnemyDamageScale(EAirsoftBotSkill Skill)
	{
		switch (Skill)
		{
		case EAirsoftBotSkill::Easy: return 0.3f;
		case EAirsoftBotSkill::Hard: return 0.65f;
		case EAirsoftBotSkill::Expert: return 0.9f;
		default: return 0.45f;
		}
	}

	const TArray<FLine>* FindBarks(FName Event)
	{
		static const TMap<FName, TArray<FLine>> Barks = []()
		{
			TMap<FName, TArray<FLine>> Out;
			const TSharedPtr<FJsonObject> Root = AirsoftAssets::LoadData(TEXT("Campaign.json"));
			const TSharedPtr<FJsonObject>* BarksObj = nullptr;
			if (!Root.IsValid() || !Root->TryGetObjectField(TEXT("Barks"), BarksObj) || !BarksObj)
			{
				return Out;
			}
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*BarksObj)->Values)
			{
				const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
				if (!Pair.Value.IsValid() || !Pair.Value->TryGetArray(Entries))
				{
					continue;
				}
				TArray<FLine>& Lines = Out.Add(FName(*Pair.Key));
				for (const TSharedPtr<FJsonValue>& Entry : *Entries)
				{
					const TSharedPtr<FJsonObject> B = Entry.IsValid() ? Entry->AsObject() : nullptr;
					const FString File = GetString(B, TEXT("File"));
					if (!File.IsEmpty())
					{
						Lines.Add({ FName(*File), GetString(B, TEXT("Text")) });
					}
				}
			}
			return Out;
		}();
		const TArray<FLine>* Found = Barks.Find(Event);
		return (Found && Found->Num() > 0) ? Found : nullptr;
	}

	const TArray<FCreditsBlock>& Credits()
	{
		static const TArray<FCreditsBlock> List = []()
		{
			TArray<FCreditsBlock> Out;
			const TSharedPtr<FJsonObject> Root = AirsoftAssets::LoadData(TEXT("Campaign.json"));
			const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
			if (Root.IsValid() && Root->TryGetArrayField(TEXT("Credits"), Entries))
			{
				for (const TSharedPtr<FJsonValue>& Entry : *Entries)
				{
					const TSharedPtr<FJsonObject> C = Entry.IsValid() ? Entry->AsObject() : nullptr;
					FCreditsBlock Block;
					Block.Heading = GetString(C, TEXT("Heading"));
					Block.Lines = GetStrings(C, TEXT("Lines"));
					if (!Block.Heading.IsEmpty() || Block.Lines.Num() > 0)
					{
						Out.Add(MoveTemp(Block));
					}
				}
			}
			if (Out.Num() == 0)
			{
				Out.Add({ FString(), { FString(TEXT("ANDREW'S AIRSOFT")), GameTitle().ToUpper() } });
				Out.Add({ FString(), { FString(TEXT("Thanks for playing.")) } });
			}
			return Out;
		}();
		return List;
	}

	FString MissionOptions(int32 Number, bool bFromCheckpoint)
	{
		FString Extra;
		if (const FMission* Mission = FindMission(Number))
		{
			Extra = MissionMap(Number) == Mission->MapPath ? Mission->Options : Mission->FallbackOptions;
		}
		return FString::Printf(TEXT("game=/Script/AndrewsAirsoft.AirsoftCampaignGameMode?Mission=%d%s%s"), Number, bFromCheckpoint ? TEXT("?Checkpoint=1") : TEXT(""), *Extra);
	}

	FString MissionMap(int32 Number)
	{
		const FMission* Mission = FindMission(Number);
		if (!Mission)
		{
			return FString();
		}
		if (!Mission->FallbackMap.IsEmpty() && !FPackageName::DoesPackageExist(Mission->MapPath))
		{
			return Mission->FallbackMap;
		}
		return Mission->MapPath;
	}

	FName VoiceKey(int32 Number, const FString& Line)
	{
		return FName(*FString::Printf(TEXT("VO_M%d_%s"), Number, *Line));
	}

	// --- Progress ----------------------------------------------------------------------

	int32 HighestUnlocked(const UObject* WorldContext)
	{
		const int32 Count = FMath::Max(1, Missions().Num());
		const UAirsoftSaveGame* P = Profile(WorldContext);
		if (!P)
		{
			return 1;
		}
		return P->bCampaignFinished ? Count : FMath::Clamp(P->CampaignReached, 1, Count);
	}

	bool IsUnlocked(const UObject* WorldContext, int32 Number)
	{
		return FindMission(Number) != nullptr && Number <= HighestUnlocked(WorldContext);
	}

	bool IsFinished(const UObject* WorldContext)
	{
		const UAirsoftSaveGame* P = Profile(WorldContext);
		return P && P->bCampaignFinished;
	}

	int32 CheckpointMission(const UObject* WorldContext)
	{
		const UAirsoftSaveGame* P = Profile(WorldContext);
		return (P && FindMission(P->CheckpointMission)) ? P->CheckpointMission : 0;
	}

	FString CheckpointLabel(const UObject* WorldContext)
	{
		const int32 Number = CheckpointMission(WorldContext);
		const FMission* Mission = FindMission(Number);
		const UAirsoftSaveGame* P = Profile(WorldContext);
		if (!Mission || !P)
		{
			return FString();
		}
		const FString Stage = P->bCheckpointBoss ? Mission->Boss.Name.ToUpper()
			: FString::Printf(TEXT("%d OF %d DOWN"), P->CheckpointKills, Mission->Enemies);
		return FString::Printf(TEXT("MISSION %d · %s · %s"), Number, *Mission->Title.ToUpper(), *Stage);
	}

	int32 ContinueMission(const UObject* WorldContext)
	{
		const int32 Checkpoint = CheckpointMission(WorldContext);
		return Checkpoint > 0 ? Checkpoint : HighestUnlocked(WorldContext);
	}

	bool CanContinue(const UObject* WorldContext)
	{
		return CheckpointMission(WorldContext) > 0 || HighestUnlocked(WorldContext) > 1 || IsFinished(WorldContext);
	}

	void Continue(const UObject* WorldContext)
	{
		const int32 Checkpoint = CheckpointMission(WorldContext);
		OpenMission(WorldContext, Checkpoint > 0 ? Checkpoint : HighestUnlocked(WorldContext), Checkpoint > 0);
	}

	void NewGame(const UObject* WorldContext)
	{
		if (UAirsoftSaveGame* P = Profile(WorldContext))
		{
			P->CheckpointMission = 0;
		}
		OpenMission(WorldContext, 1, false);
	}

	bool StartMission(const UObject* WorldContext, int32 Number)
	{
		if (!IsUnlocked(WorldContext, Number))
		{
			return false;
		}
		OpenMission(WorldContext, Number, false);
		return true;
	}
}

namespace AirsoftCampaignLocal
{
	const TArray<FString>& EnemyNames()
	{
		static const TArray<FString> Names = {
			TEXT("Ledger Enforcer"), TEXT("Ledger Gunman"), TEXT("Varga's Crew"), TEXT("Ledger Cleaner"),
			TEXT("Ledger Soldier"), TEXT("Hired Gun"), TEXT("Varga's Bodyguard"), TEXT("Ledger Collector")
		};
		return Names;
	}

	const FLinearColor StoryColor(0.9f, 0.88f, 0.85f);
	const FLinearColor BossColor(1.f, 0.16f, 0.1f);
	// Subtitle name colours.
	const FLinearColor AndrewColor(0.35f, 0.8f, 1.f);
	const FLinearColor CrewColor(0.95f, 0.45f, 0.35f);

	const FString AndrewName(TEXT("Andrew"));

	/** Best guess at a line's length when its sound isn't imported (subtitle timing). */
	float EstimateSpeech(const FString& Text)
	{
		return 0.8f + Text.Len() * 0.06f;
	}

	float Ease(float T)
	{
		const float X = FMath::Clamp(T, 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}
}

// ---------------------------------------------------------------------------
// Referee
// ---------------------------------------------------------------------------

AAirsoftCampaignGameMode::AAirsoftCampaignGameMode()
{
	// Story missions load straight in: no seamless lobby travel.
	bUseSeamlessTravel = false;
}

void AAirsoftCampaignGameMode::InitGame(const FString& MapName, const FString& Options, FString& ErrorMessage)
{
	Super::InitGame(MapName, Options, ErrorMessage);
	MissionNumber = FMath::Max(1, UGameplayStatics::GetIntOption(Options, TEXT("Mission"), 1));
	if (!AirsoftCampaign::FindMission(MissionNumber))
	{
		MissionNumber = 1;
	}
	// Continue: pick up at the saved checkpoint when it belongs to this mission.
	bResumeFromSave = UGameplayStatics::GetIntOption(Options, TEXT("Checkpoint"), 0) != 0
		&& AirsoftCampaign::CheckpointMission(this) == MissionNumber;
	// Time of day and spawn sides for maps replayed in a new light (Ironwood at night, the garage at dawn from the roof).
	bNight = UGameplayStatics::HasOption(Options, TEXT("Night"));
	bDawn = !bNight && UGameplayStatics::HasOption(Options, TEXT("Dawn"));
	bReverseSpawns = UGameplayStatics::HasOption(Options, TEXT("Reverse"));
	// Every story map is fought like a match map (team-vs-team rules), whatever the airsoft map list says.
	bPendingMatchMap = true;
	PendingMode = EAirsoftMode::TDM;
}

void AAirsoftCampaignGameMode::InitGameState()
{
	Super::InitGameState();
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
		GS->bCampaign = true;
		GS->bIsMatchMap = true;
		GS->Mode = EAirsoftMode::TDM;
		GS->MaxRounds = 0;
		GS->MissionNumber = MissionNumber;
		GS->MissionTitle = Mission ? Mission->Title : FString();
		GS->Objective = Mission ? Mission->Objective : FString();
	}
}

void AAirsoftCampaignGameMode::StartPlay()
{
	// Skip the airsoft referee's lobby/match flow: a mission is live from the first frame.
	AGameModeBase::StartPlay();
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!GS)
	{
		return;
	}
	GS->Objectives.Reset();
	for (TActorIterator<AAirsoftObjective> It(GetWorld()); It; ++It)
	{
		It->ServerReset(false);
	}
	GS->Phase = EAirsoftPhase::Live;
	GS->PhaseEndsAt = 0.f;
	UpdateObjectiveText();
	ApplyNoirGrade();
	ApplyTimeOfDay();
	AirsoftSubtitles::Clear();

	if (bResumeFromSave)
	{
		// Continue: straight back to the saved checkpoint, no opening cinematic.
		UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance());
		const UAirsoftSaveGame* Profile = GI ? GI->GetProfile() : nullptr;
		const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
		if (Profile && Mission)
		{
			bHasCheckpoint = true;
			CheckpointKills = FMath::Clamp(Profile->CheckpointKills, 0, Mission->Enemies);
			bCheckpointBoss = Profile->bCheckpointBoss && !Mission->Boss.Name.IsEmpty();
			CheckpointLocation = Profile->CheckpointLocation;
			CheckpointYaw = Profile->CheckpointYaw;
			CheckpointsReached = FMath::Max(1, Profile->CheckpointIndex);
			FTimerHandle Resume;
			GetWorldTimerManager().SetTimer(Resume, FTimerDelegate::CreateWeakLambda(this, [this]() { RestoreCheckpoint(true); }), 0.1f, false);
			return;
		}
		bResumeFromSave = false;
	}

	// The player pawn is spawned during login; give it a frame before taking over the camera.
	FTimerHandle Begin;
	GetWorldTimerManager().SetTimer(Begin, FTimerDelegate::CreateWeakLambda(this, [this]() { BeginCinematic(); }), 0.1f, false);

#if !UE_BUILD_SHIPPING
	// Testing aid: ?DebugAutoWin=N kills whatever enemies are up every N seconds (plays the mission chain unattended).
	const int32 AutoWin = UGameplayStatics::GetIntOption(OptionsString, TEXT("DebugAutoWin"), 0);
	if (AutoWin > 0)
	{
		FTimerHandle AutoWinTimer;
		GetWorldTimerManager().SetTimer(AutoWinTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { DebugKillEnemies(); }), static_cast<float>(AutoWin), true);
	}
#endif
}

void AAirsoftCampaignGameMode::Tick(float DeltaSeconds)
{
	// Not the airsoft referee's tick (no lobby, votes, rounds or bot fill).
	AGameModeBase::Tick(DeltaSeconds);
	if (bInCinematic)
	{
		UpdateCinematicCamera(DeltaSeconds);
	}
	if (bInEnding)
	{
		UpdateEndingCamera(DeltaSeconds);
	}
	UpdateBarks();
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		const AAirsoftCharacter* Boss = BossController ? Cast<AAirsoftCharacter>(BossController->GetPawn()) : nullptr;
		GS->BossHealth = (Boss && !Boss->IsOut() && Boss->GetMaxHealth() > 0.f) ? Boss->GetHealth() / Boss->GetMaxHealth() : 0.f;
	}
}

void AAirsoftCampaignGameMode::ApplyNoirGrade()
{
	// Neon-noir grade over every story map: teal-blue shadows, warm-magenta highlights, deeper contrast,
	// a touch less saturation, bloom on the practical lights, vignette, film grain and lens fringing.
	FActorSpawnParameters Params;
	Params.ObjectFlags |= RF_Transient;
	APostProcessVolume* Volume = GetWorld()->SpawnActor<APostProcessVolume>(APostProcessVolume::StaticClass(), FTransform::Identity, Params);
	if (!Volume)
	{
		return;
	}
	Volume->bUnbound = true;
	Volume->Priority = 50.f;
	Volume->BlendWeight = 1.f;
	FPostProcessSettings& S = Volume->Settings;
	S.bOverride_ColorSaturation = true;
	S.ColorSaturation = FVector4(1.f, 1.f, 1.04f, 1.f); // keep the neon saturated
	S.bOverride_ColorContrast = true;
	S.ColorContrast = FVector4(1.1f, 1.1f, 1.1f, 1.f);
	S.bOverride_ColorOffsetShadows = true;
	S.ColorOffsetShadows = FVector4(0.f, 0.004f, 0.012f, 0.f);
	S.bOverride_ColorGainHighlights = true;
	S.ColorGainHighlights = FVector4(1.04f, 0.98f, 1.02f, 1.f);
	S.bOverride_ColorGammaMidtones = true;
	S.ColorGammaMidtones = FVector4(0.98f, 0.98f, 1.02f, 1.f);
	S.bOverride_BloomIntensity = true;
	S.BloomIntensity = 1.15f;
	S.bOverride_VignetteIntensity = true;
	S.VignetteIntensity = 0.45f;
	S.bOverride_FilmGrainIntensity = true;
	S.FilmGrainIntensity = 0.22f;
	S.bOverride_SceneFringeIntensity = true;
	S.SceneFringeIntensity = 0.35f;
	S.bOverride_AutoExposureBias = true;
	S.AutoExposureBias = 0.f;
	if (bNight || bDawn)
	{
		// A day map re-lit for night or dawn meters like the night maps (EV100), so the dark stays dark.
		S.bOverride_AutoExposureMinBrightness = true;
		S.AutoExposureMinBrightness = bNight ? -2.5f : -1.5f;
		S.bOverride_AutoExposureMaxBrightness = true;
		S.AutoExposureMaxBrightness = bNight ? 1.f : 2.5f;
	}
}

void AAirsoftCampaignGameMode::ApplyTimeOfDay()
{
	if (!bNight && !bDawn)
	{
		return;
	}
	// The map's own lights are movable (Lumen), so they can be re-aimed and re-tinted at runtime.
	// Values follow the night maps' lighting preset (moon ~0.2 lux) and a low, cold-pink dawn sun.
	for (TActorIterator<ADirectionalLight> It(GetWorld()); It; ++It)
	{
		It->SetActorRotation(bNight ? FRotator(-35.f, 200.f, 0.f) : FRotator(-5.f, 95.f, 0.f));
		if (ULightComponent* Light = It->GetLightComponent())
		{
			Light->SetIntensity(bNight ? 0.25f : 2.5f);
			Light->SetUseTemperature(true); // the temperature only tints the light when this is on
			Light->SetTemperature(bNight ? 9000.f : 2700.f);
		}
	}
	for (TActorIterator<ASkyLight> It(GetWorld()); It; ++It)
	{
		if (USkyLightComponent* Sky = It->GetLightComponent())
		{
			Sky->SetIntensity(bNight ? 0.3f : 0.6f);
		}
	}
	for (TActorIterator<AExponentialHeightFog> It(GetWorld()); It; ++It)
	{
		if (UExponentialHeightFogComponent* Fog = It->GetComponent())
		{
			Fog->SetFogDensity(bNight ? 0.06f : 0.045f);
			Fog->SetStartDistance(bNight ? 300.f : 500.f);
			Fog->SetFogInscatteringColor(bNight ? FLinearColor(0.035f, 0.05f, 0.065f) : FLinearColor(0.32f, 0.26f, 0.3f));
		}
	}
	if (!bNight)
	{
		return;
	}
	// Night: sodium work lights over each objective and some of the team starts, so the yard reads in pools of light.
	TArray<FVector> Spots;
	for (TActorIterator<AAirsoftObjective> It(GetWorld()); It; ++It)
	{
		Spots.Add(It->GetActorLocation());
	}
	int32 StartIndex = 0;
	for (TActorIterator<AAirsoftTeamStart> It(GetWorld()); It; ++It)
	{
		if (StartIndex++ % 2 == 0)
		{
			Spots.Add(It->GetActorLocation());
		}
	}
	FActorSpawnParameters Params;
	Params.ObjectFlags |= RF_Transient;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	const int32 Count = FMath::Min(Spots.Num(), 12);
	for (int32 i = 0; i < Count; ++i)
	{
		APointLight* Lamp = GetWorld()->SpawnActor<APointLight>(APointLight::StaticClass(), Spots[i] + FVector(0.f, 0.f, 450.f), FRotator::ZeroRotator, Params);
		UPointLightComponent* Light = Lamp ? Cast<UPointLightComponent>(Lamp->GetLightComponent()) : nullptr;
		if (!Light)
		{
			continue;
		}
		Light->SetMobility(EComponentMobility::Movable);
		Light->SetIntensityUnits(ELightUnits::Candelas);
		Light->SetIntensity(6.f);
		Light->SetLightColor(FLinearColor(1.f, 0.62f, 0.28f));
		Light->SetAttenuationRadius(1600.f);
		// Shadows only from the lamps over the objectives (the first spots), to keep the 2070 happy.
		Light->SetCastShadows(i < 3);
	}
}

AActor* AAirsoftCampaignGameMode::FindHeroCar() const
{
	static const FName HeroTag(TEXT("Car_Hero"));
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		if (It->ActorHasTag(HeroTag))
		{
			return *It;
		}
		if (const AStaticMeshActor* Prop = Cast<AStaticMeshActor>(*It))
		{
			const UStaticMesh* Mesh = Prop->GetStaticMeshComponent() ? Prop->GetStaticMeshComponent()->GetStaticMesh() : nullptr;
			if (Mesh && Mesh->GetName().Contains(TEXT("Car_Hero")))
			{
				return *It;
			}
		}
	}
	return nullptr;
}

float AAirsoftCampaignGameMode::PlayVoice(const FString& Line)
{
	USoundBase* Sound = AirsoftAssets::Sound(AirsoftCampaign::VoiceKey(MissionNumber, Line));
	if (!Sound)
	{
		return 0.f;
	}
	UGameplayStatics::PlaySound2D(this, Sound);
	const float Length = Sound->GetDuration();
	// Story lines own the air: barks wait until they're done.
	VoiceBusyUntil = FMath::Max(VoiceBusyUntil, static_cast<double>(GetWorld()->GetTimeSeconds() + Length + 0.3f));
	return Length;
}

float AAirsoftCampaignGameMode::SpeakLine(FName File, const FString& Speaker, const FString& Text, const FLinearColor& Color, const FVector* At)
{
	float Length = 0.f;
	if (USoundBase* Sound = AirsoftAssets::Sound(File))
	{
		if (At)
		{
			AirsoftAssets::Play3D(this, File, *At);
		}
		else
		{
			UGameplayStatics::PlaySound2D(this, Sound);
		}
		Length = Sound->GetDuration();
	}
	const float Hold = Length > 0.f ? Length : AirsoftCampaignLocal::EstimateSpeech(Text);
	AirsoftSubtitles::Show(Speaker, Text, Color, Hold + 0.6f);
	VoiceBusyUntil = FMath::Max(VoiceBusyUntil, static_cast<double>(GetWorld()->GetTimeSeconds() + Hold + 0.25f));
	return Hold;
}

// ---------------------------------------------------------------------------
// Opening cinematic: the camera drifts in over Andrew's shoulder to his eyes while the
// narrator speaks; letterbox and subtitles, gameplay HUD hidden, no input until it ends.
// ---------------------------------------------------------------------------

void AAirsoftCampaignGameMode::BeginCinematic()
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Andrew = PC ? PC->GetPawn() : nullptr;
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!Mission || !PC || !Andrew || !GS)
	{
		EndCinematic();
		return;
	}

	// Length: every narrated line, at least a few seconds each.
	CinematicLength = 0.5f;
	for (int32 i = 0; i < Mission->Intro.Num(); ++i)
	{
		const USoundBase* Sound = AirsoftAssets::Sound(AirsoftCampaign::VoiceKey(MissionNumber, FString::Printf(TEXT("I%d"), i)));
		CinematicLength += FMath::Max(3.5f, (Sound ? Sound->GetDuration() : 4.5f) + 0.7f);
	}

	const FVector Eye = Andrew->GetPawnViewLocation();
	const FRotator View = PC->GetControlRotation();
	const FRotator Flat(0.f, View.Yaw, 0.f);
	// Start behind and above his shoulder (pulled in if a wall is in the way), end at his eyes.
	FVector Desired = Eye - Flat.Vector() * 340.f + FVector(0.f, 0.f, 130.f) + FRotationMatrix(Flat).GetUnitAxis(EAxis::Y) * 60.f;
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(CampaignCinematic), false, Andrew);
	if (GetWorld()->LineTraceSingleByChannel(Hit, Eye, Desired, ECC_Visibility, Params))
	{
		Desired = Hit.Location + (Eye - Hit.Location).GetSafeNormal() * 30.f;
	}
	CamFrom = Desired;
	// End just behind his head (the camera sees his body; going through it shows the inside of his goggles),
	// then cut to first person.
	CamTo = Eye - Flat.Vector() * 95.f + FVector(0.f, 0.f, 22.f) + FRotationMatrix(Flat).GetUnitAxis(EAxis::Y) * 28.f;
	CamRotFrom = (Eye + Flat.Vector() * 900.f - CamFrom).Rotation();
	CamRotTo = (Eye + View.Vector() * 900.f - CamTo).Rotation();
	// In third person, land exactly on the shoulder camera so the intro hands over without a cut.
	FVector ShoulderLoc;
	FRotator ShoulderRot;
	if (const AAirsoftCharacter* AndrewChar = Cast<AAirsoftCharacter>(Andrew); AndrewChar && AndrewChar->GetOverShoulderView(ShoulderLoc, ShoulderRot))
	{
		CamTo = ShoulderLoc;
		CamRotTo = ShoulderRot;
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.ObjectFlags |= RF_Transient;
	CinematicCamera = GetWorld()->SpawnActor<ACameraActor>(ACameraActor::StaticClass(), CamFrom, CamRotFrom, SpawnParams);
	if (CinematicCamera)
	{
		CinematicCamera->GetCameraComponent()->SetConstraintAspectRatio(false);
		CinematicCamera->GetCameraComponent()->SetFieldOfView(65.f);
		PC->SetViewTarget(CinematicCamera);
	}
	PC->SetIgnoreMoveInput(true);
	PC->SetIgnoreLookInput(true);
	if (AAirsoftCharacter* C = Cast<AAirsoftCharacter>(Andrew))
	{
		C->ServerSetFrozen(true);
	}
	bInCinematic = true;
	CinematicTime = 0.f;
	GS->bCinematic = true;
	PlayIntroLine(0);
}

void AAirsoftCampaignGameMode::PlayIntroLine(int32 Index)
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!Mission || !bInCinematic)
	{
		return;
	}
	if (!Mission->Intro.IsValidIndex(Index))
	{
		EndCinematic();
		return;
	}
	const float Voice = PlayVoice(FString::Printf(TEXT("I%d"), Index));
	const float Hold = FMath::Max(3.5f, (Voice > 0.f ? Voice : 4.5f) + 0.7f);
	const FString Title = FString::Printf(TEXT("MISSION %d · %s"), MissionNumber, *Mission->Title.ToUpper());
	AnnounceAll(Index == 0 ? Title : FString(), Mission->Intro[Index], AirsoftCampaignLocal::StoryColor, Hold);
	GetWorldTimerManager().SetTimer(IntroTimer, FTimerDelegate::CreateWeakLambda(this, [this, Index]() { PlayIntroLine(Index + 1); }), Hold, false);
}

void AAirsoftCampaignGameMode::UpdateCinematicCamera(float DeltaSeconds)
{
	CinematicTime += DeltaSeconds;
	if (!CinematicCamera)
	{
		return;
	}
	const float T = AirsoftCampaignLocal::Ease(CinematicTime / FMath::Max(CinematicLength, 0.1f));
	// A slight rise in the middle so the move reads as a crane-down rather than a straight dolly.
	const FVector Arc(0.f, 0.f, FMath::Sin(T * PI) * 40.f);
	CinematicCamera->SetActorLocationAndRotation(FMath::Lerp(CamFrom, CamTo, T) + Arc, FMath::Lerp(CamRotFrom, CamRotTo, T));
	CinematicCamera->GetCameraComponent()->SetFieldOfView(FMath::Lerp(65.f, 80.f, T));
}

void AAirsoftCampaignGameMode::SkipCinematic()
{
	if (CreditsWidget.IsValid())
	{
		StaticCastSharedPtr<SAirsoftCredits>(CreditsWidget)->Finish();
		return;
	}
	if (bInEnding)
	{
		RollCredits();
		return;
	}
	if (bInCinematic)
	{
		GetWorldTimerManager().ClearTimer(IntroTimer);
		EndCinematic();
	}
}

void AAirsoftCampaignGameMode::EndCinematic()
{
	bInCinematic = false;
	if (AAirsoftGameState* GS = GetAirsoftGameState())
	{
		GS->bCinematic = false;
	}
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (PC)
	{
		PC->ResetIgnoreInputFlags();
		if (APawn* Andrew = PC->GetPawn())
		{
			PC->SetViewTargetWithBlend(Andrew, 0.f); // a cut: a blend would pass through his head
			if (AAirsoftCharacter* C = Cast<AAirsoftCharacter>(Andrew))
			{
				C->ServerSetFrozen(false);
			}
		}
	}
	if (CinematicCamera)
	{
		CinematicCamera->SetLifeSpan(1.f);
		CinematicCamera = nullptr;
	}
	if (bEnemiesStarted || bMissionOver)
	{
		return;
	}
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (Mission)
	{
		AnnounceAll(Mission->Objective.ToUpper(), FString::Printf(TEXT("%d hostiles · they're coming"), Mission->Enemies), AirsoftColors::Accent(), 3.5f);
		// Andrew, under his breath.
		if (!Mission->AndrewStart.IsEmpty())
		{
			const FString Line = Mission->AndrewStart;
			GetWorldTimerManager().SetTimer(VoiceTimer, FTimerDelegate::CreateWeakLambda(this, [this, Line]()
			{
				SpeakLine(AirsoftCampaign::VoiceKey(MissionNumber, TEXT("Andrew_Start")), AirsoftCampaignLocal::AndrewName, Line, AirsoftCampaignLocal::AndrewColor);
			}), 0.6f, false);
		}
	}
	// The mission start is the first checkpoint (kept in the level only; the profile's starts mid-mission).
	if (const APawn* Andrew = FindPlayerPawn())
	{
		bHasCheckpoint = true;
		CheckpointKills = 0;
		bCheckpointBoss = false;
		CheckpointLocation = Andrew->GetActorLocation();
		CheckpointYaw = Andrew->GetActorRotation().Yaw;
	}
	// A breath to get into cover, then the first wave.
	FTimerHandle Start;
	GetWorldTimerManager().SetTimer(Start, FTimerDelegate::CreateWeakLambda(this, [this]()
	{
		bEnemiesStarted = true;
		TopUpEnemies();
	}), 3.f, false);
}

// ---------------------------------------------------------------------------
// Spawning
// ---------------------------------------------------------------------------

void AAirsoftCampaignGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
	if (AAirsoftPlayerState* PS = NewPlayer ? NewPlayer->GetPlayerState<AAirsoftPlayerState>() : nullptr)
	{
		PS->Team = EAirsoftTeam::Blue; // Andrew; every enemy is Red
	}
	Super::HandleStartingNewPlayer_Implementation(NewPlayer);
}

APawn* AAirsoftCampaignGameMode::FindPlayerPawn() const
{
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (const APlayerController* PC = It->Get())
		{
			if (APawn* P = PC->GetPawn())
			{
				return P;
			}
		}
	}
	return nullptr;
}

AActor* AAirsoftCampaignGameMode::ChoosePlayerStart_Implementation(AController* Player)
{
	const AAirsoftPlayerState* PS = Player ? Player->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	const bool bEnemy = PS && PS->Team == EAirsoftTeam::Red;
	// ?Reverse: Andrew comes in from the enemy's side of the map (and they from his).
	const bool bWantRed = bEnemy != bReverseSpawns;

	TArray<APlayerStart*> Mine, Neutral, All;
	for (TActorIterator<APlayerStart> It(GetWorld()); It; ++It)
	{
		APlayerStart* Start = *It;
		All.Add(Start);
		const AAirsoftTeamStart* TS = Cast<AAirsoftTeamStart>(Start);
		const EAirsoftTeam StartTeam = TS ? TS->Team : EAirsoftTeam::None;
		if (StartTeam == EAirsoftTeam::None)
		{
			Neutral.Add(Start);
		}
		else if (StartTeam == (bWantRed ? EAirsoftTeam::Red : EAirsoftTeam::Blue))
		{
			Mine.Add(Start);
		}
	}
	const TArray<APlayerStart*>& Pool = Mine.Num() > 0 ? Mine : (Neutral.Num() > 0 ? Neutral : All);
	if (Pool.Num() == 0)
	{
		return Super::ChoosePlayerStart_Implementation(Player);
	}
	if (!bEnemy)
	{
		// Andrew always starts at the same spot so a restart replays the same fight.
		return Pool[0];
	}
	// Enemies: well away from Andrew (never in his face), not on top of each other, a little random.
	const APawn* Andrew = FindPlayerPawn();
	APlayerStart* Best = nullptr;
	float BestScore = -TNumericLimits<float>::Max();
	for (APlayerStart* Start : Pool)
	{
		const FVector Loc = Start->GetActorLocation();
		bool bOccupied = false;
		for (TActorIterator<AAirsoftCharacter> It(GetWorld()); It; ++It)
		{
			if (!It->IsOut() && FVector::Dist(It->GetActorLocation(), Loc) < 110.f)
			{
				bOccupied = true;
			}
		}
		const float Dist = Andrew ? static_cast<float>(FVector::Dist(Andrew->GetActorLocation(), Loc)) : 3000.f;
		// Far is good up to ~25 m; beyond that distance stops mattering so they don't all queue at one end.
		const float Score = FMath::Min(Dist, 2500.f) - (Dist < 1200.f ? 5000.f : 0.f) + FMath::FRandRange(0.f, 900.f) - (bOccupied ? 100000.f : 0.f);
		if (Score > BestScore)
		{
			BestScore = Score;
			Best = Start;
		}
	}
	return Best;
}

void AAirsoftCampaignGameMode::SetPlayerDefaults(APawn* PlayerPawn)
{
	Super::SetPlayerDefaults(PlayerPawn);
	AAirsoftCharacter* C = Cast<AAirsoftCharacter>(PlayerPawn);
	if (!C)
	{
		return;
	}
	C->MaxHealth = 100.f;
	C->Health = C->MaxHealth;
	C->ServerSetFrozen(bInCinematic);
	if (AAirsoftPlayerState* PS = C->GetAirsoftPlayerState())
	{
		PS->ProtectedUntil = 0.f; // no airsoft spawn protection in the story
	}
}

EAirsoftBotSkill AAirsoftCampaignGameMode::Difficulty() const
{
	UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance());
	return AirsoftBots::SkillFromIndex(GI ? GI->GetUserSettings().BotSkill : 1);
}

FAirsoftLoadout AAirsoftCampaignGameMode::MakeEnemyLoadout(FName WeaponId) const
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	FAirsoftLoadout L = MakeBotLoadout();
	if (WeaponId.IsNone() && Mission && Mission->EnemyWeapons.Num() > 0)
	{
		WeaponId = Mission->EnemyWeapons[FMath::RandRange(0, Mission->EnemyWeapons.Num() - 1)];
	}
	if (const FAirsoftWeaponDef* W = AirsoftWeapons::Find(WeaponId))
	{
		FAirsoftCustomization Primary;
		Primary.WeaponId = WeaponId;
		// Iron sights or a red dot: enemies don't need magnified glass.
		if (const TArray<FName>* Optics = W->Options.Find(AirsoftWeapons::SlotOptic))
		{
			Primary.Optic = Optics->Contains(TEXT("RedDot")) && FMath::RandBool() ? FName(TEXT("RedDot")) : AirsoftWeapons::AttachOff;
		}
		L.Primary = AirsoftWeapons::Clean(Primary);
	}
	return L;
}

AAirsoftBotController* AAirsoftCampaignGameMode::SpawnEnemy()
{
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Params.ObjectFlags |= RF_Transient;
	AAirsoftBotController* Bot = GetWorld()->SpawnActor<AAirsoftBotController>(AAirsoftBotController::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Params);
	AAirsoftPlayerState* PS = Bot ? Bot->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!PS)
	{
		if (Bot)
		{
			Bot->Destroy();
		}
		return nullptr;
	}
	const TArray<FString>& Names = AirsoftCampaignLocal::EnemyNames();
	PS->SetPlayerName(Names[FMath::RandRange(0, Names.Num() - 1)]);
	PS->Team = EAirsoftTeam::Red;
	PS->Loadout = MakeEnemyLoadout();
	PS->bLoadoutReceived = true;
	PS->CareerXP = 0;
	Bot->SetSkill(Difficulty());
	return Bot;
}

void AAirsoftCampaignGameMode::TopUpEnemies()
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!Mission || bMissionOver || !bEnemiesStarted)
	{
		return;
	}
	int32 Alive = 0;
	for (const AAirsoftBotController* Bot : Enemies)
	{
		const AAirsoftCharacter* C = Bot ? Cast<AAirsoftCharacter>(Bot->GetPawn()) : nullptr;
		Alive += (C && !C->IsOut()) ? 1 : 0;
	}
	while (Alive < Mission->MaxAlive && EnemiesSpawned < Mission->Enemies)
	{
		// Reuse a controller whose last body fell, otherwise hire a new one.
		AAirsoftBotController* Bot = nullptr;
		for (AAirsoftBotController* Candidate : Enemies)
		{
			if (Candidate && !Candidate->GetPawn())
			{
				Bot = Candidate;
				break;
			}
		}
		if (!Bot)
		{
			Bot = SpawnEnemy();
			if (Bot)
			{
				Enemies.Add(Bot);
			}
		}
		if (!Bot)
		{
			break;
		}
		if (AAirsoftPlayerState* PS = Bot->GetPlayerState<AAirsoftPlayerState>())
		{
			PS->Loadout = MakeEnemyLoadout();
			PS->bOut = false;
		}
		RestartPlayer(Bot);
		++EnemiesSpawned;
		++Alive;
	}
	UpdateObjectiveText();
}

void AAirsoftCampaignGameMode::SpawnBoss()
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	AAirsoftGameState* GS = GetAirsoftGameState();
	if (!Mission || !GS || bMissionOver || BossController)
	{
		return;
	}
	BossController = SpawnEnemy();
	AAirsoftPlayerState* PS = BossController ? BossController->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!PS)
	{
		CompleteMission();
		return;
	}
	PS->SetPlayerName(Mission->Boss.Name);
	PS->Loadout = MakeEnemyLoadout(Mission->Boss.Weapon);
	// The boss is a notch sharper than the crew.
	BossController->SetSkill(static_cast<EAirsoftBotSkill>(FMath::Min(static_cast<int32>(Difficulty()) + 1, static_cast<int32>(EAirsoftBotSkill::Expert))));
	Enemies.Add(BossController);
	GS->BossName = Mission->Boss.Name; // before the spawn: the body picks its suit from it
	RestartPlayer(BossController);
	if (AAirsoftCharacter* Boss = Cast<AAirsoftCharacter>(BossController->GetPawn()))
	{
		Boss->MaxHealth = Mission->Boss.Health;
		Boss->Health = Boss->MaxHealth;
		Boss->RegenDelay = 6.f;
		Boss->RegenRate = 8.f; // bosses patch up slowly: keep the pressure on
	}
	GS->BossName = Mission->Boss.Name;
	GS->BossHealth = 1.f;
	const float Voice = PlayVoice(TEXT("Boss"));
	AnnounceAll(Mission->Boss.Name.ToUpper(), FString::Printf(TEXT("“%s”"), *Mission->Boss.Taunt), AirsoftCampaignLocal::BossColor, FMath::Max(4.f, Voice + 1.f));
	// Andrew answers once the taunt is done.
	if (!Mission->Boss.AndrewReply.IsEmpty())
	{
		const FString Reply = Mission->Boss.AndrewReply;
		GetWorldTimerManager().SetTimer(VoiceTimer, FTimerDelegate::CreateWeakLambda(this, [this, Reply]()
		{
			if (!bMissionOver)
			{
				SpeakLine(AirsoftCampaign::VoiceKey(MissionNumber, TEXT("Andrew_Boss")), AirsoftCampaignLocal::AndrewName, Reply, AirsoftCampaignLocal::AndrewColor);
			}
		}), FMath::Max(1.5f, (Voice > 0.f ? Voice : AirsoftCampaignLocal::EstimateSpeech(Mission->Boss.Taunt)) + 0.5f), false);
	}
	bBossMidSaid = false;
	UpdateObjectiveText();
}

void AAirsoftCampaignGameMode::UpdateObjectiveText()
{
	AAirsoftGameState* GS = GetAirsoftGameState();
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!GS || !Mission)
	{
		return;
	}
	GS->EnemiesLeft = FMath::Max(0, Mission->Enemies - EnemiesKilled);
	GS->RedAlive = GS->EnemiesLeft;
	if (bMissionOver)
	{
		GS->StatusMessage.Reset();
	}
	else if (BossController)
	{
		GS->StatusMessage = FString::Printf(TEXT("Take down %s"), *Mission->Boss.Name);
	}
	else
	{
		GS->StatusMessage = FString::Printf(TEXT("%s · %d hostiles left"), *Mission->Objective, GS->EnemiesLeft);
	}
}

// ---------------------------------------------------------------------------
// Damage
// ---------------------------------------------------------------------------

bool AAirsoftCampaignGameMode::HandleTag(AController* Shooter, AController* Victim, FName WeaponId)
{
	// Only grenades come through here in the campaign (shots use HandleHit).
	return ApplyCampaignDamage(Shooter, Victim, WeaponId, AirsoftCampaign::WeaponDamage(WeaponId, false), false);
}

bool AAirsoftCampaignGameMode::HandleHit(AController* Shooter, AController* Victim, FName WeaponId, const FVector& HitLocation)
{
	const APawn* VictimPawn = Victim ? Victim->GetPawn() : nullptr;
	// Head: the top ~22 cm of a standing (or crouched) body.
	const bool bHeadshot = VictimPawn && HitLocation.Z > VictimPawn->GetPawnViewLocation().Z - 22.f;
	return ApplyCampaignDamage(Shooter, Victim, WeaponId, AirsoftCampaign::WeaponDamage(WeaponId, bHeadshot), bHeadshot);
}

bool AAirsoftCampaignGameMode::ApplyCampaignDamage(AController* Shooter, AController* Victim, FName WeaponId, float Damage, bool bHeadshot)
{
	if (bMissionOver || bInCinematic || !Victim || Shooter == Victim)
	{
		return false;
	}
	AAirsoftCharacter* VictimChar = Cast<AAirsoftCharacter>(Victim->GetPawn());
	const AAirsoftPlayerState* VictimPS = Victim->GetPlayerState<AAirsoftPlayerState>();
	const AAirsoftPlayerState* ShooterPS = Shooter ? Shooter->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	if (!VictimChar || !VictimPS || VictimChar->IsOut())
	{
		return false;
	}
	if (ShooterPS && ShooterPS->Team == VictimPS->Team)
	{
		return false; // enemies don't shoot each other, and nobody else is on Andrew's side
	}
	const bool bVictimIsPlayer = Victim->IsPlayerController();
	if (bVictimIsPlayer)
	{
		if (bBossDown)
		{
			return false; // the fight is won; a stray grenade doesn't undo it
		}
		Damage *= AirsoftCampaign::EnemyDamageScale(Difficulty());
	}
	const APawn* ShooterPawn = Shooter ? Shooter->GetPawn() : nullptr;
	const FString ShooterName = ShooterPS ? ShooterPS->GetPlayerName() : FString(TEXT("a grenade"));
	const bool bKilled = VictimChar->ServerApplyDamage(Damage, ShooterName, ShooterPawn ? ShooterPawn->GetActorLocation() : VictimChar->GetActorLocation());
	if (bKilled)
	{
		if (bVictimIsPlayer)
		{
			OnPlayerKilled(Victim, ShooterName);
		}
		else
		{
			OnEnemyKilled(Shooter, Victim, WeaponId, bHeadshot);
		}
	}
	else if (!bVictimIsPlayer)
	{
		if (Victim == BossController)
		{
			// Half health: the boss's mask slips.
			const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
			if (Mission && !bBossMidSaid && !Mission->Boss.Mid.IsEmpty() && VictimChar->GetHealth() < VictimChar->GetMaxHealth() * 0.5f)
			{
				bBossMidSaid = true;
				SpeakLine(AirsoftCampaign::VoiceKey(MissionNumber, TEXT("Boss_Mid")), Mission->Boss.Name, Mission->Boss.Mid, AirsoftCampaignLocal::BossColor);
			}
		}
		else
		{
			Bark(TEXT("CrewHit"), Victim, 0.3f);
		}
	}
	return true;
}

void AAirsoftCampaignGameMode::OnEnemyKilled(AController* Shooter, AController* Victim, FName WeaponId, bool bHeadshot)
{
	const bool bBoss = Victim == BossController;
	if (!bBoss)
	{
		++EnemiesKilled;
	}
	AAirsoftPlayerState* ShooterPS = Shooter ? Shooter->GetPlayerState<AAirsoftPlayerState>() : nullptr;
	const AAirsoftPlayerState* VictimPS = Victim->GetPlayerState<AAirsoftPlayerState>();
	if (ShooterPS)
	{
		ShooterPS->Round.Tags++;
		ShooterPS->Round.Streak++;
		GiveXP(Shooter, bBoss ? 500 : 100, bBoss ? TEXT("BOSS DOWN") : TEXT("ELIMINATED"));
		if (bHeadshot)
		{
			GiveXP(Shooter, 50, TEXT("HEADSHOT"));
		}
		const int32 Streak = ShooterPS->Round.Streak;
		if (Streak == 3 || Streak == 5 || Streak == 8 || Streak == 12)
		{
			GiveXP(Shooter, Streak * 20, FString::Printf(TEXT("STREAK x%d"), Streak));
		}
		// Scavenged ammunition off the body.
		if (AAirsoftCharacter* ShooterChar = Cast<AAirsoftCharacter>(Shooter->GetPawn()))
		{
			ShooterChar->GetCombat()->ServerGiveAmmo(0.5f);
		}
	}
	for (FConstPlayerControllerIterator It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
	{
		if (AAirsoftPlayerController* PC = Cast<AAirsoftPlayerController>(It->Get()))
		{
			PC->ClientKillFeed(ShooterPS ? ShooterPS->GetPlayerName() : FString(TEXT("Grenade")), EAirsoftTeam::Blue,
				VictimPS ? VictimPS->GetPlayerName() : FString(TEXT("Hostile")), EAirsoftTeam::Red, WeaponId);
		}
	}
	// The body stays where it fell (for a while); a crew controller is free to come back as reinforcements.
	const FVector BodyLocation = Victim->GetPawn() ? Victim->GetPawn()->GetActorLocation() : FVector::ZeroVector;
	if (APawn* Body = Victim->GetPawn())
	{
		Victim->UnPossess();
		Body->SetLifeSpan(60.f);
	}
	UpdateObjectiveText();
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);

	if (bBoss)
	{
		if (AAirsoftGameState* GS = GetAirsoftGameState())
		{
			GS->BossHealth = 0.f;
		}
		// The boss's last words, then the mission ends.
		bBossDown = true;
		float Hold = 0.f;
		if (Mission && !Mission->Boss.Death.IsEmpty())
		{
			Hold = SpeakLine(AirsoftCampaign::VoiceKey(MissionNumber, TEXT("Boss_Death")), Mission->Boss.Name, Mission->Boss.Death, AirsoftCampaignLocal::BossColor);
		}
		GetWorldTimerManager().ClearTimer(VoiceTimer);
		GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { CompleteMission(); }), FMath::Max(1.2f, Hold + 0.8f), false);
		return;
	}

	const bool bByAndrew = Shooter && Shooter->IsPlayerController();
	const bool bCrewCleared = Mission && EnemiesKilled >= Mission->Enemies;
	if (bByAndrew && bCrewCleared && Mission && !Mission->Boss.Name.IsEmpty() && !bLastKillSaid)
	{
		// The last of the crew: Andrew calls for the boss.
		bLastKillSaid = true;
		if (const TArray<AirsoftCampaign::FLine>* Lines = AirsoftCampaign::FindBarks(TEXT("AndrewLastKill")))
		{
			const AirsoftCampaign::FLine& Line = (*Lines)[FMath::RandRange(0, Lines->Num() - 1)];
			SpeakLine(Line.File, AirsoftCampaignLocal::AndrewName, Line.Text, AirsoftCampaignLocal::AndrewColor);
		}
	}
	else if (!bCrewCleared)
	{
		// A crewmate nearby reacts; otherwise, now and then, Andrew does.
		AController* Witness = nullptr;
		float Nearest = 1800.f;
		for (AAirsoftBotController* Bot : Enemies)
		{
			const APawn* P = Bot ? Bot->GetPawn() : nullptr;
			const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(P);
			if (C && !C->IsOut() && Bot != Victim)
			{
				const float D = static_cast<float>(FVector::Dist(P->GetActorLocation(), BodyLocation));
				if (D < Nearest)
				{
					Nearest = D;
					Witness = Bot;
				}
			}
		}
		const int32 Left = Mission ? Mission->Enemies - EnemiesKilled : 0;
		if (!bFearSaid && Left > 0 && Left <= 2 && Witness && Bark(TEXT("CrewFear"), Witness))
		{
			bFearSaid = true;
		}
		else if (!(Witness && Bark(TEXT("CrewManDown"), Witness, 0.45f)) && bByAndrew)
		{
			Bark(TEXT("AndrewKill"), nullptr, 0.3f);
		}
	}

	if (bCrewCleared)
	{
		if (Mission->Boss.Name.IsEmpty())
		{
			CompleteMission();
		}
		else
		{
			// The crew is down: the boss fight is a checkpoint; a beat of quiet, then the boss.
			SaveCheckpoint(true);
			GetWorldTimerManager().SetTimer(BossTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { SpawnBoss(); }), 3.f, false);
		}
		return;
	}
	CheckCrewCheckpoint();
	// Reinforcements after a short pause, so there's a breath between waves.
	GetWorldTimerManager().SetTimer(RefillTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { TopUpEnemies(); }), 2.5f, false);
}

void AAirsoftCampaignGameMode::OnPlayerKilled(AController* Victim, const FString& KilledBy)
{
	if (bMissionOver)
	{
		return;
	}
	bMissionOver = true;
	if (AAirsoftPlayerState* PS = Victim->GetPlayerState<AAirsoftPlayerState>())
	{
		PS->LastTaggedBy = KilledBy;
	}
	// The HUD's "DOWN · Killed by ..." overlay says it; no second banner on top.
	UpdateObjectiveText();
	GetWorldTimerManager().ClearTimer(BossTimer);
	GetWorldTimerManager().ClearTimer(RefillTimer);
	GetWorldTimerManager().ClearTimer(VoiceTimer);
	if (bHasCheckpoint)
	{
		// Back to the last checkpoint after a moment.
		bRespawning = true;
		GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { RestoreCheckpoint(true); }), 4.f, false);
		return;
	}
	const int32 Number = MissionNumber;
	const FString Map = AirsoftCampaign::MissionMap(Number);
	GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this, Number, Map]()
	{
		UGameplayStatics::OpenLevel(this, FName(*Map), true, AirsoftCampaign::MissionOptions(Number));
	}), 5.f, false);
}

void AAirsoftCampaignGameMode::CompleteMission()
{
	if (bMissionOver)
	{
		return;
	}
	bMissionOver = true;
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	const int32 Next = MissionNumber + 1;
	const bool bLast = AirsoftCampaign::FindMission(Next) == nullptr;
	if (UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance()))
	{
		if (UAirsoftSaveGame* Profile = GI->GetProfile())
		{
			Profile->CampaignReached = FMath::Max(Profile->CampaignReached, bLast ? MissionNumber : Next);
			Profile->bCampaignFinished = Profile->bCampaignFinished || bLast;
			// Story gun unlocks for finishing this mission (first time only).
			UnlockedGunsText = AirsoftUnlocks::NamesText(AirsoftUnlocks::GrantForMission(Profile, MissionNumber));
			// The mission is done: its checkpoint is no longer something to continue from.
			if (Profile->CheckpointMission == MissionNumber)
			{
				Profile->CheckpointMission = 0;
			}
		}
		GI->SaveProfile();
	}
	GetWorldTimerManager().ClearTimer(BossTimer);
	GetWorldTimerManager().ClearTimer(RefillTimer);
	if (bLast)
	{
		BeginEnding();
		return;
	}
	const float Voice = PlayVoice(TEXT("Outro"));
	const float Hold = FMath::Max(7.f, Voice + 2.5f);
	FString Sub = Mission ? Mission->Outro : FString();
	if (!UnlockedGunsText.IsEmpty())
	{
		Sub += FString::Printf(TEXT("%sNEW GUNS UNLOCKED: %s. Equip them in the Armory."), Sub.IsEmpty() ? TEXT("") : TEXT("\n"), *UnlockedGunsText.ToUpper());
	}
	AnnounceAll(bLast ? TEXT("CONTRACT CLOSED") : TEXT("MISSION COMPLETE"), Sub, AirsoftColors::Accent(), Hold);
	UpdateObjectiveText();
	GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this, Next, bLast]()
	{
		UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance());
		if (bLast || !GI)
		{
			if (GI)
			{
				GI->ReturnToMainMenu(CompletionMessage());
			}
			return;
		}
		GI->StartMission(Next);
	}), Hold + 1.f, false);
}

FString AAirsoftCampaignGameMode::CompletionMessage() const
{
	return UnlockedGunsText.IsEmpty()
		? FString::Printf(TEXT("%s complete. Thanks for playing."), *AirsoftCampaign::GameTitle())
		: FString::Printf(TEXT("%s complete. New guns unlocked: %s."), *AirsoftCampaign::GameTitle(), *UnlockedGunsText);
}

void AAirsoftCampaignGameMode::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (CreditsWidget.IsValid())
	{
		if (UGameViewportClient* Viewport = GetWorld() ? GetWorld()->GetGameViewport() : nullptr)
		{
			Viewport->RemoveViewportWidgetContent(CreditsWidget.ToSharedRef());
		}
		CreditsWidget.Reset();
	}
	AirsoftSubtitles::Clear();
	Super::EndPlay(EndPlayReason);
}

// ---------------------------------------------------------------------------
// Checkpoints: the mission start (in the level only), a fraction of the crew down
// (Campaign.json "Checkpoints") and the boss fight. The mid-mission ones are saved in the
// profile, so Continue picks up there. A death puts Andrew back at the last one with the
// enemies that were up cleared away and the crew count as it was then.
// ---------------------------------------------------------------------------

void AAirsoftCampaignGameMode::SaveCheckpoint(bool bBossPhase)
{
	// Where Andrew stands now, if he's on his feet on solid ground; otherwise the last good spot.
	const AAirsoftCharacter* Andrew = Cast<AAirsoftCharacter>(FindPlayerPawn());
	const UCharacterMovementComponent* Move = Andrew ? Andrew->GetCharacterMovement() : nullptr;
	if (Andrew && !Andrew->IsOut() && Move && Move->IsMovingOnGround())
	{
		CheckpointLocation = Andrew->GetActorLocation();
		CheckpointYaw = Andrew->GetControlRotation().Yaw;
	}
	bHasCheckpoint = true;
	CheckpointKills = EnemiesKilled;
	bCheckpointBoss = bBossPhase;
	++CheckpointsReached;

	if (UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance()))
	{
		if (UAirsoftSaveGame* Profile = GI->GetProfile())
		{
			Profile->CheckpointMission = MissionNumber;
			Profile->CheckpointKills = CheckpointKills;
			Profile->CheckpointIndex = CheckpointsReached;
			Profile->bCheckpointBoss = bCheckpointBoss;
			Profile->CheckpointLocation = CheckpointLocation;
			Profile->CheckpointYaw = CheckpointYaw;
		}
		GI->SaveProfile();
	}
	AnnounceAll(TEXT("CHECKPOINT"), FString(), AirsoftColors::Accent(), 1.8f);
}

void AAirsoftCampaignGameMode::CheckCrewCheckpoint()
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	if (!Mission)
	{
		return;
	}
	bool bDue = false;
	while (Mission->Checkpoints.IsValidIndex(NextCheckpoint)
		&& EnemiesKilled >= FMath::Clamp(FMath::CeilToInt(Mission->Checkpoints[NextCheckpoint] * Mission->Enemies), 1, Mission->Enemies))
	{
		++NextCheckpoint;
		bDue = true;
	}
	if (bDue && EnemiesKilled < Mission->Enemies)
	{
		SaveCheckpoint(false);
	}
}

void AAirsoftCampaignGameMode::RestoreCheckpoint(bool bAnnounce)
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	AAirsoftGameState* GS = GetAirsoftGameState();
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (!Mission || !GS || !PC)
	{
		return;
	}
	FTimerManager& Timers = GetWorldTimerManager();
	Timers.ClearTimer(BossTimer);
	Timers.ClearTimer(RefillTimer);
	Timers.ClearTimer(VoiceTimer);
	Timers.ClearTimer(EndTimer);
	AirsoftSubtitles::Clear();

	// Clear the field: whoever was up goes; the controllers stay for the next wave. The boss starts over.
	const TArray<TObjectPtr<AAirsoftBotController>> Current = Enemies;
	for (AAirsoftBotController* Bot : Current)
	{
		if (Bot)
		{
			if (APawn* Body = Bot->GetPawn())
			{
				Bot->UnPossess();
				Body->Destroy();
			}
		}
	}
	if (BossController)
	{
		Enemies.Remove(BossController);
		BossController->Destroy();
		BossController = nullptr;
	}
	GS->BossName.Reset();
	GS->BossHealth = 0.f;

	EnemiesKilled = CheckpointKills;
	EnemiesSpawned = CheckpointKills;
	bBossDown = false;
	bBossMidSaid = false;
	bFearSaid = false;
	bLastKillSaid = CheckpointKills >= Mission->Enemies;
	NextCheckpoint = 0;
	while (Mission->Checkpoints.IsValidIndex(NextCheckpoint)
		&& CheckpointKills >= FMath::Clamp(FMath::CeilToInt(Mission->Checkpoints[NextCheckpoint] * Mission->Enemies), 1, Mission->Enemies))
	{
		++NextCheckpoint;
	}
	CrewWatch.Reset();
	bAndrewWasReloading = false;
	bAndrewWasThrowing = false;
	bAndrewHurtArmed = true;

	// Andrew, back on his feet at the checkpoint (or the mission start if that spot is blocked).
	if (APawn* Old = PC->GetPawn())
	{
		PC->UnPossess();
		Old->Destroy();
	}
	if (AAirsoftPlayerState* PS = PC->GetPlayerState<AAirsoftPlayerState>())
	{
		PS->bOut = false;
	}
	bMissionOver = false;
	bRespawning = false;
	const FRotator Facing(0.f, CheckpointYaw, 0.f);
	if (!CheckpointLocation.IsNearlyZero())
	{
		RestartPlayerAtTransform(PC, FTransform(Facing, CheckpointLocation));
	}
	if (!PC->GetPawn())
	{
		RestartPlayer(PC);
	}
	PC->SetControlRotation(Facing);
	PC->ResetIgnoreInputFlags();
	PC->SetViewTarget(PC->GetPawn());

	bEnemiesStarted = true;
	const int32 Left = FMath::Max(0, Mission->Enemies - EnemiesKilled);
	if (bAnnounce)
	{
		const FString Title = bResumeFromSave
			? FString::Printf(TEXT("MISSION %d · %s"), MissionNumber, *Mission->Title.ToUpper())
			: FString(TEXT("CHECKPOINT"));
		const FString Sub = bCheckpointBoss
			? FString::Printf(TEXT("Take down %s"), *Mission->Boss.Name)
			: FString::Printf(TEXT("%s · %d hostiles left"), *Mission->Objective, Left);
		AnnounceAll(Title, Sub, AirsoftColors::Accent(), 3.f);
	}
	bResumeFromSave = false;
	// A breath to find cover, then the fight picks up where the checkpoint was.
	if (bCheckpointBoss)
	{
		Timers.SetTimer(BossTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { SpawnBoss(); }), 3.f, false);
	}
	else
	{
		Timers.SetTimer(RefillTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { TopUpEnemies(); }), 3.f, false);
	}
	UpdateObjectiveText();
}

// ---------------------------------------------------------------------------
// Barks: short combat lines from Andrew and the crew (Campaign.json "Barks"), one voice
// at a time, never over a story line, with a few seconds between them. Each crew member
// keeps one of three voices (A, B, C) and is heard from where he stands.
// ---------------------------------------------------------------------------

TCHAR AAirsoftCampaignGameMode::CrewVoiceFor(const AController* Enemy)
{
	FCrewWatch& Watch = CrewWatch.FindOrAdd(TWeakObjectPtr<AController>(const_cast<AController*>(Enemy)));
	if (Watch.Voice == 0)
	{
		static const TCHAR Voices[] = { TEXT('A'), TEXT('B'), TEXT('C') };
		Watch.Voice = Voices[CrewVoicesHanded++ % 3];
	}
	return Watch.Voice;
}

bool AAirsoftCampaignGameMode::Bark(FName Event, AController* Speaker, float Chance)
{
	const double Now = GetWorld()->GetTimeSeconds();
	const bool bAndrew = Speaker == nullptr;
	if (Now < VoiceBusyUntil || Now < (bAndrew ? NextAndrewBark : NextCrewBark) || FMath::FRand() > Chance)
	{
		return false;
	}
	const TArray<AirsoftCampaign::FLine>* Lines = AirsoftCampaign::FindBarks(Event);
	if (!Lines)
	{
		return false;
	}
	const APawn* Body = Speaker ? Speaker->GetPawn() : nullptr;
	if (!bAndrew && !Body)
	{
		return false;
	}

	// The crew member's own voice when the event has a line for it.
	TArray<const AirsoftCampaign::FLine*> Pick;
	if (!bAndrew)
	{
		const FString Tag = FString::Printf(TEXT("_%c_"), CrewVoiceFor(Speaker));
		for (const AirsoftCampaign::FLine& Line : *Lines)
		{
			if (Line.File.ToString().Contains(Tag))
			{
				Pick.Add(&Line);
			}
		}
	}
	if (Pick.Num() == 0)
	{
		for (const AirsoftCampaign::FLine& Line : *Lines)
		{
			Pick.Add(&Line);
		}
	}
	const AirsoftCampaign::FLine& Line = *Pick[FMath::RandRange(0, Pick.Num() - 1)];

	if (bAndrew)
	{
		SpeakLine(Line.File, AirsoftCampaignLocal::AndrewName, Line.Text, AirsoftCampaignLocal::AndrewColor);
		NextAndrewBark = Now + FMath::FRandRange(7.f, 11.f);
	}
	else
	{
		const AAirsoftPlayerState* PS = Speaker->GetPlayerState<AAirsoftPlayerState>();
		const FVector At = Body->GetActorLocation();
		SpeakLine(Line.File, PS ? PS->GetPlayerName() : FString(TEXT("Hostile")), Line.Text, AirsoftCampaignLocal::CrewColor, &At);
		NextCrewBark = Now + FMath::FRandRange(3.f, 6.f);
	}
	return true;
}

void AAirsoftCampaignGameMode::UpdateBarks()
{
	if (!bEnemiesStarted || bMissionOver || bInCinematic || bInEnding || bRespawning || bBossDown)
	{
		return;
	}
	// Andrew: reloading, badly hurt, and the crew shouting when he throws a grenade.
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	const AAirsoftCharacter* Andrew = PC ? Cast<AAirsoftCharacter>(PC->GetPawn()) : nullptr;
	if (Andrew && !Andrew->IsOut())
	{
		if (const UAirsoftCombatComponent* Combat = Andrew->GetCombat())
		{
			const bool bReloading = Combat->IsReloading();
			if (bReloading && !bAndrewWasReloading)
			{
				Bark(TEXT("AndrewReload"), nullptr, 0.4f);
			}
			bAndrewWasReloading = bReloading;

			const bool bThrowing = Combat->IsThrowing();
			if (bThrowing && !bAndrewWasThrowing)
			{
				AController* Nearest = nullptr;
				float Best = 2500.f;
				for (AAirsoftBotController* Bot : Enemies)
				{
					const AAirsoftCharacter* C = Bot ? Cast<AAirsoftCharacter>(Bot->GetPawn()) : nullptr;
					const float D = C ? static_cast<float>(FVector::Dist(C->GetActorLocation(), Andrew->GetActorLocation())) : Best;
					if (C && !C->IsOut() && Bot != BossController && D < Best)
					{
						Best = D;
						Nearest = Bot;
					}
				}
				if (Nearest)
				{
					Bark(TEXT("CrewIncoming"), Nearest, 0.8f);
				}
			}
			bAndrewWasThrowing = bThrowing;
		}
		const float Health = Andrew->GetHealth() / FMath::Max(1.f, Andrew->GetMaxHealth());
		if (bAndrewHurtArmed && Health < 0.3f)
		{
			if (Bark(TEXT("AndrewHurt"), nullptr, 1.f))
			{
				bAndrewHurtArmed = false;
			}
		}
		else if (Health > 0.6f)
		{
			bAndrewHurtArmed = true;
		}
	}

	// The crew: spotting him, losing him, pushing, reloading, throwing.
	for (AAirsoftBotController* Bot : Enemies)
	{
		if (!Bot || Bot == BossController)
		{
			continue;
		}
		CrewVoiceFor(Bot); // makes sure the entry exists, so Bark() below never grows the map under this reference
		FCrewWatch& Watch = CrewWatch.FindChecked(TWeakObjectPtr<AController>(Bot));
		const AAirsoftCharacter* C = Cast<AAirsoftCharacter>(Bot->GetPawn());
		if (!C || C->IsOut())
		{
			Watch.LastState = static_cast<uint8>(EAirsoftBotState::Idle);
			Watch.bWasReloading = false;
			Watch.bWasThrowing = false;
			continue;
		}
		const EAirsoftBotState State = Bot->GetBotState();
		const EAirsoftBotState Last = static_cast<EAirsoftBotState>(Watch.LastState);
		if (State != Last)
		{
			if (State == EAirsoftBotState::Engage)
			{
				Bark(TEXT("CrewSpotted"), Bot, 0.6f);
			}
			else if (State == EAirsoftBotState::Investigate && Last == EAirsoftBotState::Engage)
			{
				Bark(TEXT("CrewSearch"), Bot, 0.5f);
			}
			else if (State == EAirsoftBotState::Advance && (Last == EAirsoftBotState::Engage || Last == EAirsoftBotState::Hold))
			{
				Bark(TEXT("CrewFlank"), Bot, 0.35f);
			}
			Watch.LastState = static_cast<uint8>(State);
		}
		if (const UAirsoftCombatComponent* Combat = C->GetCombat())
		{
			const bool bReloading = Combat->IsReloading();
			if (bReloading && !Watch.bWasReloading)
			{
				Bark(TEXT("CrewReload"), Bot, 0.4f);
			}
			Watch.bWasReloading = bReloading;
			const bool bThrowing = Combat->IsThrowing();
			if (bThrowing && !Watch.bWasThrowing)
			{
				Bark(TEXT("CrewGrenade"), Bot, 0.9f);
			}
			Watch.bWasThrowing = bThrowing;
		}
	}
}

// ---------------------------------------------------------------------------
// Ending: after the last boss, the camera rises away from Andrew while the narrator
// closes the story; then the screen goes black and the credits roll. Space skips each.
// ---------------------------------------------------------------------------

void AAirsoftCampaignGameMode::BeginEnding()
{
	const AirsoftCampaign::FMission* Mission = AirsoftCampaign::FindMission(MissionNumber);
	AAirsoftGameState* GS = GetAirsoftGameState();
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Andrew = PC ? PC->GetPawn() : nullptr;
	AirsoftSubtitles::Clear();
	GetWorldTimerManager().ClearTimer(VoiceTimer);
	if (!GS || !PC || !Andrew)
	{
		RollCredits();
		return;
	}
	bInEnding = true;
	EndingTime = 0.f;
	GS->bCinematic = true;
	GS->BossName.Reset();
	PC->SetIgnoreMoveInput(true);
	PC->SetIgnoreLookInput(true);
	if (AAirsoftCharacter* C = Cast<AAirsoftCharacter>(Andrew))
	{
		C->ServerSetFrozen(true);
	}

	// From a three-quarter close-up of his face to high and wide behind him: one man in the rain.
	const FVector Eye = Andrew->GetPawnViewLocation();
	const FRotator Flat(0.f, Andrew->GetActorRotation().Yaw, 0.f);
	const FVector Forward = Flat.Vector();
	const FVector Right = FRotationMatrix(Flat).GetUnitAxis(EAxis::Y);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(CampaignEnding), false, Andrew);
	auto Clear = [this, &Eye, &Params](const FVector& Want) -> FVector
	{
		FHitResult Hit;
		if (GetWorld()->LineTraceSingleByChannel(Hit, Eye, Want, ECC_Visibility, Params))
		{
			return Hit.Location + (Eye - Hit.Location).GetSafeNormal() * 30.f;
		}
		return Want;
	};
	CamFrom = Clear(Eye + Forward * 160.f + Right * 70.f - FVector(0.f, 0.f, 8.f));
	CamTo = Clear(Eye - Forward * 420.f + Right * 120.f + FVector(0.f, 0.f, 520.f));
	CamRotFrom = (Eye - CamFrom).Rotation();
	CamRotTo = (Eye - FVector(0.f, 0.f, 60.f) - CamTo).Rotation();

	// If his car is parked nearby, the shot ends wide on it instead: Andrew is gone, and the car pulls away into the rain.
	bHeroDriving = false;
	HeroCar = nullptr;
	if (AActor* Car = FindHeroCar(); Car && FVector::Dist(Car->GetActorLocation(), Eye) < 8000.f)
	{
		HeroCar = Car;
		HeroCarFrom = Car->GetActorLocation();
		HeroCarDir = Car->GetActorForwardVector().GetSafeNormal2D();
		if (HeroCarDir.IsNearlyZero())
		{
			HeroCarDir = FVector::ForwardVector;
		}
		const FVector CarRight = FVector::CrossProduct(FVector::UpVector, HeroCarDir);
		// High and to one side behind the car, looking down the road it will take.
		const FVector Look = HeroCarFrom + HeroCarDir * 900.f + FVector(0.f, 0.f, 80.f);
		FVector Want = HeroCarFrom - HeroCarDir * 1100.f + CarRight * 650.f + FVector(0.f, 0.f, 420.f);
		FHitResult Hit;
		FCollisionQueryParams CarParams(SCENE_QUERY_STAT(CampaignEndingCar), false, Car);
		if (GetWorld()->LineTraceSingleByChannel(Hit, HeroCarFrom + FVector(0.f, 0.f, 150.f), Want, ECC_Visibility, CarParams))
		{
			Want = Hit.Location + (HeroCarFrom - Hit.Location).GetSafeNormal() * 40.f;
		}
		CamTo = Want;
		CamRotTo = (Look - CamTo).Rotation();
		if (USceneComponent* Root = Car->GetRootComponent())
		{
			Root->SetMobility(EComponentMobility::Movable);
		}
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.ObjectFlags |= RF_Transient;
	if (CinematicCamera)
	{
		CinematicCamera->Destroy();
	}
	CinematicCamera = GetWorld()->SpawnActor<ACameraActor>(ACameraActor::StaticClass(), CamFrom, CamRotFrom, SpawnParams);
	if (CinematicCamera)
	{
		CinematicCamera->GetCameraComponent()->SetConstraintAspectRatio(false);
		CinematicCamera->GetCameraComponent()->SetFieldOfView(45.f);
		PC->SetViewTarget(CinematicCamera);
	}

	const float Voice = PlayVoice(TEXT("Outro"));
	EndingLength = FMath::Max(9.f, Voice + 5.f) + (HeroCar.IsValid() ? 4.f : 0.f);
	// The car starts rolling once the camera has pulled back from Andrew.
	HeroDriveStart = EndingLength * 0.55f;
	AnnounceAll(TEXT("CONTRACT CLOSED"), Mission ? Mission->Outro : FString(), AirsoftColors::Accent(), EndingLength);
	GetWorldTimerManager().SetTimer(EndTimer, FTimerDelegate::CreateWeakLambda(this, [this]() { RollCredits(); }), EndingLength, false);
}

void AAirsoftCampaignGameMode::UpdateEndingCamera(float DeltaSeconds)
{
	EndingTime += DeltaSeconds;
	if (!CinematicCamera)
	{
		return;
	}
	const float T = AirsoftCampaignLocal::Ease(EndingTime / FMath::Max(EndingLength, 0.1f));
	CinematicCamera->SetActorLocationAndRotation(FMath::Lerp(CamFrom, CamTo, T), FMath::Lerp(CamRotFrom, CamRotTo, T));
	CinematicCamera->GetCameraComponent()->SetFieldOfView(FMath::Lerp(45.f, 70.f, T));

	AActor* Car = HeroCar.Get();
	if (!Car || EndingTime < HeroDriveStart)
	{
		return;
	}
	if (!bHeroDriving)
	{
		// He's in the car now: out of the frame.
		bHeroDriving = true;
		if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
		{
			if (APawn* Andrew = PC->GetPawn())
			{
				Andrew->SetActorHiddenInGame(true);
			}
		}
	}
	// A slow, quiet pull-away that gathers speed: distance grows with the square of time (about 30 m by the fade).
	const float Drive = FMath::Clamp((EndingTime - HeroDriveStart) / FMath::Max(EndingLength - HeroDriveStart, 0.1f), 0.f, 1.f);
	Car->SetActorLocation(HeroCarFrom + HeroCarDir * (3000.f * Drive * Drive), false, nullptr, ETeleportType::TeleportPhysics);
}

void AAirsoftCampaignGameMode::RollCredits()
{
	if (CreditsWidget.IsValid() || bLeaving)
	{
		return;
	}
	bInEnding = false; // the camera holds its last frame behind the black
	GetWorldTimerManager().ClearTimer(EndTimer);
	AirsoftSubtitles::Clear();
	UGameViewportClient* Viewport = GetWorld()->GetGameViewport();
	if (!Viewport)
	{
		FinishCredits();
		return;
	}
	TSharedRef<SAirsoftCredits> Widget = SNew(SAirsoftCredits)
		.OnFinished(FSimpleDelegate::CreateWeakLambda(this, [this]()
		{
			// Leave on the next frame, not from inside the widget's own tick.
			GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this, [this]() { FinishCredits(); }));
		}));
	CreditsWidget = Widget;
	Viewport->AddViewportWidgetContent(Widget, 100);
	AirsoftAssets::Play2D(this, TEXT("PostRoundMusic"));
}

void AAirsoftCampaignGameMode::FinishCredits()
{
	if (bLeaving)
	{
		return;
	}
	bLeaving = true;
	if (CreditsWidget.IsValid())
	{
		if (UGameViewportClient* Viewport = GetWorld()->GetGameViewport())
		{
			Viewport->RemoveViewportWidgetContent(CreditsWidget.ToSharedRef());
		}
		CreditsWidget.Reset();
	}
	if (UAirsoftGameInstance* GI = Cast<UAirsoftGameInstance>(GetGameInstance()))
	{
		GI->ReturnToMainMenu(CompletionMessage());
	}
}

// ---------------------------------------------------------------------------
// Developer shortcuts
// ---------------------------------------------------------------------------

void AAirsoftCampaignGameMode::DebugKillEnemies()
{
	APlayerController* Andrew = GetWorld()->GetFirstPlayerController();
	const TArray<TObjectPtr<AAirsoftBotController>> Current = Enemies;
	for (AAirsoftBotController* Bot : Current)
	{
		if (Bot && Bot->GetPawn() && !bMissionOver)
		{
			ApplyCampaignDamage(Andrew, Bot, TEXT("M4"), 100000.f, false);
		}
	}
}

void AAirsoftCampaignGameMode::DebugCompleteMission()
{
	CompleteMission();
}

namespace AirsoftCampaignLocal
{
	// Developer shortcuts for testing the mission flow (console: ~).
	static FAutoConsoleCommandWithWorld GKillEnemies(TEXT("airsoft.campaign.killenemies"),
		TEXT("Story campaign: kills every enemy that is up right now (counts as your kills)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (AAirsoftCampaignGameMode* GM = World ? World->GetAuthGameMode<AAirsoftCampaignGameMode>() : nullptr)
			{
				GM->DebugKillEnemies();
			}
		}));
	static FAutoConsoleCommandWithWorld GComplete(TEXT("airsoft.campaign.complete"),
		TEXT("Story campaign: wins the current mission (unlocks the next one)."),
		FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
		{
			if (AAirsoftCampaignGameMode* GM = World ? World->GetAuthGameMode<AAirsoftCampaignGameMode>() : nullptr)
			{
				GM->DebugCompleteMission();
			}
		}));
}
