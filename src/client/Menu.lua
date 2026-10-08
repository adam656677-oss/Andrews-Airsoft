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
-- Loadout (armory)
---------------------------------------------------------------------------

local GunBuilder = require(Shared.GunBuilder)

-- Bars derived from final stats so attachments visibly change them.
local function statValues(w)
	return {
		Range = math.clamp((w.Velocity - 300) / 300 * 0.6 + w.Range / 420 * 0.4, 0.05, 1),
		Rate = math.clamp(60 / w.FireInterval / 1100, 0.05, 1),
		Control = math.clamp(1 - w.Recoil[1] / 2.8 - w.Spread.Hip / 12, 0.05, 1),
		Handling = math.clamp(1 - (w.AimTime - 0.1) / 0.4 + ((w.SpeedMultiplier or 1) - 1) * 2, 0.05, 1),
	}
end

local loadoutState = {
	Selected = "M4",
	Primary = "M4",
	Secondary = "G17",
}

local function currentLoadout(id: string)
	State.Settings.Loadouts = State.Settings.Loadouts or {}
	local l = Weapons.CleanLoadout(id, State.Settings.Loadouts[id])
	State.Settings.Loadouts[id] = l
	return l
end

local function rankIndex(): number
	return (Config.RankForXP(player:GetAttribute("XP") or 0))
end

