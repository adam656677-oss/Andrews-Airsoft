--[[
	"Velvet Club": a night-time CQB map. A two-level nightclub in the rain with
	a neon-lit street on one side and a loading dock on the other.

	Layout (top-down, local coordinates, +X east):

	   rainy street │ ─────────── club ─────────── │ loading dock
	   BLUE spawn   │ lobby │ dance floor (B) │ back │ RED spawn
	                │       │ bar (A) south    │ hall │
	                │       │ VIP mezzanine (C) north, upstairs

	Mirrored across local X = 0 so both teams get the same routes.
]]

local Build = require(script.Parent.Build)
local Config = require(game:GetService("ReplicatedStorage").Shared.Config)

local ClubBuilder = {}

local O = Vector3.new(1000, 0, 0) -- world origin of the arena
ClubBuilder.Origin = O

local HALF_X, HALF_Z = 60, 45 -- building footprint
local FLOOR_H = 14 -- ground floor height; mezzanine sits on top

local C = {
	Asphalt = Color3.fromRGB(34, 35, 38),
	Brick = Color3.fromRGB(78, 42, 36),
	BrickDark = Color3.fromRGB(52, 30, 28),
	Velvet = Color3.fromRGB(92, 14, 30),
	Walnut = Color3.fromRGB(58, 34, 22),
	Marble = Color3.fromRGB(24, 24, 28),
	Brass = Color3.fromRGB(196, 150, 72),
	Steel = Color3.fromRGB(70, 72, 78),
	Glass = Color3.fromRGB(140, 170, 190),
	Pink = Color3.fromRGB(255, 40, 140),
	Cyan = Color3.fromRGB(40, 220, 255),
	Amber = Color3.fromRGB(255, 170, 60),
}

local rng = Random.new(77)

local function P(x: number, y: number, z: number): Vector3
	return O + Vector3.new(x, y, z)
end

local function part(parent: Instance, name: string, size: Vector3, cf: CFrame, color: Color3, material: Enum.Material?, extra: { [string]: any }?)
	local p = Build.Part({ Name = name, Size = size, CFrame = cf, Color = color, Material = material or Enum.Material.SmoothPlastic, Parent = parent })
	for k, v in extra or {} do
		(p :: any)[k] = v
	end
	return p
end

local function glow(parent: Instance, name: string, size: Vector3, cf: CFrame, color: Color3, lightRange: number?, brightness: number?)
	local p = part(parent, name, size, cf, color, Enum.Material.Neon, { CanCollide = false, CastShadow = false })
	p.CanQuery = false
	if lightRange then
		local l = Instance.new("PointLight")
		l.Color = color
		l.Range = lightRange
		l.Brightness = brightness or 1.5
		l.Parent = p
	end
	return p
end

local function wall(parent: Instance, a: Vector3, b: Vector3, h: number, color: Color3, material: Enum.Material, openings: { Build.Opening }?)
	Build.Wall(parent, a, b, h, 1, color, material, openings)
end

-- Exterior ------------------------------------------------------------------------

local function buildGround(arena: Instance)
	local ground = part(arena, "Street", Vector3.new(280, 2, 160), CFrame.new(P(0, -1, 0)), C.Asphalt, Enum.Material.Asphalt)
	ground.Reflectance = 0.12 -- wet tarmac picks up the neon
	-- Puddles: thin glossy patches.
	for _ = 1, 26 do
		local x = rng:NextNumber(-130, 130)
		if math.abs(x) > HALF_X + 4 then
			local puddle = part(arena, "Puddle", Vector3.new(rng:NextNumber(3, 8), 0.05, rng:NextNumber(2, 6)), CFrame.new(P(x, 0.03, rng:NextNumber(-70, 70))) * CFrame.Angles(0, rng:NextNumber(0, math.pi), 0), Color3.fromRGB(20, 22, 26), Enum.Material.Glass, { Reflectance = 0.45, CanCollide = false })
			puddle.CanQuery = false
		end
	end
	-- Boundary walls: tall brick buildings around the block.
	local function boundary(a: Vector3, b: Vector3)
		wall(arena, a, b, 40, C.BrickDark, Enum.Material.Brick)
	end
	boundary(P(-140, 0, -80), P(140, 0, -80))
	boundary(P(-140, 0, 80), P(140, 0, 80))
	boundary(P(-140, 0, -80), P(-140, 0, 80))
	boundary(P(140, 0, -80), P(140, 0, 80))
	-- Lit windows on the surrounding buildings.
	for _, z in { -79.3, 79.3 } do
		for i = 0, 13 do
			for row = 0, 2 do
				if rng:NextNumber() < 0.55 then
					local warm = rng:NextNumber() < 0.7
					glow(arena, "Window", Vector3.new(4, 5, 0.2), CFrame.new(P(-126 + i * 19.5, 16 + row * 9, z)), warm and Color3.fromRGB(255, 196, 120) or Color3.fromRGB(120, 180, 255))
				end
			end
		end
	end
	local roof = part(arena, "Ceiling", Vector3.new(280, 1, 160), CFrame.new(P(0, 60, 0)), C.Asphalt, Enum.Material.Asphalt, { Transparency = 1 })
	roof.CanQuery = false
