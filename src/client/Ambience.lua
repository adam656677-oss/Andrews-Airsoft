--[[
	World ambience that only needs to exist on the client:
	  • rain and the odd lightning flash on Velvet Club (only outdoors)
	  • armory display prompts open the customisation screen
]]

local Lighting = game:GetService("Lighting")
local Players = game:GetService("Players")
local ProximityPromptService = game:GetService("ProximityPromptService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local Menu = require(script.Parent.Menu)

local Ambience = {}

local camera = workspace.CurrentCamera
local gameState = ReplicatedStorage:WaitForChild("GameState")

local function makeRain(): (BasePart, ParticleEmitter, ParticleEmitter)
	local emitterPart = Instance.new("Part")
	emitterPart.Name = "RainEmitter"
	emitterPart.Size = Vector3.new(110, 1, 110)
	emitterPart.Transparency = 1
	emitterPart.Anchored = true
	emitterPart.CanCollide = false
	emitterPart.CanQuery = false
	emitterPart.CanTouch = false
	emitterPart.CastShadow = false

	local rain = Instance.new("ParticleEmitter")
	rain.Name = "Rain"
	rain.Texture = "rbxasset://textures/particles/sparkles_main.dds"
	rain.EmissionDirection = Enum.NormalId.Bottom
	rain.Rate = 0
	rain.Lifetime = NumberRange.new(0.8, 1.1)
	rain.Speed = NumberRange.new(95, 120)
	rain.Size = NumberSequence.new(0.12)
	rain.Squash = NumberSequence.new(2.6)
	rain.Transparency = NumberSequence.new(0.35)
	rain.Color = ColorSequence.new(Color3.fromRGB(190, 210, 235))
	rain.LightInfluence = 0.8
	rain.LightEmission = 0.2
	rain.Acceleration = Vector3.new(4, 0, 2)
	rain.Parent = emitterPart

	-- Close-up streaks so rain reads in first person.
	local near = rain:Clone()
	near.Name = "NearRain"
	near.Size = NumberSequence.new(0.06)
	near.Squash = NumberSequence.new(4)
	near.Lifetime = NumberRange.new(0.3, 0.45)
	near.Parent = emitterPart

	emitterPart.Parent = workspace:WaitForChild("Effects")
	return emitterPart, rain, near
end

function Ambience.Init()
	ProximityPromptService.PromptTriggered:Connect(function(prompt)
		local weaponId = prompt:GetAttribute("WeaponId")
		if weaponId then
			Menu.OpenLoadout(weaponId)
		end
	end)

	local emitterPart, rain, near = makeRain()
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	local nextLightning = os.clock() + 20

	local lastCheck = 0
	RunService.Heartbeat:Connect(function()
		local inClub = gameState:GetAttribute("Map") == "Club" and camera.CFrame.Position.X > 800
		local now = os.clock()
		if not inClub then
			rain.Rate = 0
			near.Rate = 0
			return
		end
		local pos = camera.CFrame.Position
		emitterPart.CFrame = CFrame.new(pos + Vector3.new(0, 45, 0))
		if now - lastCheck > 0.2 then
			lastCheck = now
			-- Indoors (anything solid overhead) means no rain.
			params.FilterDescendantsInstances = { camera, workspace:FindFirstChild("Effects") :: Instance, Players.LocalPlayer.Character :: Instance }
			local roof = workspace:Raycast(pos, Vector3.new(0, 50, 0), params)
			local outdoors = roof == nil or roof.Instance.Transparency >= 1
			rain.Rate = outdoors and 1600 or 0
			near.Rate = outdoors and 500 or 0
		end
		if now > nextLightning then
			nextLightning = now + math.random(18, 40)
			local grade = Lighting:FindFirstChild("Grade") :: ColorCorrectionEffect?
			if grade then
				local base = grade.Brightness
				grade.Brightness = base + 0.35
				TweenService:Create(grade, TweenInfo.new(0.5), { Brightness = base }):Play()
			end
		end
	end)
end

return Ambience
