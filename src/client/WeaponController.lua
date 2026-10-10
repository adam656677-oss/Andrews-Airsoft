--[[
	Everything the local player does with a gun: equipping, firing, aiming,
	reloading, fire modes, grenades, weapon light, sprint, crouch, lean,
	camera recoil and FOV. Works with mouse/keyboard, gamepad and touch.
]]

local CollectionService = game:GetService("CollectionService")
local ContextActionService = game:GetService("ContextActionService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")

local Shared = ReplicatedStorage:WaitForChild("Shared")
local Config = require(Shared.Config)
local Weapons = require(Shared.Weapons)
local Ballistics = require(Shared.Ballistics)
local Remotes = require(Shared.Remotes)

local State = require(script.Parent.State)
local Effects = require(script.Parent.Effects)
local Viewmodel = require(script.Parent.Viewmodel)

local player = Players.LocalPlayer
local camera = workspace.CurrentCamera
local gameState = ReplicatedStorage:WaitForChild("GameState")
local effectsFolder = workspace:WaitForChild("Effects")

local WeaponController = {}

local viewmodel: any = nil
local equippedTool: Tool? = nil
local triggerHeld = false
local fireQueued = false
local lastShot = 0
local burstLeft = 0
local sliding = false
local slideDir = Vector3.zero
local slideStart = 0
local lastSlide = 0
local laserPart: BasePart? = nil
local laserDot: BasePart? = nil
local nextShotId = 0
local bloom = 0
local aimHeld = false
local sprintHeld = false
local leanTarget = 0
local lean = 0
local lightOn = false
local mouseDelta = Vector2.zero
local recoilOffset = Vector2.zero -- currently applied camera recoil (pitch, yaw) in radians
local recoilTarget = Vector2.zero
local defaultHipHeight: number? = nil
local reloadToken = 0
local throwing = false

local rng = Random.new()
local updateLaser: (boolean) -> ()

---------------------------------------------------------------------------
-- Helpers
---------------------------------------------------------------------------

local function character(): Model?
	return player.Character
end

local function humanoid(): Humanoid?
	local c = character()
	return c and c:FindFirstChildOfClass("Humanoid")
end

local function isOut(): boolean
	return player:GetAttribute("Out") == true
end

-- Stats with the equipped tool's attachments applied.
local resolved: { [string]: any } = {}

local function currentWeapon()
	if not State.Weapon then
		return nil
	end
	return resolved[State.Weapon] or Weapons.Get(State.Weapon)
end

local function firePitch(w): number
	local base = Config.UsingUploadedSounds and 1 or (Config.FallbackPitch[w.Sound] or 1)
	return base * rng:NextNumber(0.96, 1.05)
end

local function myColor(): Color3
	local side = player:GetAttribute("Side")
	if side and Config.Teams[side] then
		return Config.Teams[side].Color
	end
	return Color3.fromRGB(255, 196, 64)
end

local function canAct(): boolean
	local h = humanoid()
	return h ~= nil and h.Health > 0 and not isOut() and not State.MenuOpen
end

local function fireModeName(): string
	local w = currentWeapon()
	if not w then
		return ""
	end
	local index = State.FireMode[w.Id] or 1
	return w.FireModes[index] or w.FireModes[1]
end

local function rayParams(): RaycastParams
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	local list: { Instance } = { camera, effectsFolder }
	local c = character()
	if c then
		table.insert(list, c)
	end
	-- Players who are already out can't be hit; let BBs pass through them.
	for _, p in Players:GetPlayers() do
		if p:GetAttribute("Out") and p.Character then
			table.insert(list, p.Character)
		end
	end
	params.FilterDescendantsInstances = list
	params.IgnoreWater = true
	return params
end

local function playerFromPart(part: Instance): Player?
	local model = part:FindFirstAncestorOfClass("Model")
	while model do
		local p = Players:GetPlayerFromCharacter(model)
		if p then
			return p
		end
		model = model:FindFirstAncestorOfClass("Model")
	end
	return nil
end

local function isEnemy(other: Player): boolean
	if other == player then
		return false
	end
	local mine, theirs = player:GetAttribute("Side"), other:GetAttribute("Side")
	if not mine or mine == "" or not theirs or theirs == "" then
		return false
	end
	return Config.FriendlyFire or mine ~= theirs
