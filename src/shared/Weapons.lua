--[[
	Weapon, attachment and finish definitions. Units are studs and seconds.

	Velocity    muzzle velocity of a BB (studs/s). ~400 studs/s ≈ 360 fps, a typical field limit.
	Gravity     effective drop. Hop-up keeps BBs flat, so this is far lower than world gravity.
	Range       BBs are removed after travelling this far.
	Spread      cone half-angle in degrees (hip / aimed). Moving and jumping widen it.
	Recoil      camera kick in degrees: { up, sideways }.
	AimFOV      field of view while aiming down iron sights (optics override it).
	Options     which attachments each slot accepts. "None" is always allowed.
	Defaults    attachments a fresh player starts with.
]]

local Weapons = {}

local ALL_OPTICS = { "None", "RedDot", "Holo", "Scope4x" }
local ALL_MUZZLES = { "None", "Suppressor", "Compensator" }
local ALL_GRIPS = { "None", "VerticalGrip", "AngledGrip" }
local LASER = { "None", "Laser" }

Weapons.List = {
	---------------------------------------------------------------- Rifles
	M4 = {
		Name = "M4A1 Carbine",
		Kind = "AEG",
		Class = "Rifle",
		Slot = "Primary",
		Description = "The benchmark. Full auto, mid-cap mags, tight groups at any range.",
		FireModes = { "Auto", "Semi" },
		FireInterval = 0.085,
		MagSize = 30,
		Reserve = 180,
		ReloadTime = 2.1,
		EmptyReloadTime = 2.5,
		Velocity = 420,
		Gravity = 34,
		Range = 260,
		Spread = { Hip = 2.4, Aim = 0.35 },
		Recoil = { 0.55, 0.25 },
		AimFOV = 58,
		AimTime = 0.2,
		Pellets = 1,
		Sound = "FireRifle",
		Options = { Optic = ALL_OPTICS, Muzzle = ALL_MUZZLES, Grip = ALL_GRIPS, Laser = LASER },
		Defaults = { Optic = "RedDot", Grip = "VerticalGrip" },
		Stats = { Range = 0.75, Rate = 0.8, Control = 0.75, Handling = 0.7 },
	},
	AK74 = {
		Name = "AK-74 Classic",
		Kind = "AEG",
		Class = "Rifle",
		Slot = "Primary",
		Description = "Wood and steel. Hits a touch harder and kicks a touch more than the M4.",
		FireModes = { "Auto", "Semi" },
		FireInterval = 0.095,
		MagSize = 30,
		Reserve = 180,
		ReloadTime = 2.3,
		EmptyReloadTime = 2.7,
		Velocity = 435,
		Gravity = 32,
		Range = 275,
		Spread = { Hip = 2.6, Aim = 0.4 },
		Recoil = { 0.75, 0.35 },
		AimFOV = 60,
		AimTime = 0.22,
		Pellets = 1,
		Sound = "FireRifle",
		Options = { Optic = ALL_OPTICS, Muzzle = ALL_MUZZLES, Grip = ALL_GRIPS, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.8, Rate = 0.72, Control = 0.6, Handling = 0.65 },
	},
	SR25 = {
		Name = "SR-25 DMR",
		Kind = "AEG",
		Class = "DMR",
		Slot = "Primary",
		Description = "Semi-auto marksman rifle. Punishes anyone who peeks twice.",
		FireModes = { "Semi" },
		FireInterval = 0.22,
		MagSize = 20,
		Reserve = 120,
		ReloadTime = 2.4,
		EmptyReloadTime = 2.8,
		Velocity = 500,
		Gravity = 26,
		Range = 330,
		Spread = { Hip = 3.2, Aim = 0.12 },
		Recoil = { 1.3, 0.35 },
		AimFOV = 55,
		AimTime = 0.28,
		Pellets = 1,
		Sound = "FireDMR",
		SpeedMultiplier = 0.95,
		Options = { Optic = { "None", "RedDot", "Holo", "Scope4x", "ScopeLong" }, Muzzle = ALL_MUZZLES, Grip = ALL_GRIPS, Laser = LASER },
		Defaults = { Optic = "Scope4x" },
		Stats = { Range = 0.9, Rate = 0.45, Control = 0.6, Handling = 0.5 },
	},
	VSR = {
		Name = "VSR-10 Bolt Action",
		Kind = "Spring",
		Class = "Sniper",
		Slot = "Primary",
		Description = "Tuned spring sniper. One whisper-quiet shot, one tag, cycle the bolt.",
		FireModes = { "Bolt" },
		FireInterval = 1.15,
		MagSize = 12,
		Reserve = 60,
		ReloadTime = 2.6,
		EmptyReloadTime = 2.9,
		Velocity = 580,
		Gravity = 20,
		Range = 420,
		Spread = { Hip = 4.5, Aim = 0 },
		Recoil = { 2.2, 0.4 },
		AimFOV = 50,
		AimTime = 0.34,
		Pellets = 1,
		Sound = "FireSniper",
		Quiet = true,
		BuiltInSuppressor = true,
		SpeedMultiplier = 0.92,
		Options = { Optic = { "ScopeLong", "Scope4x", "RedDot" }, Laser = LASER },
		Defaults = { Optic = "ScopeLong" },
		Stats = { Range = 1, Rate = 0.1, Control = 0.5, Handling = 0.35 },
	},
	M249 = {
		Name = "M249 SAW",
		Kind = "AEG",
		Class = "LMG",
		Slot = "Primary",
		Description = "A 100-round box of suppressing fire. Slow to aim, impossible to ignore.",
		FireModes = { "Auto" },
		FireInterval = 0.075,
		MagSize = 100,
		Reserve = 300,
		ReloadTime = 4.4,
		EmptyReloadTime = 5.0,
		Velocity = 415,
		Gravity = 36,
		Range = 280,
		Spread = { Hip = 3.6, Aim = 0.75 },
		Recoil = { 0.45, 0.4 },
		AimFOV = 60,
		AimTime = 0.38,
		Pellets = 1,
		Sound = "FireLMG",
		SpeedMultiplier = 0.85,
		Options = { Optic = ALL_OPTICS, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.8, Rate = 0.85, Control = 0.45, Handling = 0.2 },
	},
	---------------------------------------------------------------- SMGs
	MP5 = {
		Name = "MP5 SD",
		Kind = "AEG",
		Class = "SMG",
		Slot = "Primary",
		Description = "Integrally suppressed CQB classic. Quiet, smooth, fast.",
		FireModes = { "Auto", "Semi" },
		FireInterval = 0.07,
		MagSize = 40,
		Reserve = 200,
		ReloadTime = 1.8,
		EmptyReloadTime = 2.2,
		Velocity = 380,
		Gravity = 42,
		Range = 180,
		Spread = { Hip = 2.0, Aim = 0.6 },
		Recoil = { 0.4, 0.3 },
		AimFOV = 62,
		AimTime = 0.14,
		Pellets = 1,
		Sound = "FireSMG",
		Quiet = true,
		BuiltInSuppressor = true,
		SpeedMultiplier = 1.06,
		Options = { Optic = { "None", "RedDot", "Holo" }, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.55, Rate = 0.95, Control = 0.8, Handling = 0.95 },
	},
	VECTOR = {
		Name = "Vector .45",
		Kind = "AEG",
		Class = "SMG",
		Slot = "Primary",
		Description = "Absurd rate of fire with almost no muzzle climb. Three-round burst on tap.",
		FireModes = { "Auto", "Burst", "Semi" },
		FireInterval = 0.055,
		MagSize = 30,
		Reserve = 210,
		ReloadTime = 1.9,
		EmptyReloadTime = 2.3,
		Velocity = 370,
		Gravity = 44,
		Range = 170,
		Spread = { Hip = 2.2, Aim = 0.7 },
		Recoil = { 0.32, 0.2 },
		AimFOV = 62,
		AimTime = 0.15,
		Pellets = 1,
		Sound = "FireSMG",
		SpeedMultiplier = 1.05,
		Options = { Optic = ALL_OPTICS, Muzzle = ALL_MUZZLES, Grip = ALL_GRIPS, Laser = LASER },
		Defaults = { Optic = "Holo" },
		Stats = { Range = 0.5, Rate = 1, Control = 0.85, Handling = 0.9 },
	},
	MP7 = {
		Name = "MP7 GBB",
		Kind = "Gas",
		Class = "SMG",
		Slot = "Primary",
		Description = "Gas blowback PDW. Snappy, compact, 40-round mags.",
		FireModes = { "Auto", "Semi" },
		FireInterval = 0.065,
		MagSize = 40,
		Reserve = 200,
		ReloadTime = 1.7,
		EmptyReloadTime = 2.0,
		Velocity = 365,
		Gravity = 44,
		Range = 165,
		Spread = { Hip = 1.9, Aim = 0.65 },
		Recoil = { 0.45, 0.3 },
		AimFOV = 62,
		AimTime = 0.13,
		Pellets = 1,
		Sound = "FireSMG",
		SpeedMultiplier = 1.07,
		Options = { Optic = ALL_OPTICS, Muzzle = ALL_MUZZLES, Grip = ALL_GRIPS, Laser = LASER },
		Defaults = { Optic = "RedDot" },
		Stats = { Range = 0.5, Rate = 0.92, Control = 0.75, Handling = 1 },
	},
	P90 = {
		Name = "P90 Bullpup",
		Kind = "AEG",
		Class = "SMG",
		Slot = "Primary",
		Description = "50-round top-loading mag in a bullpup that handles like a pistol.",
		FireModes = { "Auto", "Semi" },
		FireInterval = 0.068,
		MagSize = 50,
		Reserve = 200,
		ReloadTime = 2.2,
		EmptyReloadTime = 2.6,
		Velocity = 375,
		Gravity = 42,
		Range = 185,
		Spread = { Hip = 2.3, Aim = 0.6 },
		Recoil = { 0.38, 0.28 },
		AimFOV = 62,
		AimTime = 0.16,
		Pellets = 1,
		Sound = "FireSMG",
		SpeedMultiplier = 1.04,
		Options = { Optic = { "RedDot", "None", "Holo" }, Muzzle = ALL_MUZZLES, Laser = LASER },
		Defaults = { Optic = "RedDot" },
		Stats = { Range = 0.55, Rate = 0.9, Control = 0.8, Handling = 0.85 },
	},
	---------------------------------------------------------------- Shotgun
	M870 = {
		Name = "M870 Tri-Shot",
		Kind = "Gas",
		Class = "Shotgun",
		Slot = "Primary",
		Description = "Gas shotgun firing three BBs per shell. Owns doorways.",
		FireModes = { "Pump" },
		FireInterval = 0.7,
		MagSize = 8,
		Reserve = 48,
		ReloadTime = 2.6,
		EmptyReloadTime = 2.6,
		Velocity = 360,
		Gravity = 48,
		Range = 120,
		Spread = { Hip = 4.2, Aim = 3.0 },
		Recoil = { 2.6, 0.8 },
		AimFOV = 64,
		AimTime = 0.2,
		Pellets = 3,
		Sound = "FireShotgun",
		Options = { Optic = { "None", "RedDot" }, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.3, Rate = 0.25, Control = 0.45, Handling = 0.7 },
	},
	---------------------------------------------------------------- Pistols
	G17 = {
		Name = "G17 Gas Blowback",
		Kind = "Gas",
		Class = "Pistol",
		Slot = "Secondary",
		Description = "Reliable, accurate, forgettable until the moment you need it.",
		FireModes = { "Semi" },
		FireInterval = 0.11,
		MagSize = 20,
		Reserve = 80,
		ReloadTime = 1.5,
		EmptyReloadTime = 1.7,
		Velocity = 340,
		Gravity = 50,
		Range = 140,
		Spread = { Hip = 1.8, Aim = 0.7 },
		Recoil = { 1.1, 0.35 },
		AimFOV = 66,
		AimTime = 0.12,
		Pellets = 1,
		Sound = "FirePistol",
		SpeedMultiplier = 1.05,
		Options = { Optic = { "None", "RedDot" }, Muzzle = { "None", "Suppressor", "Compensator" }, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.4, Rate = 0.6, Control = 0.65, Handling = 1 },
	},
	G18 = {
		Name = "G18C Machine Pistol",
		Kind = "Gas",
		Class = "Pistol",
		Slot = "Secondary",
		Description = "A full-auto Glock with a 30-round stick. Empties in a heartbeat.",
		FireModes = { "Auto", "Semi" },
		FireInterval = 0.06,
		MagSize = 30,
		Reserve = 120,
		ReloadTime = 1.6,
		EmptyReloadTime = 1.8,
		Velocity = 320,
		Gravity = 52,
		Range = 115,
		Spread = { Hip = 2.6, Aim = 1.1 },
		Recoil = { 0.6, 0.45 },
		AimFOV = 66,
		AimTime = 0.12,
		Pellets = 1,
		Sound = "FirePistol",
		SpeedMultiplier = 1.05,
		Options = { Optic = { "None", "RedDot" }, Muzzle = { "None", "Compensator" }, Laser = LASER },
		Defaults = { Muzzle = "Compensator" },
		Stats = { Range = 0.3, Rate = 1, Control = 0.45, Handling = 0.95 },
	},
	M1911 = {
		Name = "1911 Gas Blowback",
		Kind = "Gas",
		Class = "Pistol",
		Slot = "Secondary",
		Description = "Steel-framed classic. Heavier, flatter shooting and dead accurate.",
		FireModes = { "Semi" },
		FireInterval = 0.13,
		MagSize = 14,
		Reserve = 70,
		ReloadTime = 1.5,
		EmptyReloadTime = 1.7,
		Velocity = 355,
		Gravity = 46,
		Range = 150,
		Spread = { Hip = 1.6, Aim = 0.5 },
		Recoil = { 1.3, 0.3 },
		AimFOV = 66,
		AimTime = 0.12,
		Pellets = 1,
		Sound = "FirePistol",
		SpeedMultiplier = 1.04,
		Options = { Optic = { "None", "RedDot" }, Muzzle = { "None", "Suppressor" }, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.45, Rate = 0.5, Control = 0.7, Handling = 0.95 },
	},
	DEAGLE = {
		Name = "Desert Eagle",
		Kind = "Gas",
		Class = "Pistol",
		Slot = "Secondary",
		Description = "Huge gas reservoir, huge velocity, huge kick. A sidearm that reaches.",
		FireModes = { "Semi" },
		FireInterval = 0.3,
		MagSize = 7,
		Reserve = 42,
		ReloadTime = 1.8,
		EmptyReloadTime = 2.0,
		Velocity = 390,
		Gravity = 38,
		Range = 180,
		Spread = { Hip = 2.2, Aim = 0.35 },
		Recoil = { 2.6, 0.5 },
		AimFOV = 64,
		AimTime = 0.16,
		Pellets = 1,
		Sound = "FireMagnum",
		SpeedMultiplier = 1.02,
		Options = { Optic = { "None", "RedDot" }, Laser = LASER },
		Defaults = {},
		Stats = { Range = 0.6, Rate = 0.25, Control = 0.35, Handling = 0.8 },
	},
}

