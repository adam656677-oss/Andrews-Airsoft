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
Config.PostRoundTime = 12

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
-- These use audio bundled with every Roblox client so they always load.
-- Swap in your own uploaded rbxassetid:// sounds for a more premium mix.
Config.Sounds = {
	FireAEG = "rbxasset://sounds/paintball.wav",
	FireGas = "rbxasset://sounds/paintball.wav",
	FireSpring = "rbxasset://sounds/paintball.wav",
	DryFire = "rbxasset://sounds/clickfast.wav",
	Reload = "rbxasset://sounds/clickfast.wav",
	HitMarker = "rbxasset://sounds/electronicpingshort.wav",
	Tagged = "rbxasset://sounds/electronicpingshort.wav",
	Ding = "rbxasset://sounds/electronicpingshort.wav",
	UIClick = "rbxasset://sounds/clickfast.wav",
	Grenade = "rbxasset://sounds/paintball.wav",
}

-- Data -----------------------------------------------------------------------
Config.DataStoreName = "AndrewsAirsoft_Profiles_v1"

Config.DefaultSettings = {
	Sensitivity = 1,
	AimSensitivity = 0.6,
	FOV = 75,
	ToggleAim = false,
	Primary = "M4",
	Secondary = "G17",
}

return Config
