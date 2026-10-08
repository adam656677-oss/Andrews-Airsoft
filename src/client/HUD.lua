--[[
	In-game HUD: compass, score bar, objectives, crosshair, hit marker, ammo,
	kill feed, announcements, XP popups, "you're hit" overlay, scope overlay.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared.Config)
local Weapons = require(Shared.Weapons)
local Remotes = require(Shared.Remotes)

local State = require(script.Parent.State)
local UI = require(script.Parent.UI)

local player = Players.LocalPlayer
local camera = workspace.CurrentCamera
local gameState = ReplicatedStorage:WaitForChild("GameState")

local HUD = {}

local gui: ScreenGui
local refs: { [string]: any } = {}

local function teamColor(side: string?): Color3
	if side and Config.Teams[side] then
		return Config.Teams[side].Color
	end
	return UI.Colors.Accent
end

local function formatTime(seconds: number): string
	seconds = math.max(0, math.floor(seconds))
	return ("%d:%02d"):format(seconds // 60, seconds % 60)
end

---------------------------------------------------------------------------
-- Construction
---------------------------------------------------------------------------

local function buildCompass()
	local holder = UI.new("Frame", {
		Name = "Compass",
		AnchorPoint = Vector2.new(0.5, 0),
		Position = UDim2.new(0.5, 0, 0, 8),
		Size = UDim2.fromOffset(420, 26),
		BackgroundTransparency = 1,
		ClipsDescendants = true,
		Parent = gui,
	})
	UI.new("UIGradient", {
		Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 1),
			NumberSequenceKeypoint.new(0.2, 0),
			NumberSequenceKeypoint.new(0.8, 0),
			NumberSequenceKeypoint.new(1, 1),
		}),
		Parent = holder,
	})
	local strip = UI.new("Frame", { Name = "Strip", BackgroundTransparency = 1, Size = UDim2.fromScale(1, 1), Parent = holder })
	local names = { [0] = "N", [45] = "NE", [90] = "E", [135] = "SE", [180] = "S", [225] = "SW", [270] = "W", [315] = "NW" }
	local marks = {}
	for deg = 0, 345, 15 do
		local label = UI.Label({
			Text = names[deg] or "|",
			TextSize = names[deg] and 15 or 10,
			Font = names[deg] and UI.FontHeavy or UI.Font,
			TextColor3 = deg == 0 and UI.Colors.Accent or UI.Colors.Text,
			TextTransparency = names[deg] and 0 or 0.5,
			AnchorPoint = Vector2.new(0.5, 0.5),
			Size = UDim2.fromOffset(30, 20),
			Parent = strip,
		})
		table.insert(marks, { Label = label, Degree = deg })
	end
	UI.new("Frame", {
		AnchorPoint = Vector2.new(0.5, 0),
		Position = UDim2.new(0.5, 0, 1, -3),
		Size = UDim2.fromOffset(2, 6),
		BackgroundColor3 = UI.Colors.Accent,
		BorderSizePixel = 0,
		Parent = holder,
	})
	refs.CompassMarks = marks
end