for id, w in Weapons.List do
	w.Id = id
	w.Options = w.Options or {}
	w.Defaults = w.Defaults or {}
end

Weapons.Primaries = { "M4", "AK74", "SR25", "VSR", "M249", "MP5", "VECTOR", "MP7", "P90", "M870" }
Weapons.Secondaries = { "G17", "G18", "M1911", "DEAGLE" }
Weapons.Classes = { "Rifle", "DMR", "Sniper", "LMG", "SMG", "Shotgun", "Pistol" }

Weapons.Grenade = {
	Id = "Grenade",
	Name = "BB Burst Grenade",
	FuseTime = 2.2,
	ThrowSpeed = 85,
	Radius = 16,
	PerLife = 1,
}

---------------------------------------------------------------------------
-- Attachments
---------------------------------------------------------------------------

Weapons.Slots = { "Optic", "Muzzle", "Grip", "Laser" }

Weapons.Attachments = {
	None = { Name = "None" },

	RedDot = { Slot = "Optic", Name = "Micro Red Dot", Blurb = "Fast, clear sight picture.", AimFOV = 56, AimTime = 1.0 },
	Holo = { Slot = "Optic", Name = "Holographic Sight", Blurb = "Wide window, quick target pickup.", AimFOV = 56, AimTime = 0.95 },
	Scope4x = { Slot = "Optic", Name = "4× Combat Scope", Blurb = "Magnified, slower to bring up.", AimFOV = 30, AimTime = 1.2, Overlay = true },
	ScopeLong = { Slot = "Optic", Name = "10× Sniper Scope", Blurb = "Full scope picture for long lanes.", AimFOV = 16, AimTime = 1.3, Overlay = true },

	Suppressor = { Slot = "Muzzle", Name = "Mock Suppressor", Blurb = "Quieter shots and a hidden tracer start.", Quiet = true, RecoilMult = 0.92, VelocityMult = 0.98 },
	Compensator = { Slot = "Muzzle", Name = "Compensator", Blurb = "Kills muzzle climb.", RecoilMult = 0.75 },

	VerticalGrip = { Slot = "Grip", Name = "Vertical Grip", Blurb = "Steadier full-auto.", RecoilMult = 0.85, SpreadMult = 0.95 },
	AngledGrip = { Slot = "Grip", Name = "Angled Grip", Blurb = "Snappier aim-down-sights.", AimTimeMult = 0.82 },

	Laser = { Slot = "Laser", Name = "Laser / Light Module", Blurb = "Tighter hip fire, visible beam. [F] toggles.", HipSpreadMult = 0.72 },
}

