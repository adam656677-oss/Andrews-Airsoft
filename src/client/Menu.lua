--[[
	Menus: loadout picker, settings, scoreboard (hold Tab), mode vote during
	intermission and the end-of-round summary.
]]

local ContextActionService = game:GetService("ContextActionService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared.Config)
local Weapons = require(Shared.Weapons)
local Remotes = require(Shared.Remotes)

local State = require(script.Parent.State)
local UI = require(script.Parent.UI)
local Effects = require(script.Parent.Effects)

local player = Players.LocalPlayer
local gameState = ReplicatedStorage:WaitForChild("GameState")

local Menu = {}

local gui: ScreenGui
local pages: { [string]: Frame } = {}
local openPage: string? = nil
local modal: TextButton

local function click()
	Effects.Play2D("UIClick", 0.4, 1)
end

local function setMenuOpen(open: boolean)
	State.MenuOpen = open
	-- A visible modal button frees the mouse even in locked first person.
	modal.Visible = open
	UserInputService.MouseIconEnabled = open
end

function Menu.Close()
	if openPage then
		pages[openPage].Visible = false
		openPage = nil
	end
	setMenuOpen(false)
end

function Menu.Open(name: string)
	if openPage == name then
		Menu.Close()
		return
	end
	if openPage then
		pages[openPage].Visible = false
	end
	openPage = name
	pages[name].Visible = true
	setMenuOpen(true)
end

local function window(name: string, title: string, size: Vector2): Frame
	local frame = UI.Panel({
		Name = name,
		AnchorPoint = Vector2.new(0.5, 0.5),
		Position = UDim2.fromScale(0.5, 0.5),
		Size = UDim2.fromOffset(size.X, size.Y),
		BackgroundTransparency = 0.08,
		Visible = false,
		ZIndex = 10,
		Parent = gui,
	})
	UI.new("UISizeConstraint", { MaxSize = Vector2.new(size.X, size.Y), Parent = frame })
	UI.Label({ Text = title, Font = UI.FontHeavy, TextSize = 22, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(20, 14), Size = UDim2.new(1, -80, 0, 28), ZIndex = 11, Parent = frame })
	local close = UI.Button({ Text = "✕", Size = UDim2.fromOffset(32, 32), AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -12, 0, 12), ZIndex = 11, Parent = frame })
	close.Activated:Connect(function()
		click()
		Menu.Close()
	end)
	UI.new("Frame", { Position = UDim2.fromOffset(20, 52), Size = UDim2.new(1, -40, 0, 1), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.85, BorderSizePixel = 0, ZIndex = 11, Parent = frame })
	pages[name] = frame
	return frame
end

---------------------------------------------------------------------------
-- Loadout
---------------------------------------------------------------------------

local function statBar(parent: Instance, label: string, value: number, y: number)
	UI.Label({ Text = label:upper(), TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(12, y), Size = UDim2.fromOffset(70, 14), ZIndex = 12, Parent = parent })
	local bg = UI.new("Frame", { Position = UDim2.fromOffset(82, y + 5), Size = UDim2.new(1, -96, 0, 4), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.85, BorderSizePixel = 0, ZIndex = 12, Parent = parent })
	UI.new("Frame", { Size = UDim2.fromScale(value, 1), BackgroundColor3 = UI.Colors.Accent, BorderSizePixel = 0, ZIndex = 12, Parent = bg })
end

