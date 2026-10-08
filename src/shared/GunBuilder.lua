--[[
	Builds every weapon model.

	Two sources, picked automatically:
	  1. Imported meshes. If ReplicatedStorage.GunModels.<ID> exists (the
	     Blender .glb files imported with Studio's 3D Importer) the gun is
	     assembled from those MeshParts using GunMeshData.
	  2. Procedural parts. Otherwise the gun is built from bevel-free parts so
	     the game always works with zero uploads.

	Convention: the Handle (pistol grip) sits at the origin, the barrel points
	down -Z and +Y is up, matching Roblox's Tool.Grip. Every part carries a
	"Role" attribute (Primary, Secondary, Metal, Wood, Mag, Slide, Bolt, Pump,
	Accent, Glass) so finishes recolour the right pieces and the viewmodel can
	animate magazines, slides and bolts.

	Attachments on the Handle:
	  Muzzle      where BBs leave the barrel (moves with muzzle devices)
	  Aim         eye position when aiming (moves with optics)
	  LeftHand    support-hand position (moves with grips)
	  MagWell     where the magazine seats
	  LaserEmitter  front of the laser module, when fitted
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Weapons = require(script.Parent.Weapons)

local meshDataModule = script.Parent:FindFirstChild("GunMeshData")
local MeshData = meshDataModule and require(meshDataModule) :: any or { Guns = {}, Attachments = {} }

local GunBuilder = {}

local BLACK = Color3.fromRGB(26, 27, 29)
local METAL = Color3.fromRGB(58, 60, 64)
local DARK_METAL = Color3.fromRGB(44, 45, 48)
local FDE = Color3.fromRGB(150, 128, 94)
local WOOD = Color3.fromRGB(110, 64, 34)
local GLASS = Color3.fromRGB(120, 170, 200)

local ROLE_MATERIAL = {
	Primary = Enum.Material.SmoothPlastic,
	Secondary = Enum.Material.SmoothPlastic,
	Metal = Enum.Material.Metal,
	Slide = Enum.Material.Metal,
	Bolt = Enum.Material.Metal,
	Wood = Enum.Material.Wood,
	Pump = Enum.Material.Wood,
	Mag = Enum.Material.SmoothPlastic,
	Accent = Enum.Material.Fabric,
	Glass = Enum.Material.Glass,
}

type Spec = {
	Name: string?,
	Role: string?,
	Size: Vector3,
	Pos: Vector3,
	Rot: Vector3?,
	Color: Color3?,
	Material: Enum.Material?,
	Shape: Enum.PartType?,
	Transparency: number?,
	Reflectance: number?,
	Neon: boolean?,
}

local function rotation(rot: Vector3?): CFrame
	if rot == nil then
		return CFrame.identity
	end
	local r = rot :: Vector3
	return CFrame.Angles(math.rad(r.X), math.rad(r.Y), math.rad(r.Z))
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

---------------------------------------------------------------------------
-- Builder
---------------------------------------------------------------------------

local Builder = {}
Builder.__index = Builder

local function newBuilder(name: string, tilt: number?)
	local model = Instance.new("Model")
	model.Name = name

	local handle = Instance.new("Part")
	handle.Name = "Handle"
	handle.Size = Vector3.new(0.22, 0.55, 0.3)
	handle.CFrame = CFrame.Angles(math.rad(tilt or -14), 0, 0)
	handle.Color = BLACK
	handle.Material = Enum.Material.SmoothPlastic
	handle:SetAttribute("Role", "Secondary")
	cosmetic(handle)
	handle.Parent = model
	model.PrimaryPart = handle

	return setmetatable({ Model = model, Handle = handle }, Builder)
end

function Builder:Add(spec: Spec): BasePart
	local part = Instance.new("Part")
	part.Name = spec.Name or "Detail"
	part.Shape = spec.Shape or Enum.PartType.Block
	part.Size = spec.Size
	part.CFrame = CFrame.new(spec.Pos) * rotation(spec.Rot)
	local role = spec.Role or "Secondary"
	part:SetAttribute("Role", role)
	part.Color = spec.Color or BLACK
	part.Material = spec.Material or (spec.Neon and Enum.Material.Neon) or ROLE_MATERIAL[role] or Enum.Material.SmoothPlastic
	part.Transparency = spec.Transparency or 0
	part.Reflectance = spec.Reflectance or 0
	if spec.Neon then
		part:SetAttribute("Fixed", true) -- never recoloured by finishes
	end
	cosmetic(part)
	part.Parent = self.Model

	local weld = Instance.new("WeldConstraint")
	weld.Part0 = self.Handle
	weld.Part1 = part
	weld.Parent = part
	return part
end

-- Cylinder lying along the Z axis (Roblox cylinders run along X by default).
function Builder:Tube(name: string, diameter: number, length: number, pos: Vector3, role: string?, color: Color3?)
	return self:Add({
		Name = name,
		Role = role or "Metal",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(length, diameter, diameter),
		Pos = pos,
		Rot = Vector3.new(0, 90, 0),
		Color = color or METAL,
	})
end

-- Attachments are stored in model space regardless of the handle's tilt.
function Builder:Attach(name: string, pos: Vector3)
	local existing = self.Handle:FindFirstChild(name) :: Attachment?
	local a = existing or Instance.new("Attachment")
	a.Name = name
	a.CFrame = self.Handle.CFrame:ToObjectSpace(CFrame.new(pos))
	a.Parent = self.Handle
	return a
end

function Builder:Point(name: string): Vector3?
	local a = self.Handle:FindFirstChild(name) :: Attachment?
	return a and (self.Handle.CFrame * a.CFrame).Position or nil
end

function Builder:Tape(size: Vector3, pos: Vector3)
	return self:Add({ Name = "TeamTape", Role = "Accent", Size = size, Pos = pos })
end

-- AR-style magazine: straight upper, angled lower, base plate.
function Builder:CurvedMag(top: Vector3, color: Color3, scale: number?)
	local s = scale or 1
	self:Add({ Name = "Mag", Role = "Mag", Color = color, Size = Vector3.new(0.2, 0.5 * s, 0.34), Pos = top + Vector3.new(0, -0.27 * s, -0.04), Rot = Vector3.new(-8, 0, 0) })
	self:Add({ Name = "MagLower", Role = "Mag", Color = color, Size = Vector3.new(0.2, 0.36 * s, 0.33), Pos = top + Vector3.new(0, -0.65 * s, -0.14 * s), Rot = Vector3.new(-20, 0, 0) })
	self:Add({ Name = "MagBase", Role = "Mag", Color = BLACK, Size = Vector3.new(0.23, 0.06, 0.37), Pos = top + Vector3.new(0, -0.84 * s, -0.21 * s), Rot = Vector3.new(-20, 0, 0) })
	self:Attach("MagWell", top)
end

---------------------------------------------------------------------------
-- Procedural guns
---------------------------------------------------------------------------

local function arReceiver(b, opts)
	local magColor = opts.MagColor or FDE
	b:Add({ Name = "Lower", Role = "Primary", Size = Vector3.new(0.24, 0.3, 1.0), Pos = Vector3.new(0, 0.24, -0.2) })
	b:Add({ Name = "Upper", Role = "Primary", Size = Vector3.new(0.26, 0.26, 1.15), Pos = Vector3.new(0, 0.5, -0.25), Material = Enum.Material.Metal })
	b:Add({ Name = "ChargingHandle", Role = "Metal", Color = BLACK, Size = Vector3.new(0.3, 0.06, 0.12), Pos = Vector3.new(0, 0.6, 0.28) })
	b:Add({ Name = "EjectionPort", Role = "Metal", Color = Color3.fromRGB(15, 15, 15), Size = Vector3.new(0.02, 0.1, 0.3), Pos = Vector3.new(0.135, 0.5, -0.2) })
	b:Add({ Name = "ForwardAssist", Role = "Metal", Size = Vector3.new(0.08, 0.08, 0.14), Pos = Vector3.new(0.15, 0.55, 0.05), Color = DARK_METAL })
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.38), Pos = Vector3.new(0, 0.02, -0.15) })
	b:Add({ Name = "Trigger", Role = "Metal", Size = Vector3.new(0.04, 0.14, 0.04), Pos = Vector3.new(0, 0.1, -0.12), Color = DARK_METAL })
	b:Add({ Name = "MagWellHousing", Role = "Primary", Size = Vector3.new(0.26, 0.2, 0.36), Pos = Vector3.new(0, 0.05, -0.55) })
	b:CurvedMag(Vector3.new(0, 0.0, -0.56), magColor)

	-- Stock
	b:Tube("BufferTube", 0.15, 0.75, Vector3.new(0, 0.46, 0.65), "Metal", BLACK)
	b:Add({ Name = "Stock", Size = Vector3.new(0.24, 0.36, 0.6), Pos = Vector3.new(0, 0.38, 1.05) })
	b:Add({ Name = "StockCheek", Size = Vector3.new(0.26, 0.1, 0.5), Pos = Vector3.new(0, 0.58, 1.05) })
	b:Add({ Name = "ButtPad", Role = "Metal", Color = Color3.fromRGB(18, 18, 18), Material = Enum.Material.Fabric, Size = Vector3.new(0.26, 0.5, 0.07), Pos = Vector3.new(0, 0.33, 1.38) })
	b:Tape(Vector3.new(0.26, 0.08, 0.62), Vector3.new(0, 0.33, 1.05))

	-- Handguard with slots and a full-length top rail
	local hgLength = opts.HandguardLength or 1.4
	local hgZ = -0.82 - hgLength / 2
	b:Add({ Name = "Handguard", Role = "Primary", Size = Vector3.new(0.32, 0.32, hgLength), Pos = Vector3.new(0, 0.5, hgZ) })
	for i = 0, math.floor(hgLength / 0.28) - 1 do
		local z = -0.95 - i * 0.28
		b:Add({ Name = "Slot", Role = "Metal", Color = Color3.fromRGB(16, 16, 16), Size = Vector3.new(0.33, 0.06, 0.14), Pos = Vector3.new(0, 0.46, z) })
	end
	local railLength = hgLength + 1.1
	b:Add({ Name = "TopRail", Role = "Metal", Color = BLACK, Size = Vector3.new(0.14, 0.05, railLength), Pos = Vector3.new(0, 0.655, hgZ + 0.55) })
	for i = 0, math.floor(railLength / 0.1) - 1 do
		b:Add({ Name = "RailTooth", Role = "Metal", Color = BLACK, Size = Vector3.new(0.16, 0.03, 0.04), Pos = Vector3.new(0, 0.69, hgZ + 0.55 + railLength / 2 - 0.05 - i * 0.1) })
	end

	local barrelEnd = -0.82 - hgLength
	b:Tube("Barrel", 0.11, 0.6, Vector3.new(0, 0.5, barrelEnd - 0.3), "Metal", DARK_METAL)
	b:Tube("FlashHider", 0.15, 0.28, Vector3.new(0, 0.5, barrelEnd - 0.72), "Metal", BLACK)
	b:Add({ Name = "FrontSight", Size = Vector3.new(0.08, 0.2, 0.08), Pos = Vector3.new(0, 0.79, hgZ - hgLength / 2 + 0.1) })
	b:Add({ Name = "RearSight", Size = Vector3.new(0.12, 0.14, 0.1), Pos = Vector3.new(0, 0.76, 0.2) })

	b:Attach("Muzzle", Vector3.new(0, 0.5, barrelEnd - 0.88))
	b:Attach("MuzzleMount", Vector3.new(0, 0.5, barrelEnd - 0.6))
	b:Attach("OpticMount", Vector3.new(0, 0.68, -0.3))
	b:Attach("UnderMount", Vector3.new(0, 0.34, hgZ - 0.1))
	b:Attach("SideMount", Vector3.new(0.16, 0.5, hgZ - hgLength / 2 + 0.25))
	b:Attach("LeftHand", Vector3.new(0, 0.32, hgZ - 0.1))
	b:Attach("Aim", Vector3.new(0, 0.79, 0.75))
	b:Tape(Vector3.new(0.34, 0.12, 0.34), Vector3.new(0, 0.5, hgZ + hgLength / 2 - 0.15))
	return barrelEnd
