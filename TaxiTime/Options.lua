-- Taxi Time: Options.lua
-- The options panel in Blizzard's own Settings window (Options > AddOns >
-- Taxi Time), built only from Blizzard's controls, and TT.SetOption: the one
-- path the panel and the slash commands use to change a setting.
--
-- API checked against Blizzard's UI source (github.com/Gethe/wow-ui-source,
-- Blizzard_Settings_Shared/Blizzard_Settings.lua, Blizzard_SettingControls.lua)
-- and warcraft.wiki.gg "Settings API" / "Using the ColorPickerFrame".
-- Interface 16001 (WoW Forever) runs the modern client; every call is still
-- checked, so a missing one only loses the panel, never the addon.

local ADDON, TT = ...

local category          -- our Settings category (nil = no panel on this client)
local settings = {}     -- option key -> Blizzard setting object (keeps the panel in sync)
local syncing = false   -- true while we push a slash-command change into the panel

------------------------------------------------------------------------
-- Options: where each one is saved and what applies it live
------------------------------------------------------------------------

-- tbl: "bar" = TaxiTimeDB.bar, "db" = TaxiTimeDB
local OPTIONS = {
	locked     = { tbl = "bar", kind = "boolean", apply = function(v) TT.Bar:SetLocked(v) end },
	width      = { tbl = "bar", kind = "number", apply = function() TT.Bar:ApplySize() end },
	scale      = { tbl = "bar", kind = "number", apply = function() TT.Bar:ApplyScale() end },
	showTotals = { tbl = "bar", kind = "boolean", apply = function(v) TT.Bar:SetShowTotals(v) end },
	flyer      = { tbl = "bar", kind = "string", apply = function() TT.RefreshFlyer() end },
	tooltip    = { tbl = "db", kind = "boolean" }, -- read on each flight-map hover
	landSound  = { tbl = "db", kind = "boolean", apply = function(v) if v then TT.Bar:PlayLandSound() end end }, -- on = preview once
	landSparkle = { tbl = "bar", kind = "boolean" }, -- read at each landing
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

-- Saves an option, applies it at once and shows it in the panel.
-- Colours: value nil = back to the default. Returns true if it was taken.
function TT.SetOption(key, value)
	local o = OPTIONS[key]
	if not o or not TT.db then return false end
	local clean = Clean(key, value)
	if clean == nil and o.kind ~= "color" then return false end
	local tbl = o.tbl == "db" and TT.db or TT.db.bar
	-- push to the panel BEFORE writing the table: the Blizzard setting reads
	-- this same table and only tells its checkbox/slider when the value differs
	local s = settings[key]
	if s and not syncing and s.SetValue then
		syncing = true
		pcall(s.SetValue, s, clean)
		syncing = false
	end
	tbl[key] = clean
	if o.apply then o.apply(clean) end
	return true
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
-- The panel
------------------------------------------------------------------------

local FLYER_LABELS = {
	{ "auto", "Automatic (by flight master)" },
	{ "gryphon", "Gryphon" },
	{ "wyvern", "Wind rider" },
	{ "bat", "Bat" },
	{ "hippogryph", "Hippogryph" },
	{ "none", "None (no creature)" },
}

local function Build()
	local S = Settings
	local cat, layout = S.RegisterVerticalLayoutCategory("Taxi Time")
	if not layout and SettingsPanel and SettingsPanel.GetLayout then layout = SettingsPanel:GetLayout(cat) end
	local VT = S.VarType or { Boolean = "boolean", Number = "number", String = "string" }

	local function Header(text)
		if layout and CreateSettingsListSectionHeaderInitializer then
			layout:AddInitializer(CreateSettingsListSectionHeaderInitializer(text))
		end
	end

	local function Button(name, text, onClick, tooltip)
		if layout and CreateSettingsButtonInitializer then
			layout:AddInitializer(CreateSettingsButtonInitializer(name, text, onClick, tooltip, true))
		end
	end

	-- a Blizzard setting stored straight in our saved table
	local function Register(key, varType, name, default)
		local o = OPTIONS[key]
		local tbl = o.tbl == "db" and TT.db or TT.db.bar
		local s = S.RegisterAddOnSetting(cat, "TaxiTime_" .. key, key, tbl, varType, name, default)
		settings[key] = s
		if s and s.SetValueChangedCallback then
			s:SetValueChangedCallback(function(_, value)
				if not syncing then TT.SetOption(key, value) end
			end)
		end
		return s
	end

	local function Checkbox(key, name, default, tooltip)
		local s = Register(key, VT.Boolean, name, default)
		if s and S.CreateCheckbox then S.CreateCheckbox(cat, s, tooltip) end
	end

	local function Slider(key, name, default, tooltip, format)
		local lim = TT.limits[key]
		local s = Register(key, VT.Number, name, default)
		if not (s and S.CreateSlider and S.CreateSliderOptions) then return end
		local opts = S.CreateSliderOptions(lim[1], lim[2], lim[3])
		if opts.SetLabelFormatter and MinimalSliderWithSteppersMixin and MinimalSliderWithSteppersMixin.Label then
			opts:SetLabelFormatter(MinimalSliderWithSteppersMixin.Label.Right, format)
		end
		S.CreateSlider(cat, s, opts, tooltip)
	end

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
	local fs = Register("flyer", VT.String, "Creature", d.flyer)
	if fs and S.CreateDropdown and S.CreateControlTextContainer then
		S.CreateDropdown(cat, fs, function()
			local c = S.CreateControlTextContainer()
			for _, l in ipairs(FLYER_LABELS) do c:Add(l[1], l[2]) end
			return c:GetData()
		end, "Automatic matches the flight master. A creature picked with /tt flyer for one flight master still wins.")
	end

	Header("Landing")
	Checkbox("landSound", "Play a sound when you land", true,
		"A short Blizzard ping when a flight lands normally. Follows the game's Sound Effects volume.")
	Checkbox("landSparkle", "Sparkle when you land", d.landSparkle,
		"A small sparkle where the creature stops on the bar.")

	Header("Flight map")
	Checkbox("tooltip", "Show times on the flight map", true, "Adds the flight time to the flight map's tooltips.")

	S.RegisterAddOnCategory(cat)
	return cat
end

-- called once from Core's ADDON_LOADED, after InitDB and Bar:Create
function TT.InitOptions()
	if category then return end
	if not (Settings and Settings.RegisterVerticalLayoutCategory and Settings.RegisterAddOnSetting
		and Settings.RegisterAddOnCategory) then
		return -- no panel on this client; the slash commands still work
	end
	local ok, result = pcall(Build)
	if ok then
		category = result
	else
		settings = {}
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
