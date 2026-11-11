-- Taxi Time: Core.lua
-- Flight detection (start node, destination, take-off, landing), route storage
-- in SavedVariables and the /tt slash command. The bar itself lives in Bar.lua.

local addonName, TT = ...
TT.name = addonName

------------------------------------------------------------------------
-- Settings and constants
------------------------------------------------------------------------

local TICK = 0.25              -- seconds between UnitOnTaxi checks while pending/flying
local TAKEOFF_TIMEOUT = 10     -- seconds after the click to wait for take-off
local MIN_FLIGHT = 5           -- flights shorter than this are never recorded
local SHORT_RATIO = 0.8        -- known route: shorter than 80% of the time = cut short
local LAND_DIST = 0.05         -- first flight: max distance (map units 0..1) from destination
local RESUME_MAX_AGE = 3600    -- ignore a saved active flight older than this (seconds)
local COST_WINDOW = 5          -- seconds after take-off to wait for the fare's gold drop
local TIME_GAP = 2             -- a step longer than this (loading screen) is not counted as flown time
local STARTER_NOTE_DIFF = 5    -- first flight on a starter time: mention the starter time if off by more (s)
local EXPORT_VERSION = 1       -- /tt export format (the merge script in plans\starter-times checks it)
local EXPORT_MIN, EXPORT_MAX = 5, 3600 -- seconds; routes outside are left out (same as MIN_SEC/MAX_SEC in merge.lua)
local GOSSIP_WINDOW = 15       -- a flight without a map click this soon after talking to an NPC is that NPC's flight
local WATCH_TRIES = 8          -- control lost while idle: look for a taxi this many times, TICK apart

