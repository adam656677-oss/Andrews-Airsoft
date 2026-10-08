--[[
	Builds every weapon model from parts so the game needs no uploaded meshes.

	Convention: the Handle (pistol grip) sits at the origin, the barrel points
	down -Z and +Y is up. That matches Roblox's default Tool.Grip, so the same
	model works as a third-person Tool and as the first-person viewmodel.

	Attachments on the Handle:
	  Muzzle    where BBs leave the barrel
	  Aim       eye position when aiming down sights
	  LeftHand  support-hand position for the viewmodel arms
]]

local GunBuilder = {}

local BLACK = Color3.fromRGB(26, 27, 29)
local POLY = Color3.fromRGB(38, 39, 42)
local METAL = Color3.fromRGB(58, 60, 64)
local DARK_METAL = Color3.fromRGB(44, 45, 48)
local FDE = Color3.fromRGB(150, 128, 94)
local WOOD = Color3.fromRGB(104, 66, 38)
local GLASS = Color3.fromRGB(120, 170, 200)

type Spec = {
	Name: string?,
	Size: Vector3,
	Pos: Vector3,
	Rot: Vector3?,
	Color: Color3?,
	Material: Enum.Material?,
	Shape: Enum.PartType?,
	Transparency: number?,
	Reflectance: number?,
}

local function rotation(rot: Vector3?): CFrame
	if not rot then
		return CFrame.identity
	end
	return CFrame.Angles(math.rad(rot.X), math.rad(rot.Y), math.rad(rot.Z))
end

local function cosmetic(part: BasePart)
	part.Anchored = false
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.Massless = true
	part.CastShadow = true
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
end

local Builder = {}
Builder.__index = Builder

local function newBuilder(name: string)
	local model = Instance.new("Model")
	model.Name = name

	local handle = Instance.new("Part")
	handle.Name = "Handle"
	handle.Size = Vector3.new(0.22, 0.55, 0.3)
	handle.CFrame = CFrame.Angles(math.rad(-14), 0, 0)
	handle.Color = POLY
	handle.Material = Enum.Material.SmoothPlastic
	cosmetic(handle)
	handle.Parent = model
	model.PrimaryPart = handle

	local self = setmetatable({ Model = model, Handle = handle }, Builder)
	return self
end

function Builder:Add(spec: Spec): BasePart
	local part = Instance.new("Part")
	part.Name = spec.Name or "Detail"
	part.Shape = spec.Shape or Enum.PartType.Block
	part.Size = spec.Size
	part.CFrame = CFrame.new(spec.Pos) * rotation(spec.Rot)
	part.Color = spec.Color or BLACK
	part.Material = spec.Material or Enum.Material.SmoothPlastic
	part.Transparency = spec.Transparency or 0
	part.Reflectance = spec.Reflectance or 0
	cosmetic(part)
	part.Parent = self.Model

	local weld = Instance.new("WeldConstraint")
	weld.Part0 = self.Handle
	weld.Part1 = part
	weld.Parent = part
	return part
end

-- Cylinder lying along the Z axis (Roblox cylinders run along X by default).
function Builder:Tube(name: string, diameter: number, length: number, pos: Vector3, color: Color3?, material: Enum.Material?)
	return self:Add({
		Name = name,
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(length, diameter, diameter),
		Pos = pos,
		Rot = Vector3.new(0, 90, 0),
		Color = color or METAL,
		Material = material or Enum.Material.Metal,
	})
end

function Builder:Attach(name: string, pos: Vector3)
	local a = Instance.new("Attachment")
	a.Name = name
	-- Handle is tilted for an ergonomic grip angle; attachments use model space.
	a.CFrame = self.Handle.CFrame:ToObjectSpace(CFrame.new(pos))
	a.Parent = self.Handle
	return a
end

