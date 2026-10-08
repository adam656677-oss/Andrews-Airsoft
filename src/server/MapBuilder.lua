--[[
	Procedurally builds "Ironwood Yard", the outdoor airsoft field, plus the
	staging area (lobby) with a chrono station and a practice range.

	Layout (top-down, +X is east):

	          [ Staging area / range ]          z ≈ +200
	  ------------------- netting -------------------  z = +125
	  |          A  container yard                   |
	  | BLUE                                     RED |
	  | spawn     B  shoot house (centre)      spawn |
	  |                                              |
	  |          C  woodline bunker                  |
	  -----------------------------------------------  z = -125

	The field is mirrored across X = 0 so neither team has an advantage.
]]

local CollectionService = game:GetService("CollectionService")
local Lighting = game:GetService("Lighting")

local Config = require(game:GetService("ReplicatedStorage").Shared.Config)
local Build = require(script.Parent.Build)

local MapBuilder = {}

local FIELD_X = 170
local FIELD_Z = 125
local LOBBY_CENTER = Vector3.new(0, 0, 205)

-- Palette --------------------------------------------------------------------
local C = {
	Plywood = Color3.fromRGB(176, 136, 92),
	PlywoodDark = Color3.fromRGB(128, 96, 62),
	Concrete = Color3.fromRGB(150, 148, 142),
	ConcreteDark = Color3.fromRGB(102, 100, 96),
	Sandbag = Color3.fromRGB(150, 134, 98),
	Tire = Color3.fromRGB(28, 28, 30),
	Steel = Color3.fromRGB(86, 90, 96),
	Net = Color3.fromRGB(20, 26, 22),
	Bark = Color3.fromRGB(78, 58, 40),
	Leaf = Color3.fromRGB(58, 86, 44),
	LeafDark = Color3.fromRGB(42, 66, 34),
	Hay = Color3.fromRGB(196, 168, 96),
	Canvas = Color3.fromRGB(96, 104, 76),
	Neutral = Color3.fromRGB(210, 210, 210),
	ContainerColors = {
		Color3.fromRGB(150, 54, 40),
		Color3.fromRGB(42, 88, 128),
		Color3.fromRGB(70, 104, 64),
		Color3.fromRGB(182, 132, 52),
		Color3.fromRGB(110, 110, 112),
	},
}

local rng = Random.new(1337)

-- Generic pieces -----------------------------------------------------------------

type Opening = { At: number, Width: number, Bottom: number, Top: number }

-- Builds a wall from `a` to `b` (both at floor level) with rectangular openings.
local function wall(parent: Instance, a: Vector3, b: Vector3, height: number, thickness: number, color: Color3, material: Enum.Material, openings: { Opening }?)
	local dir = (b - a).Unit
	local length = (b - a).Magnitude
	local list = table.clone(openings or {})
	table.sort(list, function(x, y)
		return x.At < y.At
	end)

	local function piece(from: number, to: number, y0: number, y1: number)
		if to - from < 0.05 or y1 - y0 < 0.05 then
			return
		end
		local center = a + dir * ((from + to) / 2) + Vector3.new(0, (y0 + y1) / 2, 0)
		Build.Part({
			Name = "Wall",
			Size = Vector3.new(thickness, y1 - y0, to - from),
			CFrame = CFrame.lookAt(center, center + dir),
			Color = color,
			Material = material,
			Parent = parent,
		})
	end

	local cursor = 0
	for _, o in list do
		local s = o.At - o.Width / 2
		local e = o.At + o.Width / 2
		piece(cursor, s, 0, height)
		piece(s, e, 0, o.Bottom)
		piece(s, e, o.Top, height)
		cursor = e
	end
	piece(cursor, length, 0, height)
end

local function sandbagWall(parent: Instance, cf: CFrame, bags: number, rows: number)
	local model = Build.Model("Sandbags", parent)
	local bagW, bagH, bagD = 2.3, 0.85, 1.3
	for row = 0, rows - 1 do
		local offset = (row % 2 == 0) and 0 or bagW / 2
		local count = (row % 2 == 0) and bags or bags - 1
		for i = 0, count - 1 do
			local x = -((bags - 1) * bagW) / 2 + i * bagW + offset
			local bag = Build.Part({
				Name = "Sandbag",
				Size = Vector3.new(bagW - 0.08, bagH, bagD),
				CFrame = cf * CFrame.new(x, bagH / 2 + row * (bagH - 0.05), 0) * CFrame.Angles(0, math.rad(rng:NextNumber(-4, 4)), 0),
				Color = C.Sandbag:Lerp(Color3.fromRGB(120, 108, 80), rng:NextNumber(0, 0.5)),
				Material = Enum.Material.Fabric,
				Parent = model,
			})
			bag.CastShadow = true
		end
	end
	return model
end

local function tireStack(parent: Instance, pos: Vector3, height: number)
	for i = 0, height - 1 do
		Build.Part({
			Name = "Tire",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(1.1, 3.2, 3.2),
			CFrame = CFrame.new(pos + Vector3.new(rng:NextNumber(-0.15, 0.15), 0.55 + i * 1.1, rng:NextNumber(-0.15, 0.15))) * CFrame.Angles(0, 0, math.rad(90)),
			Color = C.Tire,
			Material = Enum.Material.Rubber,
			Parent = parent,
		})
	end
end

local function tireWall(parent: Instance, cf: CFrame, count: number)
	for i = 0, count - 1 do
		local p = cf * CFrame.new((i - (count - 1) / 2) * 3.2, 0, 0)
		tireStack(parent, p.Position, 3)
	end
end

local function cableSpool(parent: Instance, cf: CFrame)
	local model = Build.Model("CableSpool", parent)
	for _, x in { -2.2, 2.2 } do
		Build.Part({
			Name = "Disc",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(0.4, 7, 7),
			CFrame = cf * CFrame.new(x, 3.5, 0),
			Color = C.PlywoodDark,
			Material = Enum.Material.Wood,
			Parent = model,
		})
	end
	Build.Part({
		Name = "Core",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(4.4, 3.6, 3.6),
		CFrame = cf * CFrame.new(0, 3.5, 0),
		Color = Color3.fromRGB(40, 40, 40),
		Material = Enum.Material.Rubber,
		Parent = model,
	})
	return model
end

local function palletStack(parent: Instance, cf: CFrame, count: number)
	for i = 0, count - 1 do
		local base = cf * CFrame.new(0, 0.3 + i * 0.6, 0) * CFrame.Angles(0, math.rad(rng:NextNumber(-6, 6)), 0)
		Build.Part({ Name = "Pallet", Size = Vector3.new(4, 0.25, 4), CFrame = base * CFrame.new(0, 0.17, 0), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = parent })
		for _, x in { -1.7, 0, 1.7 } do
			Build.Part({ Name = "Block", Size = Vector3.new(0.5, 0.35, 4), CFrame = base * CFrame.new(x, -0.12, 0), Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = parent })
		end
	end