---------------------------------------------------------------------------
-- Finishes
---------------------------------------------------------------------------

-- Unlock is the rank index (see Config.Ranks) needed to equip the finish.
Weapons.Skins = {
	{ Id = "Black", Name = "Factory Black", Primary = Color3.fromRGB(30, 31, 34), Secondary = Color3.fromRGB(40, 41, 44), Unlock = 1 },
	{ Id = "FDE", Name = "Flat Dark Earth", Primary = Color3.fromRGB(150, 126, 92), Secondary = Color3.fromRGB(38, 39, 42), Unlock = 2 },
	{ Id = "OD", Name = "Ranger Green", Primary = Color3.fromRGB(78, 86, 62), Secondary = Color3.fromRGB(40, 41, 44), Unlock = 3 },
	{ Id = "Gunmetal", Name = "Cerakote Gunmetal", Primary = Color3.fromRGB(78, 82, 90), Secondary = Color3.fromRGB(32, 33, 36), Unlock = 4 },
	{ Id = "Arctic", Name = "Arctic", Primary = Color3.fromRGB(210, 214, 218), Secondary = Color3.fromRGB(60, 62, 66), Unlock = 5 },
	{ Id = "Crimson", Name = "Crimson Lacquer", Primary = Color3.fromRGB(120, 22, 26), Secondary = Color3.fromRGB(24, 24, 26), Unlock = 6 },
	{ Id = "Carbon", Name = "Carbon Weave", Primary = Color3.fromRGB(22, 23, 26), Secondary = Color3.fromRGB(70, 72, 78), Material = "Fabric", Unlock = 7 },
	{ Id = "Gilded", Name = "Gilded", Primary = Color3.fromRGB(196, 158, 72), Secondary = Color3.fromRGB(28, 26, 24), Material = "Foil", Unlock = 8 },
}

