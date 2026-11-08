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

local DEFAULTS_BAR = {
	point = "TOP", relPoint = "TOP", x = 0, y = -160,
	width = 260, locked = true,
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

local function RouteKey(from, to)
	if from.nodeID and to.nodeID then
		return from.nodeID .. ">" .. to.nodeID
	end
	return "name:" .. (from.name or "?") .. ">" .. (to.name or "?")
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
	if type(TaxiTimeCharDB) ~= "table" then TaxiTimeCharDB = {} end
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
		if not currentNode and TaxiNodeGetType(i) == "CURRENT" then
			currentNode = e
		end
	end
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
-- Take-off and landing
------------------------------------------------------------------------

local function SaveActive(f)
	TaxiTimeCharDB.active = {
		key = f.key, fromName = f.fromName, toName = f.toName,
		mapID = f.mapID, destX = f.destX, destY = f.destY,
		startWall = f.startWall,
		noRecord = f.noRecord or nil,
		lastSeen = time(),
	}
end

local function BeginFlight(info, elapsed)
	elapsed = elapsed or 0
	local route = TT.db.routes[info.key]
	flight = {
		key = info.key, fromName = info.fromName, toName = info.toName,
		mapID = info.mapID, destX = info.destX, destY = info.destY,
		startTime = GetTime() - elapsed,
		startWall = info.startWall or time(),
		known = (route and route.time) and true or false,
		aborted = false,
		noRecord = info.noRecord and true or false, -- resumed after login/reload/disconnect
	}
	pending = nil
	state = "flying"
	TT.lastKey = flight.key
	SaveActive(flight)
	StartTicker()

	if flight.known then
		TT.Bar:StartFlight(flight.fromName, flight.toName, route.time, elapsed)
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

	local dur = GetTime() - f.startTime
	local route = TT.db.routes[f.key]
	local oldTime = route and route.time
	local reason
	if f.noRecord then
		reason = "logged out or reloaded during the flight"
	elseif f.aborted then
		reason = "early landing"
	elseif dur < MIN_FLIGHT then
		reason = "too short"
	elseif not LandedNearDest(f) and (not oldTime or dur < oldTime * SHORT_RATIO) then
		-- new route, or much shorter than the saved time: only trust it if we
		-- landed at the destination (a real faster time corrects a bad saved one)
		reason = oldTime and "shorter than the recorded time" or "landed away from the destination"
	end

	if reason then
		if not f.known or f.noRecord then
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
	if oldTime and dur < oldTime * SHORT_RATIO then
		-- correction of a bad (too long) saved time: the old best can't be trusted
		route.best = dur
		Print(string.format("Updated %s > %s: %s -> %s", TT.ShortName(f.fromName), TT.ShortName(f.toName),
			TT.FormatTime(oldTime), TT.FormatTime(dur)))
	else
		route.best = route.best and math.min(route.best, dur) or dur
	end
	route.count = (route.count or 0) + 1
	route.recorded = route.recorded or time()
	route.last = time()

	if not f.known then
		Print(string.format("Recorded %s > %s: %s", TT.ShortName(f.fromName), TT.ShortName(f.toName), TT.FormatTime(dur)))
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
			EndFlight()
		elseif TaxiTimeCharDB.active then
			TaxiTimeCharDB.active.lastSeen = time() -- heartbeat for a later login
		end
	else
		StopTicker()
	end
end

-- Hook: the player clicked a destination on the flight map
local function OnTakeTaxiNode(slot)
	if state == "flying" then return end
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
	}
	state = "pending"
	StartTicker()
end

local function OnEarlyLanding()
	if flight then flight.aborted = true end
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
	if name ~= addonName then return end
	events:UnregisterEvent("ADDON_LOADED")
	InitDB()
	TT.Bar:Create()

	hooksecurefunc("TakeTaxiNode", OnTakeTaxiNode)
	if TaxiRequestEarlyLanding then
		hooksecurefunc("TaxiRequestEarlyLanding", OnEarlyLanding)
	end

	events:RegisterEvent("TAXIMAP_OPENED")
	events:RegisterEvent("PLAYER_CONTROL_LOST")
	events:RegisterEvent("PLAYER_CONTROL_GAINED")
	events:RegisterEvent("PLAYER_ENTERING_WORLD")
	events:RegisterEvent("PLAYER_LEAVING_WORLD")
end

function handlers.TAXIMAP_OPENED()
	ScanTaxiMap()
end

function handlers.PLAYER_CONTROL_LOST()
	if state == "pending" then C_Timer.After(0.1, CheckTaxi) end
end

function handlers.PLAYER_CONTROL_GAINED()
	if state == "flying" then C_Timer.After(0.2, CheckTaxi) end
end

function handlers.PLAYER_LEAVING_WORLD()
	loading = true
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
	Print("  /tt test - show or hide a test bar")
	Print("  /tt forget - forget the time of the current or last route")
end

SLASH_TAXITIME1 = "/tt"
SLASH_TAXITIME2 = "/taxitime"
SlashCmdList.TAXITIME = function(msg)
	local cmd = strtrim((msg or "")):lower()
	if cmd == "lock" then
		TT.Bar:SetLocked(true)
		Print("bar locked.")
	elseif cmd == "unlock" then
		TT.Bar:SetLocked(false)
		Print("bar unlocked - drag it, then /tt lock.")
	elseif cmd == "reset" then
		TT.Bar:ResetPosition()
		Print("bar position reset.")
	elseif cmd == "test" then
		TT.Bar:ToggleTest()
	elseif cmd == "forget" then
		local key = TT.lastKey
		local route = key and TT.db.routes[key]
		if route then
			TT.db.routes[key] = nil
			Print(string.format("forgot %s > %s.", TT.ShortName(route.from), TT.ShortName(route.to)))
		else
			Print("no route to forget (fly one first).")
		end
	else
		Help()
	end
end
