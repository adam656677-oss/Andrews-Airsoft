--[[
	Andrew's Airsoft — server entry point.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Teams = game:GetService("Teams")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared.Config)
local Remotes = require(Shared.Remotes)
local GunBuilder = require(Shared.GunBuilder)
local Weapons = require(Shared.Weapons)

local MapBuilder = require(script.Parent.MapBuilder)
local DataService = require(script.Parent.DataService)
local PlayerService = require(script.Parent.PlayerService)
local CombatService = require(script.Parent.CombatService)
local RoundService = require(script.Parent.RoundService)

-- World ----------------------------------------------------------------------------
local map = MapBuilder.Build()

-- Display guns on the lobby racks.
local racks = map.StagingArea:FindFirstChild("Racks")
for i, id in Weapons.Primaries do
	local rack = racks and racks:FindFirstChild("Rack" .. (i - 1)) :: BasePart?
	if rack then
		local model = GunBuilder.Build(id, Color3.fromRGB(255, 196, 64))
		for _, part in model:GetDescendants() do
			if part:IsA("BasePart") then
				part.Anchored = true
			end
		end
		model:PivotTo(CFrame.new(rack.Position + Vector3.new(0, 1.3, 0)) * CFrame.Angles(0, math.rad(90), math.rad(90)))
		model.Parent = map.StagingArea
	end
end

-- Teams ------------------------------------------------------------------------------
for key, team in Config.Teams do
	local t = Teams:FindFirstChild(key) :: Team?
	if not t then
		t = Instance.new("Team")
		t.Name = key
		t.Parent = Teams
	end
	(t :: Team).TeamColor = team.BrickColor;
	(t :: Team).AutoAssignable = false
end

-- Systems ------------------------------------------------------------------------------
CombatService.Init({
	OnTag = RoundService.OnTag,
	IsLive = RoundService.IsLive,
})

Remotes.VoteMode.OnServerEvent:Connect(RoundService.Vote)

Remotes.SetLoadout.OnServerEvent:Connect(function(player, primary, secondary)
	DataService.SetLoadout(player, primary, secondary)
	local profile = DataService.Get(player)
	if profile then
		Remotes.Profile:FireClient(player, profile)
	end
	-- In the staging area, swap guns immediately so they can try them on the range.
	local state = PlayerService.Get(player)
	if state and state.Side == nil and state.Alive then
		PlayerService.SendToLobby(player)
	end
end)

Remotes.SaveSettings.OnServerEvent:Connect(function(player, settings)
	DataService.ApplySettings(player, settings)
end)

Remotes.GetProfile.OnServerInvoke = function(player)
	return DataService.Get(player)
end

-- Players ---------------------------------------------------------------------------------
local function onPlayerAdded(player: Player)
	PlayerService.Init(player)

	local stats = Instance.new("Folder")
	stats.Name = "leaderstats"
	local tags = Instance.new("IntValue")
	tags.Name = "Tags"
	tags.Parent = stats
	local outs = Instance.new("IntValue")
	outs.Name = "Outs"
	outs.Parent = stats
	stats.Parent = player

	local profile = DataService.Load(player)
	if not player.Parent then
		return
	end
	player:SetAttribute("XP", profile.XP)
	player:SetAttribute("RankIndex", (Config.RankForXP(profile.XP)))
	Remotes.Profile:FireClient(player, profile)

	RoundService.OnPlayerAdded(player)
end

Players.PlayerAdded:Connect(onPlayerAdded)
for _, player in Players:GetPlayers() do
	task.spawn(onPlayerAdded, player)
end

Players.PlayerRemoving:Connect(function(player)
	RoundService.OnPlayerRemoving(player)
	DataService.Release(player)
	PlayerService.Remove(player)
end)

RoundService.Run()
