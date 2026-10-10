// Andrew's Airsoft - weapon, attachment, finish and rank tables.

#include "AirsoftWeaponData.h"

namespace AirsoftWeapons
{
	const FName SlotOptic(TEXT("Optic"));
	const FName SlotMuzzle(TEXT("Muzzle"));
	const FName SlotGrip(TEXT("Grip"));
	const FName SlotLaser(TEXT("Laser"));
	const FName SlotMag(TEXT("Mag"));
	const FName AttachOff(TEXT("Off"));

	const TArray<FName>& AttachmentSlots()
	{
		static const TArray<FName> Slots = { SlotOptic, SlotMuzzle, SlotGrip, SlotLaser, SlotMag };
		return Slots;
	}

	namespace
	{
		using FModes = TArray<EAirsoftFireMode>;

		const TArray<FName> AllOptics = { AttachOff, TEXT("RedDot"), TEXT("Holo"), TEXT("Magnifier"), TEXT("Scope4x") };
		const TArray<FName> AllMuzzles = { AttachOff, TEXT("Suppressor"), TEXT("Compensator") };
		const TArray<FName> AllGrips = { AttachOff, TEXT("VerticalGrip"), TEXT("AngledGrip"), TEXT("Bipod") };
		const TArray<FName> LaserOpts = { AttachOff, TEXT("Laser") };
		const TArray<FName> ARMags = { AttachOff, TEXT("ExtMag"), TEXT("DrumMag") };

