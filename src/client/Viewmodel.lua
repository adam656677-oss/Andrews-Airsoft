--[[
	First-person viewmodel: a local copy of the equipped gun plus gloved arms,
	positioned relative to the camera every frame.

	Handles hip/aim blending, sway, walk bob, sprint and slide poses, recoil
	kick and procedural animations:
	  Draw      gun swings up into view on equip
	  Reload    tilt, mag drops out, support hand brings a fresh mag, seat, charge
	  Inspect   turn the gun to admire it, both sides
	  Cycle     bolt (sniper) or pump (shotgun) between shots
	  Slide     pistol slides blow back on every shot and lock on empty
]]

local Shared = game:GetService("ReplicatedStorage"):WaitForChild("Shared")
local GunBuilder = require(Shared.GunBuilder)

local Effects = require(script.Parent.Effects)

local Viewmodel = {}
Viewmodel.__index = Viewmodel

local GLOVE = Color3.fromRGB(30, 30, 28)
local SLEEVE = Color3.fromRGB(38, 40, 44) -- dark tailored jacket sleeve
local CUFF = Color3.fromRGB(220, 220, 214) -- white shirt cuff

local HIP_OFFSETS = {
	G17 = CFrame.new(0.75, -0.95, -1.9),
	G18 = CFrame.new(0.75, -0.95, -1.9),
	M1911 = CFrame.new(0.75, -0.95, -1.9),
	DEAGLE = CFrame.new(0.75, -1.0, -2.0),
	Grenade = CFrame.new(0.8, -1.0, -1.7),
	P90 = CFrame.new(0.8, -1.05, -1.5),
	MP7 = CFrame.new(0.8, -1.0, -1.5),
}
local DEFAULT_HIP = CFrame.new(0.85, -1.05, -1.25)

local function ease(t: number): number
	t = math.clamp(t, 0, 1)
	return t * t * (3 - 2 * t)
end

local function window(t: number, a: number, b: number): number
	return ease((t - a) / (b - a))
end

local function newLimb(model: Model, name: string, width: number, color: Color3, material: Enum.Material)
	local p = Instance.new("Part")
	p.Name = name
	p.Size = Vector3.new(width, width, 1)
	p.Color = color
	p.Material = material
	p.Parent = model
	return p
end

function Viewmodel.new(weaponId: string, opts: { Accent: Color3, Loadout: any? })
	local model = weaponId == "Grenade" and GunBuilder.BuildGrenade(opts.Accent)
		or GunBuilder.Build(weaponId, { Accent = opts.Accent, Loadout = opts.Loadout })
	local handle = model.PrimaryPart :: BasePart
	local handle0 = handle.CFrame -- model-space CFrame of the handle at build time

	local function modelSpace(name: string): Vector3?
		local a = handle:FindFirstChild(name) :: Attachment?
		return a and (handle0 * a.CFrame).Position or nil
	end

	-- Gather every gun part with its model-space CFrame and animation role.
	local parts: { BasePart } = {}
	local locals: { CFrame } = {}
	local roles: { string } = {}
	local opticParts: { BasePart } = {}
	for _, d in model:GetDescendants() do
		if d:IsA("BasePart") then
			d.Anchored = true
			d.CanCollide = false
			d.CanQuery = false
			d.CanTouch = false
			d.CastShadow = false
			table.insert(parts, d)
			table.insert(locals, d.CFrame)
			table.insert(roles, d:GetAttribute("Role") or "")
			if d:GetAttribute("Optic") then
				table.insert(opticParts, d)
			end
		end
	end

	-- Arms are rebuilt every frame from hand and elbow points.
	local arms = {
		RightGlove = newLimb(model, "RightGlove", 0.36, GLOVE, Enum.Material.Fabric),
		RightCuff = newLimb(model, "RightCuff", 0.42, CUFF, Enum.Material.Fabric),
		RightSleeve = newLimb(model, "RightSleeve", 0.48, SLEEVE, Enum.Material.Fabric),
		LeftGlove = newLimb(model, "LeftGlove", 0.34, GLOVE, Enum.Material.Fabric),
		LeftCuff = newLimb(model, "LeftCuff", 0.42, CUFF, Enum.Material.Fabric),
		LeftSleeve = newLimb(model, "LeftSleeve", 0.48, SLEEVE, Enum.Material.Fabric),
		Armband = newLimb(model, "Armband", 0.52, opts.Accent, Enum.Material.Neon),
	}
	for _, p in arms do
		p.Anchored = true
		p.CanCollide = false
		p.CanQuery = false
		p.CanTouch = false
		p.CastShadow = false
	end

	local aimPos = modelSpace("Aim") or Vector3.new(0, 0.6, 0.6)
	local self = setmetatable({
		Model = model,
		WeaponId = weaponId,
		Handle0 = handle0,
		Parts = parts,
		Locals = locals,
		Roles = roles,
		OpticParts = opticParts,
		OpticFade = 0,
		Arms = arms,
		Hip = HIP_OFFSETS[weaponId] or DEFAULT_HIP,
		Aim = CFrame.new(-aimPos),
		Grip = Vector3.new(0, -0.05, 0.05),
		LeftHand = modelSpace("LeftHand") or Vector3.new(0, 0.2, -1.2),
		MagWell = modelSpace("MagWell") or Vector3.new(0, 0, -0.6),
		Muzzle = handle:FindFirstChild("Muzzle") :: Attachment?,
		LaserEmitter = handle:FindFirstChild("LaserEmitter") :: Attachment?,
		Light = nil :: SpotLight?,
		Visible = true,
		KickTarget = 0,
		Sway = Vector2.zero,
		BobTime = 0,
		Sprint = 0,
		Slide = 0,
		SlideLocked = false,
		SlideKick = 0,
		Anim = nil :: any,
		LastCF = CFrame.identity,
	}, Viewmodel)

	local lens = model:FindFirstChild("LightLens", true)
	if lens then
		self.Light = lens:FindFirstChild("Beam") :: SpotLight?
	end

	model.Name = "Viewmodel"
	model.Parent = workspace.CurrentCamera
	self:Play("Draw", 0.38)
	return self
