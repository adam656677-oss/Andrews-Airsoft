--[[
	Owns per-player match state: spawning, loadouts, ammo bookkeeping, spawn
	protection and the "hit, walk off" out state.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Teams = game:GetService("Teams")

local Shared = ReplicatedStorage.Shared
local Config = require(Shared.Config)
local Weapons = require(Shared.Weapons)
local GunBuilder = require(Shared.GunBuilder)
local Remotes = require(Shared.Remotes)

local DataService = require(script.Parent.DataService)
local Gear = require(script.Parent.Gear)

local PlayerService = {}

export type AmmoState = { Mag: number, Reserve: number }

export type State = {
	Side: string?, -- "Blue" | "Red" | nil (lobby)
	Alive: boolean,
	Out: boolean,
	ProtectedUntil: number,
	Grenades: number,
	Ammo: { [string]: AmmoState },
	Weapons: { [string]: any }, -- resolved stats (attachments applied) per weapon id
	Reloading: { [string]: boolean },
	LastFire: { [string]: number },
	Shots: { [number]: any },
	Life: number, -- increments every spawn so stale callbacks can bail out
	Round: { Tags: number, Outs: number, Captures: number, XP: number, Streak: number },
}

local states: { [Player]: State } = {}

local NEUTRAL_COLOR = Color3.fromRGB(255, 196, 64)

local function newRoundStats()
	return { Tags = 0, Outs = 0, Captures = 0, XP = 0, Streak = 0 }
end

function PlayerService.Get(player: Player): State?
	return states[player]
end

function PlayerService.Init(player: Player)
	states[player] = {
		Side = nil,
		Alive = false,
		Out = false,
		ProtectedUntil = 0,
		Grenades = 0,
		Ammo = {},
		Weapons = {},
		Reloading = {},
		LastFire = {},
		Shots = {},
		Life = 0,
		Round = newRoundStats(),
	}
end

function PlayerService.Remove(player: Player)
	states[player] = nil
end

function PlayerService.ResetRoundStats(player: Player)
	local s = states[player]
	if s then
		s.Round = newRoundStats()
	end
end

function PlayerService.TeamColor(side: string?): Color3
	if side and Config.Teams[side] then
		return Config.Teams[side].Color
	end
	return NEUTRAL_COLOR
end

local function pickSpawn(side: string?): CFrame
	local map = workspace:WaitForChild("Map")
	local folder = map:WaitForChild("Spawns"):FindFirstChild("Lobby")
	if side then
		local mapId = ReplicatedStorage.GameState:GetAttribute("Map") or "Field"
		local arena = map.Arenas:FindFirstChild(mapId) or map.Arenas.Field
		folder = arena.Spawns:FindFirstChild(side) or folder
	end
	local pads = folder:GetChildren()
	-- Prefer the pad furthest from other live players to avoid stacking.
	local best, bestScore = pads[1], -math.huge
	for _, pad in pads do
		local nearest = math.huge
		for _, other in Players:GetPlayers() do
			local root = other.Character and other.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
			if root then
				nearest = math.min(nearest, (root.Position - pad.Position).Magnitude)
			end
		end
		local score = nearest + math.random() * 2
		if score > bestScore then
			best, bestScore = pad, score
		end
	end
	return best.CFrame + Vector3.new(0, 3.5, 0)
end

local function giveLoadout(player: Player, state: State)
	local profile = DataService.Get(player)
	local settings = profile and profile.Settings or Config.DefaultSettings
	local primary = Weapons.IsPrimary(settings.Primary) and settings.Primary or "M4"
	local secondary = Weapons.IsSecondary(settings.Secondary) and settings.Secondary or "G17"
	local color = PlayerService.TeamColor(state.Side)

	local backpack = player:WaitForChild("Backpack")
	backpack:ClearAllChildren()
	state.Ammo = {}
	state.Reloading = {}
	state.LastFire = {}
	state.Shots = {}

	state.Weapons = {}
	local loadouts = type(settings.Loadouts) == "table" and settings.Loadouts or {}
	for _, id in { primary, secondary } do
		local loadout = Weapons.CleanLoadout(id, loadouts[id])
		local w = Weapons.Resolve(id, loadout)
		state.Weapons[id] = w
		local tool = GunBuilder.BuildTool(id, { Accent = color, Loadout = loadout })
		tool:SetAttribute("Slot", w.Slot)
		tool.Parent = backpack
		state.Ammo[id] = { Mag = w.MagSize, Reserve = w.Reserve }
	end

	state.Grenades = Weapons.Grenade.PerLife
	local grenade = GunBuilder.BuildTool("Grenade", { Accent = color })
	grenade:SetAttribute("Slot", "Grenade")
	grenade.Parent = backpack

	player:SetAttribute("Primary", primary)
	player:SetAttribute("Secondary", secondary)
	player:SetAttribute("Grenades", state.Grenades)
	for id, ammo in state.Ammo do
		Remotes.AmmoSync:FireClient(player, id, ammo.Mag, ammo.Reserve)
	end
end

-- Spawns `player` at their side's spawn (or the lobby when side is nil).
function PlayerService.Spawn(player: Player, side: string?, opts: { Frozen: boolean?, Protect: boolean? }?)
	local state = states[player]
	if not state or not player.Parent then
		return
	end
	opts = opts or {}
	state.Side = side
	state.Life += 1
	local life = state.Life
	state.Out = false
	state.Alive = false

	if side then
		player.Neutral = false
		player.Team = Teams:FindFirstChild(side) :: Team
	else
		player.Neutral = true
		player.Team = nil
	end
	player:SetAttribute("Side", side or "")
	player:SetAttribute("Out", false)

	player:LoadCharacter()
	local character = player.Character
	if not character or state.Life ~= life then
		return
	end
	local humanoid = character:WaitForChild("Humanoid") :: Humanoid
	local root = character:WaitForChild("HumanoidRootPart") :: BasePart

	character:PivotTo(pickSpawn(side))
	humanoid.WalkSpeed = Config.WalkSpeed
	humanoid.BreakJointsOnDeath = false
	humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.Viewer
	humanoid.NameDisplayDistance = 60
	humanoid.HealthDisplayType = Enum.HumanoidHealthDisplayType.AlwaysOff
	if side then
		-- Hide enemy name tags: you have to actually spot people.
		humanoid.NameOcclusion = Enum.NameOcclusion.EnemyOcclusion
	end

	Gear.Equip(character, PlayerService.TeamColor(side))
	giveLoadout(player, state)

	state.Alive = true
	if opts.Protect ~= false and side then
		state.ProtectedUntil = os.clock() + Config.SpawnProtection
		player:SetAttribute("ProtectedUntil", workspace:GetServerTimeNow() + Config.SpawnProtection)
	else
		state.ProtectedUntil = 0
		player:SetAttribute("ProtectedUntil", 0)
	end

	-- Only freeze if the briefing is still running; a slow character load must
	-- never leave someone anchored after the round has gone live.
	if opts.Frozen and ReplicatedStorage.GameState:GetAttribute("State") == "Briefing" then
		root.Anchored = true
	end

	humanoid.Died:Connect(function()
		if state.Life ~= life then
			return
		end
		-- Fell off the world or reset: count it like a hit without a shooter.
		state.Alive = false
		task.delay(Config.RespawnTime, function()
			if state.Life == life and player.Parent then
				PlayerService.Spawn(player, state.Side)
			end
		end)
	end)
end

function PlayerService.Unfreeze(player: Player)
	local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if root then
		root.Anchored = false
	end
end

function PlayerService.IsProtected(player: Player): boolean
	local state = states[player]
	return state ~= nil and os.clock() < state.ProtectedUntil
end

function PlayerService.DropProtection(player: Player)
	local state = states[player]
	if state and state.ProtectedUntil > 0 then
		state.ProtectedUntil = 0
		player:SetAttribute("ProtectedUntil", 0)
	end
end

function PlayerService.CanBeTagged(player: Player): boolean
	local state = states[player]
	return state ~= nil and state.Side ~= nil and state.Alive and not state.Out and not PlayerService.IsProtected(player)
end

local function hitMarker(character: Model)
	local head = character:FindFirstChild("Head") :: BasePart?
	if not head then
		return
	end
	-- Orange dead rag, the universal airsoft "I'm out" signal.
	local rag = Instance.new("Part")
	rag.Name = "DeadRag"
	rag.Size = Vector3.new(head.Size.X + 0.15, head.Size.Y * 0.5, head.Size.Z + 0.15)
	rag.Color = Color3.fromRGB(255, 110, 20)
	rag.Material = Enum.Material.Neon
	rag.CanCollide = false
	rag.CanQuery = false
	rag.Massless = true
	rag.CFrame = head.CFrame * CFrame.new(0, head.Size.Y * 0.35, 0)
	local weld = Instance.new("WeldConstraint")
	weld.Part0 = head
	weld.Part1 = rag
	weld.Parent = rag
	rag.Parent = character

	local billboard = Instance.new("BillboardGui")
	billboard.Name = "HitCall"
	billboard.Size = UDim2.fromOffset(110, 40)
	billboard.StudsOffset = Vector3.new(0, 3.2, 0)
	billboard.AlwaysOnTop = true
	billboard.LightInfluence = 0
	billboard.MaxDistance = 250
	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.Text = "HIT!"
	label.Font = Enum.Font.GothamBlack
	label.TextScaled = true
	label.TextColor3 = Color3.fromRGB(255, 130, 40)
	label.TextStrokeTransparency = 0.2
	label.Parent = billboard
	billboard.Parent = head
end

-- Puts a tagged player into the "out" state and schedules their respawn.
function PlayerService.MarkOut(victim: Player)
	local state = states[victim]
	if not state or state.Out then
		return
	end
	state.Out = true
	state.Alive = false
	state.Round.Outs += 1
	state.Round.Streak = 0
	victim:SetAttribute("Out", true)
	local life = state.Life

	local character = victim.Character
	if character then
		local humanoid = character:FindFirstChildOfClass("Humanoid")
		if humanoid then
			humanoid:UnequipTools()
			humanoid.WalkSpeed = 6
			humanoid.JumpPower = 0
			humanoid.JumpHeight = 0
		end
		local backpack = victim:FindFirstChild("Backpack")
		if backpack then
			backpack:ClearAllChildren()
		end
		hitMarker(character)
	end

	task.delay(Config.RespawnTime, function()
		if state.Life == life and victim.Parent then
			PlayerService.Spawn(victim, state.Side)
		end
	end)
end

function PlayerService.SendToLobby(player: Player)
	PlayerService.Spawn(player, nil, { Protect = false })
end

function PlayerService.All()
	return states
end

return PlayerService
