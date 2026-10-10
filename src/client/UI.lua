--[[
	Small helpers so the HUD and menus share one visual language:
	dark translucent panels, amber accents, condensed bold type.
]]

local UI = {}

UI.Colors = {
	Panel = Color3.fromRGB(14, 16, 19),
	PanelLight = Color3.fromRGB(28, 31, 36),
	Text = Color3.fromRGB(236, 236, 232),
	Muted = Color3.fromRGB(150, 152, 156),
	Accent = Color3.fromRGB(255, 196, 64),
	Good = Color3.fromRGB(120, 230, 140),
	Bad = Color3.fromRGB(255, 110, 70),
}

UI.Font = Enum.Font.GothamBold
UI.FontHeavy = Enum.Font.GothamBlack
UI.FontLight = Enum.Font.GothamMedium

function UI.new(className: string, props: { [string]: any }, children: { Instance }?): any
	local inst = Instance.new(className)
	local parent = props.Parent
	for k, v in props do
		if k ~= "Parent" then
			(inst :: any)[k] = v
		end
	end
	for _, child in children or {} do
		child.Parent = inst
	end
	inst.Parent = parent
	return inst
end

function UI.Corner(radius: number?)
	return UI.new("UICorner", { CornerRadius = UDim.new(0, radius or 6) })
end

function UI.Stroke(color: Color3?, thickness: number?, transparency: number?)
	return UI.new("UIStroke", {
		Color = color or Color3.new(1, 1, 1),
		Thickness = thickness or 1,
		Transparency = transparency or 0.85,
		ApplyStrokeMode = Enum.ApplyStrokeMode.Border,
	})
end

function UI.Padding(px: number)
	local u = UDim.new(0, px)
	return UI.new("UIPadding", { PaddingTop = u, PaddingBottom = u, PaddingLeft = u, PaddingRight = u })
end

function UI.Panel(props: { [string]: any }): Frame
	props.BackgroundColor3 = props.BackgroundColor3 or UI.Colors.Panel
	props.BackgroundTransparency = props.BackgroundTransparency or 0.2
	props.BorderSizePixel = 0
	return UI.new("Frame", props, { UI.Corner(6), UI.Stroke() })
end

function UI.Label(props: { [string]: any }): TextLabel
	props.BackgroundTransparency = props.BackgroundTransparency or 1
	props.Font = props.Font or UI.Font
	props.TextColor3 = props.TextColor3 or UI.Colors.Text
	props.TextSize = props.TextSize or 16
	props.BorderSizePixel = 0
	return UI.new("TextLabel", props)
end

function UI.Button(props: { [string]: any }): TextButton
	props.BackgroundColor3 = props.BackgroundColor3 or UI.Colors.PanelLight
	props.BackgroundTransparency = props.BackgroundTransparency or 0.1
	props.Font = props.Font or UI.Font
	props.TextColor3 = props.TextColor3 or UI.Colors.Text
	props.TextSize = props.TextSize or 16
	props.AutoButtonColor = true
	props.BorderSizePixel = 0
	return UI.new("TextButton", props, { UI.Corner(5), UI.Stroke() })
end

return UI