end

local function car(parent: Instance, cf: CFrame, color: Color3)
	local m = Build.Model("Car", parent)
	part(m, "Body", Vector3.new(6.4, 2.4, 14), cf * CFrame.new(0, 2, 0), color, Enum.Material.Metal, { Reflectance = 0.25 })
	part(m, "Cabin", Vector3.new(5.8, 2, 7), cf * CFrame.new(0, 4.1, 0.6), Color3.fromRGB(20, 22, 26), Enum.Material.Glass, { Reflectance = 0.4, Transparency = 0.2 })
	for _, x in { -3.2, 3.2 } do
		for _, z in { -4.4, 4.4 } do
			part(m, "Wheel", Vector3.new(1, 2.4, 2.4), cf * CFrame.new(x, 1.2, z), Color3.fromRGB(18, 18, 18), Enum.Material.Rubber, { Shape = Enum.PartType.Cylinder })
		end
	end
	for _, x in { -2.4, 2.4 } do
		glow(m, "TailLight", Vector3.new(1.2, 0.4, 0.1), cf * CFrame.new(x, 2.6, 7.02), Color3.fromRGB(255, 30, 30), 8, 1)
		glow(m, "HeadLight", Vector3.new(1.2, 0.4, 0.1), cf * CFrame.new(x, 2.4, -7.02), Color3.fromRGB(255, 244, 220))
	end
	return m
end

local function streetLamp(parent: Instance, pos: Vector3)
	part(parent, "LampPost", Vector3.new(18, 0.6, 0.6), CFrame.new(pos + Vector3.new(0, 9, 0)) * CFrame.Angles(0, 0, math.rad(90)), C.Steel, Enum.Material.Metal, { Shape = Enum.PartType.Cylinder })
	local head = glow(parent, "LampHead", Vector3.new(2, 0.4, 1), CFrame.new(pos + Vector3.new(0, 18, 0)), Color3.fromRGB(255, 200, 140))
	local s = Instance.new("SpotLight")
	s.Face = Enum.NormalId.Bottom
	s.Range = 40
	s.Angle = 100
	s.Brightness = 2.5
	s.Color = Color3.fromRGB(255, 196, 130)
	s.Shadows = true
	s.Parent = head
end

