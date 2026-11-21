-- Taxi Time: Options.lua
-- The options panel in Blizzard's own Settings window (Options > AddOns >
-- Taxi Time), and TT.SetOption: the one path the panel and the slash
-- commands use to change a setting.
--
-- The panel is a CANVAS: our own frame, built from Blizzard's templates, that
-- the Settings window only parents to its canvas and calls OnRefresh /
-- OnDefault on (through securecallfunction). It does NOT use Blizzard's
-- vertical settings list: that list reuses the same row frames for every
-- category, and rows filled by an addon were later reused for Blizzard's
-- Social > Discord button, whose Init calls the restricted
-- C_Discord.IsUserOAuthed() -> "ADDON_ACTION_FORBIDDEN" while scrolling.
--
-- API checked against Blizzard's UI source for WoW Forever 1.60.1 (wow-ui-source
-- branch "forever": Blizzard_Settings_Shared/Blizzard_Settings.lua
-- RegisterCanvasLayoutCategory, Blizzard_SettingsPanel.lua DisplayLayout /
-- CallDefaultOnCanvases, Blizzard_SharedXML/Shared/Slider/MinimalSlider.lua,
-- Blizzard_Menu/MenuUtil.lua) and warcraft.wiki.gg "Settings API" /
-- "Using the ColorPickerFrame". Every call is checked or has a fallback, so a
-- missing one only loses (part of) the panel, never the addon.

local ADDON, TT = ...

local category          -- our Settings category (nil = no panel on this client)
local refreshing = false -- true while we put a saved value into a control (no feedback loop)

-- the panel's parts; TT.OptionsUI is also read by the offline tests
-- controls: option key -> { kind, name, default, widget, Set(value) }
local ui = { controls = {}, buttons = {}, headers = {}, y = 0 }
TT.OptionsUI = ui

------------------------------------------------------------------------
-- Options: where each one is saved and what applies it live
------------------------------------------------------------------------

-- tbl: "bar" = TaxiTimeDB.bar, "db" = TaxiTimeDB
local OPTIONS = {
	locked     = { tbl = "bar", kind = "boolean", apply = function(v) TT.Bar:SetLocked(v) end },
	width      = { tbl = "bar", kind = "number", apply = function() TT.Bar:ApplySize() end },
	scale      = { tbl = "bar", kind = "number", apply = function() TT.Bar:ApplyScale() end },
	showTotals = { tbl = "bar", kind = "boolean", apply = function(v) TT.Bar:SetShowTotals(v) end },
	showRank   = { tbl = "bar", kind = "boolean", apply = function() TT.Bar:SetShowRank() end },
	flyer      = { tbl = "bar", kind = "string", apply = function() TT.RefreshFlyer() end },
	tooltip    = { tbl = "db", kind = "boolean" }, -- read on each flight-map hover
	landSound  = { tbl = "db", kind = "boolean", apply = function(v) if v then TT.Bar:PlayLandSound() end end }, -- on = preview once
	landSparkle = { tbl = "bar", kind = "boolean" }, -- read at each landing
	milestoneChat = { tbl = "db", kind = "boolean" }, -- read when a milestone is reached
	colorFlight = { tbl = "bar", kind = "color", apply = function() TT.Bar:ApplyColors() end },
	colorRecord = { tbl = "bar", kind = "color", apply = function() TT.Bar:ApplyColors() end },
}

-- value made valid for the option, or nil = refuse (color: nil means "default")
local function Clean(key, value)
	local o = OPTIONS[key]
	if o.kind == "boolean" then
		if type(value) == "boolean" then return value end
	elseif o.kind == "number" then
		local lim = TT.limits[key]
		if type(value) == "number" and value == value then
			if value < lim[1] then value = lim[1] elseif value > lim[2] then value = lim[2] end
			-- slider steps can carry float noise (0.7 + 0.05 * n)
			return tonumber(string.format("%.4f", math.floor(value / lim[3] + 0.5) * lim[3]))
		end
	elseif o.kind == "string" then
		if value == "auto" or value == "none" or TT.FLYER_KINDS[value] then return value end
	elseif o.kind == "color" then
		if type(value) == "table" then
			local c = {}
			for i = 1, 3 do
				local v = tonumber(value[i])
				if not v or v ~= v then return nil end
				c[i] = math.max(0, math.min(1, v))
			end
			return c
		end
	end
	return nil
