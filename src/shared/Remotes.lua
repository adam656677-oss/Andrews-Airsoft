--[[
	Single place that names every network channel. The server creates them,
	clients wait for them.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local EVENTS = {
	-- client -> server
	"Fire", -- (weaponId, shotId, origin, directions)
	"Hit", -- (shotId, pelletIndex, hitPart, hitPosition)
	"Reload", -- (weaponId)
	"ThrowGrenade", -- (origin, direction)
	"SetLoadout", -- (primaryId, secondaryId)
	"SaveSettings", -- (settingsTable)
	"VoteMode", -- (modeId)
	"ToggleLight", -- (on) weapon light

	-- server -> client
	"ShotFired", -- (shooter, weaponId, origin, directions)
	"Tagged", -- (victim, shooter, weaponId, shooterPosition)
	"HitConfirm", -- (victim)
	"AmmoSync", -- (weaponId, mag, reserve)
	"Announce", -- (title, subtitle, color, duration)
	"XPGained", -- (amount, reason)
	"GrenadeBurst", -- (position, radius)
	"RoundSummary", -- (summaryTable)
	"Profile", -- (profileTable)
}

local FUNCTIONS = {
	"GetProfile",
}

local Remotes = {}

local folder: Folder
if RunService:IsServer() then
	folder = ReplicatedStorage:FindFirstChild("Remotes") :: Folder
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "Remotes"
		folder.Parent = ReplicatedStorage
	end
	for _, name in EVENTS do
		if not folder:FindFirstChild(name) then
			local remote = Instance.new("RemoteEvent")
			remote.Name = name
			remote.Parent = folder
		end
	end
	for _, name in FUNCTIONS do
		if not folder:FindFirstChild(name) then
			local remote = Instance.new("RemoteFunction")
			remote.Name = name
			remote.Parent = folder
		end
	end
else
	folder = ReplicatedStorage:WaitForChild("Remotes") :: Folder
end

for _, name in EVENTS do
	Remotes[name] = folder:WaitForChild(name)
end
for _, name in FUNCTIONS do
	Remotes[name] = folder:WaitForChild(name)
end

return Remotes