end

local function hideTool(tool: Tool)
	for _, d in tool:GetDescendants() do
		if d:IsA("BasePart") then
			d.LocalTransparencyModifier = 1
			d.Transparency = 1
		end
	end
end

---------------------------------------------------------------------------
-- Shooting
---------------------------------------------------------------------------

-- Animates a BB along the simulated path, starting at `visualStart` and
-- converging onto the real flight line within the first few studs.
local function visualBB(color: Color3, origin: Vector3, visualStart: Vector3?)
	local onStep, onEnd = Effects.BB(color)
	local offset = visualStart and (visualStart - origin) or Vector3.zero
	local travelled = 0
	local function step(from: Vector3, to: Vector3)
		local segment = (to - from).Magnitude
		local k0 = math.max(0, 1 - travelled / 25)
		travelled += segment
		local k1 = math.max(0, 1 - travelled / 25)
		onStep(from + offset * k0, to + offset * k1)
	end
	return step, onEnd
end

local function currentSpread(w): number
	local h = humanoid()
	local aim = State.AimAlpha
	local spread = w.Spread.Hip + (w.Spread.Aim - w.Spread.Hip) * aim
	if h then
		local speed = (h.RootPart and h.RootPart.AssemblyLinearVelocity * Vector3.new(1, 0, 1) or Vector3.zero).Magnitude
		spread += math.min(speed / 14, 1.4) * 1.3 * (1 - aim * 0.6)
		if h.FloorMaterial == Enum.Material.Air then
			spread += 3
		end
	end
	if State.Crouching then
		spread *= 0.75
	end
	spread += bloom * (1 - aim * 0.5)
	return spread
end

local function onBBHit(shotId: number, pellet: number, result: RaycastResult)
	local part = result.Instance
	local victim = playerFromPart(part)
	if victim then
		if isEnemy(victim) then
			Remotes.Hit:FireServer(shotId, pellet, part, result.Position)
		end
		return
	end
	if CollectionService:HasTag(part, "PracticeTarget") then
		Effects.TargetDing(part :: BasePart)
		State.Emit("HitMarker", false)
		return
	end
	Effects.Impact(result.Position, result.Normal, result.Material)
end

local function fire()
	local w = currentWeapon()
	if not w or not viewmodel then
		return
	end
	local ammo = State.Ammo[w.Id]
	if not ammo then
		return
	end
	if ammo.Mag <= 0 then
		Effects.Play2D("DryFire", 0.5, 1.2)
		triggerHeld = false
		if ammo.Reserve > 0 then
			WeaponController.Reload()
		end
		return
	end

	local now = os.clock()
	lastShot = now
	ammo.Mag -= 1
	nextShotId += 1
	local shotId = nextShotId

	local origin = camera.CFrame.Position
	local look = camera.CFrame.LookVector
	local spread = currentSpread(w)
	local dirs = {}
	for i = 1, w.Pellets do
		dirs[i] = Ballistics.Spread(look, spread, rng)
	end
	Remotes.Fire:FireServer(w.Id, shotId, origin, dirs)

	local params = rayParams()
	local color = myColor()
	local muzzle = viewmodel:MuzzlePosition()
	for i, dir in dirs do
		local step, finish = visualBB(color, origin, muzzle)
		Ballistics.Fire({
			Origin = origin,
			Direction = dir,
			Speed = w.Velocity,
			Gravity = w.Gravity,
			Range = w.Range,
			Params = params,
			OnStep = step,
			OnEnd = finish,
			OnHit = function(result)
				onBBHit(shotId, i, result)
			end,
		})
	end

	Effects.Play2D(w.Sound, w.Quiet and 0.35 or 0.55, firePitch(w))
	viewmodel:Recoil(w.Recoil[1] * 0.35)
	viewmodel:CancelInspect()
	if w.FireModes[1] == "Bolt" or w.FireModes[1] == "Pump" then
		viewmodel:Play("Cycle", w.FireInterval * 0.85)
	end
	if w.Class == "Pistol" and ammo.Mag <= 0 then
		viewmodel:SetSlideLocked(true)
	end
	local recoilScale = (1 - State.AimAlpha * 0.35) * (State.Crouching and 0.8 or 1)
	recoilTarget += Vector2.new(math.rad(w.Recoil[1]) * recoilScale, math.rad(rng:NextNumber(-w.Recoil[2], w.Recoil[2])) * recoilScale)
	bloom = math.min(bloom + w.Spread.Hip * 0.12, 2.5)

	State.Emit("Ammo")
	State.Emit("Fired")

	if ammo.Mag <= 0 and ammo.Reserve > 0 then
		task.delay(0.25, function()
			if State.Weapon == w.Id and ammo.Mag <= 0 then
				WeaponController.Reload()
			end
		end)
	end