end

local BUILDERS = {}

BUILDERS.M4 = function(b)
	arReceiver(b, { HandguardLength = 1.4 })
end

BUILDERS.SR25 = function(b)
	local barrelEnd = arReceiver(b, { HandguardLength = 1.8, MagColor = BLACK })
	b:Tube("BarrelExtension", 0.11, 0.5, Vector3.new(0, 0.5, barrelEnd - 0.4), "Metal", DARK_METAL)
	b:Add({ Name = "Bipod", Role = "Metal", Size = Vector3.new(0.2, 0.12, 0.2), Pos = Vector3.new(0, 0.32, -2.4) })
	b:Attach("Muzzle", Vector3.new(0, 0.5, barrelEnd - 1.2))
	b:Attach("MuzzleMount", Vector3.new(0, 0.5, barrelEnd - 0.65))
end

BUILDERS.M249 = function(b)
	b:Add({ Name = "Receiver", Role = "Primary", Size = Vector3.new(0.34, 0.42, 1.6), Pos = Vector3.new(0, 0.48, -0.3), Material = Enum.Material.Metal })
	b:Add({ Name = "FeedCover", Role = "Primary", Size = Vector3.new(0.36, 0.1, 0.9), Pos = Vector3.new(0, 0.74, -0.2) })
	b:Add({ Name = "CarryHandle", Role = "Metal", Size = Vector3.new(0.06, 0.32, 0.5), Pos = Vector3.new(0.2, 0.8, -1.15), Rot = Vector3.new(0, 0, 0) })
	b:Add({ Name = "Stock", Size = Vector3.new(0.26, 0.42, 0.9), Pos = Vector3.new(0, 0.38, 0.9) })
	b:Add({ Name = "ButtPad", Role = "Metal", Color = Color3.fromRGB(18, 18, 18), Size = Vector3.new(0.28, 0.5, 0.08), Pos = Vector3.new(0, 0.36, 1.36) })
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.38), Pos = Vector3.new(0, 0.05, -0.15) })
	b:Add({ Name = "Handguard", Role = "Primary", Size = Vector3.new(0.34, 0.3, 0.9), Pos = Vector3.new(0, 0.36, -1.5) })
	b:Tube("Barrel", 0.14, 2.2, Vector3.new(0, 0.5, -2.6), "Metal", DARK_METAL)
	b:Tube("GasTube", 0.1, 1.4, Vector3.new(0, 0.32, -2.3), "Metal", BLACK)
	b:Tube("FlashHider", 0.18, 0.3, Vector3.new(0, 0.5, -3.8), "Metal", BLACK)
	-- Box magazine hanging off the left side
	b:Add({ Name = "BoxMag", Role = "Mag", Color = Color3.fromRGB(70, 76, 56), Material = Enum.Material.Fabric, Size = Vector3.new(0.5, 0.6, 0.55), Pos = Vector3.new(-0.32, 0.12, -0.55) })
	b:Add({ Name = "BoxMagLid", Role = "Mag", Color = BLACK, Size = Vector3.new(0.52, 0.06, 0.57), Pos = Vector3.new(-0.32, 0.44, -0.55) })
	b:Attach("MagWell", Vector3.new(-0.32, 0.42, -0.55))
	-- Bipod legs folded
	for _, x in { -0.08, 0.08 } do
		b:Add({ Name = "BipodLeg", Role = "Metal", Size = Vector3.new(0.05, 0.05, 0.9), Pos = Vector3.new(x, 0.38, -3.0) })
	end
	b:Add({ Name = "TopRail", Role = "Metal", Size = Vector3.new(0.14, 0.05, 0.9), Pos = Vector3.new(0, 0.81, -0.2) })
	b:Attach("Muzzle", Vector3.new(0, 0.5, -3.95))
	b:Attach("OpticMount", Vector3.new(0, 0.83, -0.25))
	b:Attach("SideMount", Vector3.new(0.18, 0.36, -1.7))
	b:Attach("LeftHand", Vector3.new(0, 0.26, -1.5))
	b:Attach("Aim", Vector3.new(0, 0.95, 0.75))
	b:Add({ Name = "RearSight", Size = Vector3.new(0.12, 0.14, 0.1), Pos = Vector3.new(0, 0.88, 0.05) })
	b:Add({ Name = "FrontSight", Size = Vector3.new(0.06, 0.32, 0.06), Pos = Vector3.new(0, 0.7, -3.4) })
	b:Tape(Vector3.new(0.36, 0.32, 0.12), Vector3.new(0, 0.36, -1.2))