local function buildLoadout()
	local frame = window("Loadout", "ARMORY", Vector2.new(980, 560))

	-- Left: weapon list grouped by slot
	local list = UI.new("ScrollingFrame", {
		Position = UDim2.fromOffset(20, 66),
		Size = UDim2.new(0, 220, 1, -86),
		BackgroundTransparency = 1,
		BorderSizePixel = 0,
		ScrollBarThickness = 4,
		AutomaticCanvasSize = Enum.AutomaticSize.Y,
		CanvasSize = UDim2.new(),
		ZIndex = 11,
		Parent = frame,
	})
	UI.new("UIListLayout", { Padding = UDim.new(0, 4), SortOrder = Enum.SortOrder.LayoutOrder, Parent = list })

	-- Centre: preview + details
	local preview = UI.new("ViewportFrame", {
		Position = UDim2.fromOffset(256, 66),
		Size = UDim2.fromOffset(440, 220),
		BackgroundColor3 = Color3.fromRGB(10, 11, 13),
		BackgroundTransparency = 0.1,
		Ambient = Color3.fromRGB(150, 150, 150),
		LightColor = Color3.fromRGB(255, 240, 220),
		LightDirection = Vector3.new(-0.4, -1, -0.6),
		ZIndex = 11,
		Parent = frame,
	}, { UI.Corner(6) })
	local previewCam = Instance.new("Camera")
	previewCam.FieldOfView = 30
	previewCam.Parent = preview
	preview.CurrentCamera = previewCam

	local title = UI.Label({ Text = "", Font = UI.FontHeavy, TextSize = 20, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(256, 294), Size = UDim2.fromOffset(440, 24), ZIndex = 11, Parent = frame })
	local subtitle = UI.Label({ Text = "", TextSize = 12, TextColor3 = UI.Colors.Accent, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(256, 318), Size = UDim2.fromOffset(440, 16), ZIndex = 11, Parent = frame })
	local blurb = UI.Label({ Text = "", Font = UI.FontLight, TextSize = 13, TextColor3 = UI.Colors.Muted, TextWrapped = true, TextXAlignment = Enum.TextXAlignment.Left, TextYAlignment = Enum.TextYAlignment.Top, Position = UDim2.fromOffset(256, 338), Size = UDim2.fromOffset(440, 36), ZIndex = 11, Parent = frame })
	local stats = UI.new("Frame", { Position = UDim2.fromOffset(256, 378), Size = UDim2.fromOffset(440, 100), BackgroundTransparency = 1, ZIndex = 11, Parent = frame })
	local numbers = UI.Label({ Text = "", TextSize = 12, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(256, 482), Size = UDim2.fromOffset(440, 16), ZIndex = 11, Parent = frame })

	-- Right: attachments and finishes
	local custom = UI.new("ScrollingFrame", {
		Position = UDim2.fromOffset(712, 66),
		Size = UDim2.new(0, 248, 1, -140),
		BackgroundTransparency = 1,
		BorderSizePixel = 0,
		ScrollBarThickness = 4,
		AutomaticCanvasSize = Enum.AutomaticSize.Y,
		CanvasSize = UDim2.new(),
		ZIndex = 11,
		Parent = frame,
	})
	UI.new("UIListLayout", { Padding = UDim.new(0, 6), SortOrder = Enum.SortOrder.LayoutOrder, Parent = custom })

	local equipButton = UI.Button({ Text = "EQUIP", Font = UI.FontHeavy, AnchorPoint = Vector2.new(1, 1), Position = UDim2.new(1, -176, 1, -16), Size = UDim2.fromOffset(140, 38), ZIndex = 11, Parent = frame })
	local confirm = UI.Button({ Text = "DEPLOY LOADOUT", Font = UI.FontHeavy, BackgroundColor3 = UI.Colors.Accent, TextColor3 = Color3.fromRGB(20, 20, 20), AnchorPoint = Vector2.new(1, 1), Position = UDim2.new(1, -20, 1, -16), Size = UDim2.fromOffset(150, 38), ZIndex = 11, Parent = frame })
	local equippedLabel = UI.Label({ Text = "", TextSize = 12, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, AnchorPoint = Vector2.new(0, 1), Position = UDim2.new(0, 256, 1, -26), Size = UDim2.fromOffset(420, 16), ZIndex = 11, Parent = frame })

	local listButtons: { [string]: TextButton } = {}
	local previewModel: Model? = nil
	local spin = 0

	local refresh: () -> ()

	local function sectionHeader(parent: Instance, text: string, order: number)
		UI.Label({ LayoutOrder = order, Text = text, TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Size = UDim2.new(1, -8, 0, 18), ZIndex = 12, Parent = parent })
	end

	local order = 0
	local function addList(ids: { string }, header: string)
		order += 1
		sectionHeader(list, header, order)
		for _, id in ids do
			order += 1
			local w = Weapons.Get(id)
			local b = UI.Button({ LayoutOrder = order, Text = "", Size = UDim2.new(1, -8, 0, 40), ZIndex = 12, Parent = list })
			UI.Label({ Text = w.Name, TextSize = 13, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(10, 4), Size = UDim2.new(1, -20, 0, 18), ZIndex = 13, Parent = b })
			UI.Label({ Name = "Class", Text = w.Class:upper() .. "  •  " .. w.Kind:upper(), TextSize = 10, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(10, 22), Size = UDim2.new(1, -20, 0, 14), ZIndex = 13, Parent = b })
			b.Activated:Connect(function()
				click()
				loadoutState.Selected = id
				refresh()
			end)
			listButtons[id] = b
		end
	end
	addList(Weapons.Primaries, "PRIMARY")
	addList(Weapons.Secondaries, "SIDEARM")

	local function setPreview(id: string, loadout)
		if previewModel then
			previewModel:Destroy()
		end
		local ok, model = pcall(GunBuilder.Build, id, { Accent = UI.Colors.Accent, Loadout = loadout })
		if not ok then
			return
		end
		for _, d in model:GetDescendants() do
			if d:IsA("BasePart") then
				d.Anchored = true
			end
		end
		model:PivotTo(CFrame.identity)
		model.Parent = preview
		previewModel = model
		local _, size = model:GetBoundingBox()
		previewCam:SetAttribute("Distance", math.max(size.Magnitude, 1.5) * 1.9)
	end

	local function optionButton(parent: Instance, label: string, selected: boolean, locked: boolean, onClick: () -> ())
		local b = UI.Button({ Text = (locked and "🔒 " or "") .. label, TextSize = 12, Size = UDim2.new(0.5, -4, 0, 28), ZIndex = 13, Parent = parent })
		local stroke = b:FindFirstChildOfClass("UIStroke") :: UIStroke
		stroke.Color = selected and UI.Colors.Accent or Color3.new(1, 1, 1)
		stroke.Transparency = selected and 0 or 0.85
		stroke.Thickness = selected and 2 or 1
		b.TextColor3 = locked and UI.Colors.Muted or UI.Colors.Text
		b.Activated:Connect(function()
			if locked then
				return
			end
			click()
			onClick()
		end)
		return b
	end

	refresh = function()
		local id = loadoutState.Selected
		local base = Weapons.Get(id)
		local loadout = currentLoadout(id)
		local w = Weapons.Resolve(id, loadout)

		for bid, b in listButtons do
			local stroke = b:FindFirstChildOfClass("UIStroke") :: UIStroke
			local isSelected = bid == id
			local isEquipped = bid == loadoutState.Primary or bid == loadoutState.Secondary
			stroke.Color = isSelected and UI.Colors.Accent or (isEquipped and UI.Colors.Good or Color3.new(1, 1, 1))
			stroke.Transparency = (isSelected or isEquipped) and 0.1 or 0.85
			stroke.Thickness = isSelected and 2 or 1
		end

		title.Text = base.Name:upper()
		subtitle.Text = base.Class:upper() .. "  •  " .. base.Kind:upper() .. "  •  " .. table.concat(base.FireModes, " / "):upper()
		blurb.Text = base.Description

		for _, c in stats:GetChildren() do
			c:Destroy()
		end
		local base4 = statValues(base)
		local now4 = statValues(w)
		for i, key in { "Range", "Rate", "Control", "Handling" } do
			local y = (i - 1) * 24
			UI.Label({ Text = key:upper(), TextSize = 11, TextColor3 = UI.Colors.Muted, TextXAlignment = Enum.TextXAlignment.Left, Position = UDim2.fromOffset(0, y), Size = UDim2.fromOffset(80, 16), ZIndex = 12, Parent = stats })
			local bg = UI.new("Frame", { Position = UDim2.fromOffset(84, y + 6), Size = UDim2.new(1, -90, 0, 5), BackgroundColor3 = Color3.new(1, 1, 1), BackgroundTransparency = 0.88, BorderSizePixel = 0, ZIndex = 12, Parent = stats })
			UI.new("Frame", { Size = UDim2.fromScale(now4[key], 1), BackgroundColor3 = UI.Colors.Accent, BorderSizePixel = 0, ZIndex = 13, Parent = bg })
			local delta = now4[key] - base4[key]
			if math.abs(delta) > 0.01 then
				UI.new("Frame", {
					Position = UDim2.fromScale(math.min(base4[key], now4[key]), 0),
					Size = UDim2.fromScale(math.abs(delta), 1),
					BackgroundColor3 = delta > 0 and UI.Colors.Good or UI.Colors.Bad,
					BorderSizePixel = 0,
					ZIndex = 14,
					Parent = bg,
				})
			end
		end
		numbers.Text = ("%d RPM   •   %d FPS   •   %d RND   •   ADS %d ms%s"):format(
			math.floor(60 / w.FireInterval + 0.5),
			math.floor(w.Velocity * 0.85),
			w.MagSize,
			math.floor(w.AimTime * 1000),
			w.Quiet and "   •   SUPPRESSED" or ""
		)

		-- Attachment slots
		for _, c in custom:GetChildren() do
			if c:IsA("GuiObject") then
				c:Destroy()
			end
		end
		local corder = 0
		for _, slot in Weapons.Slots do
			local options = base.Options[slot]
			if options then
				corder += 1
				sectionHeader(custom, slot:upper(), corder)
				corder += 1
				local grid = UI.new("Frame", { LayoutOrder = corder, Size = UDim2.new(1, -6, 0, 0), AutomaticSize = Enum.AutomaticSize.Y, BackgroundTransparency = 1, ZIndex = 12, Parent = custom })
				UI.new("UIGridLayout", { CellSize = UDim2.new(0.5, -4, 0, 28), CellPadding = UDim2.fromOffset(6, 6), SortOrder = Enum.SortOrder.LayoutOrder, Parent = grid })
				for _, opt in options do
					local a = Weapons.Attachments[opt]
					optionButton(grid, a.Name, loadout[slot] == opt, false, function()
						loadout[slot] = opt
						refresh()
					end)
				end
			end
		end
		corder += 1
		sectionHeader(custom, "FINISH", corder)
		corder += 1
		local skinGrid = UI.new("Frame", { LayoutOrder = corder, Size = UDim2.new(1, -6, 0, 0), AutomaticSize = Enum.AutomaticSize.Y, BackgroundTransparency = 1, ZIndex = 12, Parent = custom })
		UI.new("UIGridLayout", { CellSize = UDim2.new(0.5, -4, 0, 28), CellPadding = UDim2.fromOffset(6, 6), SortOrder = Enum.SortOrder.LayoutOrder, Parent = skinGrid })
		local myRank = rankIndex()
		for _, skin in Weapons.Skins do
			local locked = skin.Unlock > myRank
			local b = optionButton(skinGrid, skin.Name, loadout.Skin == skin.Id, locked, function()
				loadout.Skin = skin.Id
				refresh()
			end)
			UI.new("Frame", { AnchorPoint = Vector2.new(0, 0.5), Position = UDim2.new(0, 4, 0.5, 0), Size = UDim2.fromOffset(4, 18), BackgroundColor3 = skin.Primary, BorderSizePixel = 0, ZIndex = 14, Parent = b })
			if locked then
				b.Text = "🔒 " .. Config.Ranks[skin.Unlock].Name
			end
		end

		local slotName = base.Slot == "Primary" and "PRIMARY" or "SIDEARM"
		local isEquipped = id == loadoutState.Primary or id == loadoutState.Secondary
		equipButton.Text = isEquipped and "EQUIPPED" or ("SET AS " .. slotName)
		equippedLabel.Text = ("Carrying: %s  +  %s"):format(Weapons.Get(loadoutState.Primary).Name, Weapons.Get(loadoutState.Secondary).Name)
		setPreview(id, loadout)
	end

	equipButton.Activated:Connect(function()
		click()
		local id = loadoutState.Selected
		if Weapons.IsPrimary(id) then
			loadoutState.Primary = id
		else
			loadoutState.Secondary = id
		end
		refresh()
	end)

	confirm.Activated:Connect(function()
		click()
		State.Settings.Primary = loadoutState.Primary
		State.Settings.Secondary = loadoutState.Secondary
		Remotes.SetLoadout:FireServer(loadoutState.Primary, loadoutState.Secondary, State.Settings.Loadouts)
		local inMatch = (player:GetAttribute("Side") or "") ~= ""
		Menu.Close()
		if inMatch then
			local hud = require(script.Parent.HUD)
			hud.Announce("Loadout saved", "Applies on your next respawn", UI.Colors.Accent, 2)
		end
	end)

	RunService.RenderStepped:Connect(function(dt)
		if frame.Visible and previewModel then
			spin += dt * 0.5
			local distance = previewCam:GetAttribute("Distance") or 6
			local pivot = previewModel:GetBoundingBox().Position
			previewCam.CFrame = CFrame.lookAt(pivot + Vector3.new(math.cos(spin) * distance, distance * 0.18, math.sin(spin) * distance), pivot)
		end
	end)

	State.On("Profile", function()
		loadoutState.Primary = State.Settings.Primary or loadoutState.Primary
		loadoutState.Secondary = State.Settings.Secondary or loadoutState.Secondary
		if frame.Visible then
			refresh()
		end
	end)
	frame:GetPropertyChangedSignal("Visible"):Connect(function()
		if frame.Visible then
			refresh()
		end
	end)