end

function Viewmodel:SetVisible(visible: boolean)
	if self.Visible == visible then
		return
	end
	self.Visible = visible
	self.OpticFade = -1 -- force the optic ghosting to re-apply
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
	self.SlideKick = 1
end

function Viewmodel:SetSlideLocked(locked: boolean)
	self.SlideLocked = locked
end

function Viewmodel:MuzzlePosition(): Vector3?
	return self.Muzzle and self.Muzzle.WorldPosition or nil
end

function Viewmodel:LaserPosition(): Vector3?
	return self.LaserEmitter and self.LaserEmitter.WorldPosition or nil
end

-- Starts an animation. kind: "Draw" | "Reload" | "Inspect" | "Cycle"
function Viewmodel:Play(kind: string, duration: number, data: any?)
	self.Anim = { Kind = kind, Start = os.clock(), Duration = duration, Data = data or {}, Cues = {} }
end

function Viewmodel:Busy(kind: string?): boolean
	local a = self.Anim
	if not a then
		return false
	end
	return kind == nil or a.Kind == kind
end

function Viewmodel:CancelInspect()
	if self.Anim and self.Anim.Kind == "Inspect" then
		self.Anim = nil
	end
end

local function cue(anim, name: string, at: number, t: number, fn: () -> ())
	if t >= at and not anim.Cues[name] then
		anim.Cues[name] = true
		fn()
	end
end