end

BUILDERS.AK74 = function(b)
	b:Add({ Name = "Receiver", Role = "Primary", Size = Vector3.new(0.24, 0.32, 1.25), Pos = Vector3.new(0, 0.42, -0.35), Material = Enum.Material.Metal })
	b:Add({ Name = "DustCover", Role = "Primary", Size = Vector3.new(0.22, 0.12, 1.1), Pos = Vector3.new(0, 0.62, -0.25), Material = Enum.Material.Metal })
	b:Add({ Name = "SafetyLever", Role = "Metal", Size = Vector3.new(0.02, 0.1, 0.6), Pos = Vector3.new(0.13, 0.46, -0.1) })
	b:Add({ Name = "ChargingHandle", Role = "Metal", Size = Vector3.new(0.18, 0.06, 0.06), Pos = Vector3.new(0.16, 0.54, -0.55) })
	b:Add({ Name = "TriggerGuard", Role = "Metal", Size = Vector3.new(0.06, 0.05, 0.38), Pos = Vector3.new(0, 0.05, -0.18) })
	-- Wooden furniture
	b:Add({ Name = "Stock", Role = "Wood", Color = WOOD, Size = Vector3.new(0.22, 0.34, 1.1), Pos = Vector3.new(0, 0.32, 0.75), Rot = Vector3.new(8, 0, 0) })
	b:Add({ Name = "Butt", Role = "Wood", Color = WOOD, Size = Vector3.new(0.24, 0.52, 0.3), Pos = Vector3.new(0, 0.18, 1.22) })
	b:Add({ Name = "ButtPlate", Role = "Metal", Size = Vector3.new(0.25, 0.54, 0.05), Pos = Vector3.new(0, 0.18, 1.38) })
	b:Add({ Name = "LowerHandguard", Role = "Wood", Color = WOOD, Size = Vector3.new(0.3, 0.26, 0.8), Pos = Vector3.new(0, 0.38, -1.4) })
	b:Add({ Name = "UpperHandguard", Role = "Wood", Color = WOOD, Size = Vector3.new(0.22, 0.14, 0.6), Pos = Vector3.new(0, 0.62, -1.3) })
	b:Tube("GasTube", 0.1, 0.9, Vector3.new(0, 0.62, -1.45), "Metal", DARK_METAL)
	b:Tube("Barrel", 0.1, 1.5, Vector3.new(0, 0.46, -2.1), "Metal", DARK_METAL)
	b:Add({ Name = "FrontSightBlock", Role = "Metal", Size = Vector3.new(0.14, 0.32, 0.12), Pos = Vector3.new(0, 0.6, -2.55) })
	b:Tube("MuzzleBrake", 0.17, 0.32, Vector3.new(0, 0.46, -2.95), "Metal", DARK_METAL)
	b:Add({ Name = "RearSight", Role = "Metal", Size = Vector3.new(0.14, 0.1, 0.3), Pos = Vector3.new(0, 0.68, -0.95) })
	-- Curved mag in classic plum polymer
	local magColor = Color3.fromRGB(110, 52, 38)
	b:Add({ Name = "Mag", Role = "Mag", Color = magColor, Size = Vector3.new(0.18, 0.42, 0.34), Pos = Vector3.new(0, 0.05, -0.85), Rot = Vector3.new(-12, 0, 0) })
	b:Add({ Name = "MagMid", Role = "Mag", Color = magColor, Size = Vector3.new(0.18, 0.38, 0.33), Pos = Vector3.new(0, -0.3, -1.0), Rot = Vector3.new(-26, 0, 0) })
	b:Add({ Name = "MagLower", Role = "Mag", Color = magColor, Size = Vector3.new(0.18, 0.32, 0.32), Pos = Vector3.new(0, -0.6, -1.2), Rot = Vector3.new(-40, 0, 0) })
	b:Attach("MagWell", Vector3.new(0, 0.24, -0.82))
	b:Attach("Muzzle", Vector3.new(0, 0.46, -3.12))
	b:Attach("MuzzleMount", Vector3.new(0, 0.46, -2.85))
	b:Attach("OpticMount", Vector3.new(0, 0.7, -0.35)) -- side-rail riser
	b:Attach("UnderMount", Vector3.new(0, 0.25, -1.45))
	b:Attach("SideMount", Vector3.new(0.16, 0.38, -1.6))
	b:Attach("LeftHand", Vector3.new(0, 0.28, -1.4))
	b:Attach("Aim", Vector3.new(0, 0.76, 0.2))
	b:Tape(Vector3.new(0.32, 0.28, 0.1), Vector3.new(0, 0.38, -1.05))
end

BUILDERS.MP5 = function(b)
	b:Add({ Name = "Receiver", Role = "Primary", Size = Vector3.new(0.24, 0.36, 1.5), Pos = Vector3.new(0, 0.42, -0.45), Material = Enum.Material.Metal })
	b:Add({ Name = "TriggerGroup", Size = Vector3.new(0.2, 0.18, 0.55), Pos = Vector3.new(0, 0.16, -0.12) })
	b:Add({ Name = "Mag", Role = "Mag", Size = Vector3.new(0.18, 0.55, 0.26), Pos = Vector3.new(0, -0.05, -0.85), Rot = Vector3.new(-16, 0, 0) })
	b:Add({ Name = "MagLower", Role = "Mag", Size = Vector3.new(0.18, 0.4, 0.25), Pos = Vector3.new(0, -0.46, -1.08), Rot = Vector3.new(-28, 0, 0) })
	b:Attach("MagWell", Vector3.new(0, 0.22, -0.8))
	b:Add({ Name = "Handguard", Size = Vector3.new(0.3, 0.32, 0.75), Pos = Vector3.new(0, 0.38, -1.5) })
	b:Tube("Suppressor", 0.3, 1.0, Vector3.new(0, 0.46, -2.35), "Metal", BLACK)
	b:Add({ Name = "CockingTube", Role = "Metal", Color = BLACK, Size = Vector3.new(0.12, 0.12, 1.1), Pos = Vector3.new(0, 0.66, -1.3) })
	b:Add({ Name = "CockingHandle", Role = "Metal", Color = BLACK, Size = Vector3.new(0.22, 0.06, 0.06), Pos = Vector3.new(-0.12, 0.66, -1.4) })
	b:Add({ Name = "StockRailL", Role = "Metal", Color = DARK_METAL, Size = Vector3.new(0.04, 0.06, 0.85), Pos = Vector3.new(-0.1, 0.5, 0.65) })
	b:Add({ Name = "StockRailR", Role = "Metal", Color = DARK_METAL, Size = Vector3.new(0.04, 0.06, 0.85), Pos = Vector3.new(0.1, 0.5, 0.65) })
	b:Add({ Name = "ButtPlate", Size = Vector3.new(0.26, 0.48, 0.08), Pos = Vector3.new(0, 0.4, 1.1) })
	b:Add({ Name = "RearSight", Size = Vector3.new(0.18, 0.16, 0.14), Pos = Vector3.new(0, 0.7, 0.15) })
	b:Add({ Name = "FrontSightHood", Size = Vector3.new(0.16, 0.2, 0.1), Pos = Vector3.new(0, 0.7, -1.82) })
	b:Add({ Name = "FrontPost", Size = Vector3.new(0.025, 0.12, 0.025), Pos = Vector3.new(0, 0.72, -1.82), Color = Color3.fromRGB(240, 240, 240), Neon = true })
	b:Add({ Name = "ClawMount", Role = "Metal", Size = Vector3.new(0.14, 0.06, 0.5), Pos = Vector3.new(0, 0.63, -0.45) })
	b:Attach("Muzzle", Vector3.new(0, 0.46, -2.9))
	b:Attach("OpticMount", Vector3.new(0, 0.66, -0.45))
	b:Attach("SideMount", Vector3.new(0.16, 0.38, -1.6))
	b:Attach("Aim", Vector3.new(0, 0.73, 0.7))
	b:Attach("LeftHand", Vector3.new(0, 0.28, -1.5))
	b:Tape(Vector3.new(0.32, 0.1, 0.32), Vector3.new(0, 0.38, -1.25))