local function buildStreet(arena: Instance)
	-- West: the street out front (Blue).
	local street = Build.Model("FrontStreet", arena)
	car(street, CFrame.new(P(-100, 0, -42)) * CFrame.Angles(0, math.rad(4), 0), Color3.fromRGB(16, 16, 18))
	car(street, CFrame.new(P(-82, 0, 40)) * CFrame.Angles(0, math.rad(-80), 0), Color3.fromRGB(110, 14, 20))
	for _, z in { -60, -20, 20, 60 } do
		streetLamp(street, P(-74, 0, z))
	end
	-- Velvet rope queue and planters as low cover.
	for i = -3, 3 do
		part(street, "RopePost", Vector3.new(0.4, 3, 0.4), CFrame.new(P(-68, 1.5, i * 4)), C.Brass, Enum.Material.Metal)
	end
	part(street, "VelvetRope", Vector3.new(0.25, 0.25, 24), CFrame.new(P(-68, 2.6, 0)), C.Velvet, Enum.Material.Fabric, { CanCollide = false })
	for _, z in { -30, 30 } do
		part(street, "Planter", Vector3.new(8, 3, 3), CFrame.new(P(-92, 1.5, z)), Color3.fromRGB(60, 60, 64), Enum.Material.Concrete)
		part(street, "Hedge", Vector3.new(7.6, 2, 2.6), CFrame.new(P(-92, 4, z)), Color3.fromRGB(30, 60, 34), Enum.Material.Grass)
	end
	part(street, "Dumpster", Vector3.new(6, 5, 4), CFrame.new(P(-120, 2.5, -66)), Color3.fromRGB(30, 70, 50), Enum.Material.Metal)
	part(street, "Kiosk", Vector3.new(6, 9, 6), CFrame.new(P(-118, 4.5, 58)), Color3.fromRGB(40, 40, 46), Enum.Material.Metal)
	glow(street, "KioskSign", Vector3.new(6.2, 1.4, 6.2), CFrame.new(P(-118, 9.7, 58)), C.Cyan, 18, 1.2)

	-- East: loading dock (Red).
	local dock = Build.Model("LoadingDock", arena)
	part(dock, "DockPlatform", Vector3.new(14, 4, 60), CFrame.new(P(HALF_X + 7, 2, 0)), Color3.fromRGB(80, 80, 84), Enum.Material.Concrete)
	for _, z in { -24, 24 } do
		part(dock, "DockStairs", Vector3.new(8, 2, 6), CFrame.new(P(HALF_X + 18, 1, z)), Color3.fromRGB(80, 80, 84), Enum.Material.Concrete)
	end
	local truck = Build.Model("Truck", dock)
	part(truck, "Trailer", Vector3.new(10, 11, 30), CFrame.new(P(104, 6.5, -40)), Color3.fromRGB(190, 190, 194), Enum.Material.Metal)
	part(truck, "Cab", Vector3.new(9, 8, 9), CFrame.new(P(104, 5, -60)), Color3.fromRGB(20, 40, 90), Enum.Material.Metal)
	for _, z in { -50, -30, 10, 30 } do
		part(dock, "PalletStack", Vector3.new(4, 3 + rng:NextInteger(0, 3), 4), CFrame.new(P(rng:NextNumber(84, 124), 2, z)) * CFrame.Angles(0, rng:NextNumber(0, 1), 0), Color3.fromRGB(140, 104, 66), Enum.Material.WoodPlanks)
	end
	part(dock, "Dumpster", Vector3.new(6, 5, 4), CFrame.new(P(122, 2.5, 66)), Color3.fromRGB(30, 50, 80), Enum.Material.Metal)
	part(dock, "Crates", Vector3.new(8, 6, 6), CFrame.new(P(96, 3, 52)), Color3.fromRGB(70, 60, 46), Enum.Material.WoodPlanks)
	for _, z in { -60, -20, 20, 60 } do
		streetLamp(dock, P(76, 0, z))
	end
end

-- Club interior ---------------------------------------------------------------------

local function door(at: number)
	return { At = at, Width = 6, Bottom = 0, Top = 9 }
end