local function buildLoadout()
	local frame = window("Loadout", "LOADOUT", Vector2.new(820, 470))
	local list = UI.new("ScrollingFrame", {
		Position = UDim2.fromOffset(20, 66),
		Size = UDim2.new(1, -40, 1, -130),
		BackgroundTransparency = 1,
		BorderSizePixel = 0,
		ScrollBarThickness = 4,
		AutomaticCanvasSize = Enum.AutomaticSize.X,
		CanvasSize = UDim2.new(),
		ScrollingDirection = Enum.ScrollingDirection.X,
		ZIndex = 11,
		Parent = frame,
	})
	UI.new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 10), Parent = list })

	local cards = {}
	local selected = State.Settings.Primary or "M4"
	local function refresh()
		for id, card in cards do
			local stroke = card:FindFirstChildOfClass("UIStroke") :: UIStroke
			stroke.Color = id == selected and UI.Colors.Accent or Color3.new(1, 1, 1)
			stroke.Transparency = id == selected and 0 or 0.85
			stroke.Thickness = id == selected and 2 or 1
		end
	end

	for _, id in Weapons.Primaries do
		local w = Weapons.Get(id)
		local card = UI.Button({ Text = "", Size = UDim2.fromOffset(180, 300), BackgroundColor3 = UI.Colors.PanelLight, ZIndex = 11, Parent = list })
		UI.Label({ Text = w.Name:upper(), Font = UI.FontHeavy, TextSize = 16, TextXAlignment = Enum.TextXAlignment.Left, TextWrapped = true, Position = UDim2.fromOffset(12, 12), Size = UDim2.new(1, -24, 0, 40), ZIndex = 12, Parent = card })
		UI.Label({ Text = w.Kind:upper() .. "  •  " .. table.concat(w.FireModes, " / "):upper(), TextSize = 11, TextColor3 = UI.Colors.Accent, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(12, 52), Size = UDim2.new(1, -24, 0, 14), ZIndex = 12, Parent = card })
		UI.Label({ Text = w.Description, Font = UI.FontLight, TextSize = 12, TextColor3 = UI.Colors.Muted, TextWrapped = true, TextXAlignment = Enum.TextXAlignment.Left, TextYAlignment = Enum.TextYAlignment.Top, Position = UDim2.fromOffset(12, 74), Size = UDim2.new(1, -24, 0, 70), ZIndex = 12, Parent = card })
		local y = 160
		for _, stat in { "Range", "Rate", "Control", "Handling" } do
			statBar(card, stat, w.Stats[stat], y)
			y += 22
		end
		UI.Label({ Text = ("%d RND  •  %d FPS"):format(w.MagSize, math.floor(w.Velocity * 0.85)), TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(12, 260), Size = UDim2.new(1, -24, 0, 14), ZIndex = 12, Parent = card })
		card.Activated:Connect(function()
			click()
			selected = id
			refresh()
		end)
		cards[id] = card
	end
	refresh()

	UI.Label({ Text = "SIDEARM: G17 GAS BLOWBACK   •   UTILITY: 1× BB BURST GRENADE", TextSize = 12, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, AnchorPoint = Vector2.new(0, 1), Position = UDim2.new(0, 20, 1, -24), Size = UDim2.fromOffset(500, 16), ZIndex = 11, Parent = frame })
	local confirm = UI.Button({ Text = "CONFIRM", Font = UI.FontHeavy, BackgroundColor3 = UI.Colors.Accent, TextColor3 = Color3.fromRGB(20, 20, 20), AnchorPoint = Vector2.new(1, 1), Position = UDim2.new(1, -20, 1, -16), Size = UDim2.fromOffset(150, 38), ZIndex = 11, Parent = frame })
	confirm.Activated:Connect(function()
		click()
		State.Settings.Primary = selected
		Remotes.SetLoadout:FireServer(selected, "G17")
		local inMatch = (player:GetAttribute("Side") or "") ~= ""
		Menu.Close()
		if inMatch then
			-- Loadout changes take effect on the next respawn.
			local hud = require(script.Parent.HUD)
			hud.Announce("Loadout saved", "Applies on your next respawn", UI.Colors.Accent, 2)
		end
	end)
	State.On("Profile", function()
		selected = State.Settings.Primary or selected
		refresh()
	end)
end

---------------------------------------------------------------------------
-- Settings
---------------------------------------------------------------------------

local function slider(parent: Instance, y: number, label: string, min: number, max: number, step: number, get: () -> number, set: (number) -> ())
	UI.Label({ Text = label:upper(), TextSize = 13, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(20, y), Size = UDim2.fromOffset(200, 18), ZIndex = 11, Parent = parent })
	local valueLabel = UI.Label({ Text = "", TextSize = 13, TextColor3 = UI.Colors.Accent, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -20, 0, y), Size = UDim2.fromOffset(80, 18), ZIndex = 11, Parent = parent })
	local track = UI.new("TextButton", { Text = "", AutoButtonColor = false, Position = UDim2.fromOffset(20, y + 24), Size = UDim2.new(1, -40, 0, 8), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.85, BorderSizePixel = 0, ZIndex = 11, Parent = parent }, { UI.Corner(4) })
	local fill = UI.new("Frame", { Size = UDim2.fromScale(0, 1), BackgroundColor3 = UI.Colors.Accent, BorderSizePixel = 0, ZIndex = 12, Parent = track }, { UI.Corner(4) })
	local knob = UI.new("Frame", { AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0, 0.5), Size = UDim2.fromOffset(16, 16), BackgroundColor3 = UI.Colors.Text, BorderSizePixel = 0, ZIndex = 13, Parent = track }, { UI.Corner(8) })

	local function render()
		local v = get()
		local a = (v - min) / (max - min)
		fill.Size = UDim2.fromScale(a, 1)
		knob.Position = UDim2.fromScale(a, 0.5)
		valueLabel.Text = step >= 1 and tostring(math.floor(v)) or ("%.2f"):format(v)
	end

	local dragging = false
	local function apply(x: number)
		local a = math.clamp((x - track.AbsolutePosition.X) / track.AbsoluteSize.X, 0, 1)
		local v = min + (max - min) * a
		v = math.floor(v / step + 0.5) * step
		set(v)
		render()
	end
	track.InputBegan:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			dragging = true
			apply(input.Position.X)
		end
	end)
	UserInputService.InputChanged:Connect(function(input)
		if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement or input.UserInputType == Enum.UserInputType.Touch) then
			apply(input.Position.X)
		end
	end)
	UserInputService.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			dragging = false
		end
	end)
	render()
	return render