end

BUILDERS.VECTOR = function(b)
	b:Add({ Name = "Upper", Role = "Primary", Size = Vector3.new(0.26, 0.3, 1.6), Pos = Vector3.new(0, 0.55, -0.6) })
	b:Add({ Name = "LowerBlock", Role = "Primary", Size = Vector3.new(0.26, 0.42, 0.7), Pos = Vector3.new(0, 0.22, -0.65), Rot = Vector3.new(-25, 0, 0) })
	b:Add({ Name = "Chin", Role = "Primary", Size = Vector3.new(0.24, 0.24, 0.45), Pos = Vector3.new(0, 0.3, -1.25) })
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.36), Pos = Vector3.new(0, 0.02, -0.12) })
	b:Add({ Name = "Mag", Role = "Mag", Size = Vector3.new(0.18, 0.75, 0.24), Pos = Vector3.new(0, -0.15, -0.35), Rot = Vector3.new(-6, 0, 0) })
	b:Add({ Name = "MagBase", Role = "Mag", Size = Vector3.new(0.21, 0.06, 0.27), Pos = Vector3.new(0, -0.53, -0.38) })
	b:Attach("MagWell", Vector3.new(0, 0.22, -0.32))
	b:Tube("BarrelShroud", 0.16, 0.45, Vector3.new(0, 0.55, -1.6), "Metal", BLACK)
	b:Tube("StockTube", 0.13, 0.6, Vector3.new(0, 0.52, 0.5), "Metal", BLACK)
	b:Add({ Name = "Stock", Size = Vector3.new(0.22, 0.4, 0.5), Pos = Vector3.new(0, 0.45, 0.95) })
	b:Add({ Name = "TopRail", Role = "Metal", Size = Vector3.new(0.14, 0.05, 1.3), Pos = Vector3.new(0, 0.72, -0.6) })
	b:Add({ Name = "FoldingSightRear", Role = "Metal", Size = Vector3.new(0.12, 0.12, 0.08), Pos = Vector3.new(0, 0.8, 0.0) })
	b:Add({ Name = "FoldingSightFront", Role = "Metal", Size = Vector3.new(0.06, 0.14, 0.06), Pos = Vector3.new(0, 0.81, -1.2) })
	b:Attach("Muzzle", Vector3.new(0, 0.55, -1.85))
	b:Attach("MuzzleMount", Vector3.new(0, 0.55, -1.82))
	b:Attach("OpticMount", Vector3.new(0, 0.75, -0.5))
	b:Attach("UnderMount", Vector3.new(0, 0.18, -1.3))
	b:Attach("SideMount", Vector3.new(0.15, 0.55, -1.1))
	b:Attach("LeftHand", Vector3.new(0, 0.15, -1.25))
	b:Attach("Aim", Vector3.new(0, 0.87, 0.6))
	b:Tape(Vector3.new(0.28, 0.32, 0.1), Vector3.new(0, 0.55, -1.05))
end

BUILDERS.MP7 = function(b)
	b:Add({ Name = "Body", Role = "Primary", Size = Vector3.new(0.24, 0.34, 1.2), Pos = Vector3.new(0, 0.48, -0.4) })
	b:Add({ Name = "Grip", Role = "Primary", Size = Vector3.new(0.22, 0.5, 0.3), Pos = Vector3.new(0, 0.05, -0.02), Rot = Vector3.new(-10, 0, 0) })
	b:Add({ Name = "Mag", Role = "Mag", Size = Vector3.new(0.16, 0.4, 0.22), Pos = Vector3.new(0, -0.32, 0.0), Rot = Vector3.new(-10, 0, 0) })
	b:Attach("MagWell", Vector3.new(0, -0.12, 0.0))
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.3), Pos = Vector3.new(0, 0.18, -0.25) })
	b:Add({ Name = "FoldGrip", Size = Vector3.new(0.14, 0.32, 0.14), Pos = Vector3.new(0, 0.15, -0.9) })
	b:Tube("Barrel", 0.1, 0.4, Vector3.new(0, 0.5, -1.15), "Metal", DARK_METAL)
	b:Add({ Name = "StockRails", Role = "Metal", Size = Vector3.new(0.22, 0.05, 0.7), Pos = Vector3.new(0, 0.5, 0.5) })
	b:Add({ Name = "ButtPad", Size = Vector3.new(0.24, 0.32, 0.08), Pos = Vector3.new(0, 0.45, 0.85) })
	b:Add({ Name = "TopRail", Role = "Metal", Size = Vector3.new(0.14, 0.05, 1.0), Pos = Vector3.new(0, 0.67, -0.4) })
	b:Attach("Muzzle", Vector3.new(0, 0.5, -1.35))
	b:Attach("MuzzleMount", Vector3.new(0, 0.5, -1.33))
	b:Attach("OpticMount", Vector3.new(0, 0.69, -0.35))
	b:Attach("SideMount", Vector3.new(0.14, 0.48, -0.8))
	b:Attach("LeftHand", Vector3.new(0, 0.1, -0.9))
	b:Attach("Aim", Vector3.new(0, 0.82, 0.5))
	b:Add({ Name = "RearSight", Role = "Metal", Size = Vector3.new(0.1, 0.1, 0.06), Pos = Vector3.new(0, 0.74, 0.0) })
	b:Tape(Vector3.new(0.26, 0.1, 0.3), Vector3.new(0, 0.5, -0.75))
end