local function buildShell(club: Instance)
	local floor = part(club, "Floor", Vector3.new(HALF_X * 2, 1, HALF_Z * 2), CFrame.new(P(0, 0.5, 0)), C.Marble, Enum.Material.Marble)
	floor.Reflectance = 0.12
	local h = FLOOR_H * 2 + 2
	-- Outer brick walls with double doors front and back, side fire exits.
	wall(club, P(-HALF_X, 1, -HALF_Z), P(-HALF_X, 1, HALF_Z), h, C.Brick, Enum.Material.Brick, { door(HALF_Z - 12), door(HALF_Z), door(HALF_Z + 12) })
	wall(club, P(HALF_X, 1, -HALF_Z), P(HALF_X, 1, HALF_Z), h, C.Brick, Enum.Material.Brick, { door(HALF_Z - 12), door(HALF_Z), door(HALF_Z + 12) })
	wall(club, P(-HALF_X, 1, -HALF_Z), P(HALF_X, 1, -HALF_Z), h, C.Brick, Enum.Material.Brick, { door(20), door(HALF_X * 2 - 20) })
	wall(club, P(-HALF_X, 1, HALF_Z), P(HALF_X, 1, HALF_Z), h, C.Brick, Enum.Material.Brick)
	part(club, "Roof", Vector3.new(HALF_X * 2 + 2, 1, HALF_Z * 2 + 2), CFrame.new(P(0, h + 1.5, 0)), C.BrickDark, Enum.Material.Concrete)

	-- Neon sign over the front door.
	local sign = part(club, "SignBoard", Vector3.new(1, 6, 26), CFrame.new(P(-HALF_X - 1, 20, 0)), Color3.fromRGB(14, 14, 16), Enum.Material.Metal)
	Build.SurfaceText(sign, Enum.NormalId.Left, "VELVET", C.Pink)
	glow(club, "SignGlow", Vector3.new(0.3, 6.4, 26.4), CFrame.new(P(-HALF_X - 1.6, 20, 0)), C.Pink, 40, 2.5)
	local back = part(club, "BackSign", Vector3.new(1, 3, 14), CFrame.new(P(HALF_X + 1, 14, 0)), Color3.fromRGB(14, 14, 16), Enum.Material.Metal)
	Build.SurfaceText(back, Enum.NormalId.Right, "DELIVERIES", C.Amber)
	glow(club, "BackGlow", Vector3.new(0.3, 3.2, 14.4), CFrame.new(P(HALF_X + 1.6, 14, 0)), C.Amber, 24, 1.5)

	-- Front lobby / back hall partitions with wide openings into the main hall.
	for _, s in { -1, 1 } do
		local x = s * (HALF_X - 16)
		wall(club, P(x, 1, -HALF_Z), P(x, 1, HALF_Z), FLOOR_H, C.Walnut, Enum.Material.Wood, { door(14), { At = HALF_Z, Width = 12, Bottom = 0, Top = 10 }, door(HALF_Z * 2 - 14) })
	end
	-- Coat check and cash desk as lobby cover.
	part(club, "CoatCheck", Vector3.new(4, 4, 16), CFrame.new(P(-HALF_X + 6, 3, -22)), C.Walnut, Enum.Material.Wood)
	part(club, "CashDesk", Vector3.new(4, 4, 16), CFrame.new(P(HALF_X - 6, 3, -22)), C.Steel, Enum.Material.Metal)
	for _, s in { -1, 1 } do
		part(club, "Sofa", Vector3.new(4, 3, 10), CFrame.new(P(s * (HALF_X - 8), 2.5, 20)), C.Velvet, Enum.Material.Fabric)
		part(club, "Column", Vector3.new(2, FLOOR_H, 2), CFrame.new(P(s * (HALF_X - 24), 1 + FLOOR_H / 2, -16)), C.Brass, Enum.Material.Metal)
		part(club, "Column", Vector3.new(2, FLOOR_H, 2), CFrame.new(P(s * (HALF_X - 24), 1 + FLOOR_H / 2, 16)), C.Brass, Enum.Material.Metal)
	end
end

local function buildDanceFloor(club: Instance, folder: Instance)
	-- LED tiles; the server animates their colours.
	local tiles = Build.Folder("DanceTiles", folder)
	local size = 4
	for ix = -4, 3 do
		for iz = -4, 3 do
			local tile = part(tiles, "Tile", Vector3.new(size - 0.15, 0.1, size - 0.15), CFrame.new(P(ix * size + size / 2, 1.06, iz * size + size / 2 - 2)), C.Pink, Enum.Material.Neon, { CanCollide = false, CastShadow = false })
			tile.CanQuery = false
			tile:SetAttribute("Phase", (ix + iz) % 4)
		end
	end
	-- DJ booth on the north side of the floor.
	part(club, "DJRiser", Vector3.new(18, 3, 8), CFrame.new(P(0, 2.5, 18)), Color3.fromRGB(20, 20, 22), Enum.Material.Metal)
	part(club, "DJDesk", Vector3.new(12, 3.5, 2.5), CFrame.new(P(0, 5.75, 15.5)), Color3.fromRGB(12, 12, 14), Enum.Material.Metal)
	glow(club, "DJStrip", Vector3.new(12.2, 0.3, 2.7), CFrame.new(P(0, 4.2, 15.4)), C.Cyan, 18, 1.5)
	for _, x in { -7, 7 } do
		part(club, "Speaker", Vector3.new(3, 7, 3), CFrame.new(P(x, 7.5, 18)), Color3.fromRGB(14, 14, 16), Enum.Material.Fabric)
	end
	-- Moving-head lights over the floor.
	for i, x in { -12, -4, 4, 12 } do
		local head = glow(club, "Moving" .. i, Vector3.new(1.2, 1.2, 1.2), CFrame.new(P(x, FLOOR_H - 0.8, -2)), i % 2 == 0 and C.Pink or C.Cyan)
		local s = Instance.new("SpotLight")
		s.Name = "Beam"
		s.Face = Enum.NormalId.Bottom
		s.Range = 30
		s.Angle = 35
		s.Brightness = 4
		s.Color = head.Color
		s.Parent = head
		head:SetAttribute("Sweep", i)
	end
