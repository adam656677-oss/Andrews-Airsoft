--[[
	Andrew's Airsoft — global tuning.
	Everything gameplay-related that a designer might want to tweak lives here.
]]

local Config = {}

Config.GameName = "Andrew's Airsoft"
Config.FieldName = "Ironwood Yard"

-- Round flow ---------------------------------------------------------------
Config.MinPlayers = 2 -- Studio solo testing drops this to 1 automatically
Config.IntermissionTime = 20
Config.BriefingTime = 6
Config.RoundTime = 300
Config.PostRoundTime = 15

-- Rules ----------------------------------------------------------------------
Config.RespawnTime = 4
Config.SpawnProtection = 3
Config.FriendlyFire = false

Config.Modes = {
	TDM = {
		Id = "TDM",
		Name = "Team Deathmatch",
		Blurb = "Tag the other team. First to the limit wins.",
		ScoreLimit = 30,
	},
	DOM = {
		Id = "DOM",
		Name = "Domination",
		Blurb = "Hold A, B and C. Every held point scores over time.",
		ScoreLimit = 200,
		CaptureTime = 6, -- seconds for one player to flip a neutral point
		CaptureRadius = 14,
		TickInterval = 2, -- seconds between score ticks
		PointsPerTick = 1, -- per held flag
	},
}
Config.ModeOrder = { "TDM", "DOM" }

Config.Maps = {
	Field = {
		Id = "Field",
		Name = "Ironwood Yard",
		Blurb = "Outdoor field at dusk. Container yard, CQB house, woodline.",
	},
	Club = {
		Id = "Club",
		Name = "Velvet Club",
		Blurb = "Night CQB in the rain. Neon, glass, a bar and a VIP balcony.",
	},
}
Config.MapOrder = { "Field", "Club" }

Config.Teams = {
	Blue = {
		Name = "Blue Squad",
		Color = Color3.fromRGB(64, 140, 255),
		BrickColor = BrickColor.new("Bright blue"),
	},
	Red = {
		Name = "Red Squad",
		Color = Color3.fromRGB(255, 72, 72),
		BrickColor = BrickColor.new("Bright red"),
	},
}

-- Movement -------------------------------------------------------------------
Config.WalkSpeed = 14
Config.SprintSpeed = 21
Config.AimSpeed = 9
Config.CrouchSpeed = 7
Config.DefaultFOV = 75

-- Progression ----------------------------------------------------------------
Config.XP = {
	Tag = 100,
	Capture = 150,
	CaptureTick = 5,
	Win = 400,
	Played = 100,
	GrenadeBonus = 50,
}

-- XP needed to *reach* each rank.
Config.Ranks = {
	{ Name = "Recruit", XP = 0 },
	{ Name = "Private", XP = 1000 },
	{ Name = "Specialist", XP = 3000 },
	{ Name = "Corporal", XP = 6000 },
	{ Name = "Sergeant", XP = 10000 },
	{ Name = "Staff Sergeant", XP = 16000 },
	{ Name = "Lieutenant", XP = 25000 },
	{ Name = "Captain", XP = 38000 },
	{ Name = "Major", XP = 55000 },
	{ Name = "Field Marshal", XP = 80000 },
}

function Config.RankForXP(xp: number)
	local index = 1
	for i, rank in ipairs(Config.Ranks) do
		if xp >= rank.XP then
			index = i
		end
	end
	local nextRank = Config.Ranks[index + 1]
	return index, Config.Ranks[index], nextRank
end

-- Sounds -----------------------------------------------------------------------
-- Fallbacks use audio bundled with every Roblox client so they always load.
-- Upload the generated sounds in assets/audio/ and paste their IDs into
-- src/shared/AssetIds.lua; any ID filled in there wins over the fallback.
local AssetIds = require(script.Parent.AssetIds)

local FALLBACK_SOUNDS = {
	FireRifle = "rbxasset://sounds/paintball.wav",
	FireSMG = "rbxasset://sounds/paintball.wav",
	FireDMR = "rbxasset://sounds/paintball.wav",
	FireSniper = "rbxasset://sounds/paintball.wav",
	FireShotgun = "rbxasset://sounds/paintball.wav",
	FirePistol = "rbxasset://sounds/paintball.wav",
	FireLMG = "rbxasset://sounds/paintball.wav",
	FireMagnum = "rbxasset://sounds/paintball.wav",
	FireSuppressed = "rbxasset://sounds/paintball.wav",
	DryFire = "rbxasset://sounds/clickfast.wav",
	Reload = "rbxasset://sounds/clickfast.wav",
	MagOut = "rbxasset://sounds/clickfast.wav",
	MagIn = "rbxasset://sounds/clickfast.wav",
	BoltCycle = "rbxasset://sounds/clickfast.wav",
	HitMarker = "rbxasset://sounds/electronicpingshort.wav",
	Tagged = "rbxasset://sounds/electronicpingshort.wav",
	Ding = "rbxasset://sounds/electronicpingshort.wav",
	UIClick = "rbxasset://sounds/clickfast.wav",
	Grenade = "rbxasset://sounds/paintball.wav",
	Impact = "rbxasset://sounds/clickfast.wav",
}

Config.Sounds = {}
for key, fallback in FALLBACK_SOUNDS do
	local uploaded = AssetIds.Sounds[key]
	Config.Sounds[key] = (uploaded and uploaded ~= 0) and ("rbxassetid://" .. tostring(uploaded)) or fallback
end
-- Without uploaded audio every gun shares one sample, so pitch it per class.
Config.FallbackPitch = {
	FireRifle = 1,
	FireSMG = 1.18,
	FireDMR = 0.86,
	FireSniper = 0.72,
	FireShotgun = 0.62,
	FirePistol = 1.28,
	FireLMG = 0.94,
	FireMagnum = 0.58,
	FireSuppressed = 1.45,
}

-- True when real uploaded gun audio is in use (fallbacks get pitch-shifted per class).
Config.UsingUploadedSounds = AssetIds.Sounds.FireRifle ~= nil and AssetIds.Sounds.FireRifle ~= 0

-- Data -----------------------------------------------------------------------
Config.DataStoreName = "AndrewsAirsoft_Profiles_v1"

Config.DefaultSettings = {
	Sensitivity = 1,
	AimSensitivity = 0.6,
	FOV = 75,
	ToggleAim = false,
	Primary = "M4",
	Secondary = "G17",
	Loadouts = {}, -- [weaponId] = { Optic, Muzzle, Grip, Laser, Skin }
}

return Config
