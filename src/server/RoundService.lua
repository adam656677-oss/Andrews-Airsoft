--[[
	Match flow: Waiting → Intermission (mode vote) → Briefing → Live → PostRound.

	Public match state is mirrored onto ReplicatedStorage.GameState attributes
	so every client HUD can read it without extra remotes.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local Shared = ReplicatedStorage.Shared
local Config = require(Shared.Config)
local Remotes = require(Shared.Remotes)

local PlayerService = require(script.Parent.PlayerService)
local MapBuilder = require(script.Parent.MapBuilder)
local DataService = require(script.Parent.DataService)

local RoundService = {}

local gameState = Instance.new("Folder")
gameState.Name = "GameState"
gameState.Parent = ReplicatedStorage

local match = {
	State = "Waiting",
	Mode = "TDM",
	Map = "Field",
	MapVotes = {} :: { [Player]: string },
	Scores = { Blue = 0, Red = 0 },
	Votes = {} :: { [Player]: string },
	Ending = false,
}

local function set(name: string, value: any)
	gameState:SetAttribute(name, value)
end

local function setState(state: string, duration: number?)
	match.State = state
	set("State", state)
	set("EndsAt", duration and (workspace:GetServerTimeNow() + duration) or 0)
end

local function minPlayers()
	if RunService:IsStudio() then
		return 1
	end
	return Config.MinPlayers
end

local function announceAll(title: string, subtitle: string?, color: Color3?, duration: number?)
	Remotes.Announce:FireAllClients(title, subtitle or "", color or Color3.new(1, 1, 1), duration or 3)
end

local function awardXP(player: Player, amount: number, reason: string)
	DataService.AddXP(player, amount)
	local s = PlayerService.Get(player)
	if s then
		s.Round.XP += amount
	end
	local profile = DataService.Get(player)
	if profile then
		player:SetAttribute("XP", profile.XP)
		local index = Config.RankForXP(profile.XP)
		player:SetAttribute("RankIndex", index)
	end
	Remotes.XPGained:FireClient(player, amount, reason)
end

local function teamCounts()
	local counts = { Blue = 0, Red = 0 }
	for player, s in PlayerService.All() do
		if s.Side and player.Parent then
			counts[s.Side] += 1
		end
	end
	return counts
end

local function smallerTeam(): string
	local counts = teamCounts()
	if counts.Blue == counts.Red then
		return match.Scores.Blue <= match.Scores.Red and "Blue" or "Red"
	end
	return counts.Blue < counts.Red and "Blue" or "Red"
end

local function updateLeaderstats(player: Player)
	local s = PlayerService.Get(player)
	local stats = player:FindFirstChild("leaderstats")
	if not s or not stats then
		return
	end
	(stats:FindFirstChild("Tags") :: IntValue).Value = s.Round.Tags;
	(stats:FindFirstChild("Outs") :: IntValue).Value = s.Round.Outs
end

local function addScore(side: string, amount: number)
	match.Scores[side] += amount
	set(side .. "Score", match.Scores[side])
end

-- Objectives -------------------------------------------------------------------

local function objectiveModels(mapId: string?): { Model }
	local arena = MapBuilder.Arena(mapId or match.Map)
	local folder = arena and arena:FindFirstChild("Objectives")
	return folder and folder:GetChildren() or {}
end

local NEUTRAL = Color3.fromRGB(210, 210, 210)

local function paintObjective(model: Model)
	local owner = model:GetAttribute("Owner")
	local progress = model:GetAttribute("Progress") or 0
	local color = NEUTRAL
	if owner ~= "" and Config.Teams[owner] then
		color = Config.Teams[owner].Color
	elseif progress < 0 then
		color = NEUTRAL:Lerp(Config.Teams.Blue.Color, -progress)
	elseif progress > 0 then
		color = NEUTRAL:Lerp(Config.Teams.Red.Color, progress)
	end
	local flag = model:FindFirstChild("Flag") :: BasePart
	local zone = model:FindFirstChild("Zone") :: BasePart
	flag.Color = color
	zone.Color = color
	local glow = flag:FindFirstChild("Glow") :: PointLight
	glow.Color = color
	local marker = model:FindFirstChild("Marker") :: BillboardGui
	local letter = marker:FindFirstChild("Letter") :: TextLabel
	letter.TextColor3 = color;
	(letter:FindFirstChildOfClass("UIStroke") :: UIStroke).Color = color
end

local function resetObjectives(enabled: boolean)
	for _, mapId in Config.MapOrder do
		for _, model in objectiveModels(mapId) do
			local zone = model:FindFirstChild("Zone") :: BasePart
			zone.Transparency = 1
			local marker = model:FindFirstChild("Marker") :: BillboardGui
			marker.Enabled = false
			model:SetAttribute("Active", false)
		end
	end
	for _, model in objectiveModels() do
		model:SetAttribute("Owner", "")
		model:SetAttribute("Progress", 0)
		model:SetAttribute("Capturing", "")
		paintObjective(model)
		local zone = model:FindFirstChild("Zone") :: BasePart
		zone.Transparency = enabled and 0.82 or 1
		local marker = model:FindFirstChild("Marker") :: BillboardGui
		marker.Enabled = enabled
		model:SetAttribute("Active", enabled)
	end
end

local function updateObjectives(dt: number)
	local cfg = Config.Modes.DOM
	for _, model in objectiveModels() do
		local zone = model:FindFirstChild("Zone") :: BasePart
		local center = zone.Position
		local present = { Blue = {}, Red = {} }
		for player, s in PlayerService.All() do
			if s.Side and s.Alive and not s.Out then
				local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
				if root then
					local offset = root.Position - center
					local radius = model:GetAttribute("Radius") or cfg.CaptureRadius
					local height = model:GetAttribute("Height") or 14
					if Vector3.new(offset.X, 0, offset.Z).Magnitude <= radius and math.abs(offset.Y) < height then
						table.insert(present[s.Side], player)
					end
				end
			end
		end

		local blue, red = #present.Blue, #present.Red
		local owner = model:GetAttribute("Owner")
		local progress = model:GetAttribute("Progress")
		local capturing = ""
		if blue > 0 and red == 0 and owner ~= "Blue" then
			capturing = "Blue"
		elseif red > 0 and blue == 0 and owner ~= "Red" then
			capturing = "Red"
		elseif blue > 0 and red > 0 then
			capturing = "Contested"
		end
		model:SetAttribute("Capturing", capturing)

		if capturing == "Blue" or capturing == "Red" then
			local count = capturing == "Blue" and blue or red
			local dir = capturing == "Blue" and -1 or 1
			local rate = dt / cfg.CaptureTime * math.min(1 + (count - 1) * 0.5, 2.5)
			local before = progress
			progress = math.clamp(progress + dir * rate, -1, 1)

			-- Crossing the midpoint neutralises the previous owner.
			if owner ~= "" and owner ~= capturing and math.sign(before) ~= math.sign(progress) then
				model:SetAttribute("Owner", "")
				owner = ""
			end
			if math.abs(progress) >= 1 and owner ~= capturing then
				model:SetAttribute("Owner", capturing)
				announceAll(Config.Teams[capturing].Name .. " took " .. model.Name, "", Config.Teams[capturing].Color, 2.5)
				for _, p in present[capturing] do
					local s = PlayerService.Get(p)
					if s then
						s.Round.Captures += 1
					end
					DataService.Increment(p, "Captures")
					awardXP(p, Config.XP.Capture, "Captured " .. model.Name)
				end
			end
			model:SetAttribute("Progress", progress)
			paintObjective(model)
		end
	end
end

local function scoreObjectives()
	local cfg = Config.Modes.DOM
	for _, model in objectiveModels() do
		local owner = model:GetAttribute("Owner")
		if owner == "Blue" or owner == "Red" then
			addScore(owner, cfg.PointsPerTick)
		end
	end
end

-- Hooks --------------------------------------------------------------------------

function RoundService.IsLive(): boolean
	return match.State == "Live"
end

-- The most recent tag of the round, replayed in slow motion afterwards.
local lastTag: any = nil

local function recordTag(shooter: Player, victim: Player, weaponId: string)
	local head = shooter.Character and shooter.Character:FindFirstChild("Head") :: BasePart?
	local root = victim.Character and victim.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if head and root then
		lastTag = {
			Shooter = shooter.DisplayName,
			Victim = victim.DisplayName,
			ShooterSide = shooter:GetAttribute("Side"),
			VictimSide = victim:GetAttribute("Side"),
			From = head.Position,
			To = root.Position,
			Weapon = weaponId,
		}
	end
end

function RoundService.OnTag(shooter: Player?, victim: Player, weaponId: string)
	DataService.Increment(victim, "Outs")
	updateLeaderstats(victim)
	if not shooter then
		return
	end
	recordTag(shooter, victim, weaponId)
	DataService.Increment(shooter, "Tags")
	local s = PlayerService.Get(shooter)
	local profile = DataService.Get(shooter)
	if s and profile and s.Round.Streak > profile.BestStreak then
		profile.BestStreak = s.Round.Streak
	end
	awardXP(shooter, Config.XP.Tag + (weaponId == "Grenade" and Config.XP.GrenadeBonus or 0), "Tagged " .. victim.DisplayName)
	updateLeaderstats(shooter)

	if match.Mode == "TDM" and s and s.Side then
		addScore(s.Side, 1)
	end
end

function RoundService.OnPlayerAdded(player: Player)
	if match.State == "Live" or match.State == "Briefing" then
		local side = smallerTeam()
		PlayerService.Spawn(player, side, { Frozen = match.State == "Briefing" })
		announceAll(player.DisplayName .. " joined " .. Config.Teams[side].Name, "", Config.Teams[side].Color, 2)
	else
		PlayerService.SendToLobby(player)
	end
end

function RoundService.OnPlayerRemoving(player: Player)
	match.Votes[player] = nil
end

function RoundService.VoteMap(player: Player, mapId: any)
	if match.State ~= "Intermission" or type(mapId) ~= "string" or not Config.Maps[mapId] then
		return
	end
	match.MapVotes[player] = mapId
	local tally = {}
	for _, id in Config.MapOrder do
		tally[id] = 0
	end
	for _, v in match.MapVotes do
		tally[v] += 1
	end
	for id, n in tally do
		set("MapVotes_" .. id, n)
	end
end

function RoundService.Vote(player: Player, modeId: any)
	if match.State ~= "Intermission" or type(modeId) ~= "string" or not Config.Modes[modeId] then
		return
	end
	match.Votes[player] = modeId
	local tally = {}
	for _, id in Config.ModeOrder do
		tally[id] = 0
	end
	for _, v in match.Votes do
		tally[v] += 1
	end
	for id, n in tally do
		set("Votes_" .. id, n)
	end
end

-- Phases -------------------------------------------------------------------------

local function waitFor(seconds: number, abort: (() -> boolean)?)
	local t = os.clock() + seconds
	while os.clock() < t do
		if abort and abort() then
			return false
		end
		task.wait(0.25)
	end
	return true
end

local function enoughPlayers()
	return #Players:GetPlayers() >= minPlayers()
end

local function phaseWaiting()
	setState("Waiting")
	set("Message", ("Waiting for players (%d needed)"):format(minPlayers()))
	while not enoughPlayers() do
		task.wait(1)
	end
end

local function phaseIntermission()
	match.Votes = {}
	match.MapVotes = {}
	for _, id in Config.ModeOrder do
		set("Votes_" .. id, 0)
	end
	for _, id in Config.MapOrder do
		set("MapVotes_" .. id, 0)
	end
	setState("Intermission", Config.IntermissionTime)
	set("Message", "Vote for the next map and mode")
	resetObjectives(false)
	return waitFor(Config.IntermissionTime, function()
		return not enoughPlayers()
	end)
end

local function chooseMode(): string
	local tally = {}
	for _, v in match.Votes do
		tally[v] = (tally[v] or 0) + 1
	end
	local best, bestCount = nil, -1
	for _, id in Config.ModeOrder do
		local n = tally[id] or 0
		if n > bestCount or (n == bestCount and math.random() < 0.5) then
			best, bestCount = id, n
		end
	end
	-- Nobody voted: rotate so both modes get played.
	if bestCount == 0 then
		return match.Mode == "TDM" and "DOM" or "TDM"
	end
	return best :: string
end

local function assignTeams()
	local list = Players:GetPlayers()
	-- Shuffle, then sort by XP so skill-ish is spread across teams.
	for i = #list, 2, -1 do
		local j = math.random(i)
		list[i], list[j] = list[j], list[i]
	end
	table.sort(list, function(a, b)
		return (a:GetAttribute("XP") or 0) > (b:GetAttribute("XP") or 0)
	end)
	local sides = {}
	-- Snake draft: B R R B B R R ...
	for i, player in list do
		local k = (i - 1) % 4
		sides[player] = (k == 0 or k == 3) and "Blue" or "Red"
	end
	return sides
end

local function chooseMap(): string
	local tally = {}
	for _, v in match.MapVotes do
		tally[v] = (tally[v] or 0) + 1
	end
	local best, bestCount = nil, 0
	for _, id in Config.MapOrder do
		local n = tally[id] or 0
		if n > bestCount or (n == bestCount and n > 0 and math.random() < 0.5) then
			best, bestCount = id, n
		end
	end
	if not best then
		-- Nobody voted: alternate maps so both get played.
		local i = table.find(Config.MapOrder, match.Map) or 0
		return Config.MapOrder[i % #Config.MapOrder + 1]
	end
	return best
end

local function phaseBriefing()
	lastTag = nil
	match.Map = chooseMap()
	set("Map", match.Map)
	MapBuilder.ApplyLighting(match.Map)
	match.Mode = chooseMode()
	local mode = Config.Modes[match.Mode]
	match.Scores = { Blue = 0, Red = 0 }
	match.Ending = false
	set("Mode", match.Mode)
	set("ScoreLimit", mode.ScoreLimit)
	set("BlueScore", 0)
	set("RedScore", 0)
	set("Message", mode.Blurb)
	resetObjectives(match.Mode == "DOM")
	setState("Briefing", Config.BriefingTime)

	local sides = assignTeams()
	for player, side in sides do
		PlayerService.ResetRoundStats(player)
		updateLeaderstats(player)
		task.spawn(PlayerService.Spawn, player, side, { Frozen = true })
	end
	announceAll(mode.Name .. "  •  " .. Config.Maps[match.Map].Name, mode.Blurb, Color3.fromRGB(255, 196, 64), Config.BriefingTime - 1)
	waitFor(Config.BriefingTime)
end

local function phaseLive()
	setState("Live", Config.RoundTime)
	set("Message", "")
	for _, player in Players:GetPlayers() do
		PlayerService.Unfreeze(player)
	end
	announceAll("GAME ON", "Goggles on. Call your hits.", Color3.fromRGB(120, 255, 140), 2)

	local mode = Config.Modes[match.Mode]
	local endsAt = os.clock() + Config.RoundTime
	local tickAcc = 0
	local last = os.clock()
	while os.clock() < endsAt do
		task.wait(0.2)
		local now = os.clock()
		local dt = now - last
		last = now
		if match.Mode == "DOM" then
			updateObjectives(dt)
			tickAcc += dt
			if tickAcc >= mode.TickInterval then
				tickAcc -= mode.TickInterval
				scoreObjectives()
			end
		end
		if match.Scores.Blue >= mode.ScoreLimit or match.Scores.Red >= mode.ScoreLimit then
			break
		end
		if #Players:GetPlayers() == 0 then
			break
		end
	end
end

local function phasePostRound()
	local winner = "Draw"
	if match.Scores.Blue > match.Scores.Red then
		winner = "Blue"
	elseif match.Scores.Red > match.Scores.Blue then
		winner = "Red"
	end
	setState("PostRound", Config.PostRoundTime)
	set("Winner", winner)

	-- MVP: most tags, captures break ties.
	local mvp, mvpScore = nil, -1
	local rows = {}
	for player, s in PlayerService.All() do
		if s.Side and player.Parent then
			local score = s.Round.Tags * 2 + s.Round.Captures
			if score > mvpScore then
				mvp, mvpScore = player, score
			end
			DataService.Increment(player, "Matches")
			awardXP(player, Config.XP.Played, "Match complete")
			if s.Side == winner then
				DataService.Increment(player, "Wins")
				awardXP(player, Config.XP.Win, "Victory")
			end
			table.insert(rows, {
				Name = player.DisplayName,
				UserId = player.UserId,
				Side = s.Side,
				Tags = s.Round.Tags,
				Outs = s.Round.Outs,
				Captures = s.Round.Captures,
				XP = s.Round.XP,
			})
		end
	end

	Remotes.RoundSummary:FireAllClients({
		Winner = winner,
		Mode = match.Mode,
		Blue = match.Scores.Blue,
		Red = match.Scores.Red,
		MVP = mvp and mvp.DisplayName or nil,
		FinalTag = lastTag,
		Rows = rows,
	})
	for _, player in Players:GetPlayers() do
		task.spawn(DataService.Save, player)
		local profile = DataService.Get(player)
		if profile then
			Remotes.Profile:FireClient(player, profile)
		end
	end

	-- Freeze everyone where they stand so nobody farms tags after the whistle.
	for _, player in Players:GetPlayers() do
		local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		if root then
			root.Anchored = true
		end
	end
	waitFor(Config.PostRoundTime)
	for _, player in Players:GetPlayers() do
		task.spawn(PlayerService.SendToLobby, player)
	end
	set("Winner", "")
end

function RoundService.Run()
	set("Mode", match.Mode)
	set("Map", match.Map)
	set("BlueScore", 0)
	set("RedScore", 0)
	set("ScoreLimit", Config.Modes[match.Mode].ScoreLimit)
	while true do
		phaseWaiting()
		if phaseIntermission() then
			phaseBriefing()
			phaseLive()
			phasePostRound()
		end
	end
end

RoundService.UpdateLeaderstats = updateLeaderstats

return RoundService