local function buildScoreBar()
	local bar = UI.new("Frame", {
		Name = "ScoreBar",
		AnchorPoint = Vector2.new(0.5, 0),
		Position = UDim2.new(0.5, 0, 0, 38),
		Size = UDim2.fromOffset(360, 46),
		BackgroundTransparency = 1,
		Parent = gui,
	})
	local function side(name: string, xAnchor: number, xPos: UDim)
		local panel = UI.Panel({
			Name = name,
			AnchorPoint = Vector2.new(xAnchor, 0),
			Position = UDim2.new(xPos, UDim.new(0, 0)),
			Size = UDim2.fromOffset(100, 46),
			Parent = bar,
		})
		local color = Config.Teams[name].Color
		UI.new("Frame", { Name = "Accent", Size = UDim2.new(1, 0, 0, 3), BackgroundColor3 = color, BorderSizePixel = 0, Parent = panel })
		local score = UI.Label({ Name = "Score", Text = "0", Font = UI.FontHeavy, TextSize = 26, Size = UDim2.new(1, 0, 1, -10), Position = UDim2.fromOffset(0, 2), TextColor3 = color, Parent = panel })
		local fillBg = UI.new("Frame", { Name = "FillBg", AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 1, -5), Size = UDim2.new(1, -16, 0, 3), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.85, BorderSizePixel = 0, Parent = panel })
		local fill = UI.new("Frame", { Name = "Fill", Size = UDim2.fromScale(0, 1), BackgroundColor3 = color, BorderSizePixel = 0, Parent = fillBg })
		if name == "Red" then
			fill.AnchorPoint = Vector2.new(1, 0)
			fill.Position = UDim2.fromScale(1, 0)
		end
		return score, fill
	end
	refs.BlueScore, refs.BlueFill = side("Blue", 0, UDim.new(0, 0))
	refs.RedScore, refs.RedFill = side("Red", 1, UDim.new(1, 0))

	local center = UI.Panel({ Name = "Center", AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.fromScale(0.5, 0), Size = UDim2.fromOffset(148, 46), Parent = bar })
	refs.Timer = UI.Label({ Name = "Timer", Text = "--:--", Font = UI.FontHeavy, TextSize = 22, Size = UDim2.new(1, 0, 0, 28), Position = UDim2.fromOffset(0, 2), Parent = center })
	refs.ModeLabel = UI.Label({ Name = "Mode", Text = "", TextSize = 11, TextColor3 = UI.Colors.Muted, Size = UDim2.new(1, 0, 0, 14), Position = UDim2.fromOffset(0, 28), Parent = center })

	-- Domination point chips
	local chips = UI.new("Frame", { Name = "Objectives", AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 1, 6), Size = UDim2.fromOffset(150, 34), BackgroundTransparency = 1, Visible = false, Parent = bar })
	UI.new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, HorizontalAlignment = Enum.HorizontalAlignment.Center, Padding = UDim.new(0, 8), Parent = chips })
	refs.Chips = {}
	for _, letter in { "A", "B", "C" } do
		local chip = UI.Panel({ Name = letter, Size = UDim2.fromOffset(40, 34), Parent = chips })
		local fill = UI.new("Frame", { Name = "Fill", AnchorPoint = Vector2.new(0, 1), Position = UDim2.fromScale(0, 1), Size = UDim2.fromScale(1, 0), BackgroundColor3 = UI.Colors.Text, BackgroundTransparency = 0.5, BorderSizePixel = 0, Parent = chip })
		UI.new("UICorner", { CornerRadius = UDim.new(0, 6), Parent = fill })
		local label = UI.Label({ Name = "Letter", Text = letter, Font = UI.FontHeavy, TextSize = 18, Size = UDim2.fromScale(1, 1), ZIndex = 2, Parent = chip })
		refs.Chips[letter] = { Frame = chip, Fill = fill, Label = label }
	end
	refs.ObjectiveChips = chips

	refs.StatusMessage = UI.Label({
		Name = "Status",
		AnchorPoint = Vector2.new(0.5, 0),
		Position = UDim2.new(0.5, 0, 1, 8),
		Size = UDim2.fromOffset(500, 22),
		Text = "",
		TextSize = 15,
		TextColor3 = UI.Colors.Accent,
		TextStrokeTransparency = 0.6,
		Parent = bar,
	})
end

local function buildCrosshair()
	local holder = UI.new("Frame", { Name = "Crosshair", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromOffset(1, 1), BackgroundTransparency = 1, Parent = gui })
	local lines = {}
	for i, dir in { Vector2.new(1, 0), Vector2.new(-1, 0), Vector2.new(0, 1), Vector2.new(0, -1) } do
		local horizontal = dir.Y == 0
		local line = UI.new("Frame", {
			Name = "Line" .. i,
			AnchorPoint = Vector2.new(0.5, 0.5),
			Size = horizontal and UDim2.fromOffset(9, 2) or UDim2.fromOffset(2, 9),
			BackgroundColor3 = Color3.new(1, 1, 1),
			BorderSizePixel = 0,
			Parent = holder,
		})
		UI.new("UIStroke", { Color = Color3.new(0, 0, 0), Transparency = 0.5, Parent = line })
		table.insert(lines, { Frame = line, Dir = dir })
	end
	UI.new("Frame", { Name = "Dot", AnchorPoint = Vector2.new(0.5, 0.5), Size = UDim2.fromOffset(2, 2), BackgroundColor3 = Color3.new(1, 1, 1), BorderSizePixel = 0, Parent = holder })
	refs.Crosshair = holder
	refs.CrossLines = lines

	-- Hit marker: four short diagonal strokes.
	local hm = UI.new("Frame", { Name = "HitMarker", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromOffset(34, 34), BackgroundTransparency = 1, Visible = false, Parent = gui })
	for _, angle in { 45, 135, 225, 315 } do
		local rad = math.rad(angle)
		UI.new("Frame", {
			AnchorPoint = Vector2.new(0.5, 0.5),
			Position = UDim2.new(0.5, math.cos(rad) * 11, 0.5, math.sin(rad) * 11),
			Size = UDim2.fromOffset(10, 2),
			Rotation = angle,
			BackgroundColor3 = Color3.new(1, 1, 1),
			BorderSizePixel = 0,
			Parent = hm,
		})
	end
	refs.HitMarker = hm
