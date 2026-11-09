-- Taxi Time: StarterTimes.lua
-- Flight times shipped with the addon, so the bar works on a route's very
-- first flight. A time you record yourself always replaces the starter time.
--
-- Made only from Taxi Time's own "/tt export" output, sent in by the author
-- and volunteers (no data from other addons or websites). Built with the merge
-- script; keep it a plain, readable table.
--
-- Format: [fromNodeID] = "toNodeID:seconds,toNodeID:seconds,..."
-- Node IDs are the game's flight-path node IDs (the same in every language).

local _, TT = ...

TT.starterBuild = nil -- game build the times were measured on (set by the merge script)

TT.starterRaw = {
	-- empty for now: no exports collected yet
}
