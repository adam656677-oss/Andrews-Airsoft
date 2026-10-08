--[[
	First-person viewmodel: a local copy of the equipped gun plus gloved arms,
	positioned relative to the camera every frame. Handles hip/aim blending,
	sway, walk bob, sprint pose and recoil kick.
]]

local Shared = game:GetService("ReplicatedStorage"):WaitForChild("Shared")
local GunBuilder = require(Shared.GunBuilder)

local Viewmodel = {}
Viewmodel.__index = Viewmodel

local GLOVE = Color3.fromRGB(34, 34, 32)
local SLEEVE = Color3.fromRGB(92, 92, 72)

local HIP_OFFSETS = {
	G17 = CFrame.new(0.75, -0.95, -1.9),
	Grenade = CFrame.new(0.8, -1.0, -1.7),
}
local DEFAULT_HIP = CFrame.new(0.85, -1.05, -1.25)

local function limb(model: Model, from: Vector3, to: Vector3, width: number, color: Color3, material: Enum.Material)
	local p = Instance.new("Part")
	p.Name = "Arm"
	p.Size = Vector3.new(width, width, (to - from).Magnitude)
	p.CFrame = CFrame.lookAt((from + to) / 2, to)
	p.Color = color
	p.Material = material
	p.Parent = model
	return p
end

function Viewmodel.new(weaponId: string, accent: Color3)
	local model = weaponId == "Grenade" and GunBuilder.BuildGrenade(accent) or GunBuilder.Build(weaponId, accent)
	local handle = model.PrimaryPart :: BasePart
	local handle0 = handle.CFrame -- model-space CFrame of the handle at build time

	local function modelSpace(name: string): Vector3?
		local a = handle:FindFirstChild(name) :: Attachment?
		return a and (handle0 * a.CFrame).Position or nil
	end

	-- Arms: right hand on the grip, left hand on the support position.
	local grip = Vector3.new(0, -0.05, 0.05)
	local left = modelSpace("LeftHand") or Vector3.new(0, 0.2, -1.2)
	local rightElbow = grip + Vector3.new(0.55, -1.2, 1.6)
	local leftElbow = left + Vector3.new(-0.75, -1.3, 1.1)
	limb(model, grip, grip + (rightElbow - grip).Unit * 0.45, 0.38, GLOVE, Enum.Material.Fabric)
	limb(model, grip + (rightElbow - grip).Unit * 0.4, rightElbow, 0.46, SLEEVE, Enum.Material.Fabric)
	limb(model, left, left + (leftElbow - left).Unit * 0.45, 0.36, GLOVE, Enum.Material.Fabric)
	limb(model, left + (leftElbow - left).Unit * 0.4, leftElbow, 0.46, SLEEVE, Enum.Material.Fabric)
	local band = limb(model, left + (leftElbow - left).Unit * 0.9, left + (leftElbow - left).Unit * 1.2, 0.5, accent, Enum.Material.Neon)
	band.Name = "Armband"

	for _, part in model:GetDescendants() do
		if part:IsA("BasePart") then
			part.Anchored = true
			part.CanCollide = false
			part.CanQuery = false
			part.CanTouch = false
			part.CastShadow = false
		end
	end

	local aimPos = modelSpace("Aim") or Vector3.new(0, 0.6, 0.6)
	local self = setmetatable({
		Model = model,
		WeaponId = weaponId,
		Handle0 = handle0,
		Hip = HIP_OFFSETS[weaponId] or DEFAULT_HIP,
		Aim = CFrame.new(-aimPos),
		Muzzle = handle:FindFirstChild("Muzzle") :: Attachment?,
		Light = nil :: SpotLight?,
		Visible = true,
		Kick = CFrame.identity,
		KickTarget = 0,
		Sway = Vector2.zero,
		BobTime = 0,
		Sprint = 0,
		Reload = 0,
	}, Viewmodel)

	local lens = model:FindFirstChild("LightLens", true)
	if lens then
		self.Light = lens:FindFirstChild("Beam") :: SpotLight?
	end

	model.Name = "Viewmodel"
	model.Parent = workspace.CurrentCamera
	return self
end

function Viewmodel:SetVisible(visible: boolean)
	if self.Visible == visible then
		return
	end
	self.Visible = visible
	for _, part in self.Model:GetDescendants() do
		if part:IsA("BasePart") then
			part.LocalTransparencyModifier = visible and 0 or 1
		end
	end
end

function Viewmodel:SetLight(on: boolean)
	if self.Light then
		self.Light.Enabled = on
	end
end

function Viewmodel:Recoil(strength: number)
	self.KickTarget = math.min(self.KickTarget + strength, 1.5)
end

function Viewmodel:MuzzlePosition(): Vector3?
	return self.Muzzle and self.Muzzle.WorldPosition or nil
end

-- Called every render frame.
function Viewmodel:Update(dt: number, camera: Camera, aim: number, speed: number, mouseDelta: Vector2, reloading: boolean, sprinting: boolean)
	-- Sway lags behind mouse movement.
	local targetSway = Vector2.new(math.clamp(-mouseDelta.X * 0.004, -0.12, 0.12), math.clamp(mouseDelta.Y * 0.004, -0.12, 0.12))
	self.Sway = self.Sway:Lerp(targetSway, math.min(dt * 10, 1))

	-- Walk bob, reduced while aiming.
	if speed > 1 then
		self.BobTime += dt * (speed / 14) * 9
	end
	local bobAmount = math.min(speed / 14, 1.5) * (1 - aim * 0.85)
	local bob = CFrame.new(math.sin(self.BobTime) * 0.035 * bobAmount, math.abs(math.cos(self.BobTime)) * 0.04 * bobAmount, 0)

	self.Sprint += ((sprinting and 1 or 0) - self.Sprint) * math.min(dt * 8, 1)
	self.Reload += ((reloading and 1 or 0) - self.Reload) * math.min(dt * 10, 1)

	-- Recoil kick returns with a spring.
	self.KickTarget = math.max(self.KickTarget - dt * 9, 0)
	local kick = CFrame.new(0, 0, self.KickTarget * 0.18) * CFrame.Angles(math.rad(self.KickTarget * 5), 0, 0)

	local base = self.Hip:Lerp(self.Aim, aim)
	local sprintPose = CFrame.new(0.15 * self.Sprint, -0.25 * self.Sprint, 0.1 * self.Sprint) * CFrame.Angles(math.rad(-18) * self.Sprint, math.rad(35) * self.Sprint, math.rad(12) * self.Sprint)
	local reloadPose = CFrame.new(0, -0.35 * self.Reload, 0) * CFrame.Angles(math.rad(25) * self.Reload, 0, math.rad(-30) * self.Reload)
	local sway = CFrame.Angles(self.Sway.Y * (1 - aim * 0.7), self.Sway.X * (1 - aim * 0.7), 0)

	local cf = camera.CFrame * sway * bob * base * sprintPose * reloadPose * kick
	self.Model:PivotTo(cf * self.Handle0)
end

function Viewmodel:Destroy()
	self.Model:Destroy()
end

return Viewmodel