end

local function buildBar(club: Instance)
	-- Long bar along the south wall: solid counter is the A-point cover.
	part(club, "BarCounter", Vector3.new(44, 4, 3), CFrame.new(P(0, 3, -32)), C.Walnut, Enum.Material.Wood)
	part(club, "BarTop", Vector3.new(44.6, 0.3, 3.6), CFrame.new(P(0, 5.15, -32)), C.Marble, Enum.Material.Marble, { Reflectance = 0.15 })
	glow(club, "BarUnderglow", Vector3.new(44, 0.2, 0.2), CFrame.new(P(0, 1.3, -30.4)), C.Amber, nil)
	part(club, "BackBar", Vector3.new(46, 10, 2), CFrame.new(P(0, 6, -43.5)), C.Walnut, Enum.Material.Wood)
	for shelf = 0, 2 do
		part(club, "Shelf", Vector3.new(44, 0.3, 1.6), CFrame.new(P(0, 4 + shelf * 3, -42.2)), C.Brass, Enum.Material.Metal)
		glow(club, "ShelfLight", Vector3.new(44, 0.12, 0.12), CFrame.new(P(0, 4.2 + shelf * 3, -41.5)), C.Amber, nil)
		for i = 0, 20 do
			local bottle = part(club, "Bottle", Vector3.new(0.5, 1.6, 0.5), CFrame.new(P(-21 + i * 2.1 + rng:NextNumber(-0.3, 0.3), 5 + shelf * 3, -42.2)), Color3.fromHSV(rng:NextNumber(), 0.6, 0.7), Enum.Material.Glass, { Transparency = 0.25, Shape = Enum.PartType.Cylinder })
			bottle.CFrame = bottle.CFrame * CFrame.Angles(0, 0, math.rad(90))
			bottle.CanCollide = false
		end
	end
	for i = -5, 5 do
		part(club, "Stool", Vector3.new(1.4, 3, 1.4), CFrame.new(P(i * 4, 2.5, -28.5)), C.Brass, Enum.Material.Metal, { Shape = Enum.PartType.Cylinder })
	end
	-- Cocktail tables between the bar and the floor.
	for _, x in { -18, -6, 6, 18 } do
		part(club, "HighTable", Vector3.new(3, 4.5, 3), CFrame.new(P(x, 3.25, -21)), Color3.fromRGB(20, 20, 22), Enum.Material.Metal)
	end
end

local function buildMezzanine(club: Instance)
	-- VIP level over the north side, reached by stairs at each end.
	local deckY = 1 + FLOOR_H
	part(club, "VIPDeck", Vector3.new(HALF_X * 2 - 32, 1, 22), CFrame.new(P(0, deckY, HALF_Z - 11)), C.Walnut, Enum.Material.WoodPlanks)
	part(club, "VIPCarpet", Vector3.new(HALF_X * 2 - 34, 0.1, 20), CFrame.new(P(0, deckY + 0.55, HALF_Z - 11)), C.Velvet, Enum.Material.Fabric)
	-- Glass balustrade with brass rail, open at each end where the stairs arrive.
	local railWidth = (HALF_X - 23.5) * 2
	part(club, "Balustrade", Vector3.new(railWidth, 3.5, 0.3), CFrame.new(P(0, deckY + 2.25, HALF_Z - 22)), C.Glass, Enum.Material.Glass, { Transparency = 0.6 })
	part(club, "Handrail", Vector3.new(railWidth, 0.3, 0.6), CFrame.new(P(0, deckY + 4.1, HALF_Z - 22)), C.Brass, Enum.Material.Metal)
	for _, s in { -1, 1 } do
		-- Stairs climbing along the side walls.
		local steps = 14
		for i = 0, steps - 1 do
			local stepH = FLOOR_H / steps
			part(club, "Step", Vector3.new(5, stepH, 2), CFrame.new(P(s * (HALF_X - 19), 1 + stepH * (i + 0.5), -4 + i * 2)), Color3.fromRGB(30, 30, 34), Enum.Material.Metal)
		end
		part(club, "StairRail", Vector3.new(0.3, 3, 30), CFrame.new(P(s * (HALF_X - 21.6), 1 + FLOOR_H / 2 + 2, 9)) * CFrame.Angles(math.rad(-25), 0, 0), C.Brass, Enum.Material.Metal)
		-- Booths
		for _, x in { 10, 22 } do
			part(club, "Booth", Vector3.new(9, 3, 3), CFrame.new(P(s * x, deckY + 2, HALF_Z - 3)), C.Velvet, Enum.Material.Fabric)
			part(club, "BoothTable", Vector3.new(5, 2.5, 4), CFrame.new(P(s * x, deckY + 1.75, HALF_Z - 9)), C.Marble, Enum.Material.Marble)
			glow(club, "Candle", Vector3.new(0.3, 0.6, 0.3), CFrame.new(P(s * x, deckY + 3.3, HALF_Z - 9)), C.Amber, 8, 1)
		end
	end
	-- Chandelier
	local chandelier = glow(club, "Chandelier", Vector3.new(6, 1, 6), CFrame.new(P(0, FLOOR_H * 2 - 1, HALF_Z - 11)), Color3.fromRGB(255, 220, 170), 30, 1.4)
	chandelier.Shape = Enum.PartType.Ball
