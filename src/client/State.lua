--[[
	Client-side shared state and a tiny signal so modules can react to changes.
]]

local Config = require(game:GetService("ReplicatedStorage").Shared.Config)

local State = {
	Profile = nil :: any,
	Settings = table.clone(Config.DefaultSettings),
	Ammo = {} :: { [string]: { Mag: number, Reserve: number } },
	Weapon = nil :: string?, -- equipped weapon id
	Aiming = false,
	AimAlpha = 0, -- 0 hip → 1 fully aimed
	Sprinting = false,
	Crouching = false,
	Reloading = false,
	FireMode = {} :: { [string]: number },
	MenuOpen = false,
	Spread = 0,
	ScopeVisible = false,
	Cinematic = false,
}

local listeners: { [string]: { (any) -> () } } = {}

function State.On(event: string, fn: (any) -> ())
	listeners[event] = listeners[event] or {}
	table.insert(listeners[event], fn)
end

function State.Emit(event: string, ...)
	for _, fn in listeners[event] or {} do
		task.spawn(fn, ...)
	end
end

return State