function Builder:Light(pos: Vector3)
	local body = self:Tube("WeaponLight", 0.13, 0.3, pos, BLACK, Enum.Material.Metal)
	local lens = self:Add({
		Name = "LightLens",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(0.02, 0.12, 0.12),
		Pos = pos + Vector3.new(0, 0, -0.16),
		Rot = Vector3.new(0, 90, 0),
		Color = Color3.fromRGB(230, 235, 255),
		Material = Enum.Material.Glass,
		Transparency = 0.2,
	})
	local light = Instance.new("SpotLight")
	light.Name = "Beam"
	light.Face = Enum.NormalId.Right -- the cylinder's +X face points down -Z after rotation
	light.Angle = 50
	light.Range = 55
	light.Brightness = 6
	light.Color = Color3.fromRGB(255, 246, 228)
	light.Shadows = true
	light.Enabled = false
	light.Parent = lens
	return body, lens
end

-- Coloured gaffer tape so team-mates can identify each other's guns.
function Builder:Tape(size: Vector3, pos: Vector3, accent: Color3)
	local tape = self:Add({
		Name = "TeamTape",
		Size = size,
		Pos = pos,
		Color = accent,
		Material = Enum.Material.Fabric,
	})
	return tape
end

function Builder:RedDot(y: number, z: number)
	self:Add({ Name = "OpticMount", Size = Vector3.new(0.18, 0.1, 0.34), Pos = Vector3.new(0, y - 0.16, z), Color = BLACK })
	self:Tube("OpticBody", 0.27, 0.34, Vector3.new(0, y, z), BLACK, Enum.Material.Metal)
	self:Add({ Name = "OpticHood", Size = Vector3.new(0.3, 0.06, 0.38), Pos = Vector3.new(0, y + 0.13, z), Color = BLACK })
	self:Add({
		Name = "OpticGlass",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(0.02, 0.22, 0.22),
		Pos = Vector3.new(0, y, z - 0.12),
		Rot = Vector3.new(0, 90, 0),
		Color = GLASS,
		Material = Enum.Material.Glass,
		Transparency = 0.75,
	})
	local dot = self:Add({
		Name = "Reticle",
		Shape = Enum.PartType.Ball,
		Size = Vector3.new(0.018, 0.018, 0.018),
		Pos = Vector3.new(0, y, z - 0.13),
		Color = Color3.fromRGB(255, 40, 40),
		Material = Enum.Material.Neon,
	})
	dot.CastShadow = false
	return self:Attach("Aim", Vector3.new(0, y, z + 0.55))
end

function Builder:Scope(y: number, z: number, length: number)
	self:Add({ Name = "ScopeRingRear", Size = Vector3.new(0.2, 0.26, 0.1), Pos = Vector3.new(0, y - 0.12, z + length * 0.28), Color = BLACK })
	self:Add({ Name = "ScopeRingFront", Size = Vector3.new(0.2, 0.26, 0.1), Pos = Vector3.new(0, y - 0.12, z - length * 0.28), Color = BLACK })
	self:Tube("ScopeTube", 0.2, length, Vector3.new(0, y, z), BLACK, Enum.Material.Metal)
	self:Tube("ScopeBell", 0.32, length * 0.3, Vector3.new(0, y, z - length * 0.42), BLACK, Enum.Material.Metal)
	self:Tube("ScopeEyepiece", 0.28, length * 0.2, Vector3.new(0, y, z + length * 0.45), BLACK, Enum.Material.Metal)
	self:Tube("ScopeTurret", 0.12, 0.14, Vector3.new(0, y + 0.13, z), DARK_METAL)
	self:Add({
		Name = "ScopeGlass",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(0.02, 0.28, 0.28),
		Pos = Vector3.new(0, y, z - length * 0.57),
		Rot = Vector3.new(0, 90, 0),
		Color = Color3.fromRGB(70, 120, 170),
		Material = Enum.Material.Glass,
		Transparency = 0.3,
		Reflectance = 0.4,
	})
	return self:Attach("Aim", Vector3.new(0, y, z + length * 0.55 + 0.5))
end

---------------------------------------------------------------------------
-- Individual guns
---------------------------------------------------------------------------

