--[[
	"Final tag" replay: after each round the camera rides alongside the last
	BB of the match in slow motion, letterboxed and desaturated, before the
	after-action report opens.
]]

local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Shared = game:GetService("ReplicatedStorage"):WaitForChild("Shared")
local Config = require(Shared.Config)
local Weapons = require(Shared.Weapons)

local State = require(script.Parent.State)
local UI = require(script.Parent.UI)
local Effects = require(script.Parent.Effects)

local Cinematic = {}

local DURATION = 4.2
local player = Players.LocalPlayer
local camera = workspace.CurrentCamera

local gui: ScreenGui
local topBar: Frame
local bottomBar: Frame
local caption: TextLabel
local subcaption: TextLabel

local function teamColor(side: string?): Color3
	return (side and Config.Teams[side]) and Config.Teams[side].Color or UI.Colors.Accent
end

function Cinematic.Init()
	gui = UI.new("ScreenGui", {
		Name = "AirsoftCinematic",
		ResetOnSpawn = false,
		IgnoreGuiInset = true,
		DisplayOrder = 20,
		Enabled = false,
		Parent = player:WaitForChild("PlayerGui"),
	})
	topBar = UI.new("Frame", { Size = UDim2.new(1, 0, 0.12, 0), Position = UDim2.fromScale(0, -0.12), BackgroundColor3 = Color3.new(0, 0, 0), BorderSizePixel = 0, Parent = gui })
	bottomBar = UI.new("Frame", { Size = UDim2.new(1, 0, 0.12, 0), Position = UDim2.fromScale(0, 1), BackgroundColor3 = Color3.new(0, 0, 0), BorderSizePixel = 0, Parent = gui })
	caption = UI.Label({ Text = "FINAL TAG", Font = UI.FontHeavy, TextSize = 34, TextColor3 = UI.Colors.Accent, AnchorPoint = Vector2.new(0, 1), Position = UDim2.new(0, 48, 0.88, -12), Size = UDim2.fromOffset(600, 40), TextXAlignment = Enum.TextXAlignment.Left, TextTransparency = 1, Parent = gui })
	subcaption = UI.Label({ RichText = true, Text = "", TextSize = 18, AnchorPoint = Vector2.new(0, 0), Position = UDim2.new(0, 48, 0.88, 6), Size = UDim2.fromOffset(700, 24), TextXAlignment = Enum.TextXAlignment.Left, TextTransparency = 1, Parent = gui })
end