BUILDERS.P90 = function(b)
	b:Add({ Name = "Shell", Role = "Primary", Size = Vector3.new(0.3, 0.55, 1.6), Pos = Vector3.new(0, 0.35, -0.15) })
	b:Add({ Name = "ThumbHole", Role = "Metal", Color = Color3.fromRGB(14, 14, 14), Size = Vector3.new(0.32, 0.22, 0.3), Pos = Vector3.new(0, 0.15, -0.35) })
	b:Add({ Name = "ButtCurve", Role = "Primary", Size = Vector3.new(0.28, 0.4, 0.3), Pos = Vector3.new(0, 0.25, 0.72), Rot = Vector3.new(20, 0, 0) })
	b:Add({ Name = "Mag", Role = "Mag", Color = Color3.fromRGB(150, 160, 160), Transparency = 0.35, Material = Enum.Material.Glass, Size = Vector3.new(0.26, 0.1, 1.1), Pos = Vector3.new(0, 0.68, -0.1) })
	b:Attach("MagWell", Vector3.new(0, 0.66, -0.1))
	b:Tube("Barrel", 0.11, 0.35, Vector3.new(0, 0.42, -1.1), "Metal", DARK_METAL)
	b:Add({ Name = "RearPlate", Role = "Secondary", Size = Vector3.new(0.3, 0.5, 0.06), Pos = Vector3.new(0, 0.33, 0.88) })
	b:Attach("Muzzle", Vector3.new(0, 0.42, -1.3))
	b:Attach("MuzzleMount", Vector3.new(0, 0.42, -1.27))
	b:Attach("OpticMount", Vector3.new(0, 0.74, -0.2))
	b:Attach("SideMount", Vector3.new(0.17, 0.4, -0.75))
	b:Attach("LeftHand", Vector3.new(0, 0.22, -0.85))
	b:Attach("Aim", Vector3.new(0, 0.88, 0.5))
	b:Tape(Vector3.new(0.32, 0.12, 0.3), Vector3.new(0, 0.5, 0.45))
end

BUILDERS.VSR = function(b)
	local stock = Color3.fromRGB(70, 74, 60)
	b:Add({ Name = "Stock", Role = "Primary", Color = stock, Size = Vector3.new(0.24, 0.42, 3.4), Pos = Vector3.new(0, 0.32, -0.45) })
	b:Add({ Name = "Butt", Role = "Primary", Color = stock, Size = Vector3.new(0.24, 0.62, 0.9), Pos = Vector3.new(0, 0.22, 1.1) })
	b:Add({ Name = "Cheek", Size = Vector3.new(0.26, 0.14, 0.6), Pos = Vector3.new(0, 0.6, 0.95) })
	b:Add({ Name = "ButtPad", Role = "Metal", Color = BLACK, Material = Enum.Material.Fabric, Size = Vector3.new(0.26, 0.64, 0.08), Pos = Vector3.new(0, 0.22, 1.58) })
	b:Tube("Action", 0.24, 1.0, Vector3.new(0, 0.56, -0.25), "Metal", DARK_METAL)
	b:Add({ Name = "BoltHandle", Role = "Bolt", Color = METAL, Size = Vector3.new(0.34, 0.05, 0.05), Pos = Vector3.new(0.18, 0.55, 0.12) })
	b:Add({ Name = "BoltKnob", Role = "Bolt", Color = METAL, Shape = Enum.PartType.Ball, Size = Vector3.new(0.1, 0.1, 0.1), Pos = Vector3.new(0.36, 0.52, 0.12) })
	b:Tube("OuterBarrel", 0.15, 2.4, Vector3.new(0, 0.56, -1.95), "Metal", BLACK)
	b:Tube("Silencer", 0.24, 0.8, Vector3.new(0, 0.56, -3.5), "Metal", BLACK)
	b:Add({ Name = "Mag", Role = "Mag", Size = Vector3.new(0.16, 0.28, 0.3), Pos = Vector3.new(0, 0.02, -0.55) })
	b:Attach("MagWell", Vector3.new(0, 0.14, -0.55))
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.36), Pos = Vector3.new(0, 0.06, -0.12) })
	b:Add({ Name = "ScopeBase", Role = "Metal", Size = Vector3.new(0.14, 0.05, 0.9), Pos = Vector3.new(0, 0.7, -0.25) })
	b:Attach("Muzzle", Vector3.new(0, 0.56, -3.92))
	b:Attach("OpticMount", Vector3.new(0, 0.72, -0.25))
	b:Attach("SideMount", Vector3.new(0.14, 0.4, -1.8))
	b:Attach("LeftHand", Vector3.new(0, 0.25, -1.3))
	b:Attach("Aim", Vector3.new(0, 0.85, 0.8))
	b:Tape(Vector3.new(0.26, 0.44, 0.12), Vector3.new(0, 0.32, -1.6))
	b:Tape(Vector3.new(0.26, 0.64, 0.12), Vector3.new(0, 0.22, 0.75))
end

BUILDERS.M870 = function(b)
	b:Add({ Name = "Receiver", Role = "Primary", Size = Vector3.new(0.26, 0.4, 1.0), Pos = Vector3.new(0, 0.42, -0.3), Material = Enum.Material.Metal })
	b:Add({ Name = "Stock", Role = "Wood", Color = WOOD, Size = Vector3.new(0.24, 0.42, 1.0), Pos = Vector3.new(0, 0.32, 0.65), Rot = Vector3.new(6, 0, 0) })
	b:Add({ Name = "ButtPad", Role = "Metal", Color = BLACK, Material = Enum.Material.Fabric, Size = Vector3.new(0.26, 0.5, 0.08), Pos = Vector3.new(0, 0.26, 1.18), Rot = Vector3.new(6, 0, 0) })
	b:Tube("Barrel", 0.15, 2.0, Vector3.new(0, 0.55, -1.8), "Metal", DARK_METAL)
	b:Tube("MagTube", 0.15, 1.6, Vector3.new(0, 0.36, -1.6), "Metal", DARK_METAL)
	b:Add({ Name = "Pump", Role = "Pump", Color = WOOD, Size = Vector3.new(0.28, 0.28, 0.75), Pos = Vector3.new(0, 0.38, -1.45) })
	for i = 0, 4 do
		b:Add({ Name = "PumpGroove", Role = "Pump", Color = Color3.fromRGB(70, 44, 26), Size = Vector3.new(0.29, 0.04, 0.04), Pos = Vector3.new(0, 0.3, -1.2 - i * 0.12) })
	end
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.36), Pos = Vector3.new(0, 0.12, -0.15) })
	b:Add({ Name = "Bead", Shape = Enum.PartType.Ball, Size = Vector3.new(0.06, 0.06, 0.06), Pos = Vector3.new(0, 0.66, -2.72), Color = Color3.fromRGB(255, 200, 60), Neon = true })
	b:Add({ Name = "Rib", Role = "Metal", Size = Vector3.new(0.05, 0.04, 2.0), Pos = Vector3.new(0, 0.64, -1.8) })
	b:Add({ Name = "ShellCarrier", Role = "Mag", Color = Color3.fromRGB(160, 30, 30), Size = Vector3.new(0.04, 0.22, 0.5), Pos = Vector3.new(-0.15, 0.42, -0.3) })
	b:Attach("MagWell", Vector3.new(0, 0.2, -0.4))
	b:Attach("Muzzle", Vector3.new(0, 0.55, -2.82))
	b:Attach("OpticMount", Vector3.new(0, 0.63, -0.3))
	b:Attach("SideMount", Vector3.new(0.16, 0.38, -1.9))
	b:Attach("Aim", Vector3.new(0, 0.68, 0.6))
	b:Attach("LeftHand", Vector3.new(0, 0.3, -1.45))
	b:Tape(Vector3.new(0.3, 0.3, 0.12), Vector3.new(0, 0.38, -1.92))
end

