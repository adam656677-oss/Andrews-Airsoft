--[[
	Local-only visual and audio effects: BB tracers, impact puffs, sounds,
	grenade bursts and practice-target dings.
]]

local Debris = game:GetService("Debris")
local SoundService = game:GetService("SoundService")
local TweenService = game:GetService("TweenService")

local Shared = game:GetService("ReplicatedStorage"):WaitForChild("Shared")
local Config = require(Shared.Config)
local Ballistics = require(Shared.Ballistics)

local Effects = {}

local effectsFolder = workspace:WaitForChild("Effects")

local function sound(id: string, volume: number, pitch: number): Sound
	local s = Instance.new("Sound")
	s.SoundId = id
	s.Volume = volume
	s.PlaybackSpeed = pitch
	s.RollOffMode = Enum.RollOffMode.InverseTapered
	s.RollOffMinDistance = 8
	s.RollOffMaxDistance = 220
	return s
end

-- Plays a UI/first-person sound (no spatialisation).
function Effects.Play2D(key: string, volume: number?, pitch: number?)
	local id = Config.Sounds[key]
	if not id then
		return
	end
	local s = sound(id, volume or 0.5, pitch or 1)
	s.Parent = SoundService
	s:Play()
	Debris:AddItem(s, 3)
end

-- Plays a positional sound in the world.
function Effects.Play3D(key: string, position: Vector3, volume: number?, pitch: number?)
	local id = Config.Sounds[key]
	if not id then
		return
	end
	local holder = Instance.new("Attachment")
	holder.WorldPosition = position
	holder.Parent = workspace.Terrain
	local s = sound(id, volume or 0.6, pitch or 1)
	s.Parent = holder
	s:Play()
	Debris:AddItem(holder, 3)
end

local puffTemplate: ParticleEmitter = (function()
	local p = Instance.new("ParticleEmitter")
	p.Texture = "rbxasset://textures/particles/smoke_main.dds"
	p.Lifetime = NumberRange.new(0.25, 0.5)
	p.Speed = NumberRange.new(2, 6)
	p.SpreadAngle = Vector2.new(50, 50)
	p.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.2), NumberSequenceKeypoint.new(1, 0.9) })
	p.Transparency = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.55), NumberSequenceKeypoint.new(1, 1) })
	p.Color = ColorSequence.new(Color3.fromRGB(200, 190, 170))
	p.LightInfluence = 1
	p.Enabled = false
	return p
end)()

local sparkTemplate: ParticleEmitter = (function()
	local p = Instance.new("ParticleEmitter")
	p.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	p.Lifetime = NumberRange.new(0.08, 0.18)
	p.Speed = NumberRange.new(6, 14)
	p.SpreadAngle = Vector2.new(70, 70)
	p.Size = NumberSequence.new(0.12)
	p.LightEmission = 1
	p.Color = ColorSequence.new(Color3.fromRGB(255, 240, 210))
	p.Enabled = false
	return p
end)()

function Effects.Impact(position: Vector3, normal: Vector3, material: Enum.Material)
	local holder = Instance.new("Attachment")
	holder.WorldCFrame = CFrame.lookAt(position, position + normal) * CFrame.Angles(-math.pi / 2, 0, 0)
	holder.Parent = workspace.Terrain
	local hard = material == Enum.Material.Metal
		or material == Enum.Material.CorrodedMetal
		or material == Enum.Material.DiamondPlate
		or material == Enum.Material.Concrete
	local emitter = (hard and sparkTemplate or puffTemplate):Clone()
	emitter.Parent = holder
	emitter:Emit(hard and 5 or 3)
	Debris:AddItem(holder, 1)
end

-- Spawns a visible BB that follows the simulated flight path.
function Effects.BB(color: Color3): ((Vector3, Vector3) -> (), () -> ())
	local part = Instance.new("Part")
	part.Name = "BB"
	part.Anchored = true
	part.CanCollide = false
	part.CanQuery = false
	part.CanTouch = false
	part.CastShadow = false
	part.Material = Enum.Material.Neon
	part.Color = color
	part.Size = Vector3.new(0.09, 0.09, 0.5)
	part.Transparency = 0.15
	part.Parent = effectsFolder

	local light = Instance.new("PointLight")
	light.Color = color
	light.Range = 4
	light.Brightness = 1.5
	light.Parent = part

	local function step(from: Vector3, to: Vector3)
		local d = to - from
		local len = math.max(d.Magnitude, 0.05)
		part.Size = Vector3.new(0.09, 0.09, math.min(len, 6))
		part.CFrame = CFrame.lookAt(to - d.Unit * math.min(len, 6) / 2, to)
	end
	local function finish()
		part:Destroy()
	end
	return step, finish
end

function Effects.GrenadeBurst(position: Vector3, radius: number)
	Effects.Play3D("Grenade", position, 1.2, 0.6)
	Effects.Play3D("Grenade", position, 1, 0.8)
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { effectsFolder }
	local rng = Random.new()
	for _ = 1, 36 do
		local dir = Vector3.new(rng:NextNumber(-1, 1), rng:NextNumber(-0.1, 0.8), rng:NextNumber(-1, 1)).Unit
		local onStep, onEnd = Effects.BB(Color3.fromRGB(255, 220, 150))
		Ballistics.Fire({
			Origin = position + Vector3.new(0, 0.3, 0),
			Direction = dir,
			Speed = 160,
			Gravity = 60,
			Range = radius,
			Params = params,
			OnStep = onStep,
			OnEnd = onEnd,
		})
	end
	local holder = Instance.new("Attachment")
	holder.WorldPosition = position
	holder.Parent = workspace.Terrain
	local puff = puffTemplate:Clone()
	puff.Speed = NumberRange.new(8, 16)
	puff.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 1), NumberSequenceKeypoint.new(1, 4) })
	puff.Lifetime = NumberRange.new(0.6, 1.2)
	puff.Parent = holder
	puff:Emit(20)
	Debris:AddItem(holder, 2)
end

function Effects.TargetDing(plate: BasePart)
	Effects.Play3D("Ding", plate.Position, 0.8, 1.4)
	local original = plate:GetAttribute("BaseColor") or plate.Color
	plate:SetAttribute("BaseColor", original)
	plate.Color = Color3.fromRGB(255, 80, 60)
	TweenService:Create(plate, TweenInfo.new(0.4), { Color = original }):Play()
end

return Effects