end

local function buildWeaponPanel()
	local panel = UI.Panel({ Name = "Weapon", AnchorPoint = Vector2.new(1, 1), Position = UDim2.new(1, -20, 1, -20), Size = UDim2.fromOffset(250, 92), Parent = gui })
	refs.WeaponName = UI.Label({ Text = "", TextSize = 13, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(14, 8), Size = UDim2.new(1, -28, 0, 16), Parent = panel })
	refs.Mag = UI.Label({ Text = "30", Font = UI.FontHeavy, TextSize = 44, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(14, 24), Size = UDim2.fromOffset(90, 46), Parent = panel })
	refs.Reserve = UI.Label({ Text = "/ 180", TextSize = 18, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(96, 40), Size = UDim2.fromOffset(80, 24), Parent = panel })
	refs.FireMode = UI.Label({ Text = "AUTO", TextSize = 13, TextColor3 = UI.Colors.Accent, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -14, 0, 8), Size = UDim2.fromOffset(80, 16), Parent = panel })
	refs.Grenades = UI.Label({ Text = "◆ 1", TextSize = 15, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -14, 0, 44), Size = UDim2.fromOffset(60, 20), Parent = panel })
	local reloadBg = UI.new("Frame", { Name = "ReloadBg", Position = UDim2.new(0, 14, 1, -14), Size = UDim2.new(1, -28, 0, 3), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.85, BorderSizePixel = 0, Parent = panel })
	refs.ReloadFill = UI.new("Frame", { Size = UDim2.fromScale(0, 1), BackgroundColor3 = UI.Colors.Accent, BorderSizePixel = 0, Parent = reloadBg })
	refs.ReloadHint = UI.Label({ Text = "", TextSize = 13, TextColor3 = UI.Colors.Bad, AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0.5, 46), Size = UDim2.fromOffset(240, 18), TextStrokeTransparency = 0.5, Parent = gui })
	refs.WeaponPanel = panel
end

local function buildRankPanel()
	local panel = UI.Panel({ Name = "Rank", AnchorPoint = Vector2.new(0, 1), Position = UDim2.new(0, 20, 1, -20), Size = UDim2.fromOffset(230, 52), Parent = gui })
	refs.RankName = UI.Label({ Text = "Recruit", Font = UI.FontHeavy, TextSize = 16, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(12, 6), Size = UDim2.new(1, -24, 0, 20), Parent = panel })
	refs.RankXP = UI.Label({ Text = "0 XP", TextSize = 12, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Right, AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -12, 0, 8), Size = UDim2.fromOffset(120, 16), Parent = panel })
	local bg = UI.new("Frame", { Position = UDim2.new(0, 12, 1, -16), Size = UDim2.new(1, -24, 0, 5), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.85, BorderSizePixel = 0, Parent = panel })
	UI.new("UICorner", { CornerRadius = UDim.new(1, 0), Parent = bg })
	refs.RankFill = UI.new("Frame", { Size = UDim2.fromScale(0, 1), BackgroundColor3 = UI.Colors.Accent, BorderSizePixel = 0, Parent = bg })
	UI.new("UICorner", { CornerRadius = UDim.new(1, 0), Parent = refs.RankFill })

	local hints = UI.Label({
		Name = "Hints",
		AnchorPoint = Vector2.new(0, 1),
		Position = UDim2.new(0, 22, 1, -80),
		Size = UDim2.fromOffset(420, 16),
		Text = "[L] Loadout   [P] Settings   [Tab] Scores   [B] Fire mode   [F] Light   [G] Grenade   [Q/E] Lean",
		TextSize = 11,
		TextColor3 = UI.Colors.Muted,
		TextXAlignment = Enum.TextXAlignment.Left,
		Visible = UserInputService.KeyboardEnabled,
		Parent = gui,
	})
	refs.Hints = hints