local function pistol(b, opts)
	b.Handle.Size = Vector3.new(0.2, opts.GripLength or 0.55, 0.3)
	local slideLength = opts.SlideLength or 0.9
	local slideColor = opts.SlideColor
	b:Add({ Name = "Frame", Role = "Secondary", Size = Vector3.new(0.18, 0.14, slideLength - 0.1), Pos = Vector3.new(0, 0.2, -0.3) })
	b:Add({ Name = "Slide", Role = "Slide", Color = slideColor, Size = Vector3.new(opts.SlideWidth or 0.2, opts.SlideHeight or 0.22, slideLength), Pos = Vector3.new(0, 0.38, -0.32) })
	for i = 0, 4 do
		b:Add({ Name = "Serration", Role = "Slide", Color = slideColor, Size = Vector3.new((opts.SlideWidth or 0.2) + 0.01, 0.16, 0.025), Pos = Vector3.new(0, 0.38, 0.0 + i * 0.05) })
	end
	b:Add({ Name = "TriggerGuard", Size = Vector3.new(0.06, 0.05, 0.32), Pos = Vector3.new(0, 0.07, -0.3) })
	b:Add({ Name = "FrontSight", Role = "Slide", Size = Vector3.new(0.04, 0.06, 0.05), Pos = Vector3.new(0, 0.52, -0.32 - slideLength / 2 + 0.06) })
	b:Add({ Name = "FrontDot", Size = Vector3.new(0.02, 0.02, 0.01), Pos = Vector3.new(0, 0.53, -0.32 - slideLength / 2 + 0.03), Color = Color3.fromRGB(240, 240, 240), Neon = true })
	b:Add({ Name = "RearSightL", Role = "Slide", Size = Vector3.new(0.05, 0.06, 0.06), Pos = Vector3.new(-0.06, 0.52, 0.08) })
	b:Add({ Name = "RearSightR", Role = "Slide", Size = Vector3.new(0.05, 0.06, 0.06), Pos = Vector3.new(0.06, 0.52, 0.08) })
	local magLength = opts.MagLength or 0
	if magLength > 0 then
		b:Add({ Name = "ExtendedMag", Role = "Mag", Size = Vector3.new(0.18, magLength, 0.26), Pos = Vector3.new(0, -0.32 - magLength / 2, 0.12), Rot = Vector3.new(-14, 0, 0) })
	end
	b:Add({ Name = "MagBase", Role = "Mag", Size = Vector3.new(0.22, 0.06, 0.32), Pos = Vector3.new(0, -0.34 - magLength, 0.12 + magLength * 0.25), Rot = Vector3.new(-14, 0, 0) })
	b:Attach("MagWell", Vector3.new(0, 0.05, 0.05))
	local muzzleZ = -0.32 - slideLength / 2
	b:Attach("Muzzle", Vector3.new(0, 0.38, muzzleZ - 0.02))
	b:Attach("MuzzleMount", Vector3.new(0, 0.38, muzzleZ))
	b:Attach("OpticMount", Vector3.new(0, 0.49, -0.1))
	b:Attach("SideMount", Vector3.new(0, 0.12, -0.45))
	b:Attach("Aim", Vector3.new(0, 0.54, 0.75))
	b:Attach("LeftHand", Vector3.new(-0.05, -0.05, 0.05))
	b:Tape(Vector3.new(0.21, 0.1, 0.32), Vector3.new(0, -0.2, 0.08))
end

BUILDERS.G17 = function(b)
	pistol(b, { SlideColor = DARK_METAL })
end

BUILDERS.G18 = function(b)
	pistol(b, { SlideColor = DARK_METAL, MagLength = 0.45 })
	b:Add({ Name = "Selector", Role = "Metal", Size = Vector3.new(0.03, 0.06, 0.08), Pos = Vector3.new(-0.11, 0.42, 0.1), Color = Color3.fromRGB(200, 160, 60) })
end

BUILDERS.M1911 = function(b)
	pistol(b, { SlideColor = Color3.fromRGB(150, 152, 156), SlideLength = 1.0, SlideWidth = 0.17, SlideHeight = 0.2 })
	b:Add({ Name = "GripPanelL", Role = "Wood", Color = WOOD, Size = Vector3.new(0.02, 0.4, 0.26), Pos = Vector3.new(-0.11, -0.05, 0.04), Rot = Vector3.new(-14, 0, 0) })
	b:Add({ Name = "GripPanelR", Role = "Wood", Color = WOOD, Size = Vector3.new(0.02, 0.4, 0.26), Pos = Vector3.new(0.11, -0.05, 0.04), Rot = Vector3.new(-14, 0, 0) })
	b:Add({ Name = "Hammer", Role = "Metal", Size = Vector3.new(0.06, 0.1, 0.06), Pos = Vector3.new(0, 0.42, 0.2) })
end

BUILDERS.DEAGLE = function(b)
	pistol(b, { SlideColor = Color3.fromRGB(120, 122, 128), SlideLength = 1.15, SlideWidth = 0.24, SlideHeight = 0.28, GripLength = 0.6 })
	b:Add({ Name = "BarrelBlock", Role = "Slide", Color = Color3.fromRGB(120, 122, 128), Size = Vector3.new(0.22, 0.2, 0.75), Pos = Vector3.new(0, 0.36, -0.55) })
	b:Add({ Name = "TopRib", Role = "Metal", Size = Vector3.new(0.08, 0.04, 0.75), Pos = Vector3.new(0, 0.53, -0.55) })
end

---------------------------------------------------------------------------
-- Procedural attachments (positions are relative to the mount point)
---------------------------------------------------------------------------

type AttachmentResult = { Aim: Vector3?, Muzzle: Vector3?, LeftHand: Vector3?, Laser: Vector3? }

local PROCEDURAL_ATTACHMENTS: { [string]: (any, Vector3) -> AttachmentResult } = {}

PROCEDURAL_ATTACHMENTS.RedDot = function(b, m)
	b:Add({ Name = "OpticMountBase", Role = "Metal", Color = BLACK, Size = Vector3.new(0.18, 0.08, 0.34), Pos = m + Vector3.new(0, 0.04, 0) })
	-- Hollow window (two walls + hood) so the eye can see through when aiming.
	for _, x in { -0.12, 0.12 } do
		b:Add({ Name = "OpticWall", Role = "Metal", Color = BLACK, Size = Vector3.new(0.04, 0.26, 0.34), Pos = m + Vector3.new(x, 0.21, 0) })
	end
	b:Add({ Name = "OpticHood", Role = "Metal", Color = BLACK, Size = Vector3.new(0.28, 0.05, 0.36), Pos = m + Vector3.new(0, 0.36, 0) })
	b:Add({ Name = "OpticEmitter", Role = "Metal", Color = BLACK, Size = Vector3.new(0.08, 0.06, 0.08), Pos = m + Vector3.new(0, 0.11, 0.1) })
	b:Add({ Name = "OpticGlass", Role = "Glass", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.02, 0.22, 0.22), Pos = m + Vector3.new(0, 0.24, -0.12), Rot = Vector3.new(0, 90, 0), Color = GLASS, Transparency = 0.75 })
	b:Add({ Name = "Reticle", Shape = Enum.PartType.Ball, Size = Vector3.new(0.018, 0.018, 0.018), Pos = m + Vector3.new(0, 0.24, -0.13), Color = Color3.fromRGB(255, 40, 40), Neon = true })
	return { Aim = m + Vector3.new(0, 0.24, 0.55) }
end

PROCEDURAL_ATTACHMENTS.Holo = function(b, m)
	b:Add({ Name = "HoloBase", Role = "Metal", Color = BLACK, Size = Vector3.new(0.3, 0.1, 0.55), Pos = m + Vector3.new(0, 0.05, 0) })
	for _, x in { -0.14, 0.14 } do
		b:Add({ Name = "HoloPost", Role = "Metal", Color = BLACK, Size = Vector3.new(0.04, 0.26, 0.5), Pos = m + Vector3.new(x, 0.23, -0.02) })
	end
	b:Add({ Name = "HoloHood", Role = "Metal", Color = BLACK, Size = Vector3.new(0.32, 0.05, 0.5), Pos = m + Vector3.new(0, 0.38, -0.02) })
	b:Add({ Name = "HoloGlass", Role = "Glass", Size = Vector3.new(0.24, 0.2, 0.02), Pos = m + Vector3.new(0, 0.23, -0.2), Color = GLASS, Transparency = 0.7 })
	b:Add({ Name = "Reticle", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.005, 0.05, 0.05), Pos = m + Vector3.new(0, 0.23, -0.215), Rot = Vector3.new(0, 90, 0), Color = Color3.fromRGB(255, 50, 50), Neon = true, Transparency = 0.2 })
	return { Aim = m + Vector3.new(0, 0.23, 0.6) }
