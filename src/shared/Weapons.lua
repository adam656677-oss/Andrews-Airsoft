--[[
	Weapon definitions. Units are studs and seconds.

	Velocity    muzzle velocity of a BB (studs/s). ~400 studs/s ≈ 360 fps, a typical field limit.
	Gravity     effective drop. Hop-up keeps BBs flat, so this is far lower than world gravity.
	Range       BBs are removed after travelling this far.
	Spread      cone half-angle in degrees (hip / aimed). Moving and jumping widen it.
	Recoil      camera kick in degrees: { up, sideways }.
	AimFOV      field of view while aiming.
]]

local Weapons = {}

Weapons.List = {
	M4 = {
		Id = "M4",
		Name = "M4A1 Carbine",
		Kind = "AEG",
		Slot = "Primary",
		Description = "Reliable all-rounder. Full auto, mid-cap mags, tight groups.",
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
		AimFOV = 55,
		AimTime = 0.2,
		Pellets = 1,
		Sound = "FireAEG",
		Stats = { Range = 0.75, Rate = 0.8, Control = 0.75, Handling = 0.7 },
	},
	MP5 = {
		Id = "MP5",
		Name = "MP5 SD",
		Kind = "AEG",
		Slot = "Primary",
		Description = "Compact CQB gun. Fast handling and a high rate of fire.",
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
		AimFOV = 60,
		AimTime = 0.14,
		Pellets = 1,
		Sound = "FireAEG",
		SpeedMultiplier = 1.06,
		Stats = { Range = 0.55, Rate = 0.95, Control = 0.8, Handling = 0.95 },
	},
	SR25 = {
		Id = "SR25",
		Name = "SR-25 DMR",
		Kind = "AEG",
		Slot = "Primary",
		Description = "Semi-auto marksman rifle with a 4x optic. Punishes peekers.",
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
		AimFOV = 34,
		AimTime = 0.28,
		Pellets = 1,
		Sound = "FireAEG",
		Scope = true,
		SpeedMultiplier = 0.95,
		Stats = { Range = 0.9, Rate = 0.45, Control = 0.6, Handling = 0.5 },
	},
	VSR = {
		Id = "VSR",
		Name = "VSR-10 Bolt Action",
		Kind = "Spring",
		Slot = "Primary",
		Description = "Upgraded spring sniper. One quiet shot, one tag. Bolt between shots.",
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
		AimFOV = 18,
		AimTime = 0.34,
		Pellets = 1,
		Sound = "FireSpring",
		Scope = true,
		Quiet = true,
		SpeedMultiplier = 0.92,
		Stats = { Range = 1, Rate = 0.1, Control = 0.5, Handling = 0.35 },
	},
	M870 = {
		Id = "M870",
		Name = "M870 Tri-Shot",
		Kind = "Gas",
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
		AimFOV = 62,
		AimTime = 0.2,
		Pellets = 3,
		Sound = "FireGas",
		Stats = { Range = 0.3, Rate = 0.25, Control = 0.45, Handling = 0.7 },
	},
	G17 = {
		Id = "G17",
		Name = "G17 Gas Blowback",
		Kind = "Gas",
		Slot = "Secondary",
		Description = "Snappy sidearm for when the primary runs dry.",
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
		AimFOV = 64,
		AimTime = 0.12,
		Pellets = 1,
		Sound = "FireGas",
		SpeedMultiplier = 1.05,
		Stats = { Range = 0.4, Rate = 0.6, Control = 0.65, Handling = 1 },
	},
}

Weapons.Primaries = { "M4", "MP5", "SR25", "VSR", "M870" }
Weapons.Secondaries = { "G17" }

Weapons.Grenade = {
	Id = "Grenade",
	Name = "BB Burst Grenade",
	FuseTime = 2.2,
	ThrowSpeed = 85,
	Radius = 16,
	PerLife = 1,
}

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

return Weapons