end

local function buildKillFeed()
	local feed = UI.new("Frame", { Name = "KillFeed", AnchorPoint = Vector2.new(1, 0), Position = UDim2.new(1, -20, 0, 20), Size = UDim2.fromOffset(330, 200), BackgroundTransparency = 1, Parent = gui })
	UI.new("UIListLayout", { HorizontalAlignment = Enum.HorizontalAlignment.Right, Padding = UDim.new(0, 4), SortOrder = Enum.SortOrder.LayoutOrder, Parent = feed })
	refs.KillFeed = feed
end

local function buildAnnouncement()
	local holder = UI.new("Frame", { Name = "Announce", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.3), Size = UDim2.fromOffset(700, 90), BackgroundTransparency = 1, Parent = gui })
	refs.AnnounceTitle = UI.Label({ Text = "", Font = UI.FontHeavy, TextSize = 46, Size = UDim2.new(1, 0, 0, 52), TextTransparency = 1, TextStrokeTransparency = 1, TextStrokeColor3 = Color3.new(0, 0, 0), Parent = holder })
	refs.AnnounceSub = UI.Label({ Text = "", TextSize = 18, Position = UDim2.fromOffset(0, 54), Size = UDim2.new(1, 0, 0, 24), TextColor3 = UI.Colors.Text, TextTransparency = 1, Parent = holder })

	local xp = UI.new("Frame", { Name = "XPFeed", AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0.5, 70), Size = UDim2.fromOffset(300, 120), BackgroundTransparency = 1, Parent = gui })
	UI.new("UIListLayout", { HorizontalAlignment = Enum.HorizontalAlignment.Center, Padding = UDim.new(0, 2), Parent = xp })
	refs.XPFeed = xp
end

local function buildOutOverlay()
	local overlay = UI.new("Frame", { Name = "Out", Size = UDim2.fromScale(1, 1), BackgroundColor3 = Color3.fromRGB(80, 24, 0), BackgroundTransparency = 1, Visible = false, ZIndex = 5, Parent = gui })
	UI.new("UIGradient", {
		Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.2), NumberSequenceKeypoint.new(0.5, 0.85), NumberSequenceKeypoint.new(1, 0.2) }),
		Parent = overlay,
	})
	refs.OutTitle = UI.Label({ Text = "HIT!", Font = UI.FontHeavy, TextSize = 64, TextColor3 = Color3.fromRGB(255, 140, 50), AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.4), Size = UDim2.fromOffset(600, 70), TextStrokeTransparency = 0.4, ZIndex = 6, Parent = gui, Visible = false })
	refs.OutBy = UI.Label({ Text = "", TextSize = 20, AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0.4, 40), Size = UDim2.fromOffset(600, 26), ZIndex = 6, Parent = gui, Visible = false, TextStrokeTransparency = 0.5 })
	refs.OutTimer = UI.Label({ Text = "", TextSize = 15, TextColor3 = UI.Colors.Muted, AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0.4, 70), Size = UDim2.fromOffset(600, 22), ZIndex = 6, Parent = gui, Visible = false })
	refs.Out = overlay

	-- Direction indicator pointing at whoever tagged you.
	local ring = UI.new("Frame", { Name = "HitDirection", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromOffset(260, 260), BackgroundTransparency = 1, Visible = false, ZIndex = 6, Parent = gui })
	UI.new("Frame", { AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.fromScale(0.5, 0), Size = UDim2.fromOffset(46, 8), BackgroundColor3 = Color3.fromRGB(255, 120, 40), BorderSizePixel = 0, ZIndex = 6, Parent = ring }, { UI.Corner(4) })
	refs.HitDirection = ring

	refs.Protected = UI.Label({ Text = "", TextSize = 14, TextColor3 = UI.Colors.Good, AnchorPoint = Vector2.new(0.5, 0), Position = UDim2.new(0.5, 0, 0.5, 30), Size = UDim2.fromOffset(300, 18), TextStrokeTransparency = 0.5, Parent = gui })
end