-- Returns the whole-gun pose offset plus per-role offsets for this frame.
function Viewmodel:Animate(dt: number): (CFrame, { [string]: CFrame }, Vector3?)
	local roleOffsets: { [string]: CFrame } = {}
	local leftHandOverride: Vector3? = nil
	local a = self.Anim
	local pose = CFrame.identity

	-- Pistol slide blowback and lock.
	self.SlideKick = math.max(self.SlideKick - dt / 0.07, 0)
	local slideBack = self.SlideLocked and 1 or self.SlideKick
	if slideBack > 0 then
		roleOffsets.Slide = CFrame.new(0, 0, 0.16 * slideBack)
	end

	if not a then
		return pose, roleOffsets, nil
	end
	local t = (os.clock() - a.Start) / a.Duration
	if t >= 1 then
		self.Anim = nil
		return pose, roleOffsets, nil
	end

	if a.Kind == "Draw" then
		local k = 1 - ease(t)
		pose = CFrame.new(0.2 * k, -1.1 * k, 0.3 * k) * CFrame.Angles(math.rad(-50) * k, math.rad(20) * k, math.rad(-25) * k)
	elseif a.Kind == "Reload" then
		local tilt = window(t, 0, 0.18) - window(t, 0.82, 1)
		pose = CFrame.new(-0.05 * tilt, -0.12 * tilt, 0.05 * tilt) * CFrame.Angles(math.rad(14) * tilt, math.rad(-8) * tilt, math.rad(-32) * tilt)

		local well = self.MagWell
		if self.WeaponId == "M870" or self.WeaponId == "VSR" then
			-- Thumbing in shells / rounds: the hand goes to the loading port.
			local feed = math.sin(t * math.pi * 6) * 0.08
			local reach = window(t, 0.12, 0.25) - window(t, 0.78, 0.9)
			leftHandOverride = self.LeftHand:Lerp(well + Vector3.new(-0.05, -0.15 + feed, 0.05), reach)
			cue(a, "click1", 0.3, t, function()
				Effects.Play2D("MagIn", 0.35, 1.4)
			end)
			cue(a, "click2", 0.55, t, function()
				Effects.Play2D("MagIn", 0.35, 1.3)
			end)
		else
			-- Mag drops away, fresh mag comes up from the pouch.
			local drop = window(t, 0.18, 0.4)
			local insert = window(t, 0.45, 0.7)
			local offset
			if t < 0.42 then
				offset = CFrame.new(0, -1.6 * drop * drop, 0.15 * drop) * CFrame.Angles(math.rad(-25) * drop, 0, math.rad(10) * drop)
			else
				local from = CFrame.new(-0.25, -1.3, 0.45) * CFrame.Angles(math.rad(-20), 0, 0)
				offset = from:Lerp(CFrame.identity, insert)
			end
			roleOffsets.Mag = offset
			local magPos = (CFrame.new(well) * offset).Position
			local grab = window(t, 0.36, 0.46) - window(t, 0.72, 0.84)
			leftHandOverride = self.LeftHand:Lerp(magPos + Vector3.new(0, -0.3, 0), grab)
			cue(a, "out", 0.2, t, function()
				Effects.Play2D("MagOut", 0.45, 1)
			end)
			cue(a, "in", 0.68, t, function()
				Effects.Play2D("MagIn", 0.5, 1)
			end)
			if a.Data.Empty then
				-- Charge the gun / drop the slide on an empty reload.
				local charge = window(t, 0.74, 0.82) - window(t, 0.82, 0.9)
				roleOffsets.Bolt = CFrame.new(0, 0, 0.25 * charge)
				if t > 0.8 then
					self.SlideLocked = false
				end
				cue(a, "charge", 0.8, t, function()
					Effects.Play2D("BoltCycle", 0.5, 1.1)
				end)
			end
		end
	elseif a.Kind == "Inspect" then
		local side = window(t, 0.05, 0.25) - window(t, 0.42, 0.55)
		local flip = window(t, 0.5, 0.65) - window(t, 0.85, 1)
		pose = CFrame.new(-0.35 * (side + flip), 0.15 * (side + flip), 0.35 * (side + flip))
			* CFrame.Angles(math.rad(10) * side, math.rad(60) * side - math.rad(50) * flip, math.rad(25) * side + math.rad(-70) * flip)
	elseif a.Kind == "Cycle" then
		local back = window(t, 0.1, 0.45) - window(t, 0.55, 0.9)
		if self.WeaponId == "M870" then
			roleOffsets.Pump = CFrame.new(0, 0, 0.35 * back)
			leftHandOverride = self.LeftHand + Vector3.new(0, 0, 0.35 * back)
			cue(a, "rack", 0.35, t, function()
				Effects.Play2D("BoltCycle", 0.6, 0.85)
			end)
		else
			local lift = window(t, 0.05, 0.2) - window(t, 0.8, 0.95)
			roleOffsets.Bolt = CFrame.new(0, 0.05 * lift, 0.3 * back) * CFrame.Angles(0, 0, math.rad(60) * lift)
			leftHandOverride = nil
			cue(a, "bolt", 0.3, t, function()
				Effects.Play2D("BoltCycle", 0.6, 1)
			end)
		end
		pose = CFrame.Angles(math.rad(4) * back, 0, math.rad(-8) * back)
	end
	return pose, roleOffsets, leftHandOverride
end

local function placeLimb(part: BasePart, from: Vector3, to: Vector3): CFrame
	local length = math.max((to - from).Magnitude, 0.05)
	part.Size = Vector3.new(part.Size.X, part.Size.Y, length)
	return CFrame.lookAt((from + to) / 2, to)
end