end

PROCEDURAL_ATTACHMENTS.Scope4x = function(b, m)
	b:Add({ Name = "ScopeBase", Role = "Metal", Color = BLACK, Size = Vector3.new(0.2, 0.1, 0.6), Pos = m + Vector3.new(0, 0.05, 0) })
	b:Add({ Name = "ScopeHousing", Role = "Metal", Color = Color3.fromRGB(46, 46, 44), Size = Vector3.new(0.26, 0.22, 0.6), Pos = m + Vector3.new(0, 0.2, 0.02) })
	b:Tube("ScopeBell", 0.32, 0.22, m + Vector3.new(0, 0.25, -0.38), "Metal", Color3.fromRGB(46, 46, 44))
	b:Tube("ScopeEye", 0.26, 0.18, m + Vector3.new(0, 0.25, 0.38), "Metal", Color3.fromRGB(46, 46, 44))
	b:Add({ Name = "FiberOptic", Size = Vector3.new(0.05, 0.03, 0.4), Pos = m + Vector3.new(0, 0.33, 0), Color = Color3.fromRGB(120, 255, 120), Neon = true })
	b:Add({ Name = "ScopeGlass", Role = "Glass", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.02, 0.28, 0.28), Pos = m + Vector3.new(0, 0.25, -0.5), Rot = Vector3.new(0, 90, 0), Color = Color3.fromRGB(80, 120, 160), Transparency = 0.35, Reflectance = 0.3 })
	b:Add({ Name = "Reticle", Shape = Enum.PartType.Ball, Size = Vector3.new(0.014, 0.014, 0.014), Pos = m + Vector3.new(0, 0.25, -0.1), Color = Color3.fromRGB(255, 70, 40), Neon = true })
	return { Aim = m + Vector3.new(0, 0.25, 0.8) }
end

PROCEDURAL_ATTACHMENTS.ScopeLong = function(b, m)
	local length = 1.6
	for _, z in { length * 0.25, -length * 0.25 } do
		b:Add({ Name = "ScopeRing", Role = "Metal", Color = BLACK, Size = Vector3.new(0.2, 0.26, 0.1), Pos = m + Vector3.new(0, 0.13, z) })
	end
	b:Tube("ScopeTube", 0.2, length, m + Vector3.new(0, 0.28, 0), "Metal", BLACK)
	b:Tube("ScopeBell", 0.34, length * 0.3, m + Vector3.new(0, 0.28, -length * 0.42), "Metal", BLACK)
	b:Tube("ScopeEyepiece", 0.28, length * 0.2, m + Vector3.new(0, 0.28, length * 0.45), "Metal", BLACK)
	b:Tube("ScopeTurret", 0.12, 0.14, m + Vector3.new(0, 0.42, 0), "Metal", DARK_METAL)
	b:Add({ Name = "ScopeGlass", Role = "Glass", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.02, 0.3, 0.3), Pos = m + Vector3.new(0, 0.28, -length * 0.57), Rot = Vector3.new(0, 90, 0), Color = Color3.fromRGB(70, 120, 170), Transparency = 0.3, Reflectance = 0.4 })
	return { Aim = m + Vector3.new(0, 0.28, length * 0.55 + 0.5) }
end

PROCEDURAL_ATTACHMENTS.Suppressor = function(b, m)
	b:Tube("Suppressor", 0.26, 1.0, m + Vector3.new(0, 0, -0.5), "Metal", Color3.fromRGB(32, 33, 35))
	b:Tube("SuppressorCap", 0.22, 0.06, m + Vector3.new(0, 0, -1.02), "Metal", DARK_METAL)
	return { Muzzle = m + Vector3.new(0, 0, -1.06) }
end

PROCEDURAL_ATTACHMENTS.Compensator = function(b, m)
	b:Tube("Compensator", 0.17, 0.32, m + Vector3.new(0, 0, -0.16), "Metal", DARK_METAL)
	for i = 0, 2 do
		b:Add({ Name = "Port", Role = "Metal", Color = Color3.fromRGB(12, 12, 12), Size = Vector3.new(0.12, 0.03, 0.05), Pos = m + Vector3.new(0, 0.08, -0.07 - i * 0.09) })
	end
	return { Muzzle = m + Vector3.new(0, 0, -0.34) }
end

PROCEDURAL_ATTACHMENTS.VerticalGrip = function(b, m)
	b:Add({ Name = "VerticalGrip", Role = "Secondary", Size = Vector3.new(0.15, 0.48, 0.17), Pos = m + Vector3.new(0, -0.24, 0) })
	b:Add({ Name = "GripClamp", Role = "Metal", Color = BLACK, Size = Vector3.new(0.18, 0.06, 0.24), Pos = m + Vector3.new(0, -0.02, 0) })
	return { LeftHand = m + Vector3.new(0, -0.25, 0) }
end

PROCEDURAL_ATTACHMENTS.AngledGrip = function(b, m)
	b:Add({ Name = "AngledGrip", Role = "Secondary", Size = Vector3.new(0.15, 0.16, 0.55), Pos = m + Vector3.new(0, -0.08, 0.05), Rot = Vector3.new(-18, 0, 0) })
	return { LeftHand = m + Vector3.new(0, -0.1, 0.1) }
end

PROCEDURAL_ATTACHMENTS.Laser = function(b, m)
	b:Add({ Name = "LaserBox", Role = "Metal", Color = Color3.fromRGB(60, 64, 52), Size = Vector3.new(0.12, 0.16, 0.42), Pos = m + Vector3.new(0.06, 0, 0) })
	local lens = b:Add({ Name = "LightLens", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.02, 0.1, 0.1), Pos = m + Vector3.new(0.06, 0.03, -0.215), Rot = Vector3.new(0, 90, 0), Color = Color3.fromRGB(230, 235, 255), Material = Enum.Material.Glass, Transparency = 0.2 })
	lens:SetAttribute("Fixed", true)
	b:Add({ Name = "LaserDot", Shape = Enum.PartType.Ball, Size = Vector3.new(0.04, 0.04, 0.04), Pos = m + Vector3.new(0.06, -0.04, -0.215), Color = Color3.fromRGB(255, 30, 30), Neon = true })
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
	return { Laser = m + Vector3.new(0.06, -0.04, -0.24) }
end

---------------------------------------------------------------------------
-- Imported mesh support
---------------------------------------------------------------------------

local function meshSource(id: string): Instance?
	local folder = ReplicatedStorage:FindFirstChild("GunModels")
	return folder and folder:FindFirstChild(id) or nil
end

local function findMesh(source: Instance, name: string): MeshPart?
	for _, d in source:GetDescendants() do
		if d:IsA("MeshPart") and d.Name == name then
			return d
		end
	end
	return nil
end