local function buildScope()
	local scope = UI.new("Frame", { Name = "Scope", Size = UDim2.fromScale(1, 1), BackgroundTransparency = 1, Visible = false, ZIndex = 3, Parent = gui })
	-- A circle with an enormous black stroke blacks out everything outside the lens.
	local lens = UI.new("Frame", { Name = "Lens", AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromScale(0.82, 0.82), BackgroundTransparency = 1, ZIndex = 3, Parent = scope })
	UI.new("UIAspectRatioConstraint", { AspectRatio = 1, Parent = lens })
	UI.new("UICorner", { CornerRadius = UDim.new(1, 0), Parent = lens })
	UI.new("UIStroke", { Thickness = 3000, Color = Color3.new(0, 0, 0), Parent = lens })
	UI.new("UIGradient", {
		Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 1), NumberSequenceKeypoint.new(0.85, 1), NumberSequenceKeypoint.new(1, 0.4) }),
		Parent = lens,
	})
	for _, spec in { { UDim2.new(1, 0, 0, 1), UDim2.fromScale(0.5, 0.5) }, { UDim2.new(0, 1, 1, 0), UDim2.fromScale(0.5, 0.5) } } do
		UI.new("Frame", { AnchorPoint = Vector2.new(0.5, 0.5), Position = spec[2], Size = spec[1], BackgroundColor3 = Color3.new(0, 0, 0), BorderSizePixel = 0, ZIndex = 4, Parent = lens })
	end
	-- Mil dots
	for i = -4, 4 do
		if i ~= 0 then
			UI.new("Frame", { AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.new(0.5 + i * 0.05, 0, 0.5, 0), Size = UDim2.fromOffset(5, 5), BackgroundColor3 = Color3.new(0, 0, 0), BorderSizePixel = 0, ZIndex = 4, Parent = lens }, { UI.Corner(3) })
			UI.new("Frame", { AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.new(0.5, 0, 0.5 + i * 0.05, 0), Size = UDim2.fromOffset(5, 5), BackgroundColor3 = Color3.new(0, 0, 0), BorderSizePixel = 0, ZIndex = 4, Parent = lens }, { UI.Corner(3) })
		end
	end
	UI.new("Frame", { AnchorPoint = Vector2.new(0.5, 0.5), Position = UDim2.fromScale(0.5, 0.5), Size = UDim2.fromOffset(3, 3), BackgroundColor3 = Color3.fromRGB(255, 40, 40), BorderSizePixel = 0, ZIndex = 5, Parent = lens })
	refs.Scope = scope
end

---------------------------------------------------------------------------
-- Dynamic behaviour
---------------------------------------------------------------------------

local announceToken = 0
function HUD.Announce(title: string, subtitle: string?, color: Color3?, duration: number?)
	announceToken += 1
	local token = announceToken
	refs.AnnounceTitle.Text = title
	refs.AnnounceTitle.TextColor3 = color or UI.Colors.Text
	refs.AnnounceSub.Text = subtitle or ""
	local fadeIn = TweenInfo.new(0.25)
	TweenService:Create(refs.AnnounceTitle, fadeIn, { TextTransparency = 0, TextStrokeTransparency = 0.6 }):Play()
	TweenService:Create(refs.AnnounceSub, fadeIn, { TextTransparency = 0 }):Play()
	task.delay(duration or 3, function()
		if token ~= announceToken then
			return
		end
		local fadeOut = TweenInfo.new(0.6)
		TweenService:Create(refs.AnnounceTitle, fadeOut, { TextTransparency = 1, TextStrokeTransparency = 1 }):Play()
		TweenService:Create(refs.AnnounceSub, fadeOut, { TextTransparency = 1 }):Play()
	end)
end