end

local function buildSettings()
	local frame = window("Settings", "SETTINGS", Vector2.new(460, 380))
	local renders = {}
	table.insert(renders, slider(frame, 70, "Look sensitivity", 0.1, 3, 0.05, function()
		return State.Settings.Sensitivity
	end, function(v)
		State.Settings.Sensitivity = v
	end))
	table.insert(renders, slider(frame, 130, "Aim sensitivity", 0.1, 2, 0.05, function()
		return State.Settings.AimSensitivity
	end, function(v)
		State.Settings.AimSensitivity = v
	end))
	table.insert(renders, slider(frame, 190, "Field of view", 60, 95, 1, function()
		return State.Settings.FOV
	end, function(v)
		State.Settings.FOV = v
	end))

	UI.Label({ Text = "AIM MODE", TextSize = 13, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(20, 250), Size = UDim2.fromOffset(200, 18), ZIndex = 11, Parent = frame })
	local toggle = UI.Button({ Text = "", AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -20, 0, 246), Size = UDim2.fromOffset(110, 28), ZIndex = 11, Parent = frame })
	local function renderToggle()
		toggle.Text = State.Settings.ToggleAim and "TOGGLE" or "HOLD"
	end
	toggle.Activated:Connect(function()
		click()
		State.Settings.ToggleAim = not State.Settings.ToggleAim
		renderToggle()
	end)
	renderToggle()

	local save = UI.Button({ Text = "SAVE", Font = UI.FontHeavy, BackgroundColor3 = UI.Colors.Accent, TextColor3 = Color3.fromRGB(20, 20, 20), AnchorPoint = Vector2.new(1, 1), Position = UDim2.new(1, -20, 1, -16), Size = UDim2.fromOffset(130, 36), ZIndex = 11, Parent = frame })
	save.Activated:Connect(function()
		click()
		Remotes.SaveSettings:FireServer(State.Settings)
		Menu.Close()
	end)

	State.On("Profile", function()
		for _, r in renders do
			r()
		end
		renderToggle()
	end)
end

---------------------------------------------------------------------------
-- Scoreboard
---------------------------------------------------------------------------

local scoreboard: Frame
local function buildScoreboard()
	scoreboard = UI.Panel({ Name = "Scoreboard", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromOffset(760, 420), BackgroundTransparency = 0.1, Visible = false, ZIndex = 20, Parent = gui })
	for i, side in { "Blue", "Red" } do
		local col = UI.new("Frame", { Name = side, Position = UDim2.new((i - 1) * 0.5, 10, 0, 10), Size = UDim2.new(0.5, -20, 1, -20), BackgroundTransparency = 1, ZIndex = 21, Parent = scoreboard })
		UI.Label({ Name = "Header", Text = Config.Teams[side].Name:upper(), Font = UI.FontHeavy, TextSize = 18, TextColor3 = Config.Teams[side].Color, TextXAlignment = Enum.TextXAlignment.Left, Size = UDim2.new(1, 0, 0, 26), ZIndex = 21, Parent = col })
		UI.Label({ Text = "RANK                TAGS   OUTS", TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Right, Size = UDim2.new(1, -8, 0, 26), ZIndex = 21, Parent = col })
		local rows = UI.new("Frame", { Name = "Rows", Position = UDim2.fromOffset(0, 30), Size = UDim2.new(1, 0, 1, -30), BackgroundTransparency = 1, ZIndex = 21, Parent = col })
		UI.new("UIListLayout", { Padding = UDim.new(0, 3), SortOrder = Enum.SortOrder.LayoutOrder, Parent = rows })
	end
