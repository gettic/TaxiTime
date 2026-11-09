-- Taxi Time: Tooltip.lua
-- Adds the recorded flight time to destination tooltips on the flight map
-- (old TaxiFrame buttons and the newer FlightMapFrame pins).
-- Only hooksecurefunc / HookScript post-hooks; nothing of Blizzard's is replaced.

local _, TT = ...

local Tooltip = {}
TT.Tooltip = Tooltip

local LABEL = "|cff33ccffTaxi Time:|r "
local PIN_TEMPLATE = "FlightMap_FlightPointPinTemplate"

local hookedPins = setmetatable({}, { __mode = "k" }) -- pin frame -> true
local flightMapHooked = false

local function IsReachable(slot, nodeState)
	local REACHABLE = Enum and Enum.FlightPathState and Enum.FlightPathState.Reachable
	if nodeState ~= nil and REACHABLE ~= nil then
		return nodeState == REACHABLE
	end
	return TaxiNodeGetType and TaxiNodeGetType(slot) == "REACHABLE"
end

-- Adds one line for this destination slot (tooltip already owned by `owner`)
local function AddTimeLine(owner, slot, nodeState)
	if not (TT.db and TT.db.tooltip) then return end
	if type(slot) ~= "number" then return end
	if GameTooltip:GetOwner() ~= owner then return end
	if not IsReachable(slot, nodeState) then return end
	local key = TT.RouteKeyForSlot(slot)
	if not key then return end
	local sec, isEstimate = TT.GetRouteTime(key)
	if sec then
		-- "~" = starter-list time, not flown on this account yet
		GameTooltip:AddLine(LABEL .. "|cffffffff" .. (isEstimate and "~" or "") .. TT.FormatTime(sec) .. "|r")
	else
		GameTooltip:AddLine(LABEL .. "|cff999999no time yet|r")
	end
	GameTooltip:Show() -- resize for the new line
end

-- Old flight map: TaxiButtonTemplate OnEnter calls TaxiNodeOnButtonEnter(self, motion)
local function OnTaxiButtonEnter(button)
	pcall(function()
		AddTimeLine(button, button:GetID())
	end)
end

-- New flight map: post-hook on each flight point pin's OnEnter script
local function OnPinEnter(pin)
	pcall(function()
		local data = pin.taxiNodeData
		if type(data) ~= "table" then return end
		AddTimeLine(pin, data.slotIndex, data.state)
	end)
end

local function HookPins()
	local map = FlightMapFrame
	if not (map and map.EnumeratePinsByTemplate) then return end
	pcall(function()
		for pin in map:EnumeratePinsByTemplate(PIN_TEMPLATE) do
			if not hookedPins[pin] then
				hookedPins[pin] = true
				pin:HookScript("OnEnter", OnPinEnter)
			end
		end
	end)
end

local function HookFlightMap()
	if flightMapHooked or not FlightMapFrame then return end
	flightMapHooked = true
	FlightMapFrame:HookScript("OnShow", function()
		C_Timer.After(0, HookPins)
	end)
	HookPins()
end

-- Called from Core's ADDON_LOADED (after InitDB)
function Tooltip:Init()
	if TaxiNodeOnButtonEnter then
		hooksecurefunc("TaxiNodeOnButtonEnter", OnTaxiButtonEnter)
	end
	local isLoaded = C_AddOns and C_AddOns.IsAddOnLoaded
	if isLoaded and isLoaded("Blizzard_FlightMap") then
		HookFlightMap()
	end
end

-- Other addons' ADDON_LOADED (Blizzard_FlightMap is load on demand)
function Tooltip:OnAddonLoaded(name)
	if name == "Blizzard_FlightMap" then HookFlightMap() end
end

function Tooltip:OnTaxiMapOpened()
	HookFlightMap()
	C_Timer.After(0, HookPins)
end