end

local function buildLighting(club: Instance)
	-- Low warm wall sconces and coloured ceiling washes.
	for _, z in { -HALF_Z + 1.2, HALF_Z - 1.2 } do
		for i = -2, 2 do
			glow(club, "Sconce", Vector3.new(1, 1.6, 0.4), CFrame.new(P(i * 18, 8, z)), C.Amber, 14, 0.9)
		end
	end
	for _, x in { -HALF_X + 1.2, HALF_X - 1.2 } do
		for _, z in { -30, 0, 30 } do
			glow(club, "Wash", Vector3.new(0.4, 0.4, 6), CFrame.new(P(x, FLOOR_H - 1, z)), C.Pink, 22, 1.2)
		end
	end
end

local function buildSpawns(arena: Instance)
	local spawns = Build.Folder("Spawns", arena)
	for key, x in { Blue = -118, Red = 118 } do
		local folder = Build.Folder(key, spawns)
		local face = x < 0 and 270 or 90
		for i = 0, 5 do
			local pad = part(folder, "Spawn", Vector3.new(4, 0.2, 4), CFrame.new(P(x + (i % 2) * 6 * (x < 0 and 1 or -1), 0.12, -15 + math.floor(i / 2) * 15)) * CFrame.Angles(0, math.rad(face), 0), Config.Teams[key].Color, Enum.Material.Neon, { Transparency = 0.55, CanCollide = false, CastShadow = false })
			pad.CanQuery = false
		end
	end
end

-- Objective markers are created by MapBuilder's shared builder; this returns
-- where they go plus per-point capture shapes (C is upstairs).
ClubBuilder.Objectives = {
	A = { Position = P(0, 1, -24), Radius = 11, Height = 6 },
	B = { Position = P(0, 1.1, -2), Radius = 11, Height = 6 },
	C = { Position = P(0, FLOOR_H + 1.5, HALF_Z - 12), Radius = 11, Height = 6 },
}

function ClubBuilder.Build(arena: Instance)
	buildGround(arena)
	buildStreet(arena)
	local club = Build.Model("Club", arena)
	buildShell(club)
	buildDanceFloor(club, arena)
	buildBar(club)
	buildMezzanine(club)
	buildLighting(club)
	buildSpawns(arena)
	arena:SetAttribute("RainBounds", Vector3.new(O.X, 140, 80))
end

-- Called by the server while the club is the active map: pulse the dance
-- floor and sweep the moving heads.
function ClubBuilder.Animate(arena: Instance, t: number)
	local tiles = arena:FindFirstChild("DanceTiles")
	if tiles then
		local beat = math.floor(t * 2)
		local palette = { C.Pink, C.Cyan, Color3.fromRGB(140, 60, 255), C.Amber }
		for _, tile in tiles:GetChildren() do
			local phase = tile:GetAttribute("Phase") or 0
			(tile :: BasePart).Color = palette[(beat + phase) % #palette + 1]
		end
	end
	local club = arena:FindFirstChild("Club")
	if club then
		for _, head in club:GetChildren() do
			local sweep = head:GetAttribute("Sweep")
			if sweep then
				local p = head.Position
				head.CFrame = CFrame.new(p) * CFrame.Angles(math.sin(t * 0.9 + sweep) * 0.6, 0, math.cos(t * 0.7 + sweep) * 0.6)
			end
		end
	end
end

return ClubBuilder