------------------------------------------------------------------------
-- Flying creature per start point (the bar's icon). Checked in this order:
-- the user's /tt flyer choice (TaxiTimeDB.flyers), NODE_FLYER, NPC_FLYER,
-- the Alliance-in-Kalimdor rule, else nil = the faction icon (as before).
-- The art for each kind is in Bar.lua (FLYER_ART).
------------------------------------------------------------------------

local FLYER_KINDS = { gryphon = "gryphon", wyvern = "wind rider", bat = "bat", hippogryph = "hippogryph" }
local FLYER_ALIASES = { windrider = "wyvern", wind = "wyvern", ["wind rider"] = "wyvern", hippo = "hippogryph" }

-- start taxi node ID -> kind. Empty: no node IDs sourced yet (add only checked ones)
local NODE_FLYER = {}

-- flight master NPC ID -> kind. Sources (warcraft.wiki.gg NPC pages, Wowhead links there):
--   4551 Michael Garrett <Bat Handler>, Undercity
--   2226 Karos Razok <Bat Handler>, The Sepulcher (Silverpine Forest)
--   2389 Zarise <Bat Handler>, Tarren Mill (Hillsbrad Foothills)
--   3838 Vesprystus <Hippogryph Master>, Rut'theran Village (Teldrassil)
--   3841 Caylais Moonfeather <Hippogryph Master>, Auberdine (Darkshore; the Classic ID)
--   4267 Daelyshia <Hippogryph Master>, Astranaar (Ashenvale)
-- Only the NPC ID part of a GUID is ever used (never the server or spawn parts).
local NPC_FLYER = {
	[4551] = "bat", [2226] = "bat", [2389] = "bat",
	[3838] = "hippogryph", [3841] = "hippogryph", [4267] = "hippogryph",
}

-- Kalimdor continent uiMapIDs: 12 (warcraft.wiki.gg UiMapID) and 1414 (Classic map IDs)
-- Rule from warcraft.wiki.gg "Flight path": Alliance flies hippogryphs in Kalimdor.
local KALIMDOR = { [12] = true, [1414] = true }

local DEFAULTS_BAR = {
	point = "TOP", relPoint = "TOP", x = 0, y = -160,
	width = 260, locked = true,
	showTotals = true,         -- gold/time totals line under the bar
	flyerStyle = "model",      -- "model" (the game's 3D creature) or "cartoon" (our sheets)
}

------------------------------------------------------------------------
-- State
------------------------------------------------------------------------

local state = "idle"     -- "idle" | "pending" | "flying"
local pending            -- route info between the click and take-off
local flight             -- the running flight
local nodeCache = {}     -- taxi slot index -> { nodeID, name, x, y }
local currentNode        -- the node the flight master stands at
local taxiMapID
local ticker
local loading = false    -- true between PLAYER_LEAVING_WORLD and PLAYER_ENTERING_WORLD (+1 s)
local lastGossip         -- { npcID, at }: last NPC talked to (for flights started from a talk option)
local taxiNpcID          -- NPC ID of the flight master whose map was opened last (nil if unknown)
local flyerSpot, flyerSpotName -- start point /tt flyer changes: node ID or "npc:<id>", and its name
TT.lastKey = nil         -- key of the last route flown (for /tt forget)

------------------------------------------------------------------------
-- Helpers
------------------------------------------------------------------------

local function Print(msg)
	DEFAULT_CHAT_FRAME:AddMessage("|cff33ccffTaxi Time:|r " .. tostring(msg))
end
TT.Print = Print

-- "1:32" from seconds
function TT.FormatTime(sec)
	sec = math.floor((sec or 0) + 0.5)
	if sec < 0 then sec = 0 end
	return string.format("%d:%02d", math.floor(sec / 60), sec % 60)
end

-- "Stormwind, Elwynn" -> "Stormwind"
function TT.ShortName(name)
	if not name then return "?" end
	return (name:match("^([^,]+)")) or name
end

-- "12m", "3h 12m", "123h" from seconds (flight time totals)
function TT.FormatLong(sec)
	sec = math.floor(sec or 0)
	if sec < 0 then sec = 0 end
	local h = math.floor(sec / 3600)
	local m = math.floor((sec % 3600) / 60)
	if h == 0 then return string.format("%dm", m) end
	if h < 100 then return string.format("%dh %dm", h, m) end
	return string.format("%dh", h)
end

-- copper -> gold/silver/copper with the game's coin icons (plain "1g 2s 3c" if not available)
function TT.FormatMoney(copper)
	copper = math.floor(copper or 0)
	if copper < 0 then copper = 0 end
	local f = (C_CurrencyInfo and C_CurrencyInfo.GetCoinTextureString) or GetCoinTextureString
	if f then
		local ok, s = pcall(f, copper, 10)
		if ok and type(s) == "string" and s ~= "" then return s end
	end
	local g, s, c = math.floor(copper / 10000), math.floor((copper % 10000) / 100), copper % 100
	if g > 0 then return string.format("%dg %ds %dc", g, s, c) end
	if s > 0 then return string.format("%ds %dc", s, c) end
	return string.format("%dc", c)
end

local function RouteKey(from, to)
	if from.nodeID and to.nodeID then
		return from.nodeID .. ">" .. to.nodeID
	end
	return "name:" .. (from.name or "?") .. ">" .. (to.name or "?")
end

-- Flights started without a map click (e.g. druid flights from a talk option)
-- use language-independent keys: "gossip:<npcID>:<startMapID>" or "zone:<startMapID>:<landMapID>".

local function PlayerMapID()
	if C_Map and C_Map.GetBestMapForUnit then
		local ok, id = pcall(C_Map.GetBestMapForUnit, "player")
		if ok and type(id) == "number" then return id end
	end
	return nil
end

-- zone name for the bar and chat (display only, never part of a key)
local function ZoneName()
	local z = GetZoneText and GetZoneText()
	if type(z) == "string" and z ~= "" then return z end
	z = GetSubZoneText and GetSubZoneText()
	if type(z) == "string" and z ~= "" then return z end
	return nil
end

-- "Creature-0-4372-1-1234-11798-0000ABCDEF" -> 11798
-- A secret GUID (Midnight/Forever secret values) gives nil: never worked around.
local function NpcIDFromGUID(guid)
	if issecretvalue and issecretvalue(guid) then return nil end
	if type(guid) ~= "string" then return nil end
	local parts = {}
	for p in guid:gmatch("[^%-]+") do parts[#parts + 1] = p end
	if (parts[1] == "Creature" or parts[1] == "Vehicle") and parts[6] then
		return tonumber(parts[6])
	end
	return nil
end

-- NPC ID of the unit we are talking to; read once per map/talk window, never polled
local function TalkingNpcID()
	if not UnitGUID then return nil end
	local ok, guid = pcall(UnitGUID, "npc")
	if not ok then return nil end
	local ok2, id = pcall(NpcIDFromGUID, guid)
	return ok2 and id or nil
end

-- true if the map (or one of its parents) is Kalimdor
local function InKalimdor(mapID)
	if not (C_Map and C_Map.GetMapInfo) then return false end
	for _ = 1, 10 do
		if not mapID then return false end
		if KALIMDOR[mapID] then return true end
		local ok, info = pcall(C_Map.GetMapInfo, mapID)
		if not ok or type(info) ~= "table" or not info.parentMapID or info.parentMapID == 0 then return false end
		mapID = info.parentMapID
	end
	return false
end

-- start point key for /tt flyer: the start node ID, else "npc:<id>", else nil
local function FlyerSpot(nodeID, npcID)
	if nodeID then return nodeID end
	if npcID then return "npc:" .. npcID end
	return nil
end

-- kind of creature ("gryphon", "wyvern", "bat", "hippogryph") or nil = faction icon
function TT.FlyerFor(spot, nodeID, npcID, mapID)
	local own = spot ~= nil and TT.db and TT.db.flyers and TT.db.flyers[spot]
	if own and FLYER_KINDS[own] then return own end
	if nodeID and NODE_FLYER[nodeID] then return NODE_FLYER[nodeID] end
	if npcID and NPC_FLYER[npcID] then return NPC_FLYER[npcID] end
	local faction = UnitFactionGroup and UnitFactionGroup("player")
	if faction == "Alliance" and InKalimdor(mapID) then return "hippogryph" end
	return nil
end

-- the only recorded "zone:" route from this start map, or nil (none or several)
local function OnlyZoneRoute(startMap)
	local prefix = "zone:" .. startMap .. ":"
	local found
	for key, route in pairs(TT.db.routes) do
		if type(key) == "string" and key:sub(1, #prefix) == prefix and type(route) == "table" and route.time then
			if found then return nil end
			found = key
		end
	end
	return found
end

-- totals table { copper, seconds, flights, since }: missing parts start at 0
local function FillTotals(t)
	if type(t) ~= "table" then t = {} end
	for _, k in ipairs({ "copper", "seconds", "flights" }) do
		if type(t[k]) ~= "number" then t[k] = 0 end
	end
	if type(t.since) ~= "number" then t.since = time() end
	return t
end

local function InitDB()
	if type(TaxiTimeDB) ~= "table" then TaxiTimeDB = {} end
	local db = TaxiTimeDB
	db.version = db.version or 1
	if type(db.routes) ~= "table" then db.routes = {} end
	if type(db.bar) ~= "table" then db.bar = {} end
	for k, v in pairs(DEFAULTS_BAR) do
		if db.bar[k] == nil then db.bar[k] = v end
	end
	if db.tooltip == nil then db.tooltip = true end -- flight-map tooltip line
	if type(db.flyers) ~= "table" then db.flyers = {} end -- /tt flyer choices: start point -> kind
	if type(TaxiTimeCharDB) ~= "table" then TaxiTimeCharDB = {} end
	db.totals = FillTotals(db.totals)                         -- all characters
	TaxiTimeCharDB.totals = FillTotals(TaxiTimeCharDB.totals) -- this character
	TT.accTotals = db.totals
	TT.charTotals = TaxiTimeCharDB.totals
	TT.db = db
	TT.defaultsBar = DEFAULTS_BAR
end

------------------------------------------------------------------------
-- Flight master map: start node and destinations
------------------------------------------------------------------------

local function ScanTaxiMap()
	wipe(nodeCache)
	currentNode = nil
	taxiMapID = GetTaxiMapID and GetTaxiMapID() or nil

	local CURRENT = (Enum and Enum.FlightPathState and Enum.FlightPathState.Current) or 0
	if taxiMapID and C_TaxiMap and C_TaxiMap.GetAllTaxiNodes then
		local ok, nodes = pcall(C_TaxiMap.GetAllTaxiNodes, taxiMapID)
		if ok and type(nodes) == "table" then
			for _, info in ipairs(nodes) do
				if info.slotIndex then
					local pos = info.position
					local entry = {
						nodeID = info.nodeID,
						name = info.name,
						x = pos and pos.x, y = pos and pos.y,
					}
					nodeCache[info.slotIndex] = entry
					if info.state == CURRENT then currentNode = entry end
				end
			end
		end
	end

	-- Fallback / fill-in with the old slot API
	local n = NumTaxiNodes and NumTaxiNodes() or 0
	for i = 1, n do
		local e = nodeCache[i]
		if not e then
			e = {}
			nodeCache[i] = e
		end
		e.name = e.name or TaxiNodeName(i)
		if TaxiNodeCost then
			-- listed fare in copper (no reputation discount); only works while the map is open
			local ok, cost = pcall(TaxiNodeCost, i)
			e.cost = (ok and type(cost) == "number") and cost or nil
		end
		if not currentNode and TaxiNodeGetType(i) == "CURRENT" then
			currentNode = e
		end
	end
end

------------------------------------------------------------------------
-- Starter times (StarterTimes.lua): TT.starterRaw[fromNodeID] = "toID:sec,toID:sec"
-- Only the start nodes that are looked up get parsed (into starterCache).
------------------------------------------------------------------------

local starterCache = {}  -- fromNodeID -> { [toNodeID] = seconds }

local function StarterTime(key)
	local raw = TT.starterRaw
	if type(raw) ~= "table" or type(key) ~= "string" then return nil end
	local from, to = key:match("^(%d+)>(%d+)$") -- "name:" keys never have a starter time
	if not from then return nil end
	from, to = tonumber(from), tonumber(to)
	local list = starterCache[from]
	if not list then
		list = {}
		local s = raw[from]
		if type(s) == "string" then
			for toID, sec in s:gmatch("(%d+):(%d+)") do
				list[tonumber(toID)] = tonumber(sec)
			end
		end
		starterCache[from] = list
	end
	local sec = list[to]
	return (sec and sec > 0) and sec or nil
end

-- Time (seconds) of a route key: the recorded time first, then the starter
-- list. Returns seconds, isEstimate (true = starter time), or nil.
function TT.GetRouteTime(key)
	local route = key and TT.db and TT.db.routes[key]
	if route and route.time then return route.time, false end
	local sec = StarterTime(key)
	if sec then return sec, true end
	return nil
end

-- Route key from the current node to a destination slot on the open flight map,
-- made with the same RouteKey the recorder uses; nil for the current node or no data
function TT.RouteKeyForSlot(slot)
	if not TT.db or not slot then return nil end
	if not currentNode or not nodeCache[slot] then ScanTaxiMap() end -- hovered before TAXIMAP_OPENED ran
	local from, to = currentNode, nodeCache[slot]
	if not (from and to and to.name) or from == to then return nil end
	return RouteKey(from, to)
end

------------------------------------------------------------------------
-- Ticker (only runs while a flight is pending or running)
------------------------------------------------------------------------

local CheckTaxi -- forward

local function StopTicker()
	if ticker then
		ticker:Cancel()
		ticker = nil
	end
end

local function StartTicker()
	if not ticker then
		ticker = C_Timer.NewTicker(TICK, function() CheckTaxi() end)
	end
end

------------------------------------------------------------------------
-- Totals: gold spent on flights and time flown (this character + all)
------------------------------------------------------------------------

local function AddTotals(field, amount)
	if not amount or amount <= 0 then return end
	if TT.charTotals then TT.charTotals[field] = TT.charTotals[field] + amount end
	if TT.accTotals then TT.accTotals[field] = TT.accTotals[field] + amount end
end

-- fare of the running flight: counted once, from the gold drop or the listed price
local function SetCostDone(f, copper)
	f.costDone = true
	AddTotals("copper", copper)
	if TaxiTimeCharDB.active then TaxiTimeCharDB.active.costDone = true end
end

-- no matching gold drop came: count the listed price (0 if unknown)
local function CostFallback(f)
	if f and not f.costDone then SetCostDone(f, f.listCost or 0) end
end

-- flown time since the last step; a long gap (loading screen) is skipped
local function StepTime(f)
	if not f or not f.lastTick then return end
	local now = GetTime()
	local d = now - f.lastTick
	f.lastTick = now
	if d > 0 and d <= TIME_GAP then AddTotals("seconds", d) end
end

-- flown seconds to 0.1 s, so the save holds no long floats. Only at landing
-- and when leaving the world (not per step: that would round 0.25 up each time).
local function RoundTotals()
	for _, t in ipairs({ TT.charTotals, TT.accTotals }) do
		if t and type(t.seconds) == "number" then
			t.seconds = math.floor(t.seconds * 10 + 0.5) / 10
		end
	end
end

-- PLAYER_MONEY: the first drop between 0 and the listed fare (from the click
-- until COST_WINDOW s after take-off) is the fare. Compared per event, so an
-- unrelated gain in between doesn't count; a bigger loss is rejected.
local function OnMoney()
	local w
	if state == "pending" and pending and not pending.cost then
		w = pending
	elseif state == "flying" and flight and not flight.costDone then
		w = flight
	end
	if not w or not w.lastMoney or not GetMoney then return end
	local now = GetMoney()
	local drop = w.lastMoney - now
	w.lastMoney = now
	if w.listCost and drop > 0 and drop <= w.listCost then
		if w == pending then
			pending.cost = drop -- added at take-off
		else
			SetCostDone(flight, drop)
		end
	end
end

------------------------------------------------------------------------
-- Take-off and landing
------------------------------------------------------------------------

local function SaveActive(f)
	TaxiTimeCharDB.active = {
		key = f.key, fromName = f.fromName, toName = f.toName,
		mapID = f.mapID, destX = f.destX, destY = f.destY,
		startWall = f.startWall,
		openDest = f.openDest or nil, zoneStart = f.zoneStart,
		noRecord = f.noRecord or nil,
		listCost = f.listCost,
		costDone = f.costDone or nil,
		flyer = f.flyer, flyerSpot = f.flyerSpot, flyerName = f.flyerName,
		lastSeen = time(),
	}
end

local function BeginFlight(info, elapsed)
	elapsed = elapsed or 0
	local refTime, isEstimate = TT.GetRouteTime(info.key) -- recorded, else starter
	local resumed = info.noRecord and true or false
	flight = {
		key = info.key, fromName = info.fromName, toName = info.toName,
		mapID = info.mapID, destX = info.destX, destY = info.destY,
		openDest = info.openDest and true or nil, -- no map click: destination name (and zone key) set at landing
		zoneStart = info.zoneStart,                -- "zone:" flight: start map ID
		startTime = GetTime() - elapsed,
		startWall = info.startWall or time(),
		known = refTime and true or false,
		refTime = refTime,                       -- time the bar counts down from
		estimate = isEstimate and true or false, -- refTime is a starter time
		aborted = false,
		noRecord = resumed, -- resumed after login/reload/disconnect
		listCost = info.listCost,
		lastMoney = info.lastMoney,
		costUntil = GetTime() + COST_WINDOW,
		costDone = (resumed and info.costDone) and true or nil,
		lastTick = GetTime(), -- flown time counts from here (never the offline part)
	}
	-- flying creature: worked out at take-off (still at the start); a resumed
	-- flight keeps the saved one (old saves without it: faction icon)
	flight.flyerSpot = info.flyerSpot or FlyerSpot(info.fromNode, info.npcID)
	flight.flyerName = info.flyerName or info.fromName
	local s = flight.flyerSpot -- after a resume only the spot is saved: node ID or "npc:<id>"
	flight.fromNode = info.fromNode or (type(s) == "number" and s or nil)
	flight.npcID = info.npcID or (type(s) == "string" and tonumber(s:match("^npc:(%d+)$")) or nil)
	if resumed then
		flight.flyer = FLYER_KINDS[info.flyer] and info.flyer or nil
	else
		flight.startMap = PlayerMapID()
		flight.flyer = TT.FlyerFor(flight.flyerSpot, info.fromNode, info.npcID, flight.startMap)
	end
	if flight.flyerSpot ~= nil then flyerSpot, flyerSpotName = flight.flyerSpot, flight.flyerName end
	pending = nil
	state = "flying"
	TT.lastKey = flight.key
	SaveActive(flight)
	StartTicker()

	if resumed then
		-- paid in the session where the flight started; if that session ended
		-- before the gold drop was seen, count the listed price now
		CostFallback(flight)
	else
		AddTotals("flights", 1)
		if info.cost then SetCostDone(flight, info.cost) end
	end

	TT.Bar:SetFlyer(flight.flyer)
	if flight.known then
		TT.Bar:StartFlight(flight.fromName, flight.toName, refTime, elapsed, flight.estimate)
	else
		TT.Bar:StartRecording(flight.fromName, flight.toName, elapsed)
	end
end

-- First flight only: did we land near the destination node?
local function LandedNearDest(f)
	if not (f.mapID and f.destX and f.destY and C_Map and C_Map.GetPlayerMapPosition) then
		return true -- can't tell: trust it
	end
	local ok, pos = pcall(C_Map.GetPlayerMapPosition, f.mapID, "player")
	if not ok or not pos then return true end
	local px, py = pos:GetXY()
	if not px or not py then return true end
	local dx, dy = px - f.destX, py - f.destY
	return (dx * dx + dy * dy) <= LAND_DIST * LAND_DIST
end

local function EndFlight()
	local f = flight
	flight = nil
	state = "idle"
	TaxiTimeCharDB.active = nil
	StopTicker()
	if not f then return end
	-- totals: every flight counts, recorded or not
	StepTime(f)
	CostFallback(f)
	RoundTotals()

	local noLandMap
	if f.openDest then
		-- flight without a map click: the landing zone names the destination
		local landName = ZoneName()
		if landName then f.toName = landName end
		if f.zoneStart then
			local landMap = PlayerMapID()
			if landMap then
				local key = "zone:" .. f.zoneStart .. ":" .. landMap
				if key ~= f.key then
					-- landed somewhere else than the one known route: a different route
					f.key, f.refTime, f.estimate = key, nil, false
				end
			else
				noLandMap = true
			end
		end
		TT.lastKey = f.key
	end

	local dur = GetTime() - f.startTime
	local route = TT.db.routes[f.key]
	local recTime = route and route.time
	local starterTime = (not recTime and f.estimate) and f.refTime or nil
	local oldTime = recTime or starterTime -- the starter time counts for the cut-short check
	local reason
	if f.noRecord then
		reason = "logged out or reloaded during the flight"
	elseif f.landedInLoad then
		-- the real landing moment is somewhere inside the loading screen
		reason = "landed during a loading screen"
	elseif f.aborted then
		reason = "early landing"
	elseif noLandMap then
		reason = "landing place unknown"
	elseif dur < MIN_FLIGHT then
		reason = "too short"
	elseif not LandedNearDest(f) and (not oldTime or dur < oldTime * SHORT_RATIO) then
		-- new route, or much shorter than the saved time: only trust it if we
		-- landed at the destination (a real faster time corrects a bad saved one)
		reason = recTime and "shorter than the recorded time"
			or starterTime and "shorter than the starter time"
			or "landed away from the destination"
	end

	if reason then
		if not recTime or f.noRecord then
			Print(string.format("Not recorded (%s): %s > %s", reason, TT.ShortName(f.fromName), TT.ShortName(f.toName)))
		end
		TT.Bar:Finish(nil)
		return
	end

	dur = math.floor(dur * 10 + 0.5) / 10
	if not route then
		route = {}
		TT.db.routes[f.key] = route
	end
	route.from = f.fromName
	route.to = f.toName
	route.time = dur
	if recTime and dur < recTime * SHORT_RATIO then
		-- correction of a bad (too long) saved time: the old best can't be trusted
		route.best = dur
		Print(string.format("Updated %s > %s: %s -> %s", TT.ShortName(f.fromName), TT.ShortName(f.toName),
			TT.FormatTime(recTime), TT.FormatTime(dur)))
	else
		route.best = route.best and math.min(route.best, dur) or dur
	end
	route.count = (route.count or 0) + 1
	route.recorded = route.recorded or time()
	route.last = time()

	if not recTime then
		-- first recorded time of this route (it replaces a starter time from now on)
		local note = ""
		if starterTime and math.abs(dur - starterTime) > STARTER_NOTE_DIFF then
			note = string.format(" (starter list said %s)", TT.FormatTime(starterTime))
		end
		Print(string.format("Recorded %s > %s: %s%s", TT.ShortName(f.fromName), TT.ShortName(f.toName), TT.FormatTime(dur), note))
		TT.Bar:Finish(dur, true)
	else
		TT.Bar:Finish(nil, true)
	end
end

CheckTaxi = function()
	if loading then return end
	local onTaxi = UnitOnTaxi("player")
	if state == "pending" then
		if onTaxi then
			BeginFlight(pending)
		elseif GetTime() - pending.clickedAt > TAKEOFF_TIMEOUT then
			pending = nil
			state = "idle"
			StopTicker()
		end
	elseif state == "flying" then
		if not onTaxi then
			-- first check after a loading screen and already off the taxi:
			-- we landed during the load, so the landing time is unknown
			if flight.inLoad then flight.landedInLoad = true end
			EndFlight()
		else
			-- still flying after a loading screen: the flight went on during
			-- the load (the server keeps moving us), so that time stays counted
			flight.inLoad = nil
			StepTime(flight)
			if not flight.costDone and GetTime() > flight.costUntil then CostFallback(flight) end
			if TaxiTimeCharDB.active then
				TaxiTimeCharDB.active.lastSeen = time() -- heartbeat for a later login
			end
		end
	else
		StopTicker()
	end
end

-- Hook: the player clicked a destination on the flight map
local function OnTakeTaxiNode(slot)
	if state == "flying" then return end
	lastGossip = nil -- a map flight, not a talk-option one
	local to = nodeCache[slot]
	if not to then
		to = { name = TaxiNodeName and TaxiNodeName(slot) }
	end
	local from = currentNode
	if not from or not to.name then return end
	pending = {
		key = RouteKey(from, to),
		fromName = from.name, toName = to.name,
		mapID = taxiMapID, destX = to.x, destY = to.y,
		clickedAt = GetTime(),
		listCost = to.cost,                    -- listed fare (copper), nil if unknown (see below)
		lastMoney = GetMoney and GetMoney(),   -- gold before paying (the server charges later)
		fromNode = from.nodeID, npcID = taxiNpcID, -- for the flying creature
	}
	if pending.listCost == nil and TaxiNodeCost then
		local ok, cost = pcall(TaxiNodeCost, slot)
		if ok and type(cost) == "number" then pending.listCost = cost end
	end
	state = "pending"
	StartTicker()
end

local function OnEarlyLanding()
	if flight then flight.aborted = true end
end

-- On a taxi without a map click (talk option, e.g. the druid flights in
-- Moonglade / Thunder Bluff / Rut'theran): time it with a key made from the
-- NPC talked to, else from the start map (finished at landing in EndFlight).
local function StartUntrackedFlight()
	local startMap = PlayerMapID()
	local info = { fromName = ZoneName() or "?", toName = "?", openDest = true }
	local g = lastGossip
	lastGossip = nil
	if g and g.npcID and GetTime() - g.at <= GOSSIP_WINDOW then
		info.key = "gossip:" .. g.npcID .. ":" .. (startMap or "?")
		info.npcID = g.npcID
	elseif startMap then
		info.zoneStart = startMap
		-- one known route from here: count down to it; else record ("?" until landing)
		info.key = OnlyZoneRoute(startMap) or ("zone:" .. startMap .. ":?")
	else
		return -- no way to tell routes apart
	end
	local route = TT.db.routes[info.key]
	if route and route.to then info.toName = route.to end
	BeginFlight(info)
end

-- control lost while idle: a few looks whether we are on a taxi (stun/fear: never)
local function WatchTakeoff(tries)
	C_Timer.After(TICK, function()
		if state ~= "idle" or loading then return end
		if UnitOnTaxi("player") then
			StartUntrackedFlight()
		elseif tries > 1 then
			WatchTakeoff(tries - 1)
		end
	end)
end

-- After login/reload/disconnect: carry on showing a flight that was running,
-- but never record it (the time would include the offline/loading gap)
local function TryResume(isLogin)
	local a = TaxiTimeCharDB.active
	if not a or state ~= "idle" then return end
	local age = time() - (a.startWall or 0)
	if UnitOnTaxi("player") and a.key and age >= 0 and age < RESUME_MAX_AGE then
		a.noRecord = true
		local elapsed = age
		if isLogin and a.lastSeen and a.startWall and a.lastSeen >= a.startWall then
			-- after a real login, start the bar where we were when we went offline
			elapsed = a.lastSeen - a.startWall
		end
		BeginFlight(a, elapsed)
	else
		TaxiTimeCharDB.active = nil
	end
end

------------------------------------------------------------------------
-- Events
------------------------------------------------------------------------

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")

local handlers = {}

function handlers.ADDON_LOADED(name)
	if name ~= addonName then
		-- stays registered to catch Blizzard_FlightMap (load on demand)
		if TT.db then TT.Tooltip:OnAddonLoaded(name) end
		return
	end
	InitDB()
	TT.Bar:Create()
	TT.Tooltip:Init()

	hooksecurefunc("TakeTaxiNode", OnTakeTaxiNode)
	if TaxiRequestEarlyLanding then
		hooksecurefunc("TaxiRequestEarlyLanding", OnEarlyLanding)
	end

	events:RegisterEvent("TAXIMAP_OPENED")
	events:RegisterEvent("PLAYER_CONTROL_LOST")
	events:RegisterEvent("PLAYER_CONTROL_GAINED")
	events:RegisterEvent("PLAYER_ENTERING_WORLD")
	events:RegisterEvent("PLAYER_LEAVING_WORLD")
	events:RegisterEvent("PLAYER_MONEY")
	events:RegisterEvent("GOSSIP_SHOW")
end

function handlers.PLAYER_MONEY()
	OnMoney() -- returns at once outside the fare window
end

function handlers.TAXIMAP_OPENED()
	lastGossip = nil -- flight master map: its flights come through TakeTaxiNode
	ScanTaxiMap()
	taxiNpcID = TalkingNpcID() -- once per map open (nil if unknown or secret)
	local spot = FlyerSpot(currentNode and currentNode.nodeID, taxiNpcID)
	if spot ~= nil and state ~= "flying" then
		flyerSpot, flyerSpotName = spot, currentNode and currentNode.name
	end
	TT.Tooltip:OnTaxiMapOpened()
end

function handlers.PLAYER_CONTROL_LOST()
	if state == "pending" then
		C_Timer.After(0.1, CheckTaxi)
	elseif state == "idle" and not loading then
		WatchTakeoff(WATCH_TRIES) -- flight without a map click?
	end
end

function handlers.GOSSIP_SHOW()
	lastGossip = { npcID = TalkingNpcID(), at = GetTime() }
end

function handlers.PLAYER_CONTROL_GAINED()
	if state == "flying" then C_Timer.After(0.2, CheckTaxi) end
end

function handlers.PLAYER_LEAVING_WORLD()
	loading = true
	if flight then flight.inLoad = true end
	RoundTotals() -- also fires on logout/reload, right before the save is written
end

function handlers.PLAYER_ENTERING_WORLD(isInitialLogin, isReloadingUi)
	-- give the client a moment before trusting UnitOnTaxi again
	C_Timer.After(1, function()
		loading = false
		if state ~= "idle" then
			CheckTaxi()
		elseif (isInitialLogin or isReloadingUi) and TaxiTimeCharDB.active then
			-- the taxi flag can be late right after login: if it isn't set yet,
			-- look once more at 3 s before giving the saved flight up
			if UnitOnTaxi("player") then
				TryResume(isInitialLogin and true or false)
			else
				C_Timer.After(2, function() TryResume(isInitialLogin and true or false) end)
			end
		end
	end)
end

events:SetScript("OnEvent", function(_, event, ...)
	local h = handlers[event]
	if h then h(...) end
end)

------------------------------------------------------------------------
-- Slash command
------------------------------------------------------------------------

local function Help()
	Print("commands:")
	Print("  /tt lock | unlock - lock the bar / unlock it to drag it")
	Print("  /tt reset - put the bar back in its default place")
	Print("  /tt test - show or hide a test bar (/tt test bat: with a bat)")
	Print("  /tt flyer gryphon | wind rider | bat | hippogryph | auto - the creature for flights from here")
	Print("  /tt flyer style model | cartoon - 3D creature or cartoon picture; /tt model bat - check a 3D model")
	Print("  /tt forget - forget the time of the current or last route")
	Print("  /tt tooltip - show or hide flight times on the flight map")
	Print("  /tt totals - gold spent and time flown; /tt totals on | off - line under the bar")
	Print("  /tt export - your recorded times as text to copy (for the starter list)")
end

-- /tt export text: one header line, one "fromID>toID=seconds" line per
-- recorded route (numeric node IDs only), one end line with the count.
-- No character or realm names. The merge script accepts only this format.
function TT.ExportText()
	local keys = {}
	for key, route in pairs(TT.db.routes) do
		local sec = type(route) == "table" and type(route.time) == "number" and math.floor(route.time + 0.5)
		if type(key) == "string" and key:match("^%d+>%d+$") and sec
			and sec >= EXPORT_MIN and sec <= EXPORT_MAX then
			keys[#keys + 1] = key
		end
	end
	table.sort(keys, function(a, b)
		local a1, a2 = a:match("^(%d+)>(%d+)$")
		local b1, b2 = b:match("^(%d+)>(%d+)$")
		a1, a2, b1, b2 = tonumber(a1), tonumber(a2), tonumber(b1), tonumber(b2)
		if a1 ~= b1 then return a1 < b1 end
		return a2 < b2
	end)
	local build = (GetBuildInfo and GetBuildInfo()) or "?"
	local faction = UnitFactionGroup and UnitFactionGroup("player")
	if type(faction) ~= "string" or not faction:match("^%a+$") then faction = "Unknown" end
	local lines = { string.format("-- Taxi Time export v%d, build %s, %s", EXPORT_VERSION, tostring(build), tostring(faction)) }
	for _, key in ipairs(keys) do
		lines[#lines + 1] = string.format("%s=%d", key, math.floor(TT.db.routes[key].time + 0.5))
	end
	lines[#lines + 1] = string.format("-- end, %d routes", #keys)
	return table.concat(lines, "\n"), #keys
end

-- read-only copy window for /tt export (built on first use)
local exportFrame
local function ShowExport()
	local text, n = TT.ExportText()
	if not exportFrame then
		local f = CreateFrame("Frame", "TaxiTimeExportFrame", UIParent, "BackdropTemplate")
		f:SetSize(420, 320)
		f:SetPoint("CENTER")
		f:SetFrameStrata("DIALOG")
		f:SetBackdrop({
			bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
			edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
			tile = true, tileSize = 32, edgeSize = 24,
			insets = { left = 6, right = 6, top = 6, bottom = 6 },
		})
		f:EnableMouse(true)
		f:SetMovable(true)
		f:RegisterForDrag("LeftButton")
		f:SetScript("OnDragStart", f.StartMoving)
		f:SetScript("OnDragStop", f.StopMovingOrSizing)
		local title = f:CreateFontString(nil, "OVERLAY", "GameFontNormal")
		title:SetPoint("TOP", 0, -14)
		title:SetText("Taxi Time export - Ctrl+C to copy")
		f.title = title
		local close = CreateFrame("Button", nil, f, "UIPanelCloseButton")
		close:SetPoint("TOPRIGHT", -4, -4)
		local scroll = CreateFrame("ScrollFrame", "TaxiTimeExportScroll", f, "UIPanelScrollFrameTemplate")
		scroll:SetPoint("TOPLEFT", 16, -36)
		scroll:SetPoint("BOTTOMRIGHT", -34, 16)
		local edit = CreateFrame("EditBox", nil, scroll)
		edit:SetMultiLine(true)
		edit:SetAutoFocus(false)
		edit:SetFontObject(ChatFontNormal)
		edit:SetWidth(360)
		edit:SetScript("OnEscapePressed", function() f:Hide() end)
		-- read-only: typing puts the export text back
		edit:SetScript("OnTextChanged", function(self, userInput)
			if userInput then
				self:SetText(f.exportText or "")
				self:HighlightText()
			end
		end)
		scroll:SetScrollChild(edit)
		f.edit = edit
		tinsert(UISpecialFrames, "TaxiTimeExportFrame") -- Esc closes it
		exportFrame = f
	end
	exportFrame.exportText = text
	exportFrame.edit:SetText(text)
	exportFrame:Show()
	exportFrame.edit:SetFocus()
	exportFrame.edit:HighlightText()
	Print(string.format("export: %d routes. Copy with Ctrl+C and send only your own export.", n))
end

local function PrintTotals(label, t)
	Print(string.format("%s: %s spent, %s flown, %d flights (since %s)", label,
		TT.FormatMoney(t.copper), TT.FormatLong(t.seconds), t.flights, date("%Y-%m-%d", t.since)))
end

-- /tt flyer <kind|auto>: the creature for flights from the last start point
-- (the running flight's, else the last flight's or flight map's). Saved per
-- start point in TaxiTimeDB.flyers; "auto" goes back to the automatic choice.
local function FlyerCommand(rest)
	local style = rest:match("^style ?(.*)$")
	if style then
		if style == "model" or style == "cartoon" then
			TT.Bar:SetStyle(style)
			Print(style == "model" and "flying creature: the game's 3D model (cartoon while it loads or if it can't be shown)."
				or "flying creature: cartoon pictures.")
		else
			Print("use /tt flyer style model or /tt flyer style cartoon (now: " .. tostring(TT.db.bar.flyerStyle) .. ").")
		end
		return
	end
	local spot, name = flyerSpot, flyerSpotName
	if flight and flight.flyerSpot ~= nil then spot, name = flight.flyerSpot, flight.flyerName end
	local where = TT.ShortName(name or "this flight master")
	if rest == "" then
		if spot == nil then
			Print("open a flight master's map or take a flight first, then /tt flyer bat (or gryphon, wind rider, hippogryph, auto).")
		else
			local own = TT.db.flyers[spot]
			Print(string.format("flights from %s show: %s%s. Change with /tt flyer gryphon | wind rider | bat | hippogryph | auto.",
				where, FLYER_KINDS[own] or "automatic choice", FLYER_KINDS[own] and " (your choice)" or ""))
		end
		return
	end
	if spot == nil then
		Print("no start point yet: open a flight master's map or take a flight first.")
		return
	end
	local kind = FLYER_ALIASES[rest] or rest
	if kind == "auto" then
		TT.db.flyers[spot] = nil
		Print(string.format("flights from %s: automatic creature again.", where))
	elseif FLYER_KINDS[kind] then
		TT.db.flyers[spot] = kind
		Print(string.format("flights from %s now show a %s.", where, FLYER_KINDS[kind]))
	else
		Print("use /tt flyer gryphon, wind rider, bat, hippogryph or auto.")
		return
	end
	if flight and flight.flyerSpot == spot then
		-- running flight from that start point: change the icon now
		flight.flyer = TT.FlyerFor(spot, flight.fromNode, flight.npcID, flight.startMap)
		if TaxiTimeCharDB.active then TaxiTimeCharDB.active.flyer = flight.flyer end
		TT.Bar:SetFlyer(flight.flyer)
	end
end

SLASH_TAXITIME1 = "/tt"
SLASH_TAXITIME2 = "/taxitime"
SlashCmdList.TAXITIME = function(msg)
	-- lower case, extra spaces collapsed: "totals  on" = "totals on"
	local cmd = strtrim((msg or "")):lower():gsub("%s+", " ")
	local word, rest = cmd:match("^(%S*) ?(.*)$")
	if cmd == "lock" then
		TT.Bar:SetLocked(true)
		Print("bar locked.")
	elseif cmd == "unlock" then
		TT.Bar:SetLocked(false)
		Print("bar unlocked - drag it, then /tt lock.")
	elseif cmd == "reset" then
		TT.Bar:ResetPosition()
		Print("bar position reset.")
	elseif word == "test" then
		local kind = FLYER_ALIASES[rest] or rest
		if rest ~= "" and FLYER_KINDS[kind] then
			TT.Bar:ShowTest(kind) -- /tt test bat: test bar with that creature
		else
			TT.Bar:ToggleTest()
		end
	elseif word == "flyer" then
		FlyerCommand(rest)
	elseif word == "model" then
		-- check: /tt model <kind> or /tt model <kind> <displayID>
		local k, id = rest:match("^(.-) ?(%d*)$")
		local kind = FLYER_ALIASES[k] or k
		if not FLYER_KINDS[kind] then
			Print("use /tt model gryphon | wind rider | bat | hippogryph (optional: a display ID to try).")
		else
			local displayID = tonumber(id)
			Print(string.format("loading the %s model%s...", FLYER_KINDS[kind], displayID and (" (display ID " .. displayID .. ")") or ""))
			TT.Bar:ModelCheck(kind, displayID, function(ok, how)
				if ok then
					Print(string.format("%s model shown (%s). /tt test hides the test bar.", FLYER_KINDS[kind],
						how == "creature" and "via the creature ID" or "via the display ID"))
				else
					Print(string.format("%s model not shown (%s): the cartoon is used.", FLYER_KINDS[kind], tostring(how)))
				end
			end)
		end
	elseif cmd == "forget" then
		local key = TT.lastKey
		local route = key and TT.db.routes[key]
		if route then
			TT.db.routes[key] = nil
			local starter = TT.GetRouteTime(key) -- only the starter time is left now
			Print(string.format("forgot %s > %s.%s", TT.ShortName(route.from), TT.ShortName(route.to),
				starter and (" Using the starter time ~" .. TT.FormatTime(starter) .. " until you fly it again.") or ""))
		else
			Print("no route to forget (fly one first).")
		end
	elseif cmd == "tooltip" then
		TT.db.tooltip = not TT.db.tooltip
		Print("flight-map times " .. (TT.db.tooltip and "on." or "off."))
	elseif word == "totals" then
		if rest == "" then
			PrintTotals("This character", TT.charTotals)
			PrintTotals("All characters", TT.accTotals)
		elseif rest == "on" or rest == "off" then
			local show = (rest == "on")
			TT.db.bar.showTotals = show
			TT.Bar:SetShowTotals(show)
			Print("totals under the bar " .. (show and "on." or "off."))
		else
			Print("use /tt totals, /tt totals on or /tt totals off.")
		end
	elseif cmd == "export" then
		ShowExport()
	else
		Help()
	end
end