local function buildAR(b, accent: Color3, opts)
	-- Lower / upper receiver
	b:Add({ Name = "Lower", Size = Vector3.new(0.24, 0.3, 1.0), Pos = Vector3.new(0, 0.24, -0.2), Color = POLY })
	b:Add({ Name = "Upper", Size = Vector3.new(0.26, 0.26, 1.15), Pos = Vector3.new(0, 0.5, -0.25), Color = METAL, Material = Enum.Material.Metal })
	b:Add({ Name = "ChargingHandle", Size = Vector3.new(0.3, 0.06, 0.12), Pos = Vector3.new(0, 0.6, 0.28), Color = BLACK })
	b:Add({ Name = "EjectionPort", Size = Vector3.new(0.02, 0.1, 0.3), Pos = Vector3.new(0.135, 0.5, -0.2), Color = Color3.fromRGB(15, 15, 15) })
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.38), Pos = Vector3.new(0, 0.02, -0.15), Color = BLACK })
	b:Add({ Name = "Trigger", Size = Vector3.new(0.04, 0.14, 0.04), Pos = Vector3.new(0, 0.1, -0.12), Color = DARK_METAL, Material = Enum.Material.Metal })
	b:Add({ Name = "MagWell", Size = Vector3.new(0.26, 0.2, 0.36), Pos = Vector3.new(0, 0.05, -0.55), Color = POLY })

	-- Magazine (curved mid-cap)
	local magColor = opts.MagColor or FDE
	b:Add({ Name = "Mag", Size = Vector3.new(0.2, 0.5, 0.34), Pos = Vector3.new(0, -0.27, -0.6), Rot = Vector3.new(-8, 0, 0), Color = magColor })
	b:Add({ Name = "MagLower", Size = Vector3.new(0.2, 0.36, 0.33), Pos = Vector3.new(0, -0.65, -0.7), Rot = Vector3.new(-20, 0, 0), Color = magColor })
	b:Add({ Name = "MagBase", Size = Vector3.new(0.23, 0.06, 0.37), Pos = Vector3.new(0, -0.84, -0.77), Rot = Vector3.new(-20, 0, 0), Color = BLACK })

	-- Stock
	b:Tube("BufferTube", 0.15, 0.75, Vector3.new(0, 0.46, 0.65), BLACK)
	b:Add({ Name = "Stock", Size = Vector3.new(0.24, 0.36, 0.6), Pos = Vector3.new(0, 0.38, 1.05), Color = POLY })
	b:Add({ Name = "StockCheek", Size = Vector3.new(0.26, 0.1, 0.5), Pos = Vector3.new(0, 0.58, 1.05), Color = POLY })
	b:Add({ Name = "ButtPad", Size = Vector3.new(0.26, 0.5, 0.07), Pos = Vector3.new(0, 0.33, 1.38), Color = Color3.fromRGB(18, 18, 18), Material = Enum.Material.Fabric })

	-- Handguard with M-LOK slots and rails
	local hgLength = opts.HandguardLength or 1.4
	local hgZ = -0.82 - hgLength / 2
	b:Add({ Name = "Handguard", Size = Vector3.new(0.32, 0.32, hgLength), Pos = Vector3.new(0, 0.5, hgZ), Color = POLY })
	for i = 0, math.floor(hgLength / 0.28) - 1 do
		local z = -0.95 - i * 0.28
		b:Add({ Name = "Slot", Size = Vector3.new(0.33, 0.06, 0.14), Pos = Vector3.new(0, 0.46, z), Color = Color3.fromRGB(16, 16, 16) })
	end
	b:Add({ Name = "TopRail", Size = Vector3.new(0.14, 0.05, hgLength + 1.1), Pos = Vector3.new(0, 0.655, hgZ + 0.55), Color = BLACK, Material = Enum.Material.Metal })
	for i = 0, math.floor((hgLength + 1.1) / 0.1) - 1 do
		b:Add({ Name = "RailTooth", Size = Vector3.new(0.16, 0.03, 0.04), Pos = Vector3.new(0, 0.69, hgZ + 0.55 + (hgLength + 1.1) / 2 - 0.05 - i * 0.1), Color = BLACK, Material = Enum.Material.Metal })
	end

	-- Barrel and muzzle device
	local barrelEnd = -0.82 - hgLength
	b:Tube("Barrel", 0.11, 0.6, Vector3.new(0, 0.5, barrelEnd - 0.3), DARK_METAL)
	b:Tube("FlashHider", 0.15, 0.28, Vector3.new(0, 0.5, barrelEnd - 0.72), BLACK)
	b:Add({ Name = "FrontSight", Size = Vector3.new(0.08, 0.22, 0.08), Pos = Vector3.new(0, 0.79, hgZ - hgLength / 2 + 0.1), Color = BLACK })
	b:Attach("Muzzle", Vector3.new(0, 0.5, barrelEnd - 0.88))

	-- Accessories
	b:Add({ Name = "Foregrip", Size = Vector3.new(0.15, 0.42, 0.16), Pos = Vector3.new(0, 0.2, hgZ - 0.1), Color = POLY })
	b:Attach("LeftHand", Vector3.new(0, 0.2, hgZ - 0.1))
	b:Light(Vector3.new(0.21, 0.52, hgZ - hgLength / 2 + 0.2))
	b:Tape(Vector3.new(0.34, 0.12, 0.34), Vector3.new(0, 0.5, hgZ + hgLength / 2 - 0.15), accent)
	b:Tape(Vector3.new(0.26, 0.08, 0.62), Vector3.new(0, 0.33, 1.05), accent)