-- Plays the replay; yields until it finishes. `tag` comes from RoundSummary.FinalTag.
function Cinematic.Play(tag: any)
	if type(tag) ~= "table" or typeof(tag.From) ~= "Vector3" or typeof(tag.To) ~= "Vector3" then
		return
	end
	State.Cinematic = true
	gui.Enabled = true
	local from: Vector3 = tag.From
	local to: Vector3 = tag.To
	local dir = (to - from)
	if dir.Magnitude < 1 then
		dir = Vector3.new(0, 0, -1)
	end
	local unit = dir.Unit
	local side = unit:Cross(Vector3.yAxis)
	if side.Magnitude < 0.1 then
		side = Vector3.xAxis
	end
	side = side.Unit

	-- Slow, glowing BB travelling the whole path.
	local bb = Instance.new("Part")
	bb.Name = "ReplayBB"
	bb.Shape = Enum.PartType.Ball
	bb.Size = Vector3.new(0.18, 0.18, 0.18)
	bb.Material = Enum.Material.Neon
	bb.Color = teamColor(tag.ShooterSide)
	bb.Anchored = true
	bb.CanCollide = false
	bb.CanQuery = false
	bb.CastShadow = false
	local light = Instance.new("PointLight")
	light.Color = bb.Color
	light.Range = 6
	light.Brightness = 3
	light.Parent = bb
	local trail0 = Instance.new("Attachment")
	trail0.Position = Vector3.new(0, 0.06, 0)
	trail0.Parent = bb
	local trail1 = Instance.new("Attachment")
	trail1.Position = Vector3.new(0, -0.06, 0)
	trail1.Parent = bb
	local trail = Instance.new("Trail")
	trail.Attachment0 = trail0
	trail.Attachment1 = trail1
	trail.Lifetime = 0.6
	trail.Color = ColorSequence.new(bb.Color)
	trail.LightEmission = 1
	trail.Transparency = NumberSequence.new(0.2, 1)
	trail.Parent = bb
	bb.Parent = workspace:FindFirstChild("Effects") or workspace

	local grade = Instance.new("ColorCorrectionEffect")
	grade.Name = "ReplayGrade"
	grade.Saturation = 0
	grade.Contrast = 0
	grade.Parent = Lighting
	TweenService:Create(grade, TweenInfo.new(0.6), { Saturation = -0.55, Contrast = 0.2, TintColor = Color3.fromRGB(255, 236, 214) }):Play()
	local dof = Instance.new("DepthOfFieldEffect")
	dof.FarIntensity = 0.35
	dof.InFocusRadius = 10
	dof.NearIntensity = 0.2
	dof.Parent = Lighting

	local barInfo = TweenInfo.new(0.5, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
	TweenService:Create(topBar, barInfo, { Position = UDim2.fromScale(0, 0) }):Play()
	TweenService:Create(bottomBar, barInfo, { Position = UDim2.fromScale(0, 0.88) }):Play()
	local weapon = tag.Weapon == "Grenade" and Weapons.Grenade.Name or (Weapons.Get(tag.Weapon) and Weapons.Get(tag.Weapon).Name or tostring(tag.Weapon))
	subcaption.Text = ('<font color="#%s">%s</font>  ▸  <font color="#%s">%s</font>   <font color="#9A9CA0">%s · %d studs</font>'):format(
		teamColor(tag.ShooterSide):ToHex(),
		tostring(tag.Shooter),
		teamColor(tag.VictimSide):ToHex(),
		tostring(tag.Victim),
		weapon,
		math.floor(dir.Magnitude + 0.5)
	)
	TweenService:Create(caption, TweenInfo.new(0.6), { TextTransparency = 0 }):Play()
	TweenService:Create(subcaption, TweenInfo.new(0.8), { TextTransparency = 0 }):Play()

	local previousType = camera.CameraType
	local previousFOV = camera.FieldOfView
	camera.CameraType = Enum.CameraType.Scriptable
	Effects.Play2D("FireSniper", 0.5, 0.45)

	local start = os.clock()
	local flight = DURATION * 0.78
	local connection = RunService.RenderStepped:Connect(function()
		local t = math.clamp((os.clock() - start) / flight, 0, 1)
		-- Ease-in-out so the BB crawls through the middle of its flight.
		local k = t < 0.5 and 4 * t * t * t or 1 - (-2 * t + 2) ^ 3 / 2
		local pos = from:Lerp(to, k)
		bb.Position = pos
		dof.FocusDistance = 6
		local orbit = math.rad(25) + t * math.rad(40)
		local offset = (side * math.cos(orbit) + Vector3.yAxis * 0.35 - unit * math.sin(orbit) * 0.4) * 5
		camera.CFrame = CFrame.lookAt(pos + offset, pos + unit * 3)
		camera.FieldOfView = 50 - t * 10
	end)

	task.wait(flight)
	Effects.Play2D("HitMarker", 0.6, 0.7)
	-- Hold on the impact for a beat.
	task.wait(DURATION - flight)
	connection:Disconnect()

	TweenService:Create(topBar, barInfo, { Position = UDim2.fromScale(0, -0.12) }):Play()
	TweenService:Create(bottomBar, barInfo, { Position = UDim2.fromScale(0, 1) }):Play()
	TweenService:Create(caption, TweenInfo.new(0.4), { TextTransparency = 1 }):Play()
	TweenService:Create(subcaption, TweenInfo.new(0.4), { TextTransparency = 1 }):Play()
	bb:Destroy()
	dof:Destroy()
	grade:Destroy()
	camera.CameraType = previousType == Enum.CameraType.Scriptable and Enum.CameraType.Custom or previousType
	camera.FieldOfView = previousFOV
	State.Cinematic = false
	task.delay(0.5, function()
		if not State.Cinematic then
			gui.Enabled = false
		end
	end)
end

return Cinematic
