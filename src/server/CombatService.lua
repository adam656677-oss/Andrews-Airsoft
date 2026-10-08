--[[
	Server authority for shooting.

	Clients simulate their own BBs for instant feedback and report hits. The
	server keeps a record of every shot it accepted (rate, ammo, origin) and
	validates each hit claim against it before anyone is tagged.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local Shared = ReplicatedStorage.Shared
local Config = require(Shared.Config)
local Weapons = require(Shared.Weapons)
local Ballistics = require(Shared.Ballistics)
local Remotes = require(Shared.Remotes)

local PlayerService = require(script.Parent.PlayerService)

local CombatService = {}

local hooks = {
	OnTag = function(_shooter: Player?, _victim: Player, _weaponId: string) end,
	IsLive = function(): boolean
		return false
	end,
}

local MAX_ORIGIN_OFFSET = 9 -- studs between the head and the reported muzzle
local HIT_TOLERANCE = 9 -- studs between the reported hit and the victim
local ANGLE_TOLERANCE = math.rad(16) -- BB arc + latency allowance
local SHOT_HISTORY = 4 -- seconds a shot record is kept

local function playerFromPart(part: Instance?): Player?
	if typeof(part) ~= "Instance" then
		return nil
	end
	local model = (part :: Instance):FindFirstAncestorOfClass("Model")
	while model do
		local p = Players:GetPlayerFromCharacter(model)
		if p then
			return p
		end
		model = model:FindFirstAncestorOfClass("Model")
	end
	return nil
end

local function isValidVector(v: any): boolean
	return typeof(v) == "Vector3" and v == v and v.Magnitude < 1e5
end

local function headPosition(player: Player): Vector3?
	local character = player.Character
	local head = character and character:FindFirstChild("Head") :: BasePart?
	return head and head.Position
end

local function equippedTool(player: Player, weaponId: string): Tool?
	local character = player.Character
	if not character then
		return nil
	end
	local tool = character:FindFirstChildOfClass("Tool")
	if tool and tool:GetAttribute("WeaponId") == weaponId then
		return tool
	end
	return nil
end

local function sameTeam(a: Player, b: Player): boolean
	local sa, sb = PlayerService.Get(a), PlayerService.Get(b)
	return sa ~= nil and sb ~= nil and sa.Side ~= nil and sa.Side == sb.Side
end

local function worldParams(exclude: { Instance }): RaycastParams
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	local list = table.clone(exclude)
	for _, p in Players:GetPlayers() do
		if p.Character then
			table.insert(list, p.Character)
		end
	end
	local effects = workspace:FindFirstChild("Effects")
	if effects then
		table.insert(list, effects)
	end
	params.FilterDescendantsInstances = list
	params.IgnoreWater = true
	return params
end

function CombatService.Tag(shooter: Player?, victim: Player, weaponId: string)
	if not hooks.IsLive() or not PlayerService.CanBeTagged(victim) then
		return false
	end
	if shooter and (shooter == victim or (not Config.FriendlyFire and sameTeam(shooter, victim))) then
		return false
	end
	local shooterPos = shooter and headPosition(shooter) or nil
	PlayerService.MarkOut(victim)
	if shooter then
		local s = PlayerService.Get(shooter)
		if s then
			s.Round.Tags += 1
			s.Round.Streak += 1
		end
		Remotes.HitConfirm:FireClient(shooter, victim)
	end
	Remotes.Tagged:FireAllClients(victim, shooter, weaponId, shooterPos)
	hooks.OnTag(shooter, victim, weaponId)
	return true
end

local function onFire(player: Player, weaponId: any, shotId: any, origin: any, directions: any)
	local state = PlayerService.Get(player)
	if not state or not state.Alive or state.Out then
		return
	end
	if type(weaponId) ~= "string" or type(shotId) ~= "number" or not isValidVector(origin) or type(directions) ~= "table" then
		return
	end
	local weapon = state.Weapons[weaponId]
	if not weapon or not equippedTool(player, weaponId) then
		return
	end
	if #directions ~= weapon.Pellets then
		return
	end
	for _, d in directions do
		if not isValidVector(d) or d.Magnitude < 0.5 then
			return
		end
	end

	local head = headPosition(player)
	if not head or (head - origin).Magnitude > MAX_ORIGIN_OFFSET then
		return
	end

	local now = os.clock()
	local last = state.LastFire[weaponId] or 0
	if now - last < weapon.FireInterval * 0.7 then
		return
	end

	local ammo = state.Ammo[weaponId]
	if not ammo or ammo.Mag <= 0 or state.Reloading[weaponId] then
		if ammo then
			Remotes.AmmoSync:FireClient(player, weaponId, ammo.Mag, ammo.Reserve)
		end
		return
	end

	ammo.Mag -= 1
	state.LastFire[weaponId] = now
	PlayerService.DropProtection(player)

	-- Expire old shot records.
	for id, shot in state.Shots do
		if now - shot.Time > SHOT_HISTORY then
			state.Shots[id] = nil
		end
	end
	local unitDirs = {}
	for i, d in directions do
		unitDirs[i] = d.Unit
	end
	state.Shots[shotId] = {
		Weapon = weapon,
		Origin = origin,
		Directions = unitDirs,
		Time = now,
		Used = {},
	}

	Remotes.ShotFired:FireAllClients(player, weaponId, origin, unitDirs)
end

local function onHit(player: Player, shotId: any, pellet: any, hitPart: any, hitPos: any)
	local state = PlayerService.Get(player)
	if not state or type(shotId) ~= "number" or type(pellet) ~= "number" or not isValidVector(hitPos) then
		return
	end
	local shot = state.Shots[shotId]
	if not shot or shot.Used[pellet] or not shot.Directions[pellet] then
		return
	end
	local weapon = shot.Weapon
	local elapsed = os.clock() - shot.Time
	if elapsed > Ballistics.MaxFlightTime(weapon.Velocity, weapon.Range) + 0.6 then
		return
	end

	local victim = playerFromPart(hitPart)
	if not victim or victim == player then
		return
	end
	local character = victim.Character
	local root = character and character:FindFirstChild("HumanoidRootPart") :: BasePart?
	if not root then
		return
	end

	local toHit = hitPos - shot.Origin
	local distance = toHit.Magnitude
	if distance > weapon.Range + 5 then
		return
	end
	if (root.Position - hitPos).Magnitude > HIT_TOLERANCE then
		return
	end
	if distance > 4 then
		local angle = math.acos(math.clamp(toHit.Unit:Dot(shot.Directions[pellet]), -1, 1))
		if angle > ANGLE_TOLERANCE + math.rad(weapon.Spread.Hip) then
			return
		end
	end

	-- Line of sight: nothing solid between the muzzle and the hit point.
	-- BBs arc, so only the first 85% of the straight line is checked.
	local params = worldParams({})
	local block = workspace:Raycast(shot.Origin, toHit * 0.85, params)
	if block and block.Instance.CanCollide and block.Instance.Transparency < 0.9 then
		return
	end

	shot.Used[pellet] = true
	CombatService.Tag(player, victim, weapon.Id)
end

local function onReload(player: Player, weaponId: any)
	local state = PlayerService.Get(player)
	if not state or not state.Alive or type(weaponId) ~= "string" then
		return
	end
	local weapon = state.Weapons[weaponId]
	local ammo = state.Ammo[weaponId]
	if not weapon or not ammo or state.Reloading[weaponId] then
		return
	end
	if ammo.Mag >= weapon.MagSize or ammo.Reserve <= 0 then
		Remotes.AmmoSync:FireClient(player, weaponId, ammo.Mag, ammo.Reserve)
		return
	end
	state.Reloading[weaponId] = true
	local life = state.Life
	local duration = ammo.Mag == 0 and weapon.EmptyReloadTime or weapon.ReloadTime
	task.delay(duration * 0.9, function()
		if state.Life ~= life then
			return
		end
		state.Reloading[weaponId] = nil
		local needed = weapon.MagSize - ammo.Mag
		local take = math.min(needed, ammo.Reserve)
		ammo.Mag += take
		ammo.Reserve -= take
		Remotes.AmmoSync:FireClient(player, weaponId, ammo.Mag, ammo.Reserve)
	end)
end

local function burst(thrower: Player, position: Vector3)
	local cfg = Weapons.Grenade
	Remotes.GrenadeBurst:FireAllClients(position, cfg.Radius)
	local params = worldParams({})
	for _, victim in Players:GetPlayers() do
		local root = victim.Character and victim.Character:FindFirstChild("HumanoidRootPart") :: BasePart?
		if root and victim ~= thrower then
			local offset = root.Position - position
			if offset.Magnitude <= cfg.Radius then
				local blocked = workspace:Raycast(position + Vector3.new(0, 0.5, 0), offset, params)
				if not blocked then
					CombatService.Tag(thrower, victim, "Grenade")
				end
			end
		end
	end
end

local function onThrow(player: Player, origin: any, direction: any)
	local state = PlayerService.Get(player)
	if not state or not state.Alive or state.Out or state.Grenades <= 0 then
		return
	end
	if not isValidVector(origin) or not isValidVector(direction) or direction.Magnitude < 0.5 then
		return
	end
	local head = headPosition(player)
	if not head or (head - origin).Magnitude > MAX_ORIGIN_OFFSET then
		return
	end
	if not equippedTool(player, "Grenade") then
		return
	end
	state.Grenades -= 1
	player:SetAttribute("Grenades", state.Grenades)
	PlayerService.DropProtection(player)

	local cfg = Weapons.Grenade
	local tool = player.Character and player.Character:FindFirstChildOfClass("Tool")
	if tool and state.Grenades <= 0 then
		tool:Destroy()
	end

	local nade = Instance.new("Part")
	nade.Name = "Grenade"
	nade.Shape = Enum.PartType.Cylinder
	nade.Size = Vector3.new(0.6, 0.4, 0.4)
	nade.Color = Color3.fromRGB(70, 78, 56)
	nade.Material = Enum.Material.Metal
	nade.CanQuery = false
	nade.CFrame = CFrame.new(origin + direction.Unit * 2)
	nade.AssemblyLinearVelocity = direction.Unit * cfg.ThrowSpeed + Vector3.new(0, 18, 0)
	nade.AssemblyAngularVelocity = Vector3.new(math.random() * 20, math.random() * 20, 0)
	local band = Instance.new("SelectionBox")
	band.Adornee = nade
	band.Color3 = PlayerService.TeamColor(state.Side)
	band.LineThickness = 0.02
	band.Parent = nade
	nade.Parent = workspace:FindFirstChild("Effects") or workspace
	nade:SetNetworkOwner(nil)

	task.delay(cfg.FuseTime, function()
		local pos = nade.Position
		nade:Destroy()
		if player.Parent then
			burst(player, pos)
		end
	end)
end

function CombatService.Init(opts)
	for k, v in opts do
		hooks[k] = v
	end
	Remotes.Fire.OnServerEvent:Connect(onFire)
	Remotes.Hit.OnServerEvent:Connect(onHit)
	Remotes.Reload.OnServerEvent:Connect(onReload)
	Remotes.ThrowGrenade.OnServerEvent:Connect(onThrow)
	Remotes.ToggleLight.OnServerEvent:Connect(function(player: Player, on: any)
		local tool = player.Character and player.Character:FindFirstChildOfClass("Tool")
		local lens = tool and tool:FindFirstChild("LightLens")
		local beam = lens and lens:FindFirstChild("Beam") :: SpotLight?
		if beam then
			beam.Enabled = on == true
		end
	end)
end

return CombatService
