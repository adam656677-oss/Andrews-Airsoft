--[[
	Dresses each character in airsoft kit: plate carrier with pouches, a
	team-coloured armband, ballistic goggles and a mesh lower-face guard.
	Works with both R15 and R6 rigs.
]]

local Gear = {}

local CARRIER = Color3.fromRGB(86, 90, 66)
local POUCH = Color3.fromRGB(74, 78, 58)
local STRAP = Color3.fromRGB(40, 42, 34)
local LENS = Color3.fromRGB(40, 36, 30)

local function weldTo(base: BasePart, part: BasePart, offset: CFrame)
	part.Anchored = false
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.Massless = true
	part.CFrame = base.CFrame * offset
	local weld = Instance.new("WeldConstraint")
	weld.Part0 = base
	weld.Part1 = part
	weld.Parent = part
end

local function piece(parent: Instance, name: string, size: Vector3, color: Color3, material: Enum.Material?): Part
	local p = Instance.new("Part")
	p.Name = name
	p.Size = size
	p.Color = color
	p.Material = material or Enum.Material.Fabric
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

function Gear.Equip(character: Model, teamColor: Color3)
	local old = character:FindFirstChild("AirsoftKit")
	if old then
		old:Destroy()
	end

	local torso = (character:FindFirstChild("UpperTorso") or character:FindFirstChild("Torso")) :: BasePart?
	local head = character:FindFirstChild("Head") :: BasePart?
	local leftArm = (character:FindFirstChild("LeftUpperArm") or character:FindFirstChild("Left Arm")) :: BasePart?
	if not torso or not head then
		return
	end

	local kit = Instance.new("Model")
	kit.Name = "AirsoftKit"
	kit.Parent = character

	local isR15 = torso.Name == "UpperTorso"
	local tw, th, td = torso.Size.X, torso.Size.Y, torso.Size.Z
	local yOff = isR15 and 0.05 or 0.2

	-- Plate carrier: front and back plates plus cummerbund.
	local front = piece(kit, "FrontPlate", Vector3.new(tw * 0.82, th * 0.78, 0.35), CARRIER)
	weldTo(torso, front, CFrame.new(0, yOff, -td / 2 - 0.15))
	local back = piece(kit, "BackPlate", Vector3.new(tw * 0.82, th * 0.8, 0.3), CARRIER)
	weldTo(torso, back, CFrame.new(0, yOff, td / 2 + 0.13))
	for _, side in { -1, 1 } do
		local cummerbund = piece(kit, "Cummerbund", Vector3.new(0.25, th * 0.45, td + 0.5), CARRIER)
		weldTo(torso, cummerbund, CFrame.new(side * (tw / 2 + 0.08), yOff - th * 0.15, 0))
		local strap = piece(kit, "ShoulderStrap", Vector3.new(0.45, 0.2, td + 0.55), STRAP)
		weldTo(torso, strap, CFrame.new(side * tw * 0.27, th / 2 + 0.05, 0))
	end

	-- Triple mag pouch row on the front.
	for i = -1, 1 do
		local pouch = piece(kit, "MagPouch", Vector3.new(tw * 0.22, th * 0.32, 0.32), POUCH)
		weldTo(torso, pouch, CFrame.new(i * tw * 0.25, yOff - th * 0.2, -td / 2 - 0.45))
		local mag = piece(kit, "PouchMag", Vector3.new(tw * 0.16, 0.18, 0.2), Color3.fromRGB(150, 128, 94), Enum.Material.SmoothPlastic)
		weldTo(torso, mag, CFrame.new(i * tw * 0.25, yOff - th * 0.2 + th * 0.18, -td / 2 - 0.45))
	end
	-- Admin pouch with a team patch so allies are easy to read head-on.
	local patch = piece(kit, "TeamPatch", Vector3.new(tw * 0.4, th * 0.16, 0.08), teamColor, Enum.Material.Neon)
	weldTo(torso, patch, CFrame.new(0, yOff + th * 0.2, -td / 2 - 0.36))
	local backPatch = piece(kit, "BackPatch", Vector3.new(tw * 0.5, th * 0.2, 0.08), teamColor, Enum.Material.Neon)
	weldTo(torso, backPatch, CFrame.new(0, yOff + th * 0.15, td / 2 + 0.31))
	-- Radio pouch
	local radio = piece(kit, "Radio", Vector3.new(0.3, th * 0.38, 0.3), STRAP, Enum.Material.SmoothPlastic)
	weldTo(torso, radio, CFrame.new(-tw * 0.3, yOff + th * 0.1, td / 2 + 0.45))
	local antenna = piece(kit, "Antenna", Vector3.new(0.06, 1.4, 0.06), Color3.fromRGB(20, 20, 20), Enum.Material.SmoothPlastic)
	weldTo(torso, antenna, CFrame.new(-tw * 0.3, yOff + th * 0.7, td / 2 + 0.45))

	-- Armband in team colour (glows slightly for night readability).
	if leftArm then
		local band = piece(kit, "Armband", leftArm.Size + Vector3.new(0.06, -leftArm.Size.Y * 0.75, 0.06), teamColor, Enum.Material.Neon)
		weldTo(leftArm, band, CFrame.new(0, leftArm.Size.Y * 0.18, 0))
	end

	-- Goggles: band + two lenses. Lower-face mesh guard.
	local hs = head.Size
	local band = piece(kit, "GoggleBand", Vector3.new(hs.X + 0.06, hs.Y * 0.18, hs.Z + 0.06), STRAP)
	weldTo(head, band, CFrame.new(0, hs.Y * 0.12, 0))
	local goggles = piece(kit, "Goggles", Vector3.new(hs.X * 0.8, hs.Y * 0.28, 0.2), Color3.fromRGB(30, 30, 30), Enum.Material.SmoothPlastic)
	weldTo(head, goggles, CFrame.new(0, hs.Y * 0.12, -hs.Z / 2 - 0.06))
	local lens = piece(kit, "Lens", Vector3.new(hs.X * 0.72, hs.Y * 0.2, 0.05), LENS, Enum.Material.Glass)
	lens.Reflectance = 0.35
	lens.Transparency = 0.1
	weldTo(head, lens, CFrame.new(0, hs.Y * 0.12, -hs.Z / 2 - 0.17))
	local mask = piece(kit, "MeshMask", Vector3.new(hs.X * 0.85, hs.Y * 0.36, 0.25), Color3.fromRGB(34, 34, 34), Enum.Material.DiamondPlate)
	weldTo(head, mask, CFrame.new(0, -hs.Y * 0.22, -hs.Z / 2 - 0.06))

	-- Boonie / cap in a muted tone
	local cap = piece(kit, "Cap", Vector3.new(hs.X + 0.12, hs.Y * 0.24, hs.Z + 0.12), CARRIER)
	weldTo(head, cap, CFrame.new(0, hs.Y * 0.44, 0))
	local brim = piece(kit, "Brim", Vector3.new(hs.X * 0.9, 0.08, hs.Z * 0.45), CARRIER)
	weldTo(head, brim, CFrame.new(0, hs.Y * 0.34, -hs.Z * 0.62))

	return kit
end

return Gear