end

-- Opens the armory with a specific weapon highlighted (used by armory racks).
function Menu.OpenLoadout(weaponId: string?)
	if weaponId and Weapons.Get(weaponId) then
		loadoutState.Selected = weaponId
	end
	if openPage ~= "Loadout" then
		Menu.Open("Loadout")
	end
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

local mapButtons: { [string]: TextButton } = {}
local myMapVote: string? = nil

local function voteRow(parent: Instance, y: number, label: string, ids: { string }, defs: { [string]: any }, store: { [string]: TextButton }, onPick: (string) -> ())
	UI.Label({ Text = label, TextSize = 11, TextColor3 = UI.Colors.Muted, Position = UDim2.fromOffset(16, y), Size = UDim2.new(1, -32, 0, 14), TextXAlignment = Enum.TextXAlignment.Left, Parent = parent })
	local row = UI.new("Frame", { Position = UDim2.fromOffset(14, y + 16), Size = UDim2.new(1, -28, 0, 58), BackgroundTransparency = 1, Parent = parent })
	UI.new("UIListLayout", { FillDirection = Enum.FillDirection.Horizontal, HorizontalAlignment = Enum.HorizontalAlignment.Center, Padding = UDim.new(0, 10), Parent = row })
	for i, id in ids do
		local def = defs[id]
		local b = UI.Button({ LayoutOrder = i, Text = "", Size = UDim2.fromOffset(240, 58), Parent = row })
		UI.Label({ Name = "Title", Text = def.Name:upper(), Font = UI.FontHeavy, TextSize = 15, Position = UDim2.fromOffset(0, 6), Size = UDim2.new(1, 0, 0, 20), Parent = b })
		UI.Label({ Name = "Count", Text = "0 votes", TextSize = 12, TextColor3 = UI.Colors.Muted, Position = UDim2.fromOffset(0, 30), Size = UDim2.new(1, 0, 0, 18), Parent = b })
		b.Activated:Connect(function()
			click()
			onPick(id)
		end)
		store[id] = b
	end