local function addKillFeed(victim: Player, shooter: Player?, weaponId: string)
	local feed = refs.KillFeed
	local entries = {}
	for _, child in feed:GetChildren() do
		if child:IsA("Frame") then
			table.insert(entries, child)
		end
	end
	table.sort(entries, function(a, b)
		return a.LayoutOrder < b.LayoutOrder
	end)
	while #entries >= 5 do
		table.remove(entries, 1):Destroy()
	end

	local weaponName = weaponId == "Grenade" and "Grenade" or (Weapons.Get(weaponId) and Weapons.Get(weaponId).Name or weaponId)
	local involved = victim == player or shooter == player
	local row = UI.Panel({ Size = UDim2.fromOffset(330, 26), LayoutOrder = math.floor(os.clock() * 1000), BackgroundTransparency = involved and 0.05 or 0.35, Parent = feed })
	local text = ("<font color=\"#%s\">%s</font>  <font color=\"#9A9CA0\">[%s]</font>  <font color=\"#%s\">%s</font>"):format(
		teamColor(shooter and shooter:GetAttribute("Side")):ToHex(),
		shooter and shooter.DisplayName or "Field",
		weaponName,
		teamColor(victim:GetAttribute("Side")):ToHex(),
		victim.DisplayName
	)
	UI.Label({ RichText = true, Text = text, TextSize = 13, Size = UDim2.new(1, -16, 1, 0), Position = UDim2.fromOffset(8, 0), TextXAlignment = Enum.TextXAlignment.Right, Parent = row })
	if involved then
		(row:FindFirstChildOfClass("UIStroke") :: UIStroke).Color = UI.Colors.Accent;
		(row:FindFirstChildOfClass("UIStroke") :: UIStroke).Transparency = 0.3
	end
	task.delay(7, function()
		if row.Parent then
			row:Destroy()
		end
	end)
end

local function showXP(amount: number, reason: string)
	local label = UI.Label({
		Text = ("+%d  %s"):format(amount, reason:upper()),
		TextSize = 14,
		TextColor3 = UI.Colors.Accent,
		TextStrokeTransparency = 0.5,
		Size = UDim2.fromOffset(300, 18),
		Parent = refs.XPFeed,
	})
	task.delay(1.8, function()
		TweenService:Create(label, TweenInfo.new(0.5), { TextTransparency = 1, TextStrokeTransparency = 1 }):Play()
		task.wait(0.5)
		label:Destroy()
	end)
end

local hitMarkerToken = 0
local function flashHitMarker(confirmed: boolean)
	hitMarkerToken += 1
	local token = hitMarkerToken
	local hm = refs.HitMarker
	hm.Visible = true
	for _, line in hm:GetChildren() do
		if line:IsA("Frame") then
			line.BackgroundColor3 = confirmed and Color3.fromRGB(255, 90, 60) or Color3.new(1, 1, 1)
		end
	end
	hm.Size = UDim2.fromOffset(confirmed and 44 or 30, confirmed and 44 or 30)
	task.delay(confirmed and 0.35 or 0.15, function()
		if token == hitMarkerToken then
			hm.Visible = false
		end
	end)
end

local outInfo: { Shooter: Player?, Position: Vector3?, Until: number } = { Shooter = nil, Position = nil, Until = 0 }

local function updateRank()
	local xp = player:GetAttribute("XP") or 0
	local _, rank, nextRank = Config.RankForXP(xp)
	refs.RankName.Text = rank.Name:upper()
	if nextRank then
		refs.RankXP.Text = ("%d / %d XP"):format(xp, nextRank.XP)
		refs.RankFill.Size = UDim2.fromScale((xp - rank.XP) / (nextRank.XP - rank.XP), 1)
	else
		refs.RankXP.Text = ("%d XP"):format(xp)
		refs.RankFill.Size = UDim2.fromScale(1, 1)
	end
end

local function updateAmmo()
	local id = State.Weapon
	local w = id and Weapons.Get(id)
	refs.WeaponPanel.Visible = id ~= nil
	if not w then
		if id == "Grenade" then
			refs.WeaponPanel.Visible = true
			refs.WeaponName.Text = Weapons.Grenade.Name:upper()
			refs.Mag.Text = tostring(player:GetAttribute("Grenades") or 0)
			refs.Reserve.Text = ""
			refs.FireMode.Text = "THROW"
		end
		return
	end
	local ammo = State.Ammo[id] or { Mag = w.MagSize, Reserve = w.Reserve }
	refs.WeaponName.Text = w.Name:upper()
	refs.Mag.Text = tostring(ammo.Mag)
	refs.Mag.TextColor3 = ammo.Mag <= math.ceil(w.MagSize * 0.2) and UI.Colors.Bad or UI.Colors.Text
	refs.Reserve.Text = "/ " .. ammo.Reserve
	local modeIndex = State.FireMode[id] or 1
	refs.FireMode.Text = (w.FireModes[modeIndex] or ""):upper()
	refs.Grenades.Text = "◆ " .. tostring(player:GetAttribute("Grenades") or 0)
	if ammo.Mag == 0 and ammo.Reserve == 0 then
		refs.ReloadHint.Text = "OUT OF AMMO — SWITCH TO SIDEARM"
	elseif ammo.Mag <= math.ceil(w.MagSize * 0.2) and not State.Reloading then
		refs.ReloadHint.Text = UserInputService.GamepadEnabled and "RELOAD [X]" or "RELOAD [R]"
	else
		refs.ReloadHint.Text = ""
	end