end

-- the saved value of an option
local function Saved(key)
	local o = OPTIONS[key]
	if not (o and TT.db) then return nil end
	local tbl = o.tbl == "db" and TT.db or TT.db.bar
	return tbl and tbl[key]
end

-- puts a value into the option's control (if the panel has one)
local function ShowValue(key, value)
	local c = ui.controls[key]
	if not (c and c.Set) or refreshing then return end
	refreshing = true
	pcall(c.Set, value)
	refreshing = false
end

-- Saves an option, applies it at once and shows it in the panel.
-- Colours: value nil = back to the default. Returns true if it was taken.
function TT.SetOption(key, value)
	local o = OPTIONS[key]
	if not o or not TT.db then return false end
	local clean = Clean(key, value)
	if clean == nil and o.kind ~= "color" then return false end
	local tbl = o.tbl == "db" and TT.db or TT.db.bar
	tbl[key] = clean
	if o.apply then o.apply(clean) end
	ShowValue(key, clean) -- also when the panel is open (slash commands, rounding)
	return true
end

-- a control was changed by the user: save it, or show the saved value again if refused
local function UserSet(key, value)
	if refreshing then return end
	if not TT.SetOption(key, value) then ShowValue(key, Saved(key)) end
end

-- every control shows its saved value (panel shown, Settings window refresh)
local function RefreshAll()
	if not TT.db then return end
	for key in pairs(ui.controls) do ShowValue(key, Saved(key)) end
end

-- Blizzard's "Defaults" (this page or all settings) and our Defaults button:
-- the options of the controls back to their defaults (colours and recorded
-- flights are not touched, as before). Only changed ones, so nothing replays.
local function ResetToDefaults()
	if not TT.db then return end
	for key, c in pairs(ui.controls) do
		if Saved(key) ~= c.default then TT.SetOption(key, c.default) end
	end
end

