--[[
	Andrew's Airsoft — client entry point.
]]

local StarterGui = game:GetService("StarterGui")

-- Our own HUD replaces the default backpack and health bar.
local function hideCoreGui()
	for _, kind in { Enum.CoreGuiType.Backpack, Enum.CoreGuiType.Health } do
		pcall(function()
			StarterGui:SetCoreGuiEnabled(kind, false)
		end)
	end
	pcall(function()
		StarterGui:SetCore("ResetButtonCallback", false)
	end)
end
hideCoreGui()
task.delay(2, hideCoreGui)

local HUD = require(script.Parent.HUD)
local Menu = require(script.Parent.Menu)
local WeaponController = require(script.Parent.WeaponController)
local Cinematic = require(script.Parent.Cinematic)
local Ambience = require(script.Parent.Ambience)

Cinematic.Init()
HUD.Init()
Menu.Init()
WeaponController.Init()
Ambience.Init()