end

local function hayBales(parent: Instance, cf: CFrame)
	for i, offset in { Vector3.new(-2.6, 1.2, 0), Vector3.new(2.6, 1.2, 0), Vector3.new(0, 3.6, 0) } do
		Build.Part({
			Name = "HayBale" .. i,
			Size = Vector3.new(5, 2.4, 3),
			CFrame = cf * CFrame.new(offset) * CFrame.Angles(0, math.rad(rng:NextNumber(-5, 5)), 0),
			Color = C.Hay,
			Material = Enum.Material.Sand,
			Parent = parent,
		})
	end
end

-- Plywood barricade with a shooting window.
local function barricade(parent: Instance, cf: CFrame, width: number, withWindow: boolean)
	local model = Build.Model("Barricade", parent)
	local a = (cf * CFrame.new(-width / 2, 0, 0)).Position
	local b = (cf * CFrame.new(width / 2, 0, 0)).Position
	local openings = withWindow and { { At = width / 2, Width = 3, Bottom = 3.6, Top = 5.6 } } or nil
	wall(model, a, b, 8, 0.6, C.Plywood, Enum.Material.WoodPlanks, openings)
	-- Support posts
	for _, x in { -width / 2, width / 2 } do
		Build.Part({ Name = "Post", Size = Vector3.new(0.8, 8.4, 0.8), CFrame = cf * CFrame.new(x, 4.2, 0.6), Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = model })
		Build.Part({ Name = "Brace", Size = Vector3.new(0.5, 0.5, 4), CFrame = cf * CFrame.new(x, 2, 2.2) * CFrame.Angles(math.rad(40), 0, 0), Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = model })
	end
	return model
end

local function tree(parent: Instance, pos: Vector3, scale: number)
	local model = Build.Model("Tree", parent)
	local trunkHeight = 14 * scale
	Build.Part({
		Name = "Trunk",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(trunkHeight, 1.6 * scale, 1.6 * scale),
		CFrame = CFrame.new(pos + Vector3.new(0, trunkHeight / 2, 0)) * CFrame.Angles(0, 0, math.rad(90)),
		Color = C.Bark,
		Material = Enum.Material.Wood,
		Parent = model,
	})
	for i = 1, 4 do
		local s = rng:NextNumber(8, 12) * scale
		local offset = Vector3.new(rng:NextNumber(-3, 3) * scale, trunkHeight - 1 + i * 2.2 * scale, rng:NextNumber(-3, 3) * scale)
		local leaf = Build.Part({
			Name = "Leaves",
			Shape = Enum.PartType.Ball,
			Size = Vector3.new(s, s * 0.85, s),
			CFrame = CFrame.new(pos + offset),
			Color = C.Leaf:Lerp(C.LeafDark, rng:NextNumber()),
			Material = Enum.Material.Grass,
			Parent = model,
		})
		leaf.CanCollide = false
	end
	return model
end

local function floodlight(parent: Instance, pos: Vector3, target: Vector3, shadows: boolean)
	local model = Build.Model("Floodlight", parent)
	local height = 34
	Build.Part({
		Name = "Pole",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(height, 1, 1),
		CFrame = CFrame.new(pos + Vector3.new(0, height / 2, 0)) * CFrame.Angles(0, 0, math.rad(90)),
		Color = C.Steel,
		Material = Enum.Material.DiamondPlate,
		Parent = model,
	})
	local top = pos + Vector3.new(0, height, 0)
	Build.Part({ Name = "Crossbar", Size = Vector3.new(6, 0.4, 0.4), CFrame = CFrame.lookAt(top, Vector3.new(target.X, top.Y, target.Z)) * CFrame.new(0, 0.2, 0), Color = C.Steel, Material = Enum.Material.Metal, Parent = model })
	for _, x in { -2, 2 } do
		local headPos = (CFrame.lookAt(top, Vector3.new(target.X, top.Y, target.Z)) * CFrame.new(x, 0.9, -0.4)).Position
		local head = Build.Part({
			Name = "Lamp",
			Size = Vector3.new(1.8, 1.4, 0.7),
			CFrame = CFrame.lookAt(headPos, target),
			Color = Color3.fromRGB(30, 30, 32),
			Material = Enum.Material.Metal,
			Parent = model,
		})
		local lens = Build.Part({
			Name = "Lens",
			Size = Vector3.new(1.6, 1.2, 0.1),
			CFrame = head.CFrame * CFrame.new(0, 0, -0.38),
			Color = Color3.fromRGB(255, 244, 214),
			Material = Enum.Material.Neon,
			CanCollide = false,
			Parent = model,
		})
		lens.CanQuery = false
		lens.CastShadow = false
		local spot = Instance.new("SpotLight")
		spot.Face = Enum.NormalId.Front
		spot.Range = 60
		spot.Angle = 70
		spot.Brightness = 3.2
		spot.Color = Color3.fromRGB(255, 236, 200)
		spot.Shadows = shadows
		spot.Parent = lens
	end
	return model
end

local function container(parent: Instance, cf: CFrame, color: Color3)
	local model = Build.Model("Container", parent)
	local W, H, L = 10, 10.5, 24
	Build.Part({ Name = "Body", Size = Vector3.new(W, H, L), CFrame = cf * CFrame.new(0, H / 2, 0), Color = color, Material = Enum.Material.CorrodedMetal, Parent = model })
	-- Corrugation ribs on both long sides
	for i = 0, 14 do
		local z = -L / 2 + 1 + i * ((L - 2) / 14)
		for _, side in { -1, 1 } do
			local rib = Build.Part({ Name = "Rib", Size = Vector3.new(0.25, H - 1, 0.6), CFrame = cf * CFrame.new(side * (W / 2 + 0.1), H / 2, z), Color = color:Lerp(Color3.new(0, 0, 0), 0.15), Material = Enum.Material.Metal, Parent = model })
			rib.CanCollide = false
		end
	end
	-- Corner castings and door bars
	for _, x in { -W / 2, W / 2 } do
		for _, z in { -L / 2, L / 2 } do
			Build.Part({ Name = "Corner", Size = Vector3.new(0.7, H + 0.05, 0.7), CFrame = cf * CFrame.new(x, H / 2, z), Color = color:Lerp(Color3.new(0, 0, 0), 0.35), Material = Enum.Material.Metal, Parent = model })
		end
	end
	for _, x in { -3.2, -1.2, 1.2, 3.2 } do
		local bar = Build.Part({ Name = "DoorBar", Size = Vector3.new(0.18, H - 0.8, 0.18), CFrame = cf * CFrame.new(x, H / 2, L / 2 + 0.12), Color = C.Steel, Material = Enum.Material.Metal, Parent = model })
		bar.CanCollide = false
	end
	return model