function Weapons.Skin(id: string?)
	for _, s in Weapons.Skins do
		if s.Id == id then
			return s
		end
	end
	return Weapons.Skins[1]
end

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------

function Weapons.Get(id: string)
	return Weapons.List[id]
end

function Weapons.IsPrimary(id: string)
	local w = Weapons.List[id]
	return w ~= nil and w.Slot == "Primary"
end

function Weapons.IsSecondary(id: string)
	local w = Weapons.List[id]
	return w ~= nil and w.Slot == "Secondary"
end

-- Returns a validated attachment table for a weapon: every slot filled with
-- an allowed attachment id (or "None").
function Weapons.CleanLoadout(id: string, requested: any)
	local w = Weapons.List[id]
	local out = { Skin = "Black" }
	if not w then
		return out
	end
	requested = type(requested) == "table" and requested or {}
	for _, slot in Weapons.Slots do
		local options = w.Options[slot]
		local choice = requested[slot]
		if choice == nil then
			choice = w.Defaults[slot]
		end
		if options and type(choice) == "string" and table.find(options, choice) then
			out[slot] = choice
		elseif options and options[1] ~= "None" and not table.find(options, "None") then
			out[slot] = options[1] -- slot can't be empty (e.g. sniper scope)
		else
			out[slot] = "None"
		end
	end
	if type(requested.Skin) == "string" then
		out.Skin = Weapons.Skin(requested.Skin).Id
	end
	return out