end

local BUILDERS = {}

BUILDERS.M4 = function(b, accent)
	buildAR(b, accent, { HandguardLength = 1.4 })
	b:RedDot(0.88, -0.3)
end

BUILDERS.SR25 = function(b, accent)
	buildAR(b, accent, { HandguardLength = 1.8, MagColor = BLACK })
	b:Tube("BarrelExtension", 0.11, 0.5, Vector3.new(0, 0.5, -3.25), DARK_METAL)
	b:Add({ Name = "Bipod", Size = Vector3.new(0.2, 0.12, 0.2), Pos = Vector3.new(0, 0.32, -2.4), Color = BLACK })
	b:Scope(0.92, -0.3, 1.25)
	local muzzle = b.Handle:FindFirstChild("Muzzle") :: Attachment
	muzzle.CFrame = b.Handle.CFrame:ToObjectSpace(CFrame.new(0, 0.5, -3.55))
end

BUILDERS.MP5 = function(b, accent)
	b:Add({ Name = "Receiver", Size = Vector3.new(0.24, 0.36, 1.5), Pos = Vector3.new(0, 0.42, -0.45), Color = BLACK, Material = Enum.Material.Metal })
	b:Add({ Name = "TriggerGroup", Size = Vector3.new(0.2, 0.18, 0.55), Pos = Vector3.new(0, 0.16, -0.12), Color = POLY })
	b:Add({ Name = "Mag", Size = Vector3.new(0.18, 0.55, 0.26), Pos = Vector3.new(0, -0.05, -0.85), Rot = Vector3.new(-16, 0, 0), Color = BLACK })
	b:Add({ Name = "MagLower", Size = Vector3.new(0.18, 0.4, 0.25), Pos = Vector3.new(0, -0.46, -1.08), Rot = Vector3.new(-28, 0, 0), Color = BLACK })
	b:Add({ Name = "Handguard", Size = Vector3.new(0.3, 0.32, 0.75), Pos = Vector3.new(0, 0.38, -1.5), Color = POLY })
	b:Tube("Suppressor", 0.3, 1.0, Vector3.new(0, 0.46, -2.35), BLACK, Enum.Material.Metal)
	b:Attach("Muzzle", Vector3.new(0, 0.46, -2.9))
	b:Add({ Name = "CockingTube", Size = Vector3.new(0.12, 0.12, 1.1), Pos = Vector3.new(0, 0.66, -1.3), Color = BLACK, Material = Enum.Material.Metal })
	b:Add({ Name = "CockingHandle", Size = Vector3.new(0.22, 0.06, 0.06), Pos = Vector3.new(-0.12, 0.66, -1.4), Color = BLACK })
	-- Collapsible stock
	b:Add({ Name = "StockRailL", Size = Vector3.new(0.04, 0.06, 0.85), Pos = Vector3.new(-0.1, 0.5, 0.65), Color = DARK_METAL, Material = Enum.Material.Metal })
	b:Add({ Name = "StockRailR", Size = Vector3.new(0.04, 0.06, 0.85), Pos = Vector3.new(0.1, 0.5, 0.65), Color = DARK_METAL, Material = Enum.Material.Metal })
	b:Add({ Name = "ButtPlate", Size = Vector3.new(0.26, 0.48, 0.08), Pos = Vector3.new(0, 0.4, 1.1), Color = BLACK })
	b:Add({ Name = "RearSight", Size = Vector3.new(0.18, 0.16, 0.14), Pos = Vector3.new(0, 0.7, 0.15), Color = BLACK })
	b:Add({ Name = "FrontSightHood", Size = Vector3.new(0.16, 0.2, 0.1), Pos = Vector3.new(0, 0.7, -1.82), Color = BLACK })
	b:Add({ Name = "FrontPost", Size = Vector3.new(0.025, 0.12, 0.025), Pos = Vector3.new(0, 0.72, -1.82), Color = Color3.fromRGB(240, 240, 240), Material = Enum.Material.Neon })
	b:Attach("Aim", Vector3.new(0, 0.73, 0.7))
	b:Attach("LeftHand", Vector3.new(0, 0.28, -1.5))
	b:Light(Vector3.new(0.2, 0.38, -1.62))
	b:Tape(Vector3.new(0.32, 0.1, 0.32), Vector3.new(0, 0.38, -1.25), accent)