end

local function watchtower(parent: Instance, cf: CFrame)
	local model = Build.Model("Watchtower", parent)
	local deckY = 15
	for _, x in { -4, 4 } do
		for _, z in { -4, 4 } do
			Build.Part({ Name = "Leg", Size = Vector3.new(1, deckY + 9, 1), CFrame = cf * CFrame.new(x, (deckY + 9) / 2, z), Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = model })
		end
	end
	-- Cross bracing
	for _, side in { -4, 4 } do
		local a = (cf * CFrame.new(-4, 1, side)).Position
		local b = (cf * CFrame.new(4, deckY - 1, side)).Position
		Build.Span(a, b, 0.5, { Name = "Brace", Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = model } :: any)
		local c = (cf * CFrame.new(side, 1, -4)).Position
		local d = (cf * CFrame.new(side, deckY - 1, 4)).Position
		Build.Span(c, d, 0.5, { Name = "Brace", Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = model } :: any)
	end
	Build.Part({ Name = "Deck", Size = Vector3.new(10, 0.8, 10), CFrame = cf * CFrame.new(0, deckY, 0), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = model })
	-- Half walls with a gap for the ladder
	local function rail(a: Vector3, b: Vector3, openings)
		wall(model, (cf * CFrame.new(a)).Position, (cf * CFrame.new(b)).Position, 3.4, 0.4, C.Plywood, Enum.Material.WoodPlanks, openings)
	end
	local deck = deckY + 0.4
	rail(Vector3.new(-5, deck, -5), Vector3.new(5, deck, -5))
	rail(Vector3.new(5, deck, -5), Vector3.new(5, deck, 5))
	rail(Vector3.new(-5, deck, 5), Vector3.new(-5, deck, -5))
	rail(Vector3.new(5, deck, 5), Vector3.new(-5, deck, 5), { { At = 5, Width = 3, Bottom = 0, Top = 3.4 } })
	Build.Part({ Name = "Roof", Size = Vector3.new(12, 0.6, 12), CFrame = cf * CFrame.new(0, deckY + 8.6, 0), Color = Color3.fromRGB(70, 70, 64), Material = Enum.Material.CorrodedMetal, Parent = model })
	local ladder = Instance.new("TrussPart")
	ladder.Name = "Ladder"
	ladder.Anchored = true
	ladder.Size = Vector3.new(2, deckY + 2, 2)
	ladder.CFrame = cf * CFrame.new(0, (deckY + 2) / 2, 6)
	ladder.Color = C.Steel
	ladder.Material = Enum.Material.Metal
	ladder.Parent = model
	return model
end

-- Areas -----------------------------------------------------------------------

local function buildGround(map: Instance)
	local terrain = workspace.Terrain
	terrain:Clear()
	terrain:FillBlock(CFrame.new(0, -8, 0), Vector3.new(1000, 16, 1000), Enum.Material.Grass)
	-- Worn dirt lanes where players run the most
	terrain:FillBlock(CFrame.new(0, -8, 0), Vector3.new(FIELD_X * 2 - 30, 16.2, 14), Enum.Material.Ground)
	terrain:FillBlock(CFrame.new(0, -8, 0), Vector3.new(14, 16.2, FIELD_Z * 2 - 30), Enum.Material.Ground)
	terrain:FillBlock(CFrame.new(0, -8, 80), Vector3.new(60, 16.2, 40), Enum.Material.Mud)
	terrain:FillBlock(CFrame.new(0, -8, -80), Vector3.new(50, 16.2, 36), Enum.Material.LeafyGrass)
	for _, x in { -1, 1 } do
		terrain:FillBlock(CFrame.new(x * 150, -8, 0), Vector3.new(34, 16.2, 50), Enum.Material.Pavement)
	end
	terrain:FillBlock(CFrame.new(LOBBY_CENTER - Vector3.new(0, 8, 0)), Vector3.new(140, 16.2, 90), Enum.Material.Pavement)
	terrain.WaterWaveSize = 0
	terrain.Decoration = true

	-- Invisible kill floor safety net
	local floor = Build.Part({ Name = "SafetyFloor", Size = Vector3.new(1200, 2, 1200), CFrame = CFrame.new(0, -30, 0), Transparency = 1, Parent = map })
	floor.CanQuery = false
end

local function buildPerimeter(map: Instance)
	local folder = Build.Folder("Perimeter", map)
	local h = 14
	local corners = {
		Vector3.new(-FIELD_X, 0, -FIELD_Z),
		Vector3.new(FIELD_X, 0, -FIELD_Z),
		Vector3.new(FIELD_X, 0, FIELD_Z),
		Vector3.new(-FIELD_X, 0, FIELD_Z),
	}
	for i = 1, 4 do
		local a, b = corners[i], corners[i % 4 + 1]
		local length = (b - a).Magnitude
		local dir = (b - a).Unit
		-- Netting
		local net = Build.Part({
			Name = "Netting",
			Size = Vector3.new(0.2, h, length),
			CFrame = CFrame.lookAt((a + b) / 2 + Vector3.new(0, h / 2, 0), (a + b) / 2 + Vector3.new(0, h / 2, 0) + dir),
			Color = C.Net,
			Material = Enum.Material.Fabric,
			Transparency = 0.45,
			Parent = folder,
		})
		net.CastShadow = false
		-- Posts every 20 studs
		for d = 0, length, 20 do
			Build.Part({
				Name = "Post",
				Shape = Enum.PartType.Cylinder,
				Size = Vector3.new(h + 1, 0.6, 0.6),
				CFrame = CFrame.new(a + dir * d + Vector3.new(0, (h + 1) / 2, 0)) * CFrame.Angles(0, 0, math.rad(90)),
				Color = C.Steel,
				Material = Enum.Material.Metal,
				Parent = folder,
			})
		end
	end
	-- Tall invisible boundary so nobody climbs out
	for i = 1, 4 do
		local a, b = corners[i], corners[i % 4 + 1]
		local mid = (a + b) / 2
		local dir = (b - a).Unit
		local barrier = Build.Part({
			Name = "Boundary",
			Size = Vector3.new(1, 120, (b - a).Magnitude),
			CFrame = CFrame.lookAt(mid + Vector3.new(0, 60, 0), mid + Vector3.new(0, 60, 0) + dir),
			Transparency = 1,
			Parent = folder,
		})
		barrier.CanQuery = false
	end

	-- Tree line around the outside
	local trees = Build.Folder("Treeline", map)
	for i = 0, 60 do
		local t = i / 60
		local angle = t * math.pi * 2
		local r = Vector3.new(math.cos(angle) * (FIELD_X + rng:NextNumber(18, 50)), 0, math.sin(angle) * (FIELD_Z + rng:NextNumber(18, 50)))
		if not (r.Z > FIELD_Z and math.abs(r.X) < 90) then
			tree(trees, r, rng:NextNumber(0.9, 1.5))
		end
	end

	-- Floodlights
	local lights = Build.Folder("Floodlights", map)
	local spots = {
		Vector3.new(-FIELD_X + 4, 0, -FIELD_Z + 4),
		Vector3.new(FIELD_X - 4, 0, -FIELD_Z + 4),
		Vector3.new(FIELD_X - 4, 0, FIELD_Z - 4),
		Vector3.new(-FIELD_X + 4, 0, FIELD_Z - 4),
		Vector3.new(0, 0, -FIELD_Z + 4),
		Vector3.new(0, 0, FIELD_Z - 4),
		Vector3.new(-FIELD_X + 4, 0, 0),
		Vector3.new(FIELD_X - 4, 0, 0),
		Vector3.new(-85, 0, -FIELD_Z + 4),
		Vector3.new(85, 0, -FIELD_Z + 4),
		Vector3.new(-85, 0, FIELD_Z - 4),
		Vector3.new(85, 0, FIELD_Z - 4),
	}
	for i, p in spots do
		local target = Vector3.new(p.X * 0.55, 0, p.Z * 0.55)
		floodlight(lights, p, target, i <= 8)
	end