------------------------------------------------------------------------
-- Colour picker (Blizzard's ColorPickerFrame)
------------------------------------------------------------------------

local previewing = false -- the test bar was shown only as the picker's preview
local pickerHooked = false

local function PickColor(key)
	if not (ColorPickerFrame and ColorPickerFrame.SetupColorPickerAndShow) then
		TT.Print("the colour picker is not available on this client.")
		return
	end
	local saved = TT.db.bar[key] -- nil = default; put back on Cancel
	if type(saved) == "table" then saved = { saved[1], saved[2], saved[3] } end
	local r, g, b = TT.Bar:GetColor(key)
	local function Changed()
		local nr, ng, nb = ColorPickerFrame:GetColorRGB()
		TT.SetOption(key, { nr, ng, nb })
	end
	ColorPickerFrame:SetupColorPickerAndShow({
		r = r, g = g, b = b,
		hasOpacity = false,
		swatchFunc = Changed,
		cancelFunc = function() TT.SetOption(key, saved) end,
	})
	-- the test bar is the preview while the picker is open (not during a flight);
	-- it goes away again when the picker closes, unless it was already showing
	if not pickerHooked and ColorPickerFrame.HookScript then
		ColorPickerFrame:HookScript("OnHide", function()
			if previewing then
				previewing = false
				if TT.db.bar.locked then TT.Bar:HideTest() end -- unlocked: keep it to drag
			end
		end)
		pickerHooked = true
	end
	if pickerHooked and not TT.Bar:IsTestShown() then
		TT.Bar:ShowTest()
		previewing = TT.Bar:IsTestShown()
	end
end

------------------------------------------------------------------------
-- The panel (canvas): Blizzard's look, our own frames
------------------------------------------------------------------------

local FLYER_LABELS = {
	{ "auto", "Automatic (by flight master)" },
	{ "gryphon", "Gryphon" },
	{ "wyvern", "Wind rider" },
	{ "bat", "Bat" },
	{ "hippogryph", "Hippogryph" },
	{ "none", "None (no creature)" },
}

-- every art choice of the panel in one place (Blizzard's names, none copied);
-- the same sizes and fonts as Blizzard's own settings list
local ART = {
	title = "GameFontHighlightHuge",       -- page title (SettingsListTemplate Header)
	header = "GameFontHighlightLarge",     -- section header (SettingsListSectionHeaderTemplate)
	label = "GameFontNormal",              -- control label
	divider = "Options_HorizontalDivider", -- line under the title
	checkbox = { "MinimalCheckboxTemplate", "UICheckButtonTemplate" },
	slider = "MinimalSliderWithSteppersTemplate",
	button = "UIPanelButtonTemplate",
	dropdown = "WowStyle1DropdownTemplate",
	scroll = "ScrollFrameTemplate",
	rowHeight = 26, headerHeight = 45, labelX = 37, controlX = -80, -- controlX: from the row's centre
}

-- a frame from a Blizzard template, or nil if this client hasn't got it
local function Try(kind, parent, template)
	local ok, f = pcall(CreateFrame, kind, nil, parent, template)
	if ok and f then return f end
	return nil
end

local function PlayClick(on)
	if PlaySound and SOUNDKIT then
		local id = on and SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_ON or SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_OFF
		if id then PlaySound(id) end
	end
end

-- tooltip like Blizzard's settings: the name in white, the help text below
local function TipEnter(self)
	local row = self.ttRow or self
	if not (GameTooltip and row.ttName) then return end
	GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
	GameTooltip:SetText(row.ttName, 1, 1, 1)
	if row.ttText then
		local n = NORMAL_FONT_COLOR
		GameTooltip:AddLine(row.ttText, n and n.r or 1, n and n.g or 0.82, n and n.b or 0, true)
	end
	GameTooltip:Show()
end
local function TipLeave()
	if GameTooltip then GameTooltip:Hide() end
end
local function AddTip(region, row)
	if not (region and region.HookScript) then return end
	region.ttRow = row
	region:HookScript("OnEnter", TipEnter)
	region:HookScript("OnLeave", TipLeave)
end

-- one line of the page, under the one before
local function NewRow(height, name, tooltip)
	local row = CreateFrame("Frame", nil, ui.content)
	row:SetHeight(height)
	row:SetPoint("TOPLEFT", ui.content, "TOPLEFT", 0, -ui.y)
	row:SetPoint("RIGHT", ui.content, "RIGHT", 0, 0)
	ui.y = ui.y + height
	if name then
		local fs = row:CreateFontString(nil, "ARTWORK", ART.label)
		fs:SetPoint("LEFT", row, "LEFT", ART.labelX, 0)
		fs:SetPoint("RIGHT", row, "CENTER", ART.controlX - 8, 0)
		fs:SetJustifyH("LEFT")
		if fs.SetWordWrap then fs:SetWordWrap(false) end
		fs:SetText(name)
		row.label = fs
		row.ttName, row.ttText = name, tooltip
		row:EnableMouse(true) -- tooltip over the label too
		AddTip(row, row)
	end
	return row
end

local function PlaceControl(widget, row)
	widget:SetPoint("LEFT", row, "CENTER", ART.controlX, 0)
	AddTip(widget, row)
end

local function AddControl(key, kind, name, default, widget, Set)
	ui.controls[key] = { kind = kind, name = name, default = default, widget = widget, Set = Set }
end

local function Header(text)
	local row = NewRow(ART.headerHeight)
	local fs = row:CreateFontString(nil, "OVERLAY", ART.header)
	fs:SetPoint("TOPLEFT", row, "TOPLEFT", 7, -16)
	fs:SetJustifyH("LEFT")
	fs:SetText(text)
	ui.headers[#ui.headers + 1] = text
end

local function PanelButton(parent, w, h)
	local b = Try("Button", parent, ART.button)
	if not b then -- fallback: plain button with Blizzard's button font
		b = CreateFrame("Button", nil, parent)
		if b.SetNormalFontObject then b:SetNormalFontObject("GameFontNormal") end
		if b.SetHighlightFontObject then b:SetHighlightFontObject("GameFontHighlight") end
	end
	b:SetSize(w, h)
	return b
end

local function Button(name, text, onClick, tooltip)
	local row = NewRow(ART.rowHeight, name, tooltip)
	local b = PanelButton(row, 200, 22)
	b:SetText(text)
	b:SetScript("OnClick", function() onClick() end)
	PlaceControl(b, row)
	ui.buttons[name] = b
end

local function Checkbox(key, name, default, tooltip)
	local row = NewRow(ART.rowHeight, name, tooltip)
	local cb = Try("CheckButton", row, ART.checkbox[1]) or Try("CheckButton", row, ART.checkbox[2])
	if not cb then -- fallback: Blizzard's classic checkbox textures
		cb = CreateFrame("CheckButton", nil, row)
		cb:SetNormalTexture("Interface\\Buttons\\UI-CheckBox-Up")
		cb:SetPushedTexture("Interface\\Buttons\\UI-CheckBox-Down")
		cb:SetHighlightTexture("Interface\\Buttons\\UI-CheckBox-Highlight", "ADD")
		cb:SetCheckedTexture("Interface\\Buttons\\UI-CheckBox-Check")
	end
	cb:SetSize(30, 29)
	cb:SetScript("OnClick", function(self)
		local on = self:GetChecked() and true or false
		PlayClick(on)
		UserSet(key, on)
	end)
	PlaceControl(cb, row)
	AddControl(key, "check", name, default, cb, function(v) cb:SetChecked(v and true or false) end)
end

local function Slider(key, name, default, tooltip, format)
	local lim = TT.limits[key]
	local row = NewRow(ART.rowHeight, name, tooltip)
	local M = MinimalSliderWithSteppersMixin
	local sw = Try("Frame", row, ART.slider)
	local Set
	if sw and sw.Init and sw.RegisterCallback and sw.SetValue and M and M.Event and M.Label then
		sw:SetWidth(250)
		-- formatters: label -> function(value) (MinimalSliderWithSteppersMixin:FormatValue)
		local steps = math.floor((lim[2] - lim[1]) / lim[3] + 0.5)
		sw:Init(Saved(key) or default, lim[1], lim[2], steps, { [M.Label.Right] = format })
		sw:RegisterCallback(M.Event.OnValueChanged, function(_, v) UserSet(key, v) end, row)
		Set = function(v) sw:SetValue(v) end
		AddTip(sw.Slider, row)
	else -- fallback: a plain slider bar, the value written to its right
		if sw and sw.Hide then sw:Hide() end
		sw = CreateFrame("Slider", nil, row)
		sw:SetOrientation("HORIZONTAL")
		sw:SetSize(212, 17)
		sw:SetThumbTexture("Interface\\Buttons\\UI-SliderBar-Button-Horizontal")
		sw:SetMinMaxValues(lim[1], lim[2])
		sw:SetValueStep(lim[3])
		if sw.SetObeyStepOnDrag then sw:SetObeyStepOnDrag(true) end
		local track = sw:CreateTexture(nil, "BACKGROUND")
		track:SetColorTexture(0, 0, 0, 0.6)
		track:SetPoint("LEFT", sw, "LEFT", 0, 0)
		track:SetPoint("RIGHT", sw, "RIGHT", 0, 0)
		track:SetHeight(6)
		local txt = sw:CreateFontString(nil, "OVERLAY", ART.label)
		txt:SetPoint("LEFT", sw, "RIGHT", 10, 0)
		sw:SetScript("OnValueChanged", function(_, v)
			txt:SetText(format(v))
			UserSet(key, v)
		end)
		Set = function(v)
			sw:SetValue(v)
			txt:SetText(format(v))
		end
	end
	PlaceControl(sw, row)
	AddControl(key, "slider", name, default, sw, Set)
	ui.controls[key].min, ui.controls[key].max, ui.controls[key].step, ui.controls[key].format = lim[1], lim[2], lim[3], format
end

local function LabelOf(choices, value)
	for _, l in ipairs(choices) do if l[1] == value then return l[2] end end
	return tostring(value)
end

local function Dropdown(key, name, default, tooltip, choices)
	local row = NewRow(ART.rowHeight, name, tooltip)
	local dd = Try("DropdownButton", row, ART.dropdown)
	local Set
	if dd and dd.SetupMenu then
		dd:SetWidth(200)
		dd:SetupMenu(function(_, root)
			for _, l in ipairs(choices) do
				root:CreateRadio(l[2], function(v) return Saved(key) == v end, function(v) UserSet(key, v) end, l[1])
			end
		end)
		-- the shown text comes from the selected radio: rebuild after a change
		Set = function() if dd.GenerateMenu then dd:GenerateMenu() end end
	else -- fallback: a button that steps to the next choice on each click
		if dd and dd.Hide then dd:Hide() end
		dd = PanelButton(row, 200, 22)
		dd:SetScript("OnClick", function()
			local cur, nextValue = Saved(key), choices[1][1]
			for i, l in ipairs(choices) do
				if l[1] == cur then nextValue = (choices[i + 1] or choices[1])[1] end
			end
			UserSet(key, nextValue)
		end)
		Set = function(v) dd:SetText(LabelOf(choices, v)) end
	end
	PlaceControl(dd, row)
	AddControl(key, "dropdown", name, default, dd, Set)
	ui.controls[key].choices = choices
end

-- the page frame: title, divider, Defaults button and a scrolling list
local function NewPanel()
	local panel = CreateFrame("Frame") -- the Settings window parents it to its canvas
	panel:Hide()
	ui.panel = panel

	local title = panel:CreateFontString(nil, "ARTWORK", ART.title)
	title:SetPoint("TOPLEFT", panel, "TOPLEFT", 7, -22)
	title:SetText("Taxi Time")

	local line = panel:CreateTexture(nil, "ARTWORK")
	if C_Texture and C_Texture.GetAtlasInfo and C_Texture.GetAtlasInfo(ART.divider) and line.SetAtlas then
		line:SetAtlas(ART.divider, true)
		line:SetPoint("TOP", panel, "TOP", 0, -50)
	else -- fallback: a thin light line
		line:SetColorTexture(1, 1, 1, 0.15)
		line:SetHeight(1)
		line:SetPoint("TOPLEFT", panel, "TOPLEFT", 7, -50)
		line:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -36, -50)
	end

	local def = PanelButton(panel, 96, 22)
	def:SetText("Defaults")
	def:SetPoint("TOPRIGHT", panel, "TOPRIGHT", -36, -16)
	def:SetScript("OnClick", function()
		ResetToDefaults()
		TT.Print("options set back to their defaults (colours kept).")
	end)
	def.ttName, def.ttText = "Defaults", "Set the options on this page back to their defaults. Colours and your recorded flights are kept."
	AddTip(def, def)
	ui.defaults = def

	local scroll = Try("ScrollFrame", panel, ART.scroll)
	if not scroll then -- fallback: scrolls with the mouse wheel, no bar
		scroll = CreateFrame("ScrollFrame", nil, panel)
		scroll:EnableMouseWheel(true)
		scroll:SetScript("OnMouseWheel", function(self, delta)
			local max = self:GetVerticalScrollRange() or 0
			local v = math.max(0, math.min(max, (self:GetVerticalScroll() or 0) - delta * 40))
			self:SetVerticalScroll(v)
		end)
	end
	scroll:SetPoint("TOPLEFT", panel, "TOPLEFT", 0, -56)
	scroll:SetPoint("BOTTOMRIGHT", panel, "BOTTOMRIGHT", -24, 4)
	local content = CreateFrame("Frame", nil, scroll)
	content:SetSize(600, 1)
	scroll:SetScrollChild(content)
	scroll:HookScript("OnSizeChanged", function(_, w)
		if type(w) == "number" and w > 0 then content:SetWidth(w) end
	end)
	ui.scroll, ui.content = scroll, content

	-- Settings window hooks (called through securecallfunction) + our own show
	panel.OnRefresh = RefreshAll
	panel.OnDefault = ResetToDefaults
	panel.OnCommit = function() end -- every change is saved at once
	panel:SetScript("OnShow", RefreshAll)
	return panel
end

local function Build()
	local panel = NewPanel()
	local d = TT.defaultsBar

	Header("Bar")
	Checkbox("locked", "Lock bar", d.locked, "Unlock to show a test bar you can drag to a new place.")
	Button("Bar position", "Reset", function()
		TT.Bar:ResetPosition()
		TT.Print("bar position reset.")
	end, "Put the bar back in its default place.")
	Button("Test bar", "Show / hide", function() TT.Bar:ToggleTest() end,
		"Show a test bar to see your changes (hidden during a flight).")
	Slider("width", "Width", d.width, "Length of the bar.", function(v) return tostring(math.floor(v + 0.5)) end)
	Slider("scale", "Scale", d.scale, "Size of the whole bar: frame, text and creature.",
		function(v) return math.floor(v * 100 + 0.5) .. "%" end)
	Checkbox("showTotals", "Show totals under the bar", d.showTotals, "Gold spent and time flown by this character.")
	Checkbox("showRank", "Show rank under the bar", d.showRank,
		"Your Taxi Time rank, from minutes flown and flights. /tt rank for details.")

	Header("Colours")
	Button("Flying bar colour", "Choose...", function() PickColor("colorFlight") end,
		"Fill colour on a route with a recorded time.")
	Button("Recording bar colour", "Choose...", function() PickColor("colorRecord") end,
		"Fill colour on a route's first flight, while its time is recorded.")
	Button("Reset colours", "Reset", function()
		TT.SetOption("colorFlight", nil)
		TT.SetOption("colorRecord", nil)
	end, "Back to the default blue and orange.")

	Header("Flying creature")
	Dropdown("flyer", "Creature", d.flyer,
		"Automatic matches the flight master. A creature picked with /tt flyer for one flight master still wins.",
		FLYER_LABELS)

	Header("Landing")
	Checkbox("landSound", "Play a sound when you land", true,
		"A short Blizzard ping when a flight lands normally. Follows the game's Sound Effects volume.")
	Checkbox("landSparkle", "Sparkle when you land", d.landSparkle,
		"A small sparkle where the creature stops on the bar.")

	Header("Flight map")
	Checkbox("tooltip", "Show times on the flight map", true, "Adds the flight time to the flight map's tooltips.")

	Header("Milestones")
	Checkbox("milestoneChat", "Announce milestones in chat", true,
		"A chat line when you reach a Taxi Time milestone. They are still counted when this is off.")
	Button("Milestones", "Show", function()
		if TT.ShowMilestones then TT.ShowMilestones() end
	end, "Your Taxi Time milestones: reached ones and how far you are with the rest. Also /tt milestones.")

	ui.content:SetHeight(ui.y + 16)

	local cat = Settings.RegisterCanvasLayoutCategory(panel, "Taxi Time")
	Settings.RegisterAddOnCategory(cat)
	return cat
end

-- called once from Core's ADDON_LOADED, after InitDB and Bar:Create
function TT.InitOptions()
	if category then return end
	if not (Settings and Settings.RegisterCanvasLayoutCategory and Settings.RegisterAddOnCategory) then
		return -- no panel on this client; the slash commands still work
	end
	refreshing = true -- building: the controls' first values are not user changes
	local ok, result = pcall(Build)
	refreshing = false
	if ok and result then
		category = result
		RefreshAll()
	else
		ui.controls, ui.buttons, ui.headers = {}, {}, {}
		if ui.panel then ui.panel:Hide() end
		TT.Print("the options panel could not be built (" .. tostring(result) .. "); /tt commands still work.")
	end
end

-- /tt options
function TT.OpenOptions()
	if not (category and Settings and Settings.OpenToCategory) then
		TT.Print("the options panel is not available on this client; see /tt help.")
		return
	end
	local id = category.GetID and category:GetID() or category.ID
	Settings.OpenToCategory(id)
end