-- Called every render frame.
function Viewmodel:Update(dt: number, camera: Camera, aim: number, speed: number, mouseDelta: Vector2, sprinting: boolean, sliding: boolean)
	-- Sway lags behind mouse movement.
	local targetSway = Vector2.new(math.clamp(-mouseDelta.X * 0.004, -0.12, 0.12), math.clamp(mouseDelta.Y * 0.004, -0.12, 0.12))
	self.Sway = self.Sway:Lerp(targetSway, math.min(dt * 10, 1))

	-- Walk bob, reduced while aiming.
	if speed > 1 then
		self.BobTime += dt * (speed / 14) * 9
	end
	local bobAmount = math.min(speed / 14, 1.5) * (1 - aim * 0.85) * (sliding and 0.2 or 1)
	local bob = CFrame.new(math.sin(self.BobTime) * 0.035 * bobAmount, math.abs(math.cos(self.BobTime)) * 0.04 * bobAmount, 0)

	self.Sprint += ((sprinting and 1 or 0) - self.Sprint) * math.min(dt * 8, 1)
	self.Slide += ((sliding and 1 or 0) - self.Slide) * math.min(dt * 10, 1)

	-- Recoil kick returns with a spring.
	self.KickTarget = math.max(self.KickTarget - dt * 9, 0)
	local kick = CFrame.new(0, 0, self.KickTarget * 0.18) * CFrame.Angles(math.rad(self.KickTarget * 5), 0, 0)

	local base = self.Hip:Lerp(self.Aim, aim)
	local sprintPose = CFrame.new(0.15 * self.Sprint, -0.25 * self.Sprint, 0.1 * self.Sprint)
		* CFrame.Angles(math.rad(-18) * self.Sprint, math.rad(35) * self.Sprint, math.rad(12) * self.Sprint)
	local slidePose = CFrame.new(-0.1 * self.Slide, 0.05 * self.Slide, 0) * CFrame.Angles(0, 0, math.rad(22) * self.Slide)
	local sway = CFrame.Angles(self.Sway.Y * (1 - aim * 0.7), self.Sway.X * (1 - aim * 0.7), 0)

	-- Ghost the optic housing at full aim so the sight picture is clear.
	local fade = math.clamp((aim - 0.75) / 0.25, 0, 1) * 0.85
	if math.abs(fade - self.OpticFade) > 0.01 and self.Visible then
		self.OpticFade = fade
		for _, p in self.OpticParts do
			p.LocalTransparencyModifier = fade
		end
	end

	local animPose, roleOffsets, leftOverride = self:Animate(dt)
	local modelCF = camera.CFrame * sway * bob * base * sprintPose * slidePose * animPose * kick
	self.LastCF = modelCF

	-- Move every gun part, applying role offsets for mags, slides, bolts, pumps.
	-- Magazines pivot about the mag well so multi-part mags stay together.
	local cframes = table.create(#self.Parts)
	local magPivot = CFrame.new(self.MagWell)
	local magPivotInv = magPivot:Inverse()
	for i, local0 in self.Locals do
		local role = self.Roles[i]
		local offset = roleOffsets[role]
		if offset and role == "Mag" then
			cframes[i] = modelCF * magPivot * offset * magPivotInv * local0
		elseif offset then
			cframes[i] = modelCF * CFrame.new(local0.Position) * offset * (local0 - local0.Position)
		else
			cframes[i] = modelCF * local0
		end
	end

	-- Arms
	local grip = self.Grip
	local left = leftOverride or self.LeftHand
	local rightElbow = grip + Vector3.new(0.55, -1.2, 1.6)
	local leftElbow = left + Vector3.new(-0.75, -1.3, 1.1)
	local rDir = (rightElbow - grip).Unit
	local lDir = (leftElbow - left).Unit
	local armParts = { self.Arms.RightGlove, self.Arms.RightCuff, self.Arms.RightSleeve, self.Arms.LeftGlove, self.Arms.LeftCuff, self.Arms.LeftSleeve, self.Arms.Armband }
	local armCFs = {
		placeLimb(self.Arms.RightGlove, grip, grip + rDir * 0.42),
		placeLimb(self.Arms.RightCuff, grip + rDir * 0.38, grip + rDir * 0.52),
		placeLimb(self.Arms.RightSleeve, grip + rDir * 0.5, rightElbow),
		placeLimb(self.Arms.LeftGlove, left, left + lDir * 0.42),
		placeLimb(self.Arms.LeftCuff, left + lDir * 0.38, left + lDir * 0.52),
		placeLimb(self.Arms.LeftSleeve, left + lDir * 0.5, leftElbow),
		placeLimb(self.Arms.Armband, left + lDir * 0.95, left + lDir * 1.2),
	}
	for i, cf in armCFs do
		table.insert(self.Parts, armParts[i])
		table.insert(cframes, modelCF * cf)
	end

	workspace:BulkMoveTo(self.Parts, cframes, Enum.BulkMoveMode.FireCFrameChanged)

	-- Arms were appended temporarily; trim them back off the part list.
	for _ = 1, #armParts do
		table.remove(self.Parts)
	end
end

function Viewmodel:Destroy()
	self.Model:Destroy()
end

return Viewmodel