		// Real airsoft numbers: ~110 m/s (360 fps) for AEGs, BBs slow from drag and drop
		// at the end of their flight once hop-up lift fades.
		TMap<FName, FAirsoftWeaponDef> BuildWeapons()
		{
			TMap<FName, FAirsoftWeaponDef> Out;
			auto Add = [&Out](FAirsoftWeaponDef W) { Out.Add(W.Id, MoveTemp(W)); };

			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("M4"); W.Name = TEXT("M4A1 Carbine"); W.Kind = TEXT("AEG"); W.Class = TEXT("Rifle");
				W.Description = TEXT("The benchmark. Full auto, mid-cap mags, tight groups at any range.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Semi };
				W.FireInterval = 0.066f; W.MagSize = 30; W.Reserve = 180; W.ReloadTime = 2.1f; W.EmptyReloadTime = 2.5f;
				W.MuzzleVelocity = 11000.f; W.MaxRange = 6500.f;
				W.HipSpread = 2.4f; W.AimSpread = 0.3f; W.RecoilUp = 0.45f; W.RecoilSide = 0.2f; W.AimFOV = 60.f; W.AimTime = 0.2f;
				W.Sound = TEXT("FireRifle");
				W.Options = { { SlotOptic, AllOptics }, { SlotMuzzle, AllMuzzles }, { SlotGrip, AllGrips }, { SlotLaser, LaserOpts }, { SlotMag, ARMags } };
				W.Defaults = { { SlotOptic, TEXT("RedDot") }, { SlotGrip, TEXT("VerticalGrip") } };
				W.StatRange = 0.75f; W.StatRate = 0.8f; W.StatControl = 0.75f; W.StatHandling = 0.7f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("AK74"); W.Name = TEXT("AK-74 Classic"); W.Kind = TEXT("AEG"); W.Class = TEXT("Rifle");
				W.Description = TEXT("Wood and steel. A touch more reach and a touch more kick than the M4.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Semi };
				W.FireInterval = 0.075f; W.MagSize = 30; W.Reserve = 180; W.ReloadTime = 2.3f; W.EmptyReloadTime = 2.7f;
				W.MuzzleVelocity = 11300.f; W.MaxRange = 6800.f;
				W.HipSpread = 2.6f; W.AimSpread = 0.35f; W.RecoilUp = 0.65f; W.RecoilSide = 0.3f; W.AimFOV = 62.f; W.AimTime = 0.22f;
				W.Sound = TEXT("FireRifle");
				W.Options = { { SlotOptic, AllOptics }, { SlotMuzzle, AllMuzzles }, { SlotGrip, AllGrips }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.8f; W.StatRate = 0.72f; W.StatControl = 0.6f; W.StatHandling = 0.65f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("SR25"); W.Name = TEXT("SR-25 DMR"); W.Kind = TEXT("AEG"); W.Class = TEXT("DMR");
				W.Description = TEXT("Semi-auto marksman rifle. Punishes anyone who peeks twice.");
				W.FireModes = FModes{ EAirsoftFireMode::Semi };
				W.FireInterval = 0.2f; W.MagSize = 20; W.Reserve = 120; W.ReloadTime = 2.4f; W.EmptyReloadTime = 2.8f;
				W.MuzzleVelocity = 12500.f; W.Hop = 1.05f; W.MaxRange = 8000.f;
				W.HipSpread = 3.2f; W.AimSpread = 0.1f; W.RecoilUp = 1.1f; W.RecoilSide = 0.3f; W.AimFOV = 55.f; W.AimTime = 0.28f;
				W.Sound = TEXT("FireDMR"); W.SpeedMultiplier = 0.95f;
				TArray<FName> Optics = AllOptics; Optics.Add(TEXT("ScopeLong"));
				W.Options = { { SlotOptic, Optics }, { SlotMuzzle, AllMuzzles }, { SlotGrip, AllGrips }, { SlotLaser, LaserOpts }, { SlotMag, ARMags } };
				W.Defaults = { { SlotOptic, TEXT("Scope4x") }, { SlotGrip, TEXT("Bipod") } };
				W.StatRange = 0.9f; W.StatRate = 0.45f; W.StatControl = 0.6f; W.StatHandling = 0.5f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("VSR"); W.Name = TEXT("VSR-10 Bolt Action"); W.Kind = TEXT("Spring"); W.Class = TEXT("Sniper");
				W.Description = TEXT("Tuned spring sniper. One whisper-quiet shot, one tag, cycle the bolt.");
				W.FireModes = FModes{ EAirsoftFireMode::Bolt };
				W.FireInterval = 1.15f; W.MagSize = 12; W.Reserve = 60; W.ReloadTime = 2.6f; W.EmptyReloadTime = 2.9f;
				W.MuzzleVelocity = 14500.f; W.Hop = 1.08f; W.Drag = 0.0001f; W.MaxRange = 10000.f;
				W.HipSpread = 4.5f; W.AimSpread = 0.f; W.RecoilUp = 1.8f; W.RecoilSide = 0.3f; W.AimFOV = 50.f; W.AimTime = 0.34f;
				W.Sound = TEXT("FireSniper"); W.bQuiet = true; W.bBuiltInSuppressor = true; W.SpeedMultiplier = 0.92f;
				W.Options = { { SlotOptic, { TEXT("ScopeLong"), TEXT("Scope4x"), TEXT("RedDot") } }, { SlotLaser, LaserOpts } };
				W.RequiredSlots = { SlotOptic };
				W.Defaults = { { SlotOptic, TEXT("ScopeLong") } };
				W.StatRange = 1.f; W.StatRate = 0.1f; W.StatControl = 0.5f; W.StatHandling = 0.35f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("M249"); W.Name = TEXT("M249 SAW"); W.Kind = TEXT("AEG"); W.Class = TEXT("LMG");
				W.Description = TEXT("A box of suppressing fire. Slow to aim, impossible to ignore.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto };
				W.FireInterval = 0.06f; W.MagSize = 120; W.Reserve = 360; W.ReloadTime = 4.4f; W.EmptyReloadTime = 5.0f;
				W.MuzzleVelocity = 11500.f; W.MaxRange = 7000.f;
				W.HipSpread = 3.6f; W.AimSpread = 0.7f; W.RecoilUp = 0.4f; W.RecoilSide = 0.35f; W.AimFOV = 60.f; W.AimTime = 0.38f;
				W.Sound = TEXT("FireLMG"); W.SpeedMultiplier = 0.85f;
				W.Options = { { SlotOptic, AllOptics }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.8f; W.StatRate = 0.85f; W.StatControl = 0.45f; W.StatHandling = 0.2f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("MP5"); W.Name = TEXT("MP5 SD"); W.Kind = TEXT("AEG"); W.Class = TEXT("SMG");
				W.Description = TEXT("Integrally suppressed CQB classic. Quiet, smooth, fast.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Semi };
				W.FireInterval = 0.062f; W.MagSize = 40; W.Reserve = 200; W.ReloadTime = 1.8f; W.EmptyReloadTime = 2.2f;
				W.MuzzleVelocity = 10200.f; W.MaxRange = 5000.f;
				W.HipSpread = 2.0f; W.AimSpread = 0.55f; W.RecoilUp = 0.35f; W.RecoilSide = 0.25f; W.AimFOV = 64.f; W.AimTime = 0.14f;
				W.Sound = TEXT("FireSMG"); W.bQuiet = true; W.bBuiltInSuppressor = true; W.SpeedMultiplier = 1.06f;
				W.Options = { { SlotOptic, { AttachOff, TEXT("RedDot"), TEXT("Holo") } }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.55f; W.StatRate = 0.95f; W.StatControl = 0.8f; W.StatHandling = 0.95f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("VECTOR"); W.Name = TEXT("Vector .45"); W.Kind = TEXT("AEG"); W.Class = TEXT("SMG");
				W.Description = TEXT("Absurd rate of fire with almost no climb. Three-round burst on tap.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Burst, EAirsoftFireMode::Semi };
				W.FireInterval = 0.05f; W.MagSize = 30; W.Reserve = 210; W.ReloadTime = 1.9f; W.EmptyReloadTime = 2.3f;
				W.MuzzleVelocity = 10000.f; W.MaxRange = 4800.f;
				W.HipSpread = 2.2f; W.AimSpread = 0.65f; W.RecoilUp = 0.28f; W.RecoilSide = 0.18f; W.AimFOV = 64.f; W.AimTime = 0.15f;
				W.Sound = TEXT("FireSMG"); W.SpeedMultiplier = 1.05f;
				W.Options = { { SlotOptic, AllOptics }, { SlotMuzzle, AllMuzzles }, { SlotGrip, AllGrips }, { SlotLaser, LaserOpts } };
				W.Defaults = { { SlotOptic, TEXT("Holo") } };
				W.StatRange = 0.5f; W.StatRate = 1.f; W.StatControl = 0.85f; W.StatHandling = 0.9f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("MP7"); W.Name = TEXT("MP7 GBB"); W.Kind = TEXT("Gas"); W.Class = TEXT("SMG");
				W.Description = TEXT("Gas blowback PDW. Snappy, compact, 40-round mags.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Semi };
				W.FireInterval = 0.065f; W.MagSize = 40; W.Reserve = 200; W.ReloadTime = 1.7f; W.EmptyReloadTime = 2.0f;
				W.MuzzleVelocity = 10000.f; W.MaxRange = 4800.f;
				W.HipSpread = 1.9f; W.AimSpread = 0.6f; W.RecoilUp = 0.42f; W.RecoilSide = 0.28f; W.AimFOV = 64.f; W.AimTime = 0.13f;
				W.Sound = TEXT("FireSMG"); W.SpeedMultiplier = 1.07f;
				W.Options = { { SlotOptic, AllOptics }, { SlotMuzzle, AllMuzzles }, { SlotGrip, AllGrips }, { SlotLaser, LaserOpts } };
				W.Defaults = { { SlotOptic, TEXT("RedDot") } };
				W.StatRange = 0.5f; W.StatRate = 0.92f; W.StatControl = 0.75f; W.StatHandling = 1.f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("P90"); W.Name = TEXT("P90 Bullpup"); W.Kind = TEXT("AEG"); W.Class = TEXT("SMG");
				W.Description = TEXT("A 50-round top-loading mag in a bullpup that handles like a pistol.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Semi };
				W.FireInterval = 0.06f; W.MagSize = 50; W.Reserve = 200; W.ReloadTime = 2.2f; W.EmptyReloadTime = 2.6f;
				W.MuzzleVelocity = 10300.f; W.MaxRange = 5200.f;
				W.HipSpread = 2.3f; W.AimSpread = 0.55f; W.RecoilUp = 0.34f; W.RecoilSide = 0.25f; W.AimFOV = 64.f; W.AimTime = 0.16f;
				W.Sound = TEXT("FireSMG"); W.SpeedMultiplier = 1.04f;
				W.Options = { { SlotOptic, { TEXT("RedDot"), AttachOff, TEXT("Holo") } }, { SlotMuzzle, AllMuzzles }, { SlotLaser, LaserOpts } };
				W.Defaults = { { SlotOptic, TEXT("RedDot") } };
				W.StatRange = 0.55f; W.StatRate = 0.9f; W.StatControl = 0.8f; W.StatHandling = 0.85f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("M870"); W.Name = TEXT("M870 Tri-Shot"); W.Kind = TEXT("Gas"); W.Class = TEXT("Shotgun");
				W.Description = TEXT("Gas shotgun firing three BBs per shell. Owns doorways.");
				W.FireModes = FModes{ EAirsoftFireMode::Pump };
				W.FireInterval = 0.7f; W.MagSize = 8; W.Reserve = 48; W.ReloadTime = 2.6f; W.EmptyReloadTime = 2.6f;
				W.MuzzleVelocity = 9500.f; W.MaxRange = 3500.f;
				W.HipSpread = 4.2f; W.AimSpread = 3.0f; W.RecoilUp = 2.2f; W.RecoilSide = 0.7f; W.AimFOV = 66.f; W.AimTime = 0.2f;
				W.Pellets = 3; W.Sound = TEXT("FireShotgun");
				W.Options = { { SlotOptic, { AttachOff, TEXT("RedDot") } }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.3f; W.StatRate = 0.25f; W.StatControl = 0.45f; W.StatHandling = 0.7f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("G17"); W.Name = TEXT("G17 Gas Blowback"); W.Kind = TEXT("Gas"); W.Class = TEXT("Pistol"); W.Slot = EAirsoftSlot::Secondary;
				W.Description = TEXT("Reliable, accurate, forgettable until the moment you need it.");
				W.FireModes = FModes{ EAirsoftFireMode::Semi };
				W.FireInterval = 0.11f; W.MagSize = 20; W.Reserve = 80; W.ReloadTime = 1.5f; W.EmptyReloadTime = 1.7f;
				W.MuzzleVelocity = 9000.f; W.MaxRange = 4000.f;
				W.HipSpread = 1.8f; W.AimSpread = 0.65f; W.RecoilUp = 1.0f; W.RecoilSide = 0.3f; W.AimFOV = 68.f; W.AimTime = 0.12f;
				W.Sound = TEXT("FirePistol"); W.SpeedMultiplier = 1.05f;
				W.Options = { { SlotOptic, { AttachOff, TEXT("RedDot") } }, { SlotMuzzle, AllMuzzles }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.4f; W.StatRate = 0.6f; W.StatControl = 0.65f; W.StatHandling = 1.f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("G18"); W.Name = TEXT("G18C Machine Pistol"); W.Kind = TEXT("Gas"); W.Class = TEXT("Pistol"); W.Slot = EAirsoftSlot::Secondary;
				W.Description = TEXT("A full-auto Glock with a 30-round stick. Empties in a heartbeat.");
				W.FireModes = FModes{ EAirsoftFireMode::Auto, EAirsoftFireMode::Semi };
				W.FireInterval = 0.055f; W.MagSize = 30; W.Reserve = 120; W.ReloadTime = 1.6f; W.EmptyReloadTime = 1.8f;
				W.MuzzleVelocity = 8800.f; W.MaxRange = 3500.f;
				W.HipSpread = 2.6f; W.AimSpread = 1.0f; W.RecoilUp = 0.55f; W.RecoilSide = 0.4f; W.AimFOV = 68.f; W.AimTime = 0.12f;
				W.Sound = TEXT("FirePistol"); W.SpeedMultiplier = 1.05f;
				W.Options = { { SlotOptic, { AttachOff, TEXT("RedDot") } }, { SlotMuzzle, { AttachOff, TEXT("Compensator") } }, { SlotLaser, LaserOpts } };
				W.Defaults = { { SlotMuzzle, TEXT("Compensator") } };
				W.StatRange = 0.3f; W.StatRate = 1.f; W.StatControl = 0.45f; W.StatHandling = 0.95f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("M1911"); W.Name = TEXT("1911 Gas Blowback"); W.Kind = TEXT("Gas"); W.Class = TEXT("Pistol"); W.Slot = EAirsoftSlot::Secondary;
				W.Description = TEXT("Steel-framed classic. Heavier, flatter shooting and dead accurate.");
				W.FireModes = FModes{ EAirsoftFireMode::Semi };
				W.FireInterval = 0.13f; W.MagSize = 14; W.Reserve = 70; W.ReloadTime = 1.5f; W.EmptyReloadTime = 1.7f;
				W.MuzzleVelocity = 9400.f; W.MaxRange = 4300.f;
				W.HipSpread = 1.6f; W.AimSpread = 0.45f; W.RecoilUp = 1.2f; W.RecoilSide = 0.25f; W.AimFOV = 68.f; W.AimTime = 0.12f;
				W.Sound = TEXT("FirePistol"); W.SpeedMultiplier = 1.04f;
				W.Options = { { SlotOptic, { AttachOff, TEXT("RedDot") } }, { SlotMuzzle, { AttachOff, TEXT("Suppressor") } }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.45f; W.StatRate = 0.5f; W.StatControl = 0.7f; W.StatHandling = 0.95f;
				Add(W);
			}
			{
				FAirsoftWeaponDef W;
				W.Id = TEXT("DEAGLE"); W.Name = TEXT("Desert Eagle"); W.Kind = TEXT("Gas"); W.Class = TEXT("Pistol"); W.Slot = EAirsoftSlot::Secondary;
				W.Description = TEXT("Huge gas reservoir, huge velocity, huge kick. A sidearm that reaches.");
				W.FireModes = FModes{ EAirsoftFireMode::Semi };
				W.FireInterval = 0.3f; W.MagSize = 7; W.Reserve = 42; W.ReloadTime = 1.8f; W.EmptyReloadTime = 2.0f;
				W.MuzzleVelocity = 10500.f; W.MaxRange = 5000.f;
				W.HipSpread = 2.2f; W.AimSpread = 0.3f; W.RecoilUp = 2.4f; W.RecoilSide = 0.45f; W.AimFOV = 66.f; W.AimTime = 0.16f;
				W.Sound = TEXT("FireMagnum"); W.SpeedMultiplier = 1.02f;
				W.Options = { { SlotOptic, { AttachOff, TEXT("RedDot") } }, { SlotLaser, LaserOpts } };
				W.StatRange = 0.6f; W.StatRate = 0.25f; W.StatControl = 0.35f; W.StatHandling = 0.8f;
				Add(W);
			}
			return Out;
		}

		TMap<FName, FAirsoftAttachmentDef> BuildAttachments()
		{
			TMap<FName, FAirsoftAttachmentDef> Out;
			auto Add = [&Out](FName Id, FName Slot, const TCHAR* Name, const TCHAR* Blurb) -> FAirsoftAttachmentDef&
			{
				FAirsoftAttachmentDef& A = Out.Add(Id);
				A.Id = Id;
				A.Slot = Slot;
				A.Name = Name;
				A.Blurb = Blurb;
				return A;
			};
			Add(TEXT("RedDot"), SlotOptic, TEXT("Micro Red Dot"), TEXT("Fast, clear sight picture.")).AimFOV = 58.f;
			{
				FAirsoftAttachmentDef& A = Add(TEXT("Holo"), SlotOptic, TEXT("Holographic Sight"), TEXT("Wide window, quick target pickup."));
				A.AimFOV = 58.f; A.AimTimeMult = 0.95f;
			}
			{
				FAirsoftAttachmentDef& A = Add(TEXT("Magnifier"), SlotOptic, TEXT("Holo + 3x Magnifier"), TEXT("Holographic sight with a flip-in 3x magnifier."));
				A.AimFOV = 36.f; A.AimTimeMult = 1.12f;
			}
			{
				FAirsoftAttachmentDef& A = Add(TEXT("Scope4x"), SlotOptic, TEXT("4x Combat Scope"), TEXT("Magnified prism sight, slower to bring up."));
				A.AimFOV = 28.f; A.AimTimeMult = 1.2f;
			}
			{
				FAirsoftAttachmentDef& A = Add(TEXT("ScopeLong"), SlotOptic, TEXT("10x Sniper Scope"), TEXT("Full scope picture for the long lanes."));
				A.AimFOV = 14.f; A.AimTimeMult = 1.3f; A.bOverlay = true;
			}
			{
				FAirsoftAttachmentDef& A = Add(TEXT("Suppressor"), SlotMuzzle, TEXT("Mock Suppressor"), TEXT("Quieter report; your position stays hidden."));
				A.bQuiet = true; A.RecoilMult = 0.92f; A.VelocityMult = 0.98f;
			}
			Add(TEXT("Compensator"), SlotMuzzle, TEXT("Compensator"), TEXT("Kills muzzle climb.")).RecoilMult = 0.75f;
			{
				FAirsoftAttachmentDef& A = Add(TEXT("VerticalGrip"), SlotGrip, TEXT("Vertical Grip"), TEXT("Steadier full-auto."));
				A.RecoilMult = 0.85f; A.SpreadMult = 0.95f;
			}
			Add(TEXT("AngledGrip"), SlotGrip, TEXT("Angled Grip"), TEXT("Snappier aim-down-sights.")).AimTimeMult = 0.82f;
			{
				FAirsoftAttachmentDef& A = Add(TEXT("Bipod"), SlotGrip, TEXT("Folding Bipod"), TEXT("Rock-steady when aimed, heavy in the hands."));
				A.RecoilMult = 0.8f; A.AimTimeMult = 1.08f;
			}
			Add(TEXT("Laser"), SlotLaser, TEXT("Laser / Light Module"), TEXT("Tighter hip fire and a visible beam. [F] toggles.")).HipSpreadMult = 0.72f;
			{
				FAirsoftAttachmentDef& A = Add(TEXT("ExtMag"), SlotMag, TEXT("Extended Mag"), TEXT("45 rounds, slightly slower reloads."));
				A.MagSizeOverride = 45; A.ReloadTimeMult = 1.1f;
			}
			{
				FAirsoftAttachmentDef& A = Add(TEXT("DrumMag"), SlotMag, TEXT("Drum Mag"), TEXT("100 rounds. Heavy, slow to swap."));
				A.MagSizeOverride = 100; A.ReloadTimeMult = 1.4f; A.AimTimeMult = 1.15f;
			}
			return Out;
		}

		TArray<FAirsoftSkinDef> BuildSkins()
		{
			auto Skin = [](const TCHAR* Id, const TCHAR* Name, FLinearColor P, FLinearColor S, float Metal, float Rough, int32 Unlock)
			{
				FAirsoftSkinDef D;
				D.Id = Id; D.Name = Name; D.Primary = P; D.Secondary = S; D.Metallic = Metal; D.Roughness = Rough; D.UnlockRank = Unlock;
				return D;
			};
			return {
				Skin(TEXT("Black"), TEXT("Factory Black"), FLinearColor(0.025f, 0.026f, 0.03f), FLinearColor(0.03f, 0.031f, 0.034f), 0.f, 0.55f, 1),
				Skin(TEXT("FDE"), TEXT("Flat Dark Earth"), FLinearColor(0.32f, 0.24f, 0.15f), FLinearColor(0.03f, 0.031f, 0.034f), 0.f, 0.6f, 2),
				Skin(TEXT("OD"), TEXT("Ranger Green"), FLinearColor(0.09f, 0.11f, 0.06f), FLinearColor(0.03f, 0.031f, 0.034f), 0.f, 0.6f, 3),
				Skin(TEXT("Gunmetal"), TEXT("Cerakote Gunmetal"), FLinearColor(0.09f, 0.1f, 0.12f), FLinearColor(0.025f, 0.026f, 0.03f), 0.35f, 0.45f, 4),
				Skin(TEXT("Arctic"), TEXT("Arctic"), FLinearColor(0.7f, 0.72f, 0.74f), FLinearColor(0.06f, 0.065f, 0.07f), 0.f, 0.5f, 5),
				Skin(TEXT("Crimson"), TEXT("Crimson Lacquer"), FLinearColor(0.25f, 0.01f, 0.015f), FLinearColor(0.02f, 0.02f, 0.022f), 0.1f, 0.25f, 6),
				Skin(TEXT("Carbon"), TEXT("Carbon Weave"), FLinearColor(0.015f, 0.016f, 0.018f), FLinearColor(0.07f, 0.075f, 0.08f), 0.2f, 0.3f, 7),
				Skin(TEXT("Gilded"), TEXT("Gilded"), FLinearColor(0.85f, 0.6f, 0.22f), FLinearColor(0.02f, 0.018f, 0.016f), 1.f, 0.28f, 8),
			};
		}
	}

	const FAirsoftWeaponDef* Find(FName Id)
	{
		static const TMap<FName, FAirsoftWeaponDef> Weapons = BuildWeapons();
		return Weapons.Find(Id);
	}

	const TArray<FName>& Primaries()
	{
		static const TArray<FName> List = { TEXT("M4"), TEXT("AK74"), TEXT("SR25"), TEXT("VSR"), TEXT("M249"), TEXT("MP5"), TEXT("VECTOR"), TEXT("MP7"), TEXT("P90"), TEXT("M870") };
		return List;
	}

	const TArray<FName>& Secondaries()
	{
		static const TArray<FName> List = { TEXT("G17"), TEXT("G18"), TEXT("M1911"), TEXT("DEAGLE") };
		return List;
	}

	const FAirsoftAttachmentDef* FindAttachment(FName Id)
	{
		static const TMap<FName, FAirsoftAttachmentDef> Attachments = BuildAttachments();
		return Attachments.Find(Id);
	}

	const TArray<FAirsoftSkinDef>& Skins()
	{
		static const TArray<FAirsoftSkinDef> List = BuildSkins();
		return List;
	}

	const FAirsoftSkinDef& FindSkin(FName Id)
	{
		for (const FAirsoftSkinDef& S : Skins())
		{
			if (S.Id == Id)
			{
				return S;
			}
		}
		return Skins()[0];
	}

	const TArray<FAirsoftRankDef>& Ranks()
	{
		static const TArray<FAirsoftRankDef> List = {
			{ TEXT("Recruit"), 0 }, { TEXT("Private"), 1000 }, { TEXT("Specialist"), 3000 }, { TEXT("Corporal"), 6000 },
			{ TEXT("Sergeant"), 10000 }, { TEXT("Staff Sergeant"), 16000 }, { TEXT("Lieutenant"), 25000 },
			{ TEXT("Captain"), 38000 }, { TEXT("Major"), 55000 }, { TEXT("Field Marshal"), 80000 },
		};
		return List;
	}

	FAirsoftCustomization Clean(const FAirsoftCustomization& In)
	{
		FAirsoftCustomization Out;
		Out.WeaponId = In.WeaponId;
		Out.Skin = FindSkin(In.Skin).Id;
		const FAirsoftWeaponDef* W = Find(In.WeaponId);
		if (!W)
		{
			return Out;
		}

		// NAME_None means "not chosen yet" (use the weapon's default); AttachOff is an explicit "nothing fitted".
		auto Pick = [W](FName Slot, FName Requested) -> FName
		{
			const TArray<FName>* Options = W->Options.Find(Slot);
			if (!Options || Options->Num() == 0)
			{
				return AttachOff;
			}
			if (!Requested.IsNone() && Options->Contains(Requested))
			{
				return Requested;
			}
			const FName* Default = W->Defaults.Find(Slot);
			if (Default && Options->Contains(*Default))
			{
				return *Default;
			}
			return Options->Contains(AttachOff) ? AttachOff : (*Options)[0];
		};

		Out.Optic = Pick(SlotOptic, In.Optic);
		Out.Muzzle = Pick(SlotMuzzle, In.Muzzle);
		Out.Grip = Pick(SlotGrip, In.Grip);
		Out.Laser = Pick(SlotLaser, In.Laser);
		Out.Mag = Pick(SlotMag, In.Mag);
		return Out;
	}

	FAirsoftWeaponDef Resolve(const FAirsoftCustomization& In)
	{
		const FAirsoftWeaponDef* Base = Find(In.WeaponId);
		if (!Base)
		{
			return FAirsoftWeaponDef();
		}
		FAirsoftWeaponDef W = *Base;
		const FAirsoftCustomization C = Clean(In);
		for (FName AttachmentId : { C.Optic, C.Muzzle, C.Grip, C.Laser, C.Mag })
		{
			const FAirsoftAttachmentDef* A = FindAttachment(AttachmentId);
			if (!A)
			{
				continue;
			}
			if (A->AimFOV > 0.f)
			{
				W.AimFOV = FMath::Min(W.AimFOV, A->AimFOV);
			}
			W.AimTime *= A->AimTimeMult;
			W.RecoilUp *= A->RecoilMult;
			W.RecoilSide *= A->RecoilMult;
			W.HipSpread *= A->SpreadMult * A->HipSpreadMult;
			W.AimSpread *= A->SpreadMult;
			W.MuzzleVelocity *= A->VelocityMult;
			W.ReloadTime *= A->ReloadTimeMult;
			W.EmptyReloadTime *= A->ReloadTimeMult;
			if (A->MagSizeOverride > 0)
			{
				W.Reserve = FMath::Max(W.Reserve, A->MagSizeOverride * 3);
				W.MagSize = A->MagSizeOverride;
			}
			if (A->bQuiet && !Base->bQuiet)
			{
				W.bQuiet = true;
				W.Sound = TEXT("FireSuppressed");
			}
			if (A->bOverlay)
			{
				W.bScopeOverlay = true;
			}
		}
		return W;
	}

	int32 RankIndexForXP(int32 XP)
	{
		int32 Index = 1;
		const TArray<FAirsoftRankDef>& List = Ranks();
		for (int32 i = 0; i < List.Num(); ++i)
		{
			if (XP >= List[i].XP)
			{
				Index = i + 1;
			}
		}
		return Index;
	}

	FString FireModeName(EAirsoftFireMode Mode)
	{
		switch (Mode)
		{
		case EAirsoftFireMode::Auto: return TEXT("AUTO");
		case EAirsoftFireMode::Semi: return TEXT("SEMI");
		case EAirsoftFireMode::Burst: return TEXT("BURST");
		case EAirsoftFireMode::Bolt: return TEXT("BOLT");
		case EAirsoftFireMode::Pump: return TEXT("PUMP");
		}
		return TEXT("");
	}

	FAirsoftLoadout DefaultLoadout()
	{
		FAirsoftLoadout L;
		FAirsoftCustomization P;
		P.WeaponId = TEXT("M4");
		P.Optic = TEXT("RedDot");
		P.Grip = TEXT("VerticalGrip");
		L.Primary = Clean(P);
		FAirsoftCustomization S;
		S.WeaponId = TEXT("G17");
		L.Secondary = Clean(S);
		return L;
	}
}