end

local function refreshScoreboard()
	for _, side in { "Blue", "Red" } do
		local rows = scoreboard:FindFirstChild(side):FindFirstChild("Rows")
		for _, child in rows:GetChildren() do
			if child:IsA("Frame") then
				child:Destroy()
			end
		end
	end
	local list = Players:GetPlayers()
	table.sort(list, function(a, b)
		local ta = a:FindFirstChild("leaderstats") and a.leaderstats.Tags.Value or 0
		local tb = b:FindFirstChild("leaderstats") and b.leaderstats.Tags.Value or 0
		return ta > tb
	end)
	for order, p in list do
		local side = p:GetAttribute("Side")
		if side == nil or side == "" then
			side = "Blue"
		end
		local rows = scoreboard:FindFirstChild(side) and scoreboard[side]:FindFirstChild("Rows")
		if rows then
			local _, rank = Config.RankForXP(p:GetAttribute("XP") or 0)
			local stats = p:FindFirstChild("leaderstats")
			local row = UI.new("Frame", { LayoutOrder = order, Size = UDim2.new(1, 0, 0, 28), BackgroundColor3 = p == player and Color3.fromRGB(60, 52, 30) or UI.Colors.PanelLight, BackgroundTransparency = 0.2, BorderSizePixel = 0, ZIndex = 21, Parent = rows }, { UI.Corner(4) })
			UI.Label({ Text = (p:GetAttribute("Out") and "✕ " or "") .. p.DisplayName, TextSize = 14, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(10, 0), Size = UDim2.new(0.5, 0, 1, 0), TextTruncate = Enum.TextTruncate.AtEnd, TextColor3 = p:GetAttribute("Out") and UI.Colors.Muted or UI.Colors.Text, ZIndex = 22, Parent = row })
			UI.Label({ Text = rank.Name, TextSize = 11, TextColor3 = UI.Colors.Accent, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.new(0.48, 0, 0, 0), Size = UDim2.new(0.25, 0, 1, 0), ZIndex = 22, Parent = row })
			UI.Label({ Text = ("%d      %d"):format(stats and stats.Tags.Value or 0, stats and stats.Outs.Value or 0), TextSize = 14, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -14, 0, 0), Size = UDim2.new(0.25, 0, 1, 0), ZIndex = 22, Parent = row })
		end
	end
end

---------------------------------------------------------------------------
-- Mode vote (intermission)
---------------------------------------------------------------------------

local votePanel: Frame
local voteButtons: { [string]: TextButton } = {}
local myVote: string? = nil

local function buildVote()
	votePanel = UI.Panel({ Name = "Vote", AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 1, -130), Size = UDim2.fromOffset(460, 110), Visible = false, Parent = gui })
	local voteTitle = UserInputService.KeyboardEnabled and "VOTE NEXT MODE  [V]" or "VOTE NEXT MODE"
	UI.Label({ Text = voteTitle, Font = UI.FontHeavy, TextSize = 14, TextColor3 = UI.Colors.Accent, Position = UDim2.fromOffset(0, 8), Size = UDim2.new(1, 0, 0, 18), Parent = votePanel })
	local row = UI.new("Frame", { Position = UDim2.fromOffset(14, 34), Size = UDim2.new(1, -28, 0, 62), BackgroundTransparency = 1, Parent = votePanel })
	UI.new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, HorizontalAlignment = Enum.HorizontalAlignment.Center, Padding = UDim.new(0, 10), Parent = row })
	for i, id in Config.ModeOrder do
		local mode = Config.Modes[id]
		local b = UI.Button({ LayoutOrder = i, Text = "", Size = UDim2.fromOffset(210, 62), Parent = row })
		UI.Label({ Name = "Title", Text = mode.Name:upper(), Font = UI.FontHeavy, TextSize = 15, Position = UDim2.fromOffset(0, 8), Size = UDim2.new(1, 0, 0, 20), Parent = b })
		UI.Label({ Name = "Count", Text = "0 votes", TextSize = 12, TextColor3 = UI.Colors.Muted, Position = UDim2.fromOffset(0, 32), Size = UDim2.new(1, 0, 0, 18), Parent = b })
		b.Activated:Connect(function()
			click()
			myVote = id
			Remotes.VoteMode:FireServer(id)
			if not openPage then
				setMenuOpen(false)
			end
		end)
		voteButtons[id] = b
	end