end

local function buildSpawn(map: Instance, spawns: Instance, teamKey: string, side: number)
	local team = Config.Teams[teamKey]
	local area = Build.Model(teamKey .. "Base", map)
	local x = side * 150
	local face = CFrame.lookAt(Vector3.new(x, 0, 0), Vector3.new(0, 0, 0)) -- faces the centre

	-- Command tent
	local tentCF = CFrame.new(side * 162, 0, 0) * (face - face.Position)
	Build.Part({ Name = "TentFloor", Size = Vector3.new(26, 0.4, 14), CFrame = tentCF * CFrame.new(0, 0.2, 0) * CFrame.Angles(0, math.rad(90), 0), Color = C.ConcreteDark, Material = Enum.Material.Concrete, Parent = area })
	for _, s in { -1, 1 } do
		local wedge = Build.Wedge({
			Name = "TentRoof",
			Size = Vector3.new(26, 7, 7),
			CFrame = tentCF * CFrame.new(s * 3.5, 9.5, 0) * CFrame.Angles(0, math.rad(s == 1 and -90 or 90), 0),
			Color = C.Canvas,
			Material = Enum.Material.Fabric,
			Parent = area,
		})
		wedge.CanCollide = false
	end
	for _, z in { -12, 12 } do
		for _, s in { -6, 6 } do
			Build.Part({ Name = "TentPole", Size = Vector3.new(0.4, 6, 0.4), CFrame = tentCF * CFrame.new(s, 3, z), Color = C.Steel, Material = Enum.Material.Metal, Parent = area })
		end
	end
	local light = Instance.new("PointLight")
	light.Range = 22
	light.Brightness = 1.4
	light.Color = Color3.fromRGB(255, 214, 160)
	light.Shadows = true
	local bulb = Build.Part({ Name = "Bulb", Shape = Enum.PartType.Ball, Size = Vector3.new(0.8, 0.8, 0.8), CFrame = tentCF * CFrame.new(0, 8.2, 0), Color = Color3.fromRGB(255, 220, 170), Material = Enum.Material.Neon, CanCollide = false, Parent = area })
	bulb.CanQuery = false
	light.Parent = bulb

	-- Gear table and weapon rack
	Build.Part({ Name = "Table", Size = Vector3.new(3, 0.3, 10), CFrame = tentCF * CFrame.new(-3, 3, 0), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = area })
	for _, z in { -4.5, 4.5 } do
		Build.Part({ Name = "TableLeg", Size = Vector3.new(2.6, 3, 0.3), CFrame = tentCF * CFrame.new(-3, 1.5, z), Color = C.Steel, Material = Enum.Material.Metal, Parent = area })
	end

	-- Team banner
	local pole = Build.Part({ Name = "BannerPole", Shape = Enum.PartType.Cylinder, Size = Vector3.new(22, 0.5, 0.5), CFrame = CFrame.new(side * 140, 11, 22) * CFrame.Angles(0, 0, math.rad(90)), Color = C.Steel, Material = Enum.Material.Metal, Parent = area })
	local banner = Build.Part({ Name = "Banner", Size = Vector3.new(0.2, 5, 8), CFrame = CFrame.new(side * 140, 19, 22 + 4.2), Color = team.Color, Material = Enum.Material.Fabric, Parent = area })
	banner.CanCollide = false
	Build.SurfaceText(banner, Enum.NormalId.Right, team.Name:upper(), Color3.new(1, 1, 1))
	Build.SurfaceText(banner, Enum.NormalId.Left, team.Name:upper(), Color3.new(1, 1, 1))
	_ = pole

	-- Spawn pads
	local folder = Build.Folder(teamKey, spawns)
	for i = 0, 5 do
		local zOff = (i - 2.5) * 6
		local pad = Build.Part({
			Name = "Spawn",
			Size = Vector3.new(4, 0.2, 4),
			CFrame = CFrame.new(side * 146, 0.15, zOff) * (face - face.Position),
			Color = team.Color,
			Material = Enum.Material.Neon,
			Transparency = 0.55,
			CanCollide = false,
			Parent = folder,
		})
		pad.CanQuery = false
		pad.CastShadow = false
	end

	-- Safe zone markings and a low wall shielding the spawn
	local zone = Build.Part({ Name = "SafeZone", Size = Vector3.new(30, 0.1, 54), CFrame = CFrame.new(side * 152, 0.06, 0), Color = team.Color, Material = Enum.Material.SmoothPlastic, Transparency = 0.85, CanCollide = false, Parent = area })
	zone.CanQuery = false
	zone.CastShadow = false
	for _, z in { -18, 18 } do
		sandbagWall(area, CFrame.new(side * 134, 0, z) * CFrame.Angles(0, math.rad(90), 0), 6, 3)
	end
	barricade(area, CFrame.new(side * 128, 0, 0) * CFrame.Angles(0, math.rad(90), 0), 14, true)

	watchtower(area, CFrame.new(side * 132, 0, side * 40) * CFrame.Angles(0, math.rad(side == 1 and -90 or 90), 0))
end

