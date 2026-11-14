-- Taxi Time: Rank.lua
-- The addon's own "Taxi Time rank": a fun level from how much you fly.
-- XP = whole minutes flown + 2 per flight, read from the totals Core already
-- keeps (TaxiTimeCharDB.totals / TaxiTimeDB.totals). The rank is never saved
-- as the truth: it is always worked out from the totals. Only the last rank
-- announced (TaxiTimeCharDB.rankShown) is saved, so nothing is announced twice.
-- Plan and table: plans\level-up\plan-rank.md.

local ADDON, TT = ...

local XP_PER_FLIGHT = 2

-- total XP needed for each rank: round(9 * (r-1)^2.15 / 5) * 5, rank 2 = 10
-- (about 108 XP per hour in the air: rank 10 ~9 h, rank 20 ~47 h, rank 30 ~116 h)
local RANK_XP = {
	0, 10, 40, 95, 175, 285, 425, 590, 785, 1015,
	1270, 1560, 1880, 2235, 2620, 3040, 3490, 3980, 4500, 5055,
	5640, 6265, 6925, 7620, 8350, 9115, 9920, 10755, 11630, 12545,
}

-- our own titles (never shown as a character title, only as Taxi Time text)
local RANK_TITLES = {
	"Grounded", "First-Time Flyer", "Nervous Passenger", "Window Seat", "Saddle Sore",
	"Peanut Collector", "Frequent Flapper", "Feather Duster", "Cloud Counter", "Sky Tourist",
	"Map Clicker", "Breeze Rider", "Tailwind Fan", "Altitude Enjoyer", "Professional Passenger",
	"Wing Buddy", "Seat Belt Optional", "Long-Haul Napper", "Postcard Sender", "Sky Commuter",
	"Cloud Regular", "Flight Path Philosopher", "Gold Card Member", "Mostly Airborne", "Honorary Bird",
	"Feet Rarely Touch Ground", "Lives in the Sky", "Cloud Mayor", "Almost a Bird", "Taxi Legend",
}

local MAX_RANK = #RANK_XP
TT.RANK_MAX = MAX_RANK

local startNote -- rank to announce once after login (set by TT.RankInit)

local function Count(v)
	v = tonumber(v) or 0
	if v ~= v or v < 0 or v == math.huge then return 0 end
	return v
end

-- XP from a totals table (missing or bad values count as 0)
function TT.RankXP(t)
	if type(t) ~= "table" then return 0 end
	return math.floor(Count(t.seconds) / 60) + XP_PER_FLIGHT * math.floor(Count(t.flights))
end

-- rank, title, xp, pct to the next rank (nil at max), next rank's title (nil at max)
function TT.RankFor(t)
	local xp = TT.RankXP(t)
	local r = 1
	for i = MAX_RANK, 1, -1 do
		if xp >= RANK_XP[i] then r = i break end
	end
	if r >= MAX_RANK then return r, RANK_TITLES[r], xp, nil, nil end
	local from, to = RANK_XP[r], RANK_XP[r + 1]
	local pct = math.floor((xp - from) / (to - from) * 100)
	return r, RANK_TITLES[r], xp, pct, RANK_TITLES[r + 1]
end

-- from InitDB: old saves (no rankShown) start at the rank their totals give,
-- with one quiet line later if this character has flown before
function TT.RankInit()
	local c = TaxiTimeCharDB
	local r = TT.RankFor(TT.charTotals)
	local was = c.rankShown
	if type(was) ~= "number" or was ~= was or was < 1 or was > MAX_RANK or was % 1 ~= 0 then
		c.rankShown = r
		if was == nil and TT.charTotals and Count(TT.charTotals.flights) > 0 then startNote = r end
	end
end

-- once, after the first PLAYER_ENTERING_WORLD (chat is ready then)
function TT.RankStartNote()
	if not startNote then return end
	local r = startNote
	startNote = nil
	TT.Print(string.format("you start at Rank %d, %s, from your flights so far. (/tt rank)", r, RANK_TITLES[r]))
end

-- after every landing (Core EndFlight): announce a higher rank once
function TT.CheckRankUp()
	local c = TaxiTimeCharDB
	if type(c) ~= "table" then return end
	local r, title = TT.RankFor(TT.charTotals)
	local shown = c.rankShown
	if type(shown) ~= "number" or shown ~= shown then
		c.rankShown = r
		return
	end
	if r > shown then
		c.rankShown = r
		startNote = nil -- the rank-up line says it all
		TT.Print(string.format("Rank up! Rank %d, %s. (/tt rank)", r, title))
		if TT.Bar and TT.Bar.RankUp then TT.Bar:RankUp() end
	elseif r < shown then
		c.rankShown = r -- totals went down (hand-edited save): follow quietly
	end
end

local function RankLine(label, t)
	local r, title, xp, pct, nextTitle = TT.RankFor(t)
	if pct then
		TT.Print(string.format("rank (%s): Rank %d %s - %d XP, %d%% to Rank %d (%s)", label, r, title, xp, pct, r + 1, nextTitle))
	else
		TT.Print(string.format("rank (%s): Rank %d %s - %d XP (max rank)", label, r, title, xp))
	end
end

-- /tt rank
function TT.PrintRank()
	RankLine("this character", TT.charTotals)
	RankLine("all characters", TT.accTotals)
	local since = TT.charTotals and tonumber(TT.charTotals.since)
	TT.Print(string.format("XP = minutes flown + %d per flight.%s", XP_PER_FLIGHT,
		since and (" Counting since " .. date("%Y-%m-%d", since) .. ".") or ""))
end