end

local function tryFire()
	local w = currentWeapon()
	if not w or not canAct() or State.Reloading or throwing then
		return
	end
	local phase = gameState:GetAttribute("State")
	if phase == "Briefing" or phase == "PostRound" then
		return
	end
	if State.Sprinting then
		return
	end
	if os.clock() - lastShot < w.FireInterval then
		return
	end
	local mode = fireModeName()
	if mode == "Burst" then
		if burstLeft <= 0 then
			if not fireQueued then
				return
			end
			fireQueued = false
			burstLeft = 3
		end
		burstLeft -= 1
	elseif mode ~= "Auto" then
		if not fireQueued then
			return
		end
		fireQueued = false
	end
	if viewmodel and viewmodel:Busy("Cycle") then
		return
	end
	fire()
end

function WeaponController.Reload()
	local w = currentWeapon()
	if not w or State.Reloading or not canAct() then
		return
	end
	local ammo = State.Ammo[w.Id]
	if not ammo or ammo.Mag >= w.MagSize or ammo.Reserve <= 0 then
		return
	end
	State.Reloading = true
	burstLeft = 0
	State.Emit("Reload", true)
	reloadToken += 1
	local token = reloadToken
	local weaponId = w.Id
	local duration = ammo.Mag == 0 and w.EmptyReloadTime or w.ReloadTime
	Remotes.Reload:FireServer(weaponId)
	if viewmodel then
		viewmodel:Play("Reload", duration, { Empty = ammo.Mag == 0 })
	end
	task.delay(duration, function()
		if token ~= reloadToken then
			return
		end
		State.Reloading = false
		-- Predict the result; the server's AmmoSync will correct it if needed.
		local a = State.Ammo[weaponId]
		if a then
			local take = math.min(w.MagSize - a.Mag, a.Reserve)
			a.Mag += take
			a.Reserve -= take
			if a.Mag > 0 and viewmodel and State.Weapon == weaponId then
				viewmodel:SetSlideLocked(false)
			end
		end
		State.Emit("Reload", false)
		State.Emit("Ammo")
	end)
end

local function cancelReload()
	if State.Reloading then
		reloadToken += 1
		State.Reloading = false
		if viewmodel and viewmodel:Busy("Reload") then
			viewmodel.Anim = nil
		end
		State.Emit("Reload", false)
	end
end

local function cycleFireMode()
	local w = currentWeapon()
	if not w or #w.FireModes < 2 then
		return
	end
	burstLeft = 0
	local index = (State.FireMode[w.Id] or 1) % #w.FireModes + 1
	State.FireMode[w.Id] = index
	Effects.Play2D("UIClick", 0.4, 1.3)
	State.Emit("FireMode", w.FireModes[index])
end

---------------------------------------------------------------------------
-- Equipping
---------------------------------------------------------------------------

local function findTool(slot: string): Tool?
	local backpack = player:FindFirstChild("Backpack")
	local c = character()
	for _, container in { c, backpack } do
		if container then
			for _, t in container:GetChildren() do
				if t:IsA("Tool") and t:GetAttribute("Slot") == slot then
					return t
				end
			end
		end
	end
	return nil
end

function WeaponController.EquipSlot(slot: string)
	if not canAct() or throwing then
		return
	end
	local tool = findTool(slot)
	local h = humanoid()
	if tool and h and tool.Parent ~= character() then
		cancelReload()
		h:EquipTool(tool)
	end
end

local SLOT_ORDER = { "Primary", "Secondary" }
local function cycleWeapon(direction: number)
	local current = equippedTool and equippedTool:GetAttribute("Slot") or "Primary"
	local index = table.find(SLOT_ORDER, current) or 1
	index = (index - 1 + direction) % #SLOT_ORDER + 1
	WeaponController.EquipSlot(SLOT_ORDER[index])