local function buildShootHouse(map: Instance)
	local house = Build.Model("ShootHouse", map)
	local W, D, H = 46, 36, 11
	local hw, hd = W / 2, D / 2
	local wallColor = C.Plywood
	local mat = Enum.Material.WoodPlanks
	local function door(at)
		return { At = at, Width = 4.5, Bottom = 0, Top = 8 }
	end
	local function window(at)
		return { At = at, Width = 4, Bottom = 3.8, Top = 6.6 }
	end

	Build.Part({ Name = "Slab", Size = Vector3.new(W + 2, 0.5, D + 2), CFrame = CFrame.new(0, 0.25, 0), Color = C.Concrete, Material = Enum.Material.Concrete, Parent = house })
	local base = 0.5

	-- Outer walls: doors face both spawns plus north/south flank doors.
	wall(house, Vector3.new(-hw, base, -hd), Vector3.new(-hw, base, hd), H, 1, wallColor, mat, { window(6), door(18), window(30) })
	wall(house, Vector3.new(hw, base, -hd), Vector3.new(hw, base, hd), H, 1, wallColor, mat, { window(6), door(18), window(30) })
	wall(house, Vector3.new(-hw, base, hd), Vector3.new(hw, base, hd), H, 1, wallColor, mat, { door(10), window(23), door(36) })
	wall(house, Vector3.new(-hw, base, -hd), Vector3.new(hw, base, -hd), H, 1, wallColor, mat, { door(10), window(23), door(36) })

	-- Inner courtyard walls (16 x 14 open-air centre)
	local cw, cd = 8, 7
	wall(house, Vector3.new(-cw, base, -cd), Vector3.new(-cw, base, cd), H, 0.8, C.PlywoodDark, mat, { door(7) })
	wall(house, Vector3.new(cw, base, -cd), Vector3.new(cw, base, cd), H, 0.8, C.PlywoodDark, mat, { door(7) })
	wall(house, Vector3.new(-cw, base, cd), Vector3.new(cw, base, cd), H, 0.8, C.PlywoodDark, mat, { window(4), door(12) })
	wall(house, Vector3.new(-cw, base, -cd), Vector3.new(cw, base, -cd), H, 0.8, C.PlywoodDark, mat, { door(4), window(12) })

	-- Room dividers out to the corners
	wall(house, Vector3.new(-hw, base, 0), Vector3.new(-cw, base, 0), H, 0.8, C.PlywoodDark, mat, { door(7.5) })
	wall(house, Vector3.new(cw, base, 0), Vector3.new(hw, base, 0), H, 0.8, C.PlywoodDark, mat, { door(7.5) })
	wall(house, Vector3.new(0, base, cd), Vector3.new(0, base, hd), H, 0.8, C.PlywoodDark, mat, { door(5.5) })
	wall(house, Vector3.new(0, base, -hd), Vector3.new(0, base, -cd), H, 0.8, C.PlywoodDark, mat, { door(5.5) })

	-- Roof over the rooms only, leaving the courtyard open to the sky.
	local roofY = base + H + 0.3
	local roofColor = Color3.fromRGB(64, 64, 60)
	local roofMat = Enum.Material.CorrodedMetal
	Build.Part({ Name = "RoofN", Size = Vector3.new(W + 1, 0.6, hd - cd + 0.5), CFrame = CFrame.new(0, roofY, (hd + cd) / 2), Color = roofColor, Material = roofMat, Parent = house })
	Build.Part({ Name = "RoofS", Size = Vector3.new(W + 1, 0.6, hd - cd + 0.5), CFrame = CFrame.new(0, roofY, -(hd + cd) / 2), Color = roofColor, Material = roofMat, Parent = house })
	Build.Part({ Name = "RoofW", Size = Vector3.new(hw - cw + 0.5, 0.6, cd * 2), CFrame = CFrame.new(-(hw + cw) / 2, roofY, 0), Color = roofColor, Material = roofMat, Parent = house })
	Build.Part({ Name = "RoofE", Size = Vector3.new(hw - cw + 0.5, 0.6, cd * 2), CFrame = CFrame.new((hw + cw) / 2, roofY, 0), Color = roofColor, Material = roofMat, Parent = house })

	-- Caged work lights in each room
	for _, p in { Vector3.new(-15, 0, 10), Vector3.new(15, 0, 10), Vector3.new(-15, 0, -10), Vector3.new(15, 0, -10), Vector3.new(0, 0, 12), Vector3.new(0, 0, -12) } do
		local lamp = Build.Part({ Name = "WorkLight", Size = Vector3.new(1.2, 0.3, 1.2), CFrame = CFrame.new(p.X, roofY - 0.5, p.Z), Color = Color3.fromRGB(255, 228, 180), Material = Enum.Material.Neon, CanCollide = false, Parent = house })
		lamp.CanQuery = false
		local l = Instance.new("PointLight")
		l.Range = 20
		l.Brightness = 1.6
		l.Color = Color3.fromRGB(255, 222, 170)
		l.Shadows = true
		l.Parent = lamp
	end

	-- Interior cover
	palletStack(house, CFrame.new(-17, base, 12), 3)
	palletStack(house, CFrame.new(17, base, -12), 3)
	Build.Part({ Name = "Crate", Size = Vector3.new(4, 4, 4), CFrame = CFrame.new(-12, base + 2, -12) * CFrame.Angles(0, math.rad(12), 0), Color = C.PlywoodDark, Material = Enum.Material.WoodPlanks, Parent = house })
	Build.Part({ Name = "Crate", Size = Vector3.new(4, 4, 4), CFrame = CFrame.new(12, base + 2, 12) * CFrame.Angles(0, math.rad(-12), 0), Color = C.PlywoodDark, Material = Enum.Material.WoodPlanks, Parent = house })
	Build.Part({ Name = "Table", Size = Vector3.new(6, 3, 3), CFrame = CFrame.new(-4, base + 1.5, 14), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = house })
	Build.Part({ Name = "Table", Size = Vector3.new(6, 3, 3), CFrame = CFrame.new(4, base + 1.5, -14), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = house })

	-- Exterior signage
	local sign = Build.Part({ Name = "Sign", Size = Vector3.new(10, 2.4, 0.3), CFrame = CFrame.new(0, 9.5, hd + 0.7), Color = Color3.fromRGB(20, 20, 20), Parent = house })
	Build.SurfaceText(sign, Enum.NormalId.Back, "CQB HOUSE", Color3.fromRGB(255, 200, 60))
	return house
end