end

local function refreshVote()
	local show = gameState:GetAttribute("State") == "Intermission"
	if votePanel.Visible and not show and not openPage and State.MenuOpen then
		setMenuOpen(false)
	end
	votePanel.Visible = show
	if not show then
		myVote = nil
		return
	end
	for id, b in voteButtons do
		local n = gameState:GetAttribute("Votes_" .. id) or 0
		(b:FindFirstChild("Count") :: TextLabel).Text = ("%d vote%s"):format(n, n == 1 and "" or "s")
		local stroke = b:FindFirstChildOfClass("UIStroke") :: UIStroke
		stroke.Color = id == myVote and UI.Colors.Accent or Color3.new(1, 1, 1)
		stroke.Transparency = id == myVote and 0 or 0.85
	end
end

---------------------------------------------------------------------------
-- Round summary
---------------------------------------------------------------------------

local function buildSummary()
	local frame = window("Summary", "AFTER ACTION REPORT", Vector2.new(640, 440))
	local banner = UI.Label({ Name = "Banner", Text = "", Font = UI.FontHeavy, TextSize = 34, Position = UDim2.fromOffset(20, 64), Size = UDim2.new(1, -40, 0, 40), ZIndex = 11, Parent = frame })
	local sub = UI.Label({ Name = "Sub", Text = "", TextSize = 15, TextColor3 = UI.Colors.Muted, Position = UDim2.fromOffset(20, 104), Size = UDim2.new(1, -40, 0, 20), ZIndex = 11, Parent = frame })
	local rows = UI.new("ScrollingFrame", { Name = "Rows", Position = UDim2.fromOffset(20, 140), Size = UDim2.new(1, -40, 1, -160), BackgroundTransparency = 1, BorderSizePixel = 0, ScrollBarThickness = 4, AutomaticCanvasSize = Enum.AutomaticSize.Y, CanvasSize = UDim2.new(), ZIndex = 11, Parent = frame })
	UI.new("UIListLayout", { Padding = UDim.new(0, 3), SortOrder = Enum.SortOrder.LayoutOrder, Parent = rows })

	Remotes.RoundSummary.OnClientEvent:Connect(function(summary)
		local winner = summary.Winner
		if winner == "Draw" then
			banner.Text = "DRAW"
			banner.TextColor3 = UI.Colors.Text
		else
			banner.Text = Config.Teams[winner].Name:upper() .. " WINS"
			banner.TextColor3 = Config.Teams[winner].Color
		end
		sub.Text = ("%s  •  %d – %d%s"):format(Config.Modes[summary.Mode].Name, summary.Blue, summary.Red, summary.MVP and ("  •  MVP: " .. summary.MVP) or "")
		for _, child in rows:GetChildren() do
			if child:IsA("Frame") then
				child:Destroy()
			end
		end
		table.sort(summary.Rows, function(a, b)
			return a.Tags * 2 + a.Captures > b.Tags * 2 + b.Captures
		end)
		local header = UI.new("Frame", { LayoutOrder = 0, Size = UDim2.new(1, -8, 0, 20), BackgroundTransparency = 1, ZIndex = 11, Parent = rows })
		UI.Label({ Text = "OPERATOR", TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(10, 0), Size = UDim2.new(0.4, 0, 1, 0), ZIndex = 12, Parent = header })
		UI.Label({ Text = "TAGS     OUTS     CAPS     XP", TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -10, 0, 0), Size = UDim2.new(0.6, 0, 1, 0), ZIndex = 12, Parent = header })
		for i, r in summary.Rows do
			local row = UI.new("Frame", { LayoutOrder = i, Size = UDim2.new(1, -8, 0, 28), BackgroundColor3 = r.UserId == player.UserId and Color3.fromRGB(60, 52, 30) or UI.Colors.PanelLight, BackgroundTransparency = 0.2, BorderSizePixel = 0, ZIndex = 11, Parent = rows }, { UI.Corner(4) })
			UI.new("Frame", { Size = UDim2.new(0, 3, 1, 0), BackgroundColor3 = Config.Teams[r.Side] and Config.Teams[r.Side].Color or UI.Colors.Text, BorderSizePixel = 0, ZIndex = 12, Parent = row })
			UI.Label({ Text = r.Name, TextSize = 14, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(12, 0), Size = UDim2.new(0.4, 0, 1, 0), TextTruncate = Enum.TextTruncate.AtEnd, ZIndex = 12, Parent = row })
			UI.Label({ Text = ("%d          %d          %d        +%d"):format(r.Tags, r.Outs, r.Captures, r.XP), TextSize = 14, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -10, 0, 0), Size = UDim2.new(0.6, 0, 1, 0), ZIndex = 12, Parent = row })
		end
		Menu.Open("Summary")
		task.delay(Config.PostRoundTime - 0.5, function()
			if openPage == "Summary" then
				Menu.Close()
			end
		end)
	end)