end

local function onToolEquipped(tool: Tool)
	equippedTool = tool
	burstLeft = 0
	local id = tool:GetAttribute("WeaponId")
	State.Weapon = id
	State.Reloading = false
	hideTool(tool)
	if viewmodel then
		viewmodel:Destroy()
	end
	local loadout = Weapons.ParseLoadout(tool:GetAttribute("Loadout"))
	-- The finish the server actually built the tool with, not unsaved menu edits.
	loadout.Skin = tool:GetAttribute("Skin") or "Black"
	if Weapons.Get(id) then
		resolved[id] = Weapons.Resolve(id, loadout)
	end
	viewmodel = Viewmodel.new(id, { Accent = myColor(), Loadout = loadout })
	viewmodel:SetLight(lightOn)
	local ammo = State.Ammo[id]
	if ammo and ammo.Mag <= 0 and resolved[id] and resolved[id].Class == "Pistol" then
		viewmodel:SetSlideLocked(true)
	end
	Effects.Play2D("UIClick", 0.35, 0.8)
	State.Emit("Equipped", id)
end

local function onToolUnequipped(tool: Tool)
	if equippedTool ~= tool then
		return
	end
	equippedTool = nil
	State.Weapon = nil
	burstLeft = 0
	cancelReload()
	if viewmodel then
		viewmodel:Destroy()
		viewmodel = nil
	end
	State.Emit("Equipped", nil)
end

function WeaponController.ThrowGrenade()
	if not canAct() or throwing or (player:GetAttribute("Grenades") or 0) <= 0 then
		return
	end
	local grenade = findTool("Grenade")
	local h = humanoid()
	if not grenade or not h then
		return
	end
	local phase = gameState:GetAttribute("State")
	if phase == "Briefing" or phase == "PostRound" then
		return
	end
	throwing = true
	local previous = equippedTool and equippedTool:GetAttribute("Slot") or "Primary"
	cancelReload()
	h:EquipTool(grenade)
	task.wait(0.35)
	if canAct() then
		local look = camera.CFrame.LookVector
		Remotes.ThrowGrenade:FireServer(camera.CFrame.Position, (look + Vector3.new(0, 0.15, 0)).Unit)
		Effects.Play2D("UIClick", 0.5, 0.6)
	end
	task.wait(0.3)
	throwing = false
	WeaponController.EquipSlot(previous)
end

---------------------------------------------------------------------------
-- Input bindings (keyboard/mouse, gamepad, touch)
---------------------------------------------------------------------------

local function bind(name: string, handler, touch: boolean, ...)
	ContextActionService:BindAction(name, handler, touch, ...)
end

local function onFireAction(_, inputState)
	if inputState == Enum.UserInputState.Begin then
		if State.MenuOpen then
			return Enum.ContextActionResult.Pass
		end
		triggerHeld = true
		fireQueued = true
		tryFire()
	elseif inputState == Enum.UserInputState.End or inputState == Enum.UserInputState.Cancel then
		triggerHeld = false
	end
	return Enum.ContextActionResult.Sink
end

local function onAimAction(_, inputState)
	if State.MenuOpen then
		return Enum.ContextActionResult.Pass
	end
	local touchOnly = UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled
	if State.Settings.ToggleAim or touchOnly then
		if inputState == Enum.UserInputState.Begin then
			aimHeld = not aimHeld
		end
	else
		aimHeld = inputState == Enum.UserInputState.Begin or inputState == Enum.UserInputState.Change
	end
	return Enum.ContextActionResult.Sink
end

local function onSimple(fn)
	return function(_, inputState)
		if inputState == Enum.UserInputState.Begin and not State.MenuOpen then
			task.spawn(fn)
		end
		return Enum.ContextActionResult.Sink
	end
end

local SLIDE_TIME = 0.75
local SLIDE_COOLDOWN = 1.2