end

BUILDERS.VSR = function(b, accent)
	b:Add({ Name = "Stock", Size = Vector3.new(0.24, 0.42, 3.4), Pos = Vector3.new(0, 0.32, -0.45), Color = Color3.fromRGB(70, 74, 60) })
	b:Add({ Name = "Butt", Size = Vector3.new(0.24, 0.62, 0.9), Pos = Vector3.new(0, 0.22, 1.1), Color = Color3.fromRGB(70, 74, 60) })
	b:Add({ Name = "Cheek", Size = Vector3.new(0.26, 0.14, 0.6), Pos = Vector3.new(0, 0.6, 0.95), Color = BLACK })
	b:Add({ Name = "ButtPad", Size = Vector3.new(0.26, 0.64, 0.08), Pos = Vector3.new(0, 0.22, 1.58), Color = BLACK, Material = Enum.Material.Fabric })
	b:Tube("Action", 0.24, 1.0, Vector3.new(0, 0.56, -0.25), DARK_METAL)
	b:Add({ Name = "BoltHandle", Size = Vector3.new(0.34, 0.05, 0.05), Pos = Vector3.new(0.18, 0.55, 0.12), Color = METAL, Material = Enum.Material.Metal })
	b:Add({ Name = "BoltKnob", Shape = Enum.PartType.Ball, Size = Vector3.new(0.1, 0.1, 0.1), Pos = Vector3.new(0.36, 0.52, 0.12), Color = METAL, Material = Enum.Material.Metal })
	b:Tube("OuterBarrel", 0.15, 2.4, Vector3.new(0, 0.56, -1.95), BLACK, Enum.Material.Metal)
	b:Tube("Silencer", 0.24, 0.8, Vector3.new(0, 0.56, -3.5), BLACK, Enum.Material.Metal)
	b:Attach("Muzzle", Vector3.new(0, 0.56, -3.92))
	b:Add({ Name = "Mag", Size = Vector3.new(0.16, 0.28, 0.3), Pos = Vector3.new(0, 0.02, -0.55), Color = BLACK })
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.36), Pos = Vector3.new(0, 0.06, -0.12), Color = BLACK })
	b:Attach("LeftHand", Vector3.new(0, 0.25, -1.3))
	b:Scope(0.92, -0.25, 1.5)
	b:Tape(Vector3.new(0.26, 0.44, 0.12), Vector3.new(0, 0.32, -1.6), accent)
	b:Tape(Vector3.new(0.26, 0.64, 0.12), Vector3.new(0, 0.22, 0.75), accent)