end

---------------------------------------------------------------------------
-- Menu bar
---------------------------------------------------------------------------

local function buildMenuBar()
	local bar = UI.new("Frame", { Name = "MenuBar", Position = UDim2.fromOffset(20, 20), Size = UDim2.fromOffset(300, 32), BackgroundTransparency = 1, Parent = gui })
	UI.new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, Padding = UDim.new(0, 6), Parent = bar })
	for i, spec in { { "LOADOUT", "Loadout" }, { "SETTINGS", "Settings" } } do
		local b = UI.Button({ LayoutOrder = i, Text = spec[1], TextSize = 12, Size = UDim2.fromOffset(92, 30), BackgroundTransparency = 0.3, Parent = bar })
		b.Activated:Connect(function()
			click()
			Menu.Open(spec[2])
		end)
	end
	local scores = UI.Button({ LayoutOrder = 3, Text = "SCORES", TextSize = 12, Size = UDim2.fromOffset(92, 30), BackgroundTransparency = 0.3, Parent = bar })
	scores.Activated:Connect(function()
		click()
		scoreboard.Visible = not scoreboard.Visible
		if scoreboard.Visible then
			refreshScoreboard()
		end
	end)
end

function Menu.Init()
	gui = UI.new("ScreenGui", {
		Name = "AirsoftMenus",
		ResetOnSpawn = false,
		IgnoreGuiInset = true,
		DisplayOrder = 5,
		ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
		Parent = player:WaitForChild("PlayerGui"),
	})
	modal = UI.new("TextButton", { Name = "MouseUnlock", Text = "", BackgroundTransparency = 1, Size = UDim2.fromOffset(0, 0), Modal = true, Visible = false, Parent = gui })

	buildLoadout()
	buildSettings()
	buildScoreboard()
	buildVote()
	buildSummary()
	buildMenuBar()

	ContextActionService:BindAction("AirsoftLoadoutMenu", function(_, inputState)
		if inputState == Enum.UserInputState.Begin then
			Menu.Open("Loadout")
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.KeyCode.L, Enum.KeyCode.DPadLeft)
	ContextActionService:BindAction("AirsoftSettingsMenu", function(_, inputState)
		if inputState == Enum.UserInputState.Begin then
			Menu.Open("Settings")
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.KeyCode.P, Enum.KeyCode.ButtonSelect)
	ContextActionService:BindAction("AirsoftVote", function(_, inputState)
		if inputState == Enum.UserInputState.Begin and votePanel.Visible and not openPage then
			-- Free the mouse so the vote buttons can be clicked.
			setMenuOpen(not State.MenuOpen)
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.KeyCode.V)
	ContextActionService:BindAction("AirsoftScoreboard", function(_, inputState)
		if inputState == Enum.UserInputState.Begin then
			refreshScoreboard()
			scoreboard.Visible = true
		elseif inputState == Enum.UserInputState.End then
			scoreboard.Visible = false
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.KeyCode.Tab, Enum.KeyCode.DPadDown)

	-- Profile from the server seeds settings and loadout.
	local function applyProfile(profile)
		if type(profile) ~= "table" then
			return
		end
		State.Profile = profile
		for k, v in profile.Settings or {} do
			State.Settings[k] = v
		end
		State.Emit("Profile", profile)
	end
	Remotes.Profile.OnClientEvent:Connect(applyProfile)
	task.spawn(function()
		local ok, profile = pcall(function()
			return Remotes.GetProfile:InvokeServer()
		end)
		if ok then
			applyProfile(profile)
		end
	end)

	local lastVoteRefresh = 0
	RunService.Heartbeat:Connect(function()
		if os.clock() - lastVoteRefresh > 0.25 then
			lastVoteRefresh = os.clock()
			refreshVote()
			if scoreboard.Visible then
				refreshScoreboard()
			end
		end
	end)

	-- First visit: show the loadout picker so new players learn the guns.
	task.delay(2, function()
		if not openPage and (player:GetAttribute("Side") or "") == "" then
			Menu.Open("Loadout")
		end
	end)
end

return Menu