-- Crouching out of a sprint turns into a slide.
local function toggleCrouch()
	local h = humanoid()
	local root = h and h.RootPart
	if State.Sprinting and h and root and h.FloorMaterial ~= Enum.Material.Air and os.clock() - lastSlide > SLIDE_COOLDOWN then
		sliding = true
		slideStart = os.clock()
		lastSlide = slideStart
		local flat = camera.CFrame.LookVector * Vector3.new(1, 0, 1)
		slideDir = flat.Magnitude > 0.01 and flat.Unit or root.CFrame.LookVector
		State.Crouching = true
		Effects.Play2D("UIClick", 0.3, 0.5)
		State.Emit("Crouch", true)
		return
	end
	State.Crouching = not State.Crouching
	State.Emit("Crouch", State.Crouching)
end

local function inspect()
	if viewmodel and not State.Reloading and State.AimAlpha < 0.1 and not viewmodel:Busy() then
		viewmodel:Play("Inspect", 2.6)
	end
end

local function toggleLight()
	lightOn = not lightOn
	if viewmodel then
		viewmodel:SetLight(lightOn)
	end
	Remotes.ToggleLight:FireServer(lightOn)
	Effects.Play2D("UIClick", 0.4, 1.6)
end

local function setupInput()
	bind("AirsoftFire", onFireAction, true, Enum.UserInputType.MouseButton1, Enum.KeyCode.ButtonR2)
	bind("AirsoftAim", onAimAction, true, Enum.UserInputType.MouseButton2, Enum.KeyCode.ButtonL2)
	bind("AirsoftReload", onSimple(WeaponController.Reload), true, Enum.KeyCode.R, Enum.KeyCode.ButtonX)
	bind("AirsoftSwitch", onSimple(function()
		cycleWeapon(1)
	end), true, Enum.KeyCode.ButtonY)
	bind("AirsoftPrimary", onSimple(function()
		WeaponController.EquipSlot("Primary")
	end), false, Enum.KeyCode.One)
	bind("AirsoftSecondary", onSimple(function()
		WeaponController.EquipSlot("Secondary")
	end), false, Enum.KeyCode.Two)
	bind("AirsoftGrenade", onSimple(WeaponController.ThrowGrenade), true, Enum.KeyCode.G, Enum.KeyCode.ButtonR1)
	bind("AirsoftFireMode", onSimple(cycleFireMode), false, Enum.KeyCode.B, Enum.KeyCode.DPadUp)
	bind("AirsoftCrouch", onSimple(toggleCrouch), true, Enum.KeyCode.C, Enum.KeyCode.LeftControl, Enum.KeyCode.ButtonB)
	bind("AirsoftLight", onSimple(toggleLight), false, Enum.KeyCode.F, Enum.KeyCode.DPadRight)
	bind("AirsoftInspect", onSimple(inspect), false, Enum.KeyCode.I)
	bind("AirsoftSprint", function(_, inputState)
		if inputState == Enum.UserInputState.Begin then
			sprintHeld = not UserInputService.GamepadEnabled and true or not sprintHeld
		elseif inputState == Enum.UserInputState.End and not UserInputService.GamepadEnabled then
			sprintHeld = false
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.KeyCode.LeftShift, Enum.KeyCode.ButtonL3)
	bind("AirsoftLean", function(_, inputState, input)
		if State.MenuOpen then
			return Enum.ContextActionResult.Pass
		end
		local dir = input.KeyCode == Enum.KeyCode.Q and -1 or 1
		if inputState == Enum.UserInputState.Begin then
			leanTarget = dir
		elseif inputState == Enum.UserInputState.End and leanTarget == dir then
			leanTarget = 0
		end
		return Enum.ContextActionResult.Sink
	end, false, Enum.KeyCode.Q, Enum.KeyCode.E)

	-- Lay out touch buttons around the right thumb.
	local function touchButton(name: string, title: string, pos: UDim2, size: number?)
		local button = ContextActionService:GetButton(name)
		if button then
			ContextActionService:SetTitle(name, title)
			ContextActionService:SetPosition(name, pos)
			button.Size = UDim2.fromOffset(size or 56, size or 56)
		end
	end
	touchButton("AirsoftFire", "FIRE", UDim2.new(1, -170, 1, -190), 80)
	touchButton("AirsoftAim", "AIM", UDim2.new(1, -250, 1, -150))
	touchButton("AirsoftReload", "R", UDim2.new(1, -95, 1, -250))
	touchButton("AirsoftSwitch", "SWAP", UDim2.new(1, -175, 1, -270))
	touchButton("AirsoftCrouch", "C", UDim2.new(1, -90, 1, -170))
	touchButton("AirsoftGrenade", "G", UDim2.new(1, -250, 1, -230))

	UserInputService.InputChanged:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseMovement then
			mouseDelta += Vector2.new(input.Delta.X, input.Delta.Y)
		elseif input.KeyCode == Enum.KeyCode.Thumbstick2 then
			mouseDelta += Vector2.new(input.Position.X, -input.Position.Y) * 6
		end
	end)
	UserInputService.InputChanged:Connect(function(input, processed)
		if not processed and not State.MenuOpen and input.UserInputType == Enum.UserInputType.MouseWheel then
			cycleWeapon(input.Position.Z > 0 and -1 or 1)
		end
	end)