end

-- Parses the "Optic,Muzzle,Grip,Laser" string GunBuilder stores on tools.
function Weapons.ParseLoadout(text: any)
	local out = {}
	if type(text) == "string" then
		local parts = string.split(text, ",")
		for i, slot in Weapons.Slots do
			out[slot] = parts[i]
		end
	end
	return out
end

-- Final stats for a weapon with attachments applied. Returns a new table.
function Weapons.Resolve(id: string, loadout: any)
	local base = Weapons.List[id]
	if not base then
		return nil
	end
	local clean = Weapons.CleanLoadout(id, loadout)
	local w = table.clone(base)
	w.Spread = table.clone(base.Spread)
	w.Recoil = table.clone(base.Recoil)
	w.Loadout = clean

	for _, slot in Weapons.Slots do
		local a = Weapons.Attachments[clean[slot]]
		if a and a.Slot then
			if a.AimFOV then
				w.AimFOV = math.min(w.AimFOV, a.AimFOV)
			end
			if a.AimTime then
				w.AimTime *= a.AimTime
			end
			if a.AimTimeMult then
				w.AimTime *= a.AimTimeMult
			end
			if a.RecoilMult then
				w.Recoil[1] *= a.RecoilMult
				w.Recoil[2] *= a.RecoilMult
			end
			if a.SpreadMult then
				w.Spread.Hip *= a.SpreadMult
				w.Spread.Aim *= a.SpreadMult
			end
			if a.HipSpreadMult then
				w.Spread.Hip *= a.HipSpreadMult
			end
			if a.VelocityMult then
				w.Velocity *= a.VelocityMult
			end
			if a.Quiet then
				w.Quiet = true
			end
			if a.Overlay then
				w.Scope = true
			end
		end
	end
	if w.Quiet and not base.Quiet then
		w.Sound = "FireSuppressed"
	end
	return w
end

return Weapons
