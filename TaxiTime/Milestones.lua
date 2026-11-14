-- Taxi Time: Milestones.lua
-- Light, finishable goals worked out from data the addon already keeps
-- (totals per character, recorded routes per account), plus one small new
-- value: the creatures flown (TaxiTimeDB.flownKinds). Saved per milestone is
-- only WHEN it was first reached, so nothing is announced twice and an earned
-- one stays earned. Always called "milestones" (our own names, never the
-- game's achievement look or wording). Plan: plans\milestones\plan.md.

local ADDON, TT = ...

local GOLD = 10000 -- copper per gold

-- scope "char" = this character's totals (TaxiTimeCharDB.milestones),
-- "all" = account data shared by every character (TaxiTimeDB.milestones)
local MILESTONES = {
	{ id = "fl1",    name = "Boarding Pass",           goal = "your first flight",       scope = "char", stat = "flights", need = 1 },
	{ id = "fl10",   name = "Punch Card",              goal = "10 flights",              scope = "char", stat = "flights", need = 10 },
	{ id = "fl100",  name = "Loyalty Stamp",           goal = "100 flights",             scope = "char", stat = "flights", need = 100 },
	{ id = "fl500",  name = "Seat 1A Is Yours",        goal = "500 flights",             scope = "char", stat = "flights", need = 500 },
	{ id = "hr1",    name = "First Hour Up",           goal = "1 hour in the air",       scope = "char", stat = "seconds", need = 3600 },
	{ id = "hr10",   name = "Ten Hours of Clouds",     goal = "10 hours in the air",     scope = "char", stat = "seconds", need = 36000 },
	{ id = "hr24",   name = "A Whole Day Up There",    goal = "24 hours in the air",     scope = "char", stat = "seconds", need = 86400 },
	{ id = "g1",     name = "Pocket Change",           goal = "1 gold spent on flights", scope = "char", stat = "copper",  need = 1 * GOLD },
	{ id = "g10",    name = "Fare Payer",              goal = "10 gold spent",           scope = "char", stat = "copper",  need = 10 * GOLD },
	{ id = "g100",   name = "Flight Masters Love You", goal = "100 gold spent",          scope = "char", stat = "copper",  need = 100 * GOLD },
	{ id = "rt10",   name = "Getting Around",          goal = "10 different routes",     scope = "all",  stat = "routes",  need = 10 },
	{ id = "rt25",   name = "Route Collector",         goal = "25 different routes",     scope = "all",  stat = "routes",  need = 25 },
	{ id = "rt50",   name = "Map Full of Lines",       goal = "50 different routes",     scope = "all",  stat = "routes",  need = 50 },
	{ id = "same10", name = "The Usual",               goal = "one route flown 10 times", scope = "all", stat = "same",    need = 10 },
	{ id = "same25", name = "Could Fly It Blind",      goal = "one route flown 25 times", scope = "all", stat = "same",    need = 25 },
	{ id = "long",   name = "Long Haul",               goal = "a route of 8 minutes or more", scope = "all", stat = "longest", need = 480 },
	{ id = "flock",  name = "Whole Flock",             goal = "all 4 creatures (needs both factions)", scope = "all", stat = "kinds", need = 4 },
}
TT.MILESTONE_COUNT = #MILESTONES

-- creatures for "Whole Flock" (same keys as Core's FLYER_KINDS, Kiwi never counts)
local KINDS = { "gryphon", "wyvern", "bat", "hippogryph" }
local FACTION_KIND = { Alliance = "gryphon", Horde = "wyvern" } -- no kind = the faction's creature (as Bar.lua)

-- Look of the list window, all in one place. Blizzard's own ready-check tick,
-- referenced by its FrameXML constant (fallback: the same path written out);
-- if the texture can't be set, a text tick is shown instead.
local ART = {
	tick = READY_CHECK_READY_TEXTURE or "Interface\\RaidFrame\\ReadyCheck-Ready",
	backdrop = {
		bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
		edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
		tile = true, tileSize = 32, edgeSize = 24,
		insets = { left = 6, right = 6, top = 6, bottom = 6 },
	},
	fontTitle = "GameFontNormal",
	fontSub = "GameFontHighlightSmall",
	fontSection = "GameFontNormalSmall",
	fontDone = "GameFontHighlight",
	fontOpen = "GameFontDisable",
	fontGoalDone = "GameFontHighlightSmall",
	fontGoalOpen = "GameFontDisableSmall",
}
local ROW_H = 18
local WIDTH = 380

local startNote -- number of milestones marked quietly on this load (one line after login)

local function Num(v)
	v = tonumber(v) or 0
	if v ~= v or v < 0 or v == math.huge then return 0 end
	return v
end

-- the two saved tables (made valid by TT.MilestoneInit)
local function Saved(scope)
	if scope == "char" then return TaxiTimeCharDB and TaxiTimeCharDB.milestones end
	return TT.db and TT.db.milestones
end

-- everything the milestones read, worked out once per check
local function Stats()
	local t = TT.charTotals or {}
	local st = { flights = Num(t.flights), seconds = Num(t.seconds), copper = Num(t.copper),
		routes = 0, same = 0, longest = 0, kinds = 0, kindList = {} }
	local routes = TT.db and TT.db.routes
	if type(routes) == "table" then
		for _, r in pairs(routes) do
			if type(r) == "table" and type(r.time) == "number" and r.time == r.time and r.time > 0 then
				st.routes = st.routes + 1
				if r.time > st.longest and r.time < math.huge then st.longest = r.time end
				local c = Num(r.count)
				if c > st.same then st.same = c end
			end
		end
	end
	local flown = TT.db and TT.db.flownKinds
	if type(flown) == "table" then
		for _, k in ipairs(KINDS) do
			if flown[k] == true then
				st.kinds = st.kinds + 1
				st.kindList[#st.kindList + 1] = TT.FLYER_KINDS and TT.FLYER_KINDS[k] or k
			end
		end
	end
	return st
end

local function Reached(m, st)
	return st[m.stat] >= m.need
end

-- progress text for a milestone not reached yet
local function Progress(m, st)
	local v = st[m.stat]
	if m.stat == "seconds" then
		return TT.FormatLong(v) .. " of " .. TT.FormatLong(m.need)
	elseif m.stat == "copper" then
		return string.format("%dg of %dg", math.floor(v / GOLD), m.need / GOLD)
	elseif m.stat == "longest" then
		return TT.FormatTime(v) .. " of " .. TT.FormatTime(m.need)
	elseif m.stat == "kinds" then
		local s = string.format("%d/%d", v, m.need)
		if #st.kindList > 0 then s = s .. ": " .. table.concat(st.kindList, ", ") end
		return s
	end
	return string.format("%d/%d", math.floor(v), m.need)
end

-- the list for the window and tests: { m, earned, when (saved time, 0 = before
-- milestones were counted, nil = reached but not saved yet), progress }
function TT.MilestoneList()
	local st = Stats()
	local list, have = {}, 0
	for _, m in ipairs(MILESTONES) do
		local saved = Saved(m.scope)
		local when = saved and saved[m.id]
		local earned = when ~= nil or Reached(m, st)
		if earned then have = have + 1 end
		list[#list + 1] = { m = m, earned = earned, when = when, progress = (not earned) and Progress(m, st) or nil }
	end
	return list, have
end

-- from Core's InitDB (TT.db and TT.charTotals are set): makes the saved tables
-- valid; on the first load after the update everything already reached is
-- marked quietly (time 0) and one summary line is queued for after login
function TT.MilestoneInit()
	local db, c = TaxiTimeDB, TaxiTimeCharDB
	local firstChar = type(c.milestones) ~= "table"
	local firstAll = type(db.milestones) ~= "table"
	if firstChar then c.milestones = {} end
	if firstAll then db.milestones = {} end
	for _, tbl in ipairs({ c.milestones, db.milestones }) do
		for k, v in pairs(tbl) do
			if type(v) ~= "number" or v ~= v then tbl[k] = nil end -- only our own milestone marks
		end
	end
	if type(db.flownKinds) ~= "table" then db.flownKinds = {} end
	startNote = nil
	if not (firstChar or firstAll) then return end
	local st = Stats()
	local quiet = 0
	for _, m in ipairs(MILESTONES) do
		local first = (m.scope == "char" and firstChar) or (m.scope == "all" and firstAll)
		local saved = Saved(m.scope)
		if first and saved[m.id] == nil and Reached(m, st) then
			saved[m.id] = 0
			quiet = quiet + 1
		end
	end
	if quiet > 0 then startNote = true end
end

-- once, after the first PLAYER_ENTERING_WORLD (next to the rank's start line)
function TT.MilestoneStartNote()
	if not startNote then return end
	startNote = nil
	if not (TT.db and TT.db.milestoneChat) then return end
	local _, have = TT.MilestoneList()
	TT.Print(string.format("you already have %d of %d milestones from your flying so far. (/tt milestones)", have, #MILESTONES))
end

local frame -- the list window (built on first use)
local Refresh

-- after every landing (Core EndFlight, after the rank check)
function TT.CheckMilestones()
	if type(TaxiTimeCharDB) ~= "table" or not TT.db then return end
	local st = Stats()
	local new = {}
	for _, m in ipairs(MILESTONES) do
		local saved = Saved(m.scope)
		if saved and saved[m.id] == nil and Reached(m, st) then
			saved[m.id] = time()
			new[#new + 1] = m
		end
	end
	if #new > 0 then
		startNote = nil -- the new line says enough
		if TT.db.milestoneChat then
			if #new == 1 then
				TT.Print(string.format("milestone - %s (%s). (/tt milestones)", new[1].name, new[1].goal))
			else
				local names = {}
				for i, m in ipairs(new) do names[i] = m.name end
				TT.Print(string.format("%d milestones - %s. (/tt milestones)", #new, table.concat(names, ", ")))
			end
		end
	end
	if frame and frame:IsShown() then Refresh() end
	return #new
end

-- at take-off (Core BeginFlight, new flights only), when the creature was the
-- automatic pick (not one chosen with /tt flyer or the Options panel).
-- kind nil = the faction's creature, as the bar shows it.
function TT.NoteFlownKind(kind)
	if not (TT.db and type(TT.db.flownKinds) == "table") then return end
	if kind == nil then kind = FACTION_KIND[UnitFactionGroup and UnitFactionGroup("player") or ""] end
	for _, k in ipairs(KINDS) do
		if k == kind then TT.db.flownKinds[k] = true return end
	end
end

------------------------------------------------------------------------
-- The list window (/tt milestones, Options button)
------------------------------------------------------------------------

local function WhenText(when)
	if when == 0 then return "Reached before milestones were counted." end
	if type(when) == "number" then return "Reached " .. date("%Y-%m-%d", when) .. "." end
	return "Reached."
end

local function RowEnter(row)
	if not (GameTooltip and row.item) then return end
	local it = row.item
	GameTooltip:SetOwner(row, "ANCHOR_RIGHT")
	GameTooltip:SetText(it.m.name)
	GameTooltip:AddLine(it.m.goal .. (it.m.scope == "all" and " (all characters)" or " (this character)"), 1, 1, 1)
	if it.earned then
		GameTooltip:AddLine(WhenText(it.when), 0.6, 0.6, 0.6)
	else
		GameTooltip:AddLine("So far: " .. it.progress, 0.6, 0.6, 0.6)
	end
	GameTooltip:Show()
end

local function RowLeave()
	if GameTooltip then GameTooltip:Hide() end
end

local function MakeRow(parent, y)
	local row = CreateFrame("Frame", nil, parent)
	row:SetSize(WIDTH - 32, ROW_H)
	row:SetPoint("TOPLEFT", 16, y)
	row:EnableMouse(true)
	row:SetScript("OnEnter", RowEnter)
	row:SetScript("OnLeave", RowLeave)
	row.tick = row:CreateTexture(nil, "ARTWORK")
	row.tick:SetSize(14, 14)
	row.tick:SetPoint("LEFT", 0, 0)
	row.mark = row:CreateFontString(nil, "OVERLAY", ART.fontOpen) -- text tick / dash
	row.mark:SetPoint("CENTER", row.tick, "CENTER", 0, 0)
	row.name = row:CreateFontString(nil, "OVERLAY", ART.fontOpen)
	row.name:SetPoint("LEFT", 20, 0)
	row.goal = row:CreateFontString(nil, "OVERLAY", ART.fontGoalOpen)
	row.goal:SetPoint("RIGHT", 0, 0)
	row.goal:SetJustifyH("RIGHT")
	return row
end

local function Build()
	local f = CreateFrame("Frame", "TaxiTimeMilestonesFrame", UIParent, "BackdropTemplate")
	local rows = #MILESTONES + 2 -- two section lines
	f:SetSize(WIDTH, 64 + rows * ROW_H + 16)
	f:SetPoint("CENTER")
	f:SetFrameStrata("DIALOG")
	if f.SetBackdrop then f:SetBackdrop(ART.backdrop) end
	f:EnableMouse(true)
	f:SetMovable(true)
	f:RegisterForDrag("LeftButton")
	f:SetScript("OnDragStart", f.StartMoving)
	f:SetScript("OnDragStop", f.StopMovingOrSizing)
	f.title = f:CreateFontString(nil, "OVERLAY", ART.fontTitle)
	f.title:SetPoint("TOP", 0, -14)
	f.title:SetText("Taxi Time milestones")
	f.sub = f:CreateFontString(nil, "OVERLAY", ART.fontSub)
	f.sub:SetPoint("TOP", 0, -32)
	local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
	close:SetPoint("TOPRIGHT", -4, -4)
	f.rows, f.sections = {}, {}
	local y = -54
	local lastScope
	for i, m in ipairs(MILESTONES) do
		if m.scope ~= lastScope then
			local sec = f:CreateFontString(nil, "OVERLAY", ART.fontSection)
			sec:SetPoint("TOPLEFT", 16, y - 2)
			sec:SetText(m.scope == "char" and "This character" or "All characters")
			f.sections[#f.sections + 1] = sec
			y = y - ROW_H
			lastScope = m.scope
		end
		f.rows[i] = MakeRow(f, y)
		y = y - ROW_H
	end
	if UISpecialFrames then table.insert(UISpecialFrames, "TaxiTimeMilestonesFrame") end -- Esc closes it
	return f
end

Refresh = function()
	local list, have = TT.MilestoneList()
	local who = UnitName and UnitName("player")
	frame.sub:SetText(string.format("%d of %d%s", have, #MILESTONES, who and (" - this character: " .. who) or ""))
	for i, it in ipairs(list) do
		local row = frame.rows[i]
		row.item = it
		row.name:SetFontObject(it.earned and ART.fontDone or ART.fontOpen)
		row.name:SetText(it.m.name)
		row.goal:SetFontObject(it.earned and ART.fontGoalDone or ART.fontGoalOpen)
		row.goal:SetText(it.earned and it.m.goal or (it.m.goal .. "  (" .. it.progress .. ")"))
		local ticked = false
		if it.earned then ticked = row.tick:SetTexture(ART.tick) and true or false end
		if ticked then row.tick:Show() else row.tick:Hide() end
		row.mark:SetText(ticked and "" or (it.earned and "x" or "-"))
	end
end

-- /tt milestones and the Options button: opens the window, or closes it if open
local opened = false -- shown by us (a new frame starts shown before its first Refresh)
function TT.ShowMilestones()
	if not frame then
		frame = Build()
		frame:SetScript("OnHide", function() opened = false end)
	end
	if opened and frame:IsShown() then
		frame:Hide()
		opened = false
		return
	end
	Refresh()
	frame:Show()
	opened = true
end

-- for tests: the window (nil before first use)
function TT.MilestoneFrame() return frame end