end

---------------------------------------------------------------------------
-- Per-frame update
---------------------------------------------------------------------------

local function updateMovement(dt: number)
	local h = humanoid()
	if not h or isOut() or h.Health <= 0 then
		State.Sprinting = false
		return
	end
	local w = currentWeapon()
	local moving = h.MoveDirection.Magnitude > 0.1
	-- Sprint only when moving roughly forward.
	local forward = moving and h.MoveDirection:Dot(camera.CFrame.LookVector * Vector3.new(1, 0, 1)) > 0.5
	State.Sprinting = sprintHeld and forward and not State.Crouching and not aimHeld and not State.Reloading and not sliding
	if not moving and UserInputService.GamepadEnabled then
		sprintHeld = false
	end
	if State.Sprinting then
		triggerHeld = false
	end

	local speed = Config.WalkSpeed
	if State.Sprinting then
		speed = Config.SprintSpeed
	elseif State.Crouching then
		speed = Config.CrouchSpeed
	elseif State.AimAlpha > 0.5 then
		speed = Config.AimSpeed
	end
	speed *= (w and w.SpeedMultiplier) or 1
	h.WalkSpeed = speed

	-- Slide: carry sprint momentum low to the ground, then settle into a crouch.
	if sliding then
		local t = (os.clock() - slideStart) / SLIDE_TIME
		local root = h.RootPart
		if t >= 1 or not root or h.FloorMaterial == Enum.Material.Air and t > 0.3 then
			sliding = false
		else
			local slideSpeed = Config.SprintSpeed * 1.55 * (1 - t * 0.75)
			local v = root.AssemblyLinearVelocity
			root.AssemblyLinearVelocity = Vector3.new(slideDir.X * slideSpeed, v.Y, slideDir.Z * slideSpeed)
		end
	end

	-- Crouch lowers the hip height on R15 rigs; camera follows on both rigs.
	if h.RigType == Enum.HumanoidRigType.R15 then
		defaultHipHeight = defaultHipHeight or h.HipHeight
		local target = State.Crouching and (defaultHipHeight :: number) * 0.45 or defaultHipHeight :: number
		h.HipHeight += (target - h.HipHeight) * math.min(dt * 12, 1)
	end
	lean += (leanTarget - lean) * math.min(dt * 10, 1)
	local crouchOffset = (State.Crouching and h.RigType ~= Enum.HumanoidRigType.R15) and -1.6 or 0
	h.CameraOffset = Vector3.new(lean * 1.4, crouchOffset, 0)
end