end

local reloadStart, reloadDuration = 0, 0

local function onRender()
	local now = workspace:GetServerTimeNow()

	-- Compass
	local look = camera.CFrame.LookVector
	local yaw = (math.deg(math.atan2(look.X, -look.Z)) + 360) % 360
	for _, mark in refs.CompassMarks do
		local diff = (mark.Degree - yaw + 540) % 360 - 180
		mark.Label.Position = UDim2.new(0.5, diff * 2.4, 0.5, 0)
		mark.Label.Visible = math.abs(diff) < 95
	end

	-- Score bar and timer
	local phase = gameState:GetAttribute("State") or "Waiting"
	local endsAt = gameState:GetAttribute("EndsAt") or 0
	local limit = gameState:GetAttribute("ScoreLimit") or 1
	local blue = gameState:GetAttribute("BlueScore") or 0
	local red = gameState:GetAttribute("RedScore") or 0
	refs.BlueScore.Text = tostring(blue)
	refs.RedScore.Text = tostring(red)
	refs.BlueFill.Size = UDim2.fromScale(math.clamp(blue / limit, 0, 1), 1)
	refs.RedFill.Size = UDim2.fromScale(math.clamp(red / limit, 0, 1), 1)
	refs.Timer.Text = endsAt > 0 and formatTime(endsAt - now) or "--:--"
	local mode = Config.Modes[gameState:GetAttribute("Mode") or "TDM"]
	local phaseNames = { Waiting = "WAITING", Intermission = "INTERMISSION", Briefing = "BRIEFING", Live = mode and mode.Name:upper() or "", PostRound = "ROUND OVER" }
	refs.ModeLabel.Text = phaseNames[phase] or phase
	local message = gameState:GetAttribute("Message") or ""
	if phase == "Briefing" then
		message = ("Deploying in %d…"):format(math.max(0, math.ceil(endsAt - now)))
	end
	refs.StatusMessage.Text = message

	-- Objectives
	local showObjectives = phase ~= "Waiting" and phase ~= "Intermission" and gameState:GetAttribute("Mode") == "DOM"
	refs.ObjectiveChips.Visible = showObjectives
	if showObjectives then
		local folder = workspace:FindFirstChild("Map") and workspace.Map:FindFirstChild("Objectives")
		for letter, chip in refs.Chips do
			local model = folder and folder:FindFirstChild(letter)
			if model then
				local owner = model:GetAttribute("Owner") or ""
				local progress = model:GetAttribute("Progress") or 0
				local capturing = model:GetAttribute("Capturing") or ""
				local color = owner ~= "" and teamColor(owner) or UI.Colors.Text
				chip.Label.TextColor3 = color
				chip.Fill.BackgroundColor3 = progress < 0 and Config.Teams.Blue.Color or Config.Teams.Red.Color
				chip.Fill.Size = UDim2.fromScale(1, math.abs(progress))
				chip.Fill.BackgroundTransparency = owner ~= "" and 0.55 or 0.3
				local stroke = chip.Frame:FindFirstChildOfClass("UIStroke") :: UIStroke
				stroke.Color = capturing == "Contested" and UI.Colors.Bad or color
				stroke.Transparency = capturing ~= "" and 0.1 or 0.75
			end
		end
	end

	-- Crosshair
	local w = State.Weapon and Weapons.Get(State.Weapon)
	local outNow = player:GetAttribute("Out") == true
	refs.Crosshair.Visible = w ~= nil and State.AimAlpha < 0.35 and not State.Sprinting and not outNow and not State.MenuOpen
	if refs.Crosshair.Visible then
		local pxPerDeg = camera.ViewportSize.Y / camera.FieldOfView
		local gap = math.clamp(State.Spread * pxPerDeg, 4, 120)
		for _, line in refs.CrossLines do
			line.Frame.Position = UDim2.fromOffset(line.Dir.X * (gap + 5), line.Dir.Y * (gap + 5))
		end
	end

	-- Reload bar
	if State.Reloading and reloadDuration > 0 then
		refs.ReloadFill.Size = UDim2.fromScale(math.clamp((os.clock() - reloadStart) / reloadDuration, 0, 1), 1)
	else
		refs.ReloadFill.Size = UDim2.fromScale(0, 1)
	end

	-- Spawn protection
	local protectedUntil = player:GetAttribute("ProtectedUntil") or 0
	if protectedUntil > now and not outNow then
		refs.Protected.Text = ("SPAWN PROTECTED  %.1fs"):format(protectedUntil - now)
	else
		refs.Protected.Text = ""
	end

	-- Out overlay
	if outNow then
		local remaining = math.max(0, outInfo.Until - os.clock())
		refs.OutTimer.Text = ("Walking back to spawn… %.1fs"):format(remaining)
		if outInfo.Position then
			local flat = (outInfo.Position - camera.CFrame.Position) * Vector3.new(1, 0, 1)
			local camLook = camera.CFrame.LookVector * Vector3.new(1, 0, 1)
			if flat.Magnitude > 0.1 and camLook.Magnitude > 0.1 then
				local angle = math.deg(math.atan2(flat.Unit:Cross(camLook.Unit).Y, flat.Unit:Dot(camLook.Unit)))
				refs.HitDirection.Rotation = -angle
			end
		end
	end
