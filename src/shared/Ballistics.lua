--[[
	BB flight simulation shared by client and server.

	BBs are real projectiles: they travel at the weapon's muzzle velocity, drop
	slightly (hop-up keeps it low) and are swept with raycasts every frame so
	nothing tunnels through thin cover.
]]

local RunService = game:GetService("RunService")

local Ballistics = {}

export type Shot = {
	Origin: Vector3,
	Direction: Vector3,
	Speed: number,
	Gravity: number,
	Range: number,
	Params: RaycastParams,
	OnHit: ((RaycastResult) -> ())?,
	OnStep: ((Vector3, Vector3) -> ())?,
	OnEnd: ((Vector3) -> ())?,
}

type ActiveShot = {
	Shot: Shot,
	Position: Vector3,
	Velocity: Vector3,
	Travelled: number,
	Done: boolean,
}

local active: { ActiveShot } = {}
local connection: RBXScriptConnection? = nil

local function step(dt: number)
	local i = 1
	while i <= #active do
		local a = active[i]
		local shot = a.Shot
		if not a.Done then
			local velocity = a.Velocity - Vector3.new(0, shot.Gravity * dt, 0)
			local delta = (a.Velocity + velocity) * 0.5 * dt
			a.Velocity = velocity

			local result = workspace:Raycast(a.Position, delta, shot.Params)
			if result then
				if shot.OnStep then
					shot.OnStep(a.Position, result.Position)
				end
				a.Done = true
				a.Position = result.Position
				if shot.OnHit then
					shot.OnHit(result)
				end
			else
				local nextPos = a.Position + delta
				if shot.OnStep then
					shot.OnStep(a.Position, nextPos)
				end
				a.Position = nextPos
				a.Travelled += delta.Magnitude
				if a.Travelled >= shot.Range or nextPos.Y < -200 then
					a.Done = true
				end
			end

			if a.Done and shot.OnEnd then
				shot.OnEnd(a.Position)
			end
		end

		if a.Done then
			table.remove(active, i)
		else
			i += 1
		end
	end

	if #active == 0 and connection then
		connection:Disconnect()
		connection = nil
	end
end

function Ballistics.Fire(shot: Shot)
	table.insert(active, {
		Shot = shot,
		Position = shot.Origin,
		Velocity = shot.Direction.Unit * shot.Speed,
		Travelled = 0,
		Done = false,
	})
	if not connection then
		connection = RunService.Heartbeat:Connect(step)
	end
end

-- Random direction inside a cone of `degrees` half-angle around `direction`.
function Ballistics.Spread(direction: Vector3, degrees: number, rng: Random?): Vector3
	if degrees <= 0 then
		return direction.Unit
	end
	local r = rng or Random.new()
	local cf = CFrame.lookAt(Vector3.zero, direction)
	local angle = math.rad(degrees) * math.sqrt(r:NextNumber())
	local roll = r:NextNumber() * math.pi * 2
	return (cf * CFrame.Angles(0, 0, roll) * CFrame.Angles(angle, 0, 0)).LookVector
end

-- Worst-case flight time, used by the server to expire shot records.
function Ballistics.MaxFlightTime(speed: number, range: number): number
	return range / speed * 1.6 + 0.5
end

return Ballistics