-- Draws the laser beam and dot locally when a laser module is fitted and on.
updateLaser = function(alive: boolean)
	local w = currentWeapon()
	local emitter = viewmodel and viewmodel:LaserPosition()
	local on = alive and lightOn and emitter ~= nil and w ~= nil and w.Loadout and w.Loadout.Laser == "Laser" and not State.ScopeVisible
	if not on then
		if laserPart then
			laserPart.Transparency = 1
		end
		if laserDot then
			laserDot.Transparency = 1
		end
		return
	end
	if not laserPart then
		local beam = Instance.new("Part")
		beam.Name = "LaserBeam"
		beam.Anchored = true
		beam.CanCollide = false
		beam.CanQuery = false
		beam.CanTouch = false
		beam.CastShadow = false
		beam.Material = Enum.Material.Neon
		beam.Color = Color3.fromRGB(255, 30, 30)
		beam.Parent = effectsFolder
		laserPart = beam
		local dot = beam:Clone()
		dot.Name = "LaserDot"
		dot.Shape = Enum.PartType.Ball
		dot.Size = Vector3.new(0.12, 0.12, 0.12)
		dot.Parent = effectsFolder
		laserDot = dot
	end
	local origin = emitter :: Vector3
	local aimPoint = camera.CFrame.Position + camera.CFrame.LookVector * 300
	local result = workspace:Raycast(camera.CFrame.Position, camera.CFrame.LookVector * 300, rayParams())
	local hit = result and result.Position or aimPoint
	-- Hip-fire laser points where the gun points, converging on the crosshair.
	local length = (hit - origin).Magnitude
	local beam = laserPart :: BasePart
	beam.Size = Vector3.new(0.012, 0.012, length)
	beam.CFrame = CFrame.lookAt(origin, hit) * CFrame.new(0, 0, -length / 2)
	beam.Transparency = 0.55
	local dot = laserDot :: BasePart
	dot.CFrame = CFrame.new(hit)
	dot.Transparency = 0.1
end

local function updateCamera(dt: number)
	if State.Cinematic then
		if viewmodel then
			viewmodel:SetVisible(false)
		end
		updateLaser(false)
		return
	end
	local w = currentWeapon()
	local h = humanoid()
	local alive = h ~= nil and h.Health > 0 and not isOut()

	local wantsAim = alive and aimHeld and w ~= nil and not State.Sprinting and not State.Reloading and not throwing
	local aimTime = w and w.AimTime or 0.2
	local step = dt / aimTime
	State.AimAlpha = math.clamp(State.AimAlpha + (wantsAim and step or -step), 0, 1)
	State.Aiming = State.AimAlpha > 0.5

	-- Field of view
	local baseFOV = State.Settings.FOV or Config.DefaultFOV
	local aimFOV = w and w.AimFOV or baseFOV
	local eased = 1 - (1 - State.AimAlpha) ^ 2
	camera.FieldOfView = baseFOV + (aimFOV - baseFOV) * eased + (State.Sprinting and 4 or 0) + (sliding and 7 or 0)

	-- Sensitivity scales with zoom so aiming feels consistent.
	local sens = State.Settings.Sensitivity or 1
	if State.AimAlpha > 0 then
		sens *= 1 + ((State.Settings.AimSensitivity or 0.6) * (aimFOV / baseFOV) - 1) * State.AimAlpha
	end
	UserInputService.MouseDeltaSensitivity = sens

	-- Recoil spring: kick toward the target, target recovers toward zero.
	recoilTarget = recoilTarget:Lerp(Vector2.zero, math.min(dt * 5, 1))
	local newOffset = recoilOffset:Lerp(recoilTarget, math.min(dt * 28, 1))
	local delta = newOffset - recoilOffset
	recoilOffset = newOffset
	local lookPitch = math.asin(math.clamp(camera.CFrame.LookVector.Y, -1, 1))
	local pitchDelta = delta.X
	if lookPitch + pitchDelta > math.rad(85) then
		pitchDelta = 0
	end
	camera.CFrame = camera.CFrame * CFrame.Angles(pitchDelta, delta.Y, 0) * CFrame.Angles(0, 0, math.rad(-lean * 8))

	bloom = math.max(bloom - dt * 3, 0)

	-- Scoped weapons swap to the scope overlay at full zoom.
	local scoped = w ~= nil and w.Scope == true and State.AimAlpha > 0.92
	if scoped ~= State.ScopeVisible then
		State.ScopeVisible = scoped
		State.Emit("Scope", scoped)
	end

	if viewmodel then
		local root = h and h.RootPart
		local speed = root and (root.AssemblyLinearVelocity * Vector3.new(1, 0, 1)).Magnitude or 0
		viewmodel:SetVisible(not scoped and alive)
		viewmodel:Update(dt, camera, eased, speed, mouseDelta, State.Sprinting, sliding)
		if aimHeld then
			viewmodel:CancelInspect()
		end
	end
	updateLaser(alive)
	mouseDelta = Vector2.zero

	if w then
		State.Spread = currentSpread(w)
	end
end

local function onRender(dt: number)
	updateMovement(dt)
	if triggerHeld or burstLeft > 0 then
		tryFire()
	end
	updateCamera(dt)