end

local function setOut(out: boolean)
	refs.Out.Visible = out
	refs.OutTitle.Visible = out
	refs.OutBy.Visible = out
	refs.OutTimer.Visible = out
	refs.HitDirection.Visible = out and outInfo.Position ~= nil
	if out then
		refs.Out.BackgroundTransparency = 0.4
		TweenService:Create(refs.Out, TweenInfo.new(1.2), { BackgroundTransparency = 0.75 }):Play()
	end
end

function HUD.Init()
	gui = UI.new("ScreenGui", {
		Name = "AirsoftHUD",
		ResetOnSpawn = false,
		IgnoreGuiInset = true,
		ZIndexBehavior = Enum.ZIndexBehavior.Sibling,
		Parent = player:WaitForChild("PlayerGui"),
	})

	buildCompass()
	buildScoreBar()
	buildCrosshair()
	buildWeaponPanel()
	buildRankPanel()
	buildKillFeed()
	buildAnnouncement()
	buildOutOverlay()
	buildScope()

	refs.WeaponPanel.Visible = false
	updateRank()
	player:GetAttributeChangedSignal("XP"):Connect(updateRank)
	player:GetAttributeChangedSignal("Grenades"):Connect(updateAmmo)

	State.On("Ammo", updateAmmo)
	State.On("Equipped", updateAmmo)
	State.On("FireMode", updateAmmo)
	State.On("Reload", function(active: boolean)
		if active then
			local w = State.Weapon and Weapons.Get(State.Weapon)
			local ammo = State.Weapon and State.Ammo[State.Weapon]
			reloadStart = os.clock()
			reloadDuration = w and (ammo and ammo.Mag == 0 and w.EmptyReloadTime or w.ReloadTime) or 0
		end
		updateAmmo()
	end)
	State.On("HitMarker", flashHitMarker)
	State.On("Scope", function(visible: boolean)
		refs.Scope.Visible = visible
	end)

	Remotes.Announce.OnClientEvent:Connect(HUD.Announce)
	Remotes.XPGained.OnClientEvent:Connect(showXP)
	Remotes.Tagged.OnClientEvent:Connect(function(victim: Player, shooter: Player?, weaponId: string, shooterPos: Vector3?)
		addKillFeed(victim, shooter, weaponId)
		if victim == player then
			outInfo.Shooter = shooter
			outInfo.Position = shooterPos
			outInfo.Until = os.clock() + Config.RespawnTime
			local weaponName = weaponId == "Grenade" and "a BB grenade" or (Weapons.Get(weaponId) and Weapons.Get(weaponId).Name or weaponId)
			refs.OutBy.Text = shooter and ("Tagged by %s with %s"):format(shooter.DisplayName, weaponName) or "You're out"
			refs.OutBy.TextColor3 = teamColor(shooter and shooter:GetAttribute("Side"))
			refs.HitDirection.Visible = shooterPos ~= nil
		end
	end)

	player:GetAttributeChangedSignal("Out"):Connect(function()
		setOut(player:GetAttribute("Out") == true)
	end)
	setOut(false)

	RunService.RenderStepped:Connect(onRender)
end

return HUD
