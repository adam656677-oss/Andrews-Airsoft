--[[
	Tiny helpers for building anchored world geometry.
]]

local Build = {}

export type PartProps = {
	Name: string?,
	Size: Vector3,
	CFrame: CFrame,
	Color: Color3?,
	Material: Enum.Material?,
	Shape: Enum.PartType?,
	Transparency: number?,
	CanCollide: boolean?,
	CastShadow: boolean?,
	Reflectance: number?,
	Parent: Instance?,
}

function Build.Part(props: PartProps): Part
	local part = Instance.new("Part")
	part.Name = props.Name or "Part"
	part.Anchored = true
	part.Shape = props.Shape or Enum.PartType.Block
	part.Size = props.Size
	part.CFrame = props.CFrame
	part.Color = props.Color or Color3.fromRGB(120, 120, 120)
	part.Material = props.Material or Enum.Material.SmoothPlastic
	part.Transparency = props.Transparency or 0
	part.Reflectance = props.Reflectance or 0
	if props.CanCollide ~= nil then
		part.CanCollide = props.CanCollide
	end
	if props.CastShadow ~= nil then
		part.CastShadow = props.CastShadow
	end
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.Parent = props.Parent
	return part
end

function Build.Wedge(props: PartProps): WedgePart
	local part = Instance.new("WedgePart")
	part.Name = props.Name or "Wedge"
	part.Anchored = true
	part.Size = props.Size
	part.CFrame = props.CFrame
	part.Color = props.Color or Color3.fromRGB(120, 120, 120)
	part.Material = props.Material or Enum.Material.SmoothPlastic
	part.TopSurface = Enum.SurfaceType.Smooth
	part.BottomSurface = Enum.SurfaceType.Smooth
	part.Parent = props.Parent
	return part
end

function Build.Model(name: string, parent: Instance?): Model
	local m = Instance.new("Model")
	m.Name = name
	m.Parent = parent
	return m
end

function Build.Folder(name: string, parent: Instance?): Folder
	local f = Instance.new("Folder")
	f.Name = name
	f.Parent = parent
	return f
end

-- A beam-shaped part spanning two points.
function Build.Span(a: Vector3, b: Vector3, thickness: number, props: PartProps?)
	local p = props or ({} :: any)
	local length = (b - a).Magnitude
	return Build.Part({
		Name = p.Name or "Span",
		Size = Vector3.new(thickness, thickness, length),
		CFrame = CFrame.lookAt((a + b) / 2, b),
		Color = p.Color,
		Material = p.Material,
		CanCollide = p.CanCollide,
		Parent = p.Parent,
	})
end

export type Opening = { At: number, Width: number, Bottom: number, Top: number }

-- Builds a wall from `a` to `b` (both at floor level) with rectangular openings.
function Build.Wall(parent: Instance, a: Vector3, b: Vector3, height: number, thickness: number, color: Color3, material: Enum.Material, openings: { Opening }?)
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

function Build.SurfaceText(part: BasePart, face: Enum.NormalId, text: string, color: Color3?, background: Color3?)
	local gui = Instance.new("SurfaceGui")
	gui.Face = face
	gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	gui.PixelsPerStud = 40
	gui.LightInfluence = 0.6
	gui.Parent = part

	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundColor3 = background or Color3.new(0, 0, 0)
	label.BackgroundTransparency = background and 0 or 1
	label.TextColor3 = color or Color3.new(1, 1, 1)
	label.Font = Enum.Font.GothamBlack
	label.TextScaled = true
	label.Text = text
	label.Parent = gui

	local pad = Instance.new("UIPadding")
	pad.PaddingTop = UDim.new(0.12, 0)
	pad.PaddingBottom = UDim.new(0.12, 0)
	pad.PaddingLeft = UDim.new(0.06, 0)
	pad.PaddingRight = UDim.new(0.06, 0)
	pad.Parent = label
	return gui
end

return Build