end

---------------------------------------------------------------------------
-- Character lifecycle and network events
---------------------------------------------------------------------------

local function onCharacter(c: Model)
	defaultHipHeight = nil
	State.Crouching = false
	State.Reloading = false
	State.AimAlpha = 0
	aimHeld = false
	triggerHeld = false
	throwing = false
	burstLeft = 0
	sliding = false
	recoilOffset = Vector2.zero
	recoilTarget = Vector2.zero
	if viewmodel then
		viewmodel:Destroy()
		viewmodel = nil
	end
	State.Weapon = nil
	equippedTool = nil

	c.ChildAdded:Connect(function(child)
		if child:IsA("Tool") then
			onToolEquipped(child)
		end
	end)
	c.ChildRemoved:Connect(function(child)
		if child:IsA("Tool") then
			onToolUnequipped(child)
		end
	end)

	-- Auto-equip the primary once the server has handed out the loadout.
	task.spawn(function()
		local backpack = player:WaitForChild("Backpack")
		local deadline = os.clock() + 10
		while os.clock() < deadline and c.Parent do
			if findTool("Primary") then
				break
			end
			backpack.ChildAdded:Wait()
		end
		if c.Parent and not equippedTool then
			WeaponController.EquipSlot("Primary")
		end
	end)
end

function WeaponController.Init()
	player.CameraMode = Enum.CameraMode.LockFirstPerson
	UserInputService.MouseIconEnabled = false

	setupInput()
	RunService:BindToRenderStep("AirsoftWeapons", Enum.RenderPriority.Camera.Value + 1, onRender)

	if player.Character then
		onCharacter(player.Character)
	end
	player.CharacterAdded:Connect(onCharacter)

	Remotes.AmmoSync.OnClientEvent:Connect(function(weaponId, mag, reserve)
		State.Ammo[weaponId] = { Mag = mag, Reserve = reserve }
		State.Emit("Ammo")
	end)

	-- Render everyone else's BBs.
	Remotes.ShotFired.OnClientEvent:Connect(function(shooter: Player, weaponId: string, origin: Vector3, dirs: { Vector3 })
		if shooter == player then
			return
		end
		local shooterTool = shooter.Character and shooter.Character:FindFirstChildOfClass("Tool")
		local w = Weapons.Resolve(weaponId, Weapons.ParseLoadout(shooterTool and shooterTool:GetAttribute("Loadout")))
		if not w then
			return
		end
		local side = shooter:GetAttribute("Side")
		local color = (side and Config.Teams[side]) and Config.Teams[side].Color or Color3.fromRGB(255, 196, 64)
		local tool = shooter.Character and shooter.Character:FindFirstChildOfClass("Tool")
		local handle = tool and tool:FindFirstChild("Handle")
		local muzzle = handle and handle:FindFirstChild("Muzzle") :: Attachment?
		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		params.FilterDescendantsInstances = { camera, effectsFolder, shooter.Character :: Instance }
		for _, dir in dirs do
			local step, finish = visualBB(color, origin, muzzle and muzzle.WorldPosition)
			Ballistics.Fire({
				Origin = origin,
				Direction = dir,
				Speed = w.Velocity,
				Gravity = w.Gravity,
				Range = w.Range,
				Params = params,
				OnStep = step,
				OnEnd = finish,
				OnHit = function(result)
					if not playerFromPart(result.Instance) then
						Effects.Impact(result.Position, result.Normal, result.Material)
					end
				end,
			})
		end
		Effects.Play3D(w.Sound, muzzle and muzzle.WorldPosition or origin, w.Quiet and 0.25 or 0.6, firePitch(w))
	end)

	Remotes.GrenadeBurst.OnClientEvent:Connect(Effects.GrenadeBurst)

	Remotes.HitConfirm.OnClientEvent:Connect(function()
		Effects.Play2D("HitMarker", 0.6, 1.2)
		State.Emit("HitMarker", true)
	end)

	player:GetAttributeChangedSignal("Out"):Connect(function()
		if isOut() then
			triggerHeld = false
			aimHeld = false
			cancelReload()
		end
	end)
end

function WeaponController.FireModeName()
	return fireModeName()
end

return WeaponController