end

BUILDERS.M870 = function(b, accent)
	b:Add({ Name = "Receiver", Size = Vector3.new(0.26, 0.4, 1.0), Pos = Vector3.new(0, 0.42, -0.3), Color = BLACK, Material = Enum.Material.Metal })
	b:Add({ Name = "Stock", Size = Vector3.new(0.24, 0.42, 1.0), Pos = Vector3.new(0, 0.32, 0.65), Rot = Vector3.new(6, 0, 0), Color = WOOD, Material = Enum.Material.Wood })
	b:Add({ Name = "ButtPad", Size = Vector3.new(0.26, 0.5, 0.08), Pos = Vector3.new(0, 0.26, 1.18), Rot = Vector3.new(6, 0, 0), Color = BLACK, Material = Enum.Material.Fabric })
	b:Tube("Barrel", 0.15, 2.0, Vector3.new(0, 0.55, -1.8), DARK_METAL)
	b:Tube("MagTube", 0.15, 1.6, Vector3.new(0, 0.36, -1.6), DARK_METAL)
	b:Add({ Name = "Pump", Size = Vector3.new(0.28, 0.28, 0.75), Pos = Vector3.new(0, 0.38, -1.45), Color = WOOD, Material = Enum.Material.Wood })
	for i = 0, 4 do
		b:Add({ Name = "PumpGroove", Size = Vector3.new(0.29, 0.04, 0.04), Pos = Vector3.new(0, 0.3, -1.2 - i * 0.12), Color = Color3.fromRGB(70, 44, 26) })
	end
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.36), Pos = Vector3.new(0, 0.12, -0.15), Color = BLACK })
	b:Add({ Name = "Bead", Shape = Enum.PartType.Ball, Size = Vector3.new(0.06, 0.06, 0.06), Pos = Vector3.new(0, 0.66, -2.72), Color = Color3.fromRGB(255, 200, 60), Material = Enum.Material.Neon })
	b:Add({ Name = "Rib", Size = Vector3.new(0.05, 0.04, 2.0), Pos = Vector3.new(0, 0.64, -1.8), Color = BLACK })
	b:Add({ Name = "ShellCarrier", Size = Vector3.new(0.04, 0.22, 0.5), Pos = Vector3.new(-0.15, 0.42, -0.3), Color = Color3.fromRGB(160, 30, 30) })
	b:Attach("Muzzle", Vector3.new(0, 0.55, -2.82))
	b:Attach("Aim", Vector3.new(0, 0.68, 0.6))
	b:Attach("LeftHand", Vector3.new(0, 0.3, -1.45))
	b:Tape(Vector3.new(0.3, 0.3, 0.12), Vector3.new(0, 0.38, -1.92), accent)
end