-- Clones each MeshPart named in `pieces` into the builder at `offset`.
local function addMeshPieces(b, source: Instance, pieces: { any }, offset: Vector3)
	for _, piece in pieces do
		local mesh = findMesh(source, piece.Name)
		if mesh then
			local part = mesh:Clone()
			for _, child in part:GetChildren() do
				if not child:IsA("SurfaceAppearance") then
					child:Destroy()
				end
			end
			part.Name = piece.Name
			part.Size = piece.Size
			part.CFrame = CFrame.new(piece.Center + offset)
			local role = piece.Role == "Accent" and "Accent" or piece.Role
			if piece.Name == "Mag" or piece.Name == "Pump" or piece.Name == "Slide" or piece.Name == "Bolt" then
				role = piece.Name
			end
			part:SetAttribute("Role", role)
			if piece.Name == "Glass" then
				part.Transparency = 0.6
				part:SetAttribute("Role", "Glass")
			elseif piece.Name == "Reticle" then
				part.Material = Enum.Material.Neon
				part.Color = Color3.fromRGB(255, 40, 40)
				part:SetAttribute("Fixed", true)
			end
			cosmetic(part)
			part.Parent = b.Model
			local weld = Instance.new("WeldConstraint")
			weld.Part0 = b.Handle
			weld.Part1 = part
			weld.Parent = part
		end
	end
end

local function buildFromMeshes(id: string): any?
	local data = MeshData.Guns[id]
	local source = meshSource(id)
	if not data or not source then
		return nil
	end
	local b = newBuilder(id, 0)
	b.Handle.Transparency = 1
	b.Handle.Size = Vector3.new(0.2, 0.4, 0.2)
	addMeshPieces(b, source, data.Pieces, Vector3.zero)
	local points = data.Points or {}
	local map = { Muzzle = "Muzzle", Aim = "Aim", LeftHand = "LeftHand", MagWell = "MagWell", Optic = "OpticMount", Underbarrel = "UnderMount", MuzzleMount = "MuzzleMount", Side = "SideMount" }
	for key, attachName in map do
		if points[key] then
			b:Attach(attachName, points[key])
		end
	end
	b.FromMeshes = true
	return b
end

---------------------------------------------------------------------------
-- Assembly
---------------------------------------------------------------------------

local function addAttachments(b, weaponId: string, loadout: any)
	local clean = Weapons.CleanLoadout(weaponId, loadout)
	local mounts = {
		Optic = "OpticMount",
		Muzzle = "MuzzleMount",
		Grip = "UnderMount",
		Laser = "SideMount",
	}
	for _, slot in Weapons.Slots do
		local choice = clean[slot]
		local mount = b:Point(mounts[slot])
		if choice and choice ~= "None" and mount then
			local before = {}
			for _, d in b.Model:GetChildren() do
				before[d] = true
			end
			local result: AttachmentResult
			local meshInfo = MeshData.Attachments["ATT_" .. choice]
			local source = meshSource("ATT_" .. choice)
			local procedural = PROCEDURAL_ATTACHMENTS[choice]
			if meshInfo and source and slot ~= "Laser" then
				addMeshPieces(b, source, meshInfo.Pieces, mount)
				local p = meshInfo.Points or {}
				result = {
					Aim = p.Aim and mount + p.Aim or nil,
					Muzzle = p.MuzzleOffset and mount + p.MuzzleOffset or nil,
					LeftHand = slot == "Grip" and mount + Vector3.new(0, -0.22, 0) or nil,
				}
			elseif procedural then
				result = procedural(b, mount)
			else
				result = {}
			end
			if slot == "Optic" then
				-- Tag optic housings so the viewmodel can ghost them at full aim.
				for _, d in b.Model:GetChildren() do
					if not before[d] and d:IsA("BasePart") and d:GetAttribute("Role") ~= "Glass" and d.Name ~= "Reticle" then
						d:SetAttribute("Optic", true)
					end
				end
			end
			if result.Aim then
				b:Attach("Aim", result.Aim)
			end
			if result.Muzzle then
				b:Attach("Muzzle", result.Muzzle)
			end
			if result.LeftHand then
				b:Attach("LeftHand", result.LeftHand)
			end
			if result.Laser then
				b:Attach("LaserEmitter", result.Laser)
			end
		end
	end
	b.Model:SetAttribute("Loadout", table.concat({ clean.Optic, clean.Muzzle, clean.Grip, clean.Laser }, ","))
end

-- Applies a finish and team accent to every part by role.
function GunBuilder.ApplyFinish(model: Model, skinId: string?, accent: Color3?)
	local skin = Weapons.Skin(skinId)
	local material = skin.Material and (Enum.Material :: any)[skin.Material] or nil
	for _, part in model:GetDescendants() do
		if part:IsA("BasePart") and not part:GetAttribute("Fixed") then
			local role = part:GetAttribute("Role")
			if role == "Primary" or role == "Slide" then
				part.Color = skin.Primary
				if material then
					part.Material = material
				end
			elseif role == "Secondary" then
				part.Color = skin.Secondary
			elseif role == "Accent" and accent then
				part.Color = accent
			end
		end
	end
end

export type BuildOptions = { Accent: Color3?, Loadout: any? }

function GunBuilder.Build(weaponId: string, opts: BuildOptions?): Model
	local options: BuildOptions = opts or {}
	local b = buildFromMeshes(weaponId)
	if not b then
		local build = BUILDERS[weaponId]
		assert(build, "No model for weapon " .. tostring(weaponId))
		b = newBuilder(weaponId)
		build(b)
	end
	addAttachments(b, weaponId, options.Loadout)
	local loadout = Weapons.CleanLoadout(weaponId, options.Loadout)
	GunBuilder.ApplyFinish(b.Model, loadout.Skin, options.Accent or Color3.fromRGB(200, 200, 200))
	return b.Model
end

function GunBuilder.BuildGrenade(accent: Color3?): Model
	local b = newBuilder("Grenade", 0)
	local handle = b.Handle
	handle.Shape = Enum.PartType.Cylinder
	handle.Size = Vector3.new(0.6, 0.38, 0.38)
	handle.CFrame = CFrame.Angles(0, 0, math.rad(90))
	handle.Color = Color3.fromRGB(70, 78, 56)
	handle:SetAttribute("Fixed", true)
	b:Add({ Name = "Cap", Size = Vector3.new(0.22, 0.12, 0.22), Pos = Vector3.new(0, 0.36, 0), Color = BLACK })
	b:Add({ Name = "Lever", Role = "Metal", Size = Vector3.new(0.08, 0.5, 0.04), Pos = Vector3.new(0.2, 0.15, 0), Rot = Vector3.new(0, 0, -8), Color = METAL })
	b:Add({ Name = "Ring", Role = "Metal", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.03, 0.16, 0.16), Pos = Vector3.new(-0.16, 0.38, 0), Color = METAL })
	local tape = b:Tape(Vector3.new(0.4, 0.08, 0.4), Vector3.new(0, -0.1, 0))
	tape.Color = accent or Color3.new(1, 1, 1)
	b:Attach("LeftHand", Vector3.new(0, 0, 0))
	b:Attach("Aim", Vector3.new(0, 0.3, 1.2))
	b:Attach("Muzzle", Vector3.new(0, 0.3, -0.3))
	return b.Model
end

-- Wraps a gun model in a Tool for third-person holding.
function GunBuilder.BuildTool(weaponId: string, opts: BuildOptions?): Tool
	local options: BuildOptions = opts or {}
	local model = weaponId == "Grenade" and GunBuilder.BuildGrenade(options.Accent) or GunBuilder.Build(weaponId, options)
	local tool = Instance.new("Tool")
	tool.Name = weaponId
	tool.CanBeDropped = false
	tool.RequiresHandle = true
	tool.ManualActivationOnly = true
	tool:SetAttribute("WeaponId", weaponId)
	tool:SetAttribute("Loadout", model:GetAttribute("Loadout"))

	-- Rotate the tilted grip back so the barrel points straight ahead.
	local handle = model.PrimaryPart :: BasePart
	tool.Grip = handle.CFrame:Inverse()

	for _, child in model:GetChildren() do
		child.Parent = tool
	end
	model:Destroy()
	return tool
end

GunBuilder.HasMeshes = function(weaponId: string): boolean
	return MeshData.Guns[weaponId] ~= nil and meshSource(weaponId) ~= nil
end

return GunBuilder