local function buildContainerYard(map: Instance)
	local yard = Build.Model("ContainerYard", map)
	local z = 80
	local function place(x: number, zz: number, yaw: number, stack: number, colorIndex: number)
		for level = 0, stack - 1 do
			container(yard, CFrame.new(x, level * 10.55, zz) * CFrame.Angles(0, math.rad(yaw), 0), C.ContainerColors[(colorIndex + level - 1) % #C.ContainerColors + 1])
		end
	end
	-- Symmetric across X = 0
	for _, s in { -1, 1 } do
		place(s * 14, z + 14, 90, 2, s == 1 and 1 or 2)
		place(s * 14, z - 14, 90, 1, s == 1 and 3 or 4)
		place(s * 36, z + 2, 0, 1, s == 1 and 5 or 1)
		place(s * 30, z + 30, 90, 1, s == 1 and 2 or 3)
		place(s * 52, z - 18, 15 * s, 1, s == 1 and 4 or 5)
		tireWall(yard, CFrame.new(s * 24, 0, z - 30) * CFrame.Angles(0, math.rad(90), 0), 3)
		cableSpool(yard, CFrame.new(s * 6, 0, z - 2))
	end
	palletStack(yard, CFrame.new(0, 0, z + 34), 4)
	-- Catwalk between the stacked containers
	Build.Part({ Name = "Catwalk", Size = Vector3.new(18, 0.4, 3), CFrame = CFrame.new(0, 21.2, z + 14), Color = C.Steel, Material = Enum.Material.DiamondPlate, Parent = yard })
	for _, s in { -1, 1 } do
		local ladder = Instance.new("TrussPart")
		ladder.Anchored = true
		ladder.Size = Vector3.new(2, 22, 2)
		ladder.CFrame = CFrame.new(s * 14, 11, z + 1)
		ladder.Color = C.Steel
		ladder.Material = Enum.Material.Metal
		ladder.Parent = yard
	end
	return yard
end

local function buildWoodline(map: Instance)
	local wood = Build.Model("Woodline", map)
	local z = -80
	-- Log-and-sandbag bunker in the middle
	local bunker = Build.Model("Bunker", wood)
	for _, s in { -1, 1 } do
		sandbagWall(bunker, CFrame.new(s * 7, 0, z) * CFrame.Angles(0, math.rad(90), 0), 6, 4)
	end
	sandbagWall(bunker, CFrame.new(0, 0, z - 7), 5, 4)
	sandbagWall(bunker, CFrame.new(0, 0, z + 7), 3, 2)
	for i = -3, 3 do
		Build.Part({ Name = "Log", Shape = Enum.PartType.Cylinder, Size = Vector3.new(16, 1.4, 1.4), CFrame = CFrame.new(i * 2, 4.6, z) * CFrame.Angles(0, math.rad(90), 0), Color = C.Bark, Material = Enum.Material.Wood, Parent = bunker })
	end
	Build.Part({ Name = "Camo", Size = Vector3.new(18, 0.3, 18), CFrame = CFrame.new(0, 5.5, z), Color = C.LeafDark, Material = Enum.Material.Grass, Parent = bunker })

	for _, s in { -1, 1 } do
		-- Dense trees and fallen logs either side
		for i = 1, 9 do
			tree(wood, Vector3.new(s * rng:NextNumber(18, 80), 0, z + rng:NextNumber(-34, 30)), rng:NextNumber(0.7, 1.15))
		end
		for i = 1, 3 do
			Build.Part({
				Name = "FallenLog",
				Shape = Enum.PartType.Cylinder,
				Size = Vector3.new(rng:NextNumber(10, 16), 2.2, 2.2),
				CFrame = CFrame.new(s * rng:NextNumber(20, 70), 1.1, z + rng:NextNumber(-25, 25)) * CFrame.Angles(0, math.rad(rng:NextNumber(0, 180)), 0),
				Color = C.Bark,
				Material = Enum.Material.Wood,
				Parent = wood,
			})
		end
		hayBales(wood, CFrame.new(s * 26, 0, z + 18))
		hayBales(wood, CFrame.new(s * 42, 0, z - 22) * CFrame.Angles(0, math.rad(90), 0))
	end
	return wood
end

local function buildMidfield(map: Instance)
	local mid = Build.Model("Midfield", map)
	for _, s in { -1, 1 } do
		-- Mirrored cover lanes between spawns and the objectives
		barricade(mid, CFrame.new(s * 70, 0, 22) * CFrame.Angles(0, math.rad(90), 0), 12, true)
		barricade(mid, CFrame.new(s * 70, 0, -22) * CFrame.Angles(0, math.rad(90), 0), 12, true)
		barricade(mid, CFrame.new(s * 98, 0, 52), 14, false)
		barricade(mid, CFrame.new(s * 98, 0, -52), 14, false)
		barricade(mid, CFrame.new(s * 44, 0, 40) * CFrame.Angles(0, math.rad(35 * s), 0), 10, true)
		barricade(mid, CFrame.new(s * 44, 0, -40) * CFrame.Angles(0, math.rad(-35 * s), 0), 10, true)
		sandbagWall(mid, CFrame.new(s * 50, 0, 0) * CFrame.Angles(0, math.rad(90), 0), 5, 3)
		sandbagWall(mid, CFrame.new(s * 112, 0, 18), 4, 3)
		sandbagWall(mid, CFrame.new(s * 112, 0, -18), 4, 3)
		tireWall(mid, CFrame.new(s * 86, 0, 0) * CFrame.Angles(0, math.rad(90), 0), 4)
		tireStack(mid, Vector3.new(s * 60, 0, 70), 4)
		tireStack(mid, Vector3.new(s * 60, 0, -70), 4)
		cableSpool(mid, CFrame.new(s * 116, 0, 60) * CFrame.Angles(0, math.rad(20), 0))
		cableSpool(mid, CFrame.new(s * 116, 0, -60) * CFrame.Angles(0, math.rad(-20), 0))
		palletStack(mid, CFrame.new(s * 30, 0, 18), 3)
		palletStack(mid, CFrame.new(s * 30, 0, -18), 2)
		hayBales(mid, CFrame.new(s * 130, 0, 92))
		hayBales(mid, CFrame.new(s * 130, 0, -92))
		-- Wrecked car as heavy cover
		local car = Build.Model("Wreck", mid)
		local carCF = CFrame.new(s * 80, 0, 96) * CFrame.Angles(0, math.rad(20 * s), 0)
		Build.Part({ Name = "Body", Size = Vector3.new(7, 3, 14), CFrame = carCF * CFrame.new(0, 2.3, 0), Color = Color3.fromRGB(92, 70, 52), Material = Enum.Material.CorrodedMetal, Parent = car })
		Build.Part({ Name = "Cabin", Size = Vector3.new(6.6, 2.4, 7), CFrame = carCF * CFrame.new(0, 4.9, 0.8), Color = Color3.fromRGB(80, 60, 46), Material = Enum.Material.CorrodedMetal, Parent = car })
		for _, wx in { -3.4, 3.4 } do
			for _, wz in { -4.4, 4.4 } do
				Build.Part({ Name = "Wheel", Shape = Enum.PartType.Cylinder, Size = Vector3.new(1, 2.6, 2.6), CFrame = carCF * CFrame.new(wx, 1.3, wz), Color = C.Tire, Material = Enum.Material.Rubber, Parent = car })
			end
		end
	end
	return mid
end

local function buildObjectives(map: Instance)
	local folder = Build.Folder("Objectives", map)
	local points = {
		A = Vector3.new(0, 0, 80),
		B = Vector3.new(0, 0.5, 0),
		C = Vector3.new(0, 0, -80),
	}
	local radius = Config.Modes.DOM.CaptureRadius
	for name, pos in points do
		local model = Build.Model(name, folder)
		local ring = Build.Part({
			Name = "Zone",
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(0.2, radius * 2, radius * 2),
			CFrame = CFrame.new(pos + Vector3.new(0, 0.15, 0)) * CFrame.Angles(0, 0, math.rad(90)),
			Color = C.Neutral,
			Material = Enum.Material.Neon,
			Transparency = 0.82,
			CanCollide = false,
			Parent = model,
		})
		ring.CanQuery = false
		ring.CastShadow = false
		Build.Part({ Name = "Pole", Shape = Enum.PartType.Cylinder, Size = Vector3.new(14, 0.4, 0.4), CFrame = CFrame.new(pos + Vector3.new(0, 7, 0)) * CFrame.Angles(0, 0, math.rad(90)), Color = C.Steel, Material = Enum.Material.Metal, Parent = model })
		local flag = Build.Part({ Name = "Flag", Size = Vector3.new(0.15, 3, 4.6), CFrame = CFrame.new(pos + Vector3.new(0, 12.3, 2.4)), Color = C.Neutral, Material = Enum.Material.Fabric, CanCollide = false, Parent = model })
		flag.CanQuery = false
		local glow = Instance.new("PointLight")
		glow.Name = "Glow"
		glow.Range = 16
		glow.Brightness = 1.2
		glow.Color = C.Neutral
		glow.Parent = flag

		local billboard = Instance.new("BillboardGui")
		billboard.Name = "Marker"
		billboard.Size = UDim2.fromOffset(44, 44)
		billboard.StudsOffset = Vector3.new(0, 16, 0)
		billboard.AlwaysOnTop = true
		billboard.LightInfluence = 0
		billboard.MaxDistance = 600
		billboard.Enabled = false
		billboard.Adornee = ring
		billboard.Parent = model
		local label = Instance.new("TextLabel")
		label.Name = "Letter"
		label.Size = UDim2.fromScale(1, 1)
		label.BackgroundColor3 = Color3.fromRGB(20, 22, 26)
		label.BackgroundTransparency = 0.25
		label.TextColor3 = C.Neutral
		label.Font = Enum.Font.GothamBlack
		label.TextScaled = true
		label.Text = name
		label.Parent = billboard
		local corner = Instance.new("UICorner")
		corner.CornerRadius = UDim.new(1, 0)
		corner.Parent = label
		local stroke = Instance.new("UIStroke")
		stroke.Color = C.Neutral
		stroke.Thickness = 2
		stroke.Parent = label

		model:SetAttribute("Owner", "")
		model:SetAttribute("Progress", 0)
		model:SetAttribute("Capturing", "")
	end
	return folder
end

local function buildLobby(map: Instance, spawns: Instance)
	local lobby = Build.Model("StagingArea", map)
	local o = LOBBY_CENTER

	Build.Part({ Name = "Pad", Size = Vector3.new(120, 1, 70), CFrame = CFrame.new(o + Vector3.new(0, 0.5, 0)), Color = C.Concrete, Material = Enum.Material.Concrete, Parent = lobby })
	-- Walls (low on the field side so you can look over the field)
	wall(lobby, o + Vector3.new(-60, 1, -35), o + Vector3.new(60, 1, -35), 5, 1, C.ConcreteDark, Enum.Material.Concrete)
	wall(lobby, o + Vector3.new(-60, 1, 35), o + Vector3.new(60, 1, 35), 12, 1, C.ConcreteDark, Enum.Material.Concrete)
	wall(lobby, o + Vector3.new(-60, 1, -35), o + Vector3.new(-60, 1, 35), 12, 1, C.ConcreteDark, Enum.Material.Concrete)
	wall(lobby, o + Vector3.new(60, 1, -35), o + Vector3.new(60, 1, 35), 12, 1, C.ConcreteDark, Enum.Material.Concrete)

	-- Signage
	local sign = Build.Part({ Name = "Sign", Size = Vector3.new(36, 6, 0.5), CFrame = CFrame.new(o + Vector3.new(0, 9, 34.2)), Color = Color3.fromRGB(18, 20, 22), Parent = lobby })
	Build.SurfaceText(sign, Enum.NormalId.Front, Config.GameName:upper() .. "  •  " .. Config.FieldName:upper(), Color3.fromRGB(255, 196, 64))
	local safety = Build.Part({ Name = "SafetySign", Size = Vector3.new(16, 5, 0.4), CFrame = CFrame.new(o + Vector3.new(-40, 6, 34.2)), Color = Color3.fromRGB(200, 40, 30), Parent = lobby })
	Build.SurfaceText(safety, Enum.NormalId.Front, "EYE PROTECTION MUST BE WORN BEYOND THIS POINT", Color3.new(1, 1, 1))
	local rules = Build.Part({ Name = "RulesBoard", Size = Vector3.new(16, 8, 0.4), CFrame = CFrame.new(o + Vector3.new(40, 6, 34.2)), Color = Color3.fromRGB(24, 28, 32), Parent = lobby })
	Build.SurfaceText(rules, Enum.NormalId.Front, "FIELD RULES\nCall your hits  •  No blind firing\nNo friendly fire  •  Respect spawn zones", Color3.fromRGB(230, 230, 230))

	-- Chrono station
	Build.Part({ Name = "ChronoTable", Size = Vector3.new(10, 0.4, 4), CFrame = CFrame.new(o + Vector3.new(-30, 4, 20)), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = lobby })
	for _, x in { -4.5, 4.5 } do
		Build.Part({ Name = "Leg", Size = Vector3.new(0.4, 3, 3.6), CFrame = CFrame.new(o + Vector3.new(-30 + x, 2.5, 20)), Color = C.Steel, Material = Enum.Material.Metal, Parent = lobby })
	end
	local chrono = Build.Part({ Name = "Chronograph", Size = Vector3.new(2, 1, 1.2), CFrame = CFrame.new(o + Vector3.new(-30, 4.7, 20)), Color = Color3.fromRGB(30, 30, 30), Parent = lobby })
	Build.SurfaceText(chrono, Enum.NormalId.Front, "358 FPS", Color3.fromRGB(80, 255, 120), Color3.fromRGB(10, 14, 10))

	-- Weapon racks with display guns are added by the server after the gun builder runs.
	local racks = Build.Folder("Racks", lobby)
	for i = 0, 4 do
		Build.Part({ Name = "Rack" .. i, Size = Vector3.new(6, 0.4, 2), CFrame = CFrame.new(o + Vector3.new(-50 + i * 7, 3.2, 31)), Color = C.PlywoodDark, Material = Enum.Material.Wood, Parent = racks })
	end

	-- Practice range on the east side
	local range = Build.Folder("Range", lobby)
	Build.Part({ Name = "FiringLine", Size = Vector3.new(0.4, 0.05, 30), CFrame = CFrame.new(o + Vector3.new(10, 1.03, 0)), Color = Color3.fromRGB(255, 200, 40), Material = Enum.Material.Neon, CanCollide = false, Parent = range })
	Build.Part({ Name = "Bench", Size = Vector3.new(2, 3.2, 30), CFrame = CFrame.new(o + Vector3.new(12, 2.6, 0)), Color = C.Plywood, Material = Enum.Material.WoodPlanks, Parent = range })
	Build.Part({ Name = "Backstop", Size = Vector3.new(1, 12, 64), CFrame = CFrame.new(o + Vector3.new(58, 7, 0)), Color = C.Net, Material = Enum.Material.Fabric, Parent = range })
	local targets = Build.Folder("Targets", range)
	for i, spec in { { 24, -10 }, { 30, 8 }, { 38, -2 }, { 46, 12 }, { 52, -12 }, { 55, 3 } } do
		local dist, zOff = spec[1], spec[2]
		local standPos = o + Vector3.new(dist, 1, zOff)
		Build.Part({ Name = "Stand", Size = Vector3.new(0.4, 4, 0.4), CFrame = CFrame.new(standPos + Vector3.new(0, 2, 0)), Color = C.Steel, Material = Enum.Material.Metal, Parent = targets })
		local plate = Build.Part({
			Name = "Plate" .. i,
			Shape = Enum.PartType.Cylinder,
			Size = Vector3.new(0.3, 3, 3),
			CFrame = CFrame.new(standPos + Vector3.new(0, 5, 0)),
			Color = Color3.fromRGB(230, 230, 230),
			Material = Enum.Material.Metal,
			Parent = targets,
		})
		CollectionService:AddTag(plate, "PracticeTarget")
	end

	-- Lobby lighting
	for _, x in { -40, 0, 40 } do
		local lamp = Build.Part({ Name = "Lamp", Size = Vector3.new(6, 0.4, 1.2), CFrame = CFrame.new(o + Vector3.new(x, 13, 0)), Color = Color3.fromRGB(255, 236, 210), Material = Enum.Material.Neon, CanCollide = false, Parent = lobby })
		lamp.CanQuery = false
		local l = Instance.new("SurfaceLight")
		l.Face = Enum.NormalId.Bottom
		l.Range = 26
		l.Angle = 120
		l.Brightness = 2
		l.Color = Color3.fromRGB(255, 232, 200)
		l.Parent = lamp
	end

	local folder = Build.Folder("Lobby", spawns)
	for i = 0, 7 do
		local p = Build.Part({
			Name = "Spawn",
			Size = Vector3.new(4, 0.2, 4),
			CFrame = CFrame.new(o + Vector3.new(-30 + (i % 4) * 8, 1.1, -12 + math.floor(i / 4) * 8)) * CFrame.Angles(0, math.rad(180), 0),
			Color = Color3.fromRGB(255, 196, 64),
			Material = Enum.Material.Neon,
			Transparency = 0.7,
			CanCollide = false,
			Parent = folder,
		})
		p.CanQuery = false
	end
	return lobby
end

local function setupLighting()
	for _, child in Lighting:GetChildren() do
		if child:IsA("PostEffect") or child:IsA("Atmosphere") or child:IsA("Sky") then
			child:Destroy()
		end
	end
	Lighting.ClockTime = 18.35
	Lighting.GeographicLatitude = 38
	Lighting.Brightness = 2.2
	Lighting.Ambient = Color3.fromRGB(40, 38, 44)
	Lighting.OutdoorAmbient = Color3.fromRGB(108, 98, 102)
	Lighting.EnvironmentDiffuseScale = 1
	Lighting.EnvironmentSpecularScale = 1
	Lighting.GlobalShadows = true

	local atmosphere = Instance.new("Atmosphere")
	atmosphere.Density = 0.32
	atmosphere.Offset = 0.15
	atmosphere.Color = Color3.fromRGB(214, 170, 140)
	atmosphere.Decay = Color3.fromRGB(96, 78, 92)
	atmosphere.Glare = 0.35
	atmosphere.Haze = 1.4
	atmosphere.Parent = Lighting

	local sky = Instance.new("Sky")
	sky.SunAngularSize = 14
	sky.MoonAngularSize = 8
	sky.StarCount = 2500
	sky.Parent = Lighting

	local bloom = Instance.new("BloomEffect")
	bloom.Intensity = 0.6
	bloom.Size = 28
	bloom.Threshold = 1.6
	bloom.Parent = Lighting

	local sunRays = Instance.new("SunRaysEffect")
	sunRays.Intensity = 0.06
	sunRays.Spread = 0.6
	sunRays.Parent = Lighting

	local grade = Instance.new("ColorCorrectionEffect")
	grade.Name = "Grade"
	grade.Brightness = 0.02
	grade.Contrast = 0.12
	grade.Saturation = 0.05
	grade.TintColor = Color3.fromRGB(255, 244, 236)
	grade.Parent = Lighting
end

function MapBuilder.Build()
	local old = workspace:FindFirstChild("Map")
	if old then
		old:Destroy()
	end
	local map = Build.Folder("Map", workspace)
	local spawns = Build.Folder("Spawns", map)
	Build.Folder("Effects", workspace)

	setupLighting()
	buildGround(map)
	buildPerimeter(map)
	buildSpawn(map, spawns, "Blue", -1)
	buildSpawn(map, spawns, "Red", 1)
	buildShootHouse(map)
	buildContainerYard(map)
	buildWoodline(map)
	buildMidfield(map)
	buildObjectives(map)
	buildLobby(map, spawns)
	return map
end

MapBuilder.LobbyCenter = LOBBY_CENTER

return MapBuilder