BUILDERS.G17 = function(b, accent)
	b.Handle.Size = Vector3.new(0.2, 0.55, 0.3)
	b:Add({ Name = "Frame", Size = Vector3.new(0.18, 0.14, 0.8), Pos = Vector3.new(0, 0.2, -0.3), Color = POLY })
	b:Add({ Name = "Slide", Size = Vector3.new(0.2, 0.22, 0.9), Pos = Vector3.new(0, 0.38, -0.32), Color = DARK_METAL, Material = Enum.Material.Metal })
	for i = 0, 4 do
		b:Add({ Name = "Serration", Size = Vector3.new(0.21, 0.16, 0.025), Pos = Vector3.new(0, 0.38, 0.0 + i * 0.05), Color = BLACK })
	end
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.32), Pos = Vector3.new(0, 0.07, -0.3), Color = POLY })
	b:Add({ Name = "FrontSight", Size = Vector3.new(0.04, 0.06, 0.05), Pos = Vector3.new(0, 0.52, -0.72), Color = Color3.fromRGB(240, 240, 240), Material = Enum.Material.Neon })
	b:Add({ Name = "RearSightL", Size = Vector3.new(0.05, 0.06, 0.06), Pos = Vector3.new(-0.06, 0.52, 0.08), Color = BLACK })
	b:Add({ Name = "RearSightR", Size = Vector3.new(0.05, 0.06, 0.06), Pos = Vector3.new(0.06, 0.52, 0.08), Color = BLACK })
	b:Add({ Name = "MagBase", Size = Vector3.new(0.22, 0.06, 0.32), Pos = Vector3.new(0, -0.34, 0.12), Rot = Vector3.new(-14, 0, 0), Color = BLACK })
	b:Attach("Muzzle", Vector3.new(0, 0.38, -0.8))
	b:Attach("Aim", Vector3.new(0, 0.54, 0.75))
	b:Attach("LeftHand", Vector3.new(-0.05, -0.05, 0.05))
	b:Tape(Vector3.new(0.21, 0.1, 0.32), Vector3.new(0, -0.2, 0.08), accent)
end

function GunBuilder.Build(weaponId: string, accent: Color3?): Model
	local build = BUILDERS[weaponId]
	assert(build, "No model for weapon " .. tostring(weaponId))
	local b = newBuilder(weaponId)
	build(b, accent or Color3.fromRGB(200, 200, 200))
	return b.Model
end

function GunBuilder.BuildGrenade(accent: Color3?): Model
	local b = newBuilder("Grenade")
	local handle = b.Handle
	handle.Shape = Enum.PartType.Cylinder
	handle.Size = Vector3.new(0.6, 0.38, 0.38)
	handle.CFrame = CFrame.Angles(0, 0, math.rad(90))
	handle.Color = Color3.fromRGB(70, 78, 56)
	b:Add({ Name = "Cap", Size = Vector3.new(0.22, 0.12, 0.22), Pos = Vector3.new(0, 0.36, 0), Color = BLACK })
	b:Add({ Name = "Lever", Size = Vector3.new(0.08, 0.5, 0.04), Pos = Vector3.new(0.2, 0.15, 0), Rot = Vector3.new(0, 0, -8), Color = METAL, Material = Enum.Material.Metal })
	b:Add({ Name = "Ring", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.03, 0.16, 0.16), Pos = Vector3.new(-0.16, 0.38, 0), Color = METAL, Material = Enum.Material.Metal })
	b:Tape(Vector3.new(0.4, 0.08, 0.4), Vector3.new(0, -0.1, 0), accent or Color3.new(1, 1, 1))
	b:Attach("LeftHand", Vector3.new(0, 0, 0))
	b:Attach("Aim", Vector3.new(0, 0.3, 1.2))
	b:Attach("Muzzle", Vector3.new(0, 0.3, -0.3))
	return b.Model
end

-- Wraps a gun model in a Tool for third-person holding.
function GunBuilder.BuildTool(weaponId: string, accent: Color3?): Tool
	local model = weaponId == "Grenade" and GunBuilder.BuildGrenade(accent) or GunBuilder.Build(weaponId, accent)
	local tool = Instance.new("Tool")
	tool.Name = weaponId
	tool.CanBeDropped = false
	tool.RequiresHandle = true
	tool.ManualActivationOnly = true
	tool:SetAttribute("WeaponId", weaponId)

	-- Rotate the tilted grip back so the barrel points straight ahead.
	local handle = model.PrimaryPart :: BasePart
	tool.Grip = handle.CFrame:Inverse()

	for _, child in model:GetChildren() do
		child.Parent = tool
	end
	model:Destroy()
	return tool
end

return GunBuilder