end

local function buildVote()
	votePanel = UI.Panel({ Name = "Vote", AnchorPoint = Vector2.new(0.5, 1), Position = UDim2.new(0.5, 0, 1, -120), Size = UDim2.fromOffset(530, 196), Visible = false, Parent = gui })
	local voteTitle = UserInputService.KeyboardEnabled and "NEXT ROUND  ·  PRESS [V] TO VOTE" or "NEXT ROUND  ·  TAP TO VOTE"
	UI.Label({ Text = voteTitle, Font = UI.FontHeavy, TextSize = 14, TextColor3 = UI.Colors.Accent, Position = UDim2.fromOffset(0, 8), Size = UDim2.new(1, 0, 0, 18), Parent = votePanel })
	local function done()
		if not openPage then
			setMenuOpen(false)
		end
	end
	voteRow(votePanel, 32, "MAP", Config.MapOrder, Config.Maps, mapButtons, function(id)
		myMapVote = id
		Remotes.VoteMap:FireServer(id)
	end)
	voteRow(votePanel, 112, "MODE", Config.ModeOrder, Config.Modes, voteButtons, function(id)
		myVote = id
		Remotes.VoteMode:FireServer(id)
		done()
	end)
end

local function paintVotes(store: { [string]: TextButton }, prefix: string, mine: string?)
	for id, b in store do
		local n = gameState:GetAttribute(prefix .. id) or 0
		(b:FindFirstChild("Count") :: TextLabel).Text = ("%d vote%s"):format(n, n == 1 and "" or "s")
		local stroke = b:FindFirstChildOfClass("UIStroke") :: UIStroke
		stroke.Color = id == mine and UI.Colors.Accent or Color3.new(1, 1, 1)
		stroke.Transparency = id == mine and 0 or 0.85
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
		myMapVote = nil
		return
	end
	paintVotes(voteButtons, "Votes_", myVote)
	paintVotes(mapButtons, "MapVotes_", myMapVote)
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
		local received = os.clock()
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
		-- Slow-motion replay of the last tag first, then the report.
		require(script.Parent.Cinematic).Play(summary.FinalTag)
		Menu.Open("Summary")
		task.delay(math.max(Config.PostRoundTime - 0.5 - (os.clock() - received), 1), function()
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
