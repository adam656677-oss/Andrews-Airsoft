--[[
	Persists each player's profile (XP, career stats, settings, loadout) in a
	DataStore. Falls back to an in-memory profile when DataStores are
	unavailable, e.g. in Studio without "Enable Studio Access to API Services".
]]

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")

local Config = require(game:GetService("ReplicatedStorage").Shared.Config)
local Weapons = require(game:GetService("ReplicatedStorage").Shared.Weapons)

local DataService = {}

local store: DataStore? = nil
local storeOk, storeErr = pcall(function()
	store = DataStoreService:GetDataStore(Config.DataStoreName)
end)
if not storeOk then
	warn("[DataService] DataStores unavailable, progress will not save:", storeErr)
end

local profiles: { [Player]: any } = {}
local loaded: { [Player]: boolean } = {}

local function defaultSettings()
	local s = table.clone(Config.DefaultSettings)
	s.Loadouts = {} -- never share the nested table between players
	return s
end

local function defaultProfile()
	return {
		Version = 1,
		XP = 0,
		Tags = 0,
		Outs = 0,
		Wins = 0,
		Matches = 0,
		Captures = 0,
		BestStreak = 0,
		Settings = defaultSettings(),
	}
end

local function reconcile(data)
	local base = defaultProfile()
	if type(data) ~= "table" then
		return base
	end
	for k, v in base do
		if data[k] == nil then
			data[k] = v
		end
	end
	if type(data.Settings) ~= "table" then
		data.Settings = defaultSettings()
	end
	for k, v in Config.DefaultSettings do
		if data.Settings[k] == nil then
			data.Settings[k] = type(v) == "table" and table.clone(v) or v
		end
	end
	return data
end

local function key(player: Player)
	return "u_" .. player.UserId
end

function DataService.Load(player: Player)
	local data = nil
	if store then
		for attempt = 1, 3 do
			local ok, result = pcall(function()
				return (store :: DataStore):GetAsync(key(player))
			end)
			if ok then
				data = result
				loaded[player] = true
				break
			end
			warn(("[DataService] Load attempt %d failed for %s: %s"):format(attempt, player.Name, tostring(result)))
			if RunService:IsStudio() then
				-- Usually "Studio access to API services" is off; don't stall play-testing.
				break
			end
			task.wait(attempt)
		end
	end
	profiles[player] = reconcile(data)
	return profiles[player]
end

function DataService.Save(player: Player)
	local profile = profiles[player]
	-- Only write back if the initial read worked, so a failed load can never
	-- overwrite real progress with a blank profile.
	if not profile or not store or not loaded[player] then
		return
	end
	local ok, err = pcall(function()
		(store :: DataStore):UpdateAsync(key(player), function()
			return profile
		end)
	end)
	if not ok then
		warn("[DataService] Save failed for", player.Name, err)
	end
end

function DataService.Get(player: Player)
	return profiles[player]
end

function DataService.AddXP(player: Player, amount: number)
	local profile = profiles[player]
	if profile then
		profile.XP += amount
	end
end

function DataService.Increment(player: Player, field: string, amount: number?)
	local profile = profiles[player]
	if profile and type(profile[field]) == "number" then
		profile[field] += amount or 1
	end
end

-- Validates and stores client-submitted settings.
function DataService.ApplySettings(player: Player, incoming: any)
	local profile = profiles[player]
	if not profile or type(incoming) ~= "table" then
		return
	end
	local s = profile.Settings
	if type(incoming.Sensitivity) == "number" then
		s.Sensitivity = math.clamp(incoming.Sensitivity, 0.1, 3)
	end
	if type(incoming.AimSensitivity) == "number" then
		s.AimSensitivity = math.clamp(incoming.AimSensitivity, 0.1, 2)
	end
	if type(incoming.FOV) == "number" then
		s.FOV = math.clamp(math.floor(incoming.FOV), 60, 95)
	end
	if type(incoming.ToggleAim) == "boolean" then
		s.ToggleAim = incoming.ToggleAim
	end
end

-- `custom` is { [weaponId] = { Optic, Muzzle, Grip, Laser, Skin } } for any
-- weapons the player changed. Finishes above the player's rank are refused.
function DataService.SetLoadout(player: Player, primary: any, secondary: any, custom: any)
	local profile = profiles[player]
	if not profile then
		return false
	end
	if type(primary) == "string" and Weapons.IsPrimary(primary) then
		profile.Settings.Primary = primary
	end
	if type(secondary) == "string" and Weapons.IsSecondary(secondary) then
		profile.Settings.Secondary = secondary
	end
	if type(custom) == "table" then
		local rankIndex = Config.RankForXP(profile.XP)
		profile.Settings.Loadouts = type(profile.Settings.Loadouts) == "table" and profile.Settings.Loadouts or {}
		local count = 0
		for id, requested in custom do
			count += 1
			if count > 32 then
				break
			end
			if type(id) == "string" and Weapons.Get(id) then
				local clean = Weapons.CleanLoadout(id, requested)
				if Weapons.Skin(clean.Skin).Unlock > rankIndex then
					clean.Skin = "Black"
				end
				profile.Settings.Loadouts[id] = clean
			end
		end
	end
	return true
end

function DataService.Release(player: Player)
	DataService.Save(player)
	profiles[player] = nil
	loaded[player] = nil
end

-- Autosave every few minutes and on shutdown.
task.spawn(function()
	while true do
		task.wait(180)
		for _, player in Players:GetPlayers() do
			task.spawn(DataService.Save, player)
		end
	end
end)

game:BindToClose(function()
	local pending = 0
	for _, player in Players:GetPlayers() do
		pending += 1
		task.spawn(function()
			DataService.Save(player)
			pending -= 1
		end)
	end
	local start = os.clock()
	while pending > 0 and os.clock() - start < 20 do
		task.wait(0.1)
	end
end)

return DataService
