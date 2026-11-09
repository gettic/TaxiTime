-- Taxi Time: Bar.lua
-- The flight bar: fills over the recorded time with a flying icon on top,
-- a pulsing "Recording" bar on a first flight, movable and lockable.

local ADDON, TT = ...
local Bar = {}
TT.Bar = Bar

-- false = back to the v1 look (built-in icons and tooltip border), e.g. if
-- the media files don't load. New files need a full game restart, not /reload.
local USE_CUSTOM_ART = true
local MEDIA = "Interface\\AddOns\\" .. ADDON .. "\\media\\"

local HEIGHT = 26
local ICON_SIZE = USE_CUSTOM_ART and 28 or 24
local ICON_ALLIANCE, ICON_HORDE
if USE_CUSTOM_ART then
	-- 256x64 sheets, 4 frames of 64x64 facing right (up, mid, down, mid)
	ICON_ALLIANCE = MEDIA .. "flyer_alliance"
	ICON_HORDE = MEDIA .. "flyer_horde"       -- wind rider
else
	ICON_ALLIANCE = "Interface\\Icons\\Ability_Mount_Gryphon_01"
	ICON_HORDE = "Interface\\Icons\\Ability_Mount_Wyvern_01"
end
local FLAP_FPS = 10              -- wing-flap frames per second
local HALF_TEXEL = 0.5 / 256     -- keeps a frame from bleeding into its neighbour
local CAP_W = HEIGHT / 2         -- frame caps: 32x64 of the texture -> 13x26
local CLOUD_SPEED = 12           -- px per second, right to left
local CLOUD_ALPHA = 0.85
local SPARKLE_STEP = 0.12        -- seconds per sparkle frame
local SPARKLE_TIME = 1.0         -- sparkle shown for this long
local FLYER_KEEP = 0.5           -- flyer stays this long after a real landing
local COLOR_FLIGHT = { 0.25, 0.6, 1.0 }
local COLOR_RECORD = { 1.0, 0.5, 0.1 }
local COLOR_DONE = { 0.2, 0.8, 0.3 }

local frame, status, iconFrame, icon, leftText, rightText
local totalsText      -- "Spent ... | Flown ..." line under the bar
local lastMoneyText, lastCopper -- cache for the coin string
local cloud, sparkleFrame, sparkle
local pulseAnim, fadeAnim
local flapIndex       -- frame of the flyer sheet shown now
local iconX = 0       -- flyer centre x from the bar's left edge
local landTime        -- GetTime() of a real landing (sparkle), or nil
local mode            -- nil | "flight" | "record" | "test" | "done"
local total = 1       -- recorded time of the route (flight/test mode)
local estimate = ""   -- "~" while the time comes from the starter list, else ""
local startTime = 0   -- GetTime() at take-off
local lastSec         -- last whole second written to the time text
local doneToken = 0   -- cancels an old "Recorded" fade timer

------------------------------------------------------------------------
-- Position and lock
------------------------------------------------------------------------

local function ApplyPosition()
	local b = TT.db.bar
	frame:ClearAllPoints()
	frame:SetPoint(b.point or "TOP", UIParent, b.relPoint or "TOP", b.x or 0, b.y or -160)
end

local function SavePosition()
	local point, _, relPoint, x, y = frame:GetPoint(1)
	local b = TT.db.bar
	b.point, b.relPoint = point, relPoint
	b.x = math.floor(x + 0.5)
	b.y = math.floor(y + 0.5)
end

------------------------------------------------------------------------
-- Look per mode
------------------------------------------------------------------------

local function SetColor(c)
	status:SetStatusBarColor(c[1], c[2], c[3])
end

local function SetFlap(now)
	if not USE_CUSTOM_ART then return end
	local i = math.floor(now * FLAP_FPS) % 4
	if i ~= flapIndex then
		flapIndex = i
		icon:SetTexCoord(i * 0.25 + HALF_TEXEL, (i + 1) * 0.25 - HALF_TEXEL, 0, 1)
	end
end

local function SetIconX(pct, now)
	local w = status:GetWidth()
	iconX = ICON_SIZE / 2 + (w - ICON_SIZE) * pct
	local bob = 2 * math.sin(now * 4)
	iconFrame:ClearAllPoints()
	if USE_CUSTOM_ART then
		-- the sheet has empty space under the creature: sit 6 px into the bar
		iconFrame:SetPoint("BOTTOM", status, "TOPLEFT", iconX, -6 + bob)
	else
		iconFrame:SetPoint("BOTTOM", status, "TOPLEFT", iconX, 3 + bob)
	end
	SetFlap(now)
end

-- cloud drifting right to left above the bar, fading in and out at the ends
local function UpdateCloud(now)
	local w = frame:GetWidth()
	local x = w - ((now * CLOUD_SPEED) % (w + 64))
	local a = math.min((w - x) / 64, (x + 64) / 64, 1)
	if a < 0 then a = 0 end
	cloud:ClearAllPoints()
	cloud:SetPoint("BOTTOMLEFT", frame, "TOPLEFT", x, 4)
	cloud:SetAlpha(CLOUD_ALPHA * a)
end

local function ShowCloud(show)
	if not cloud then return end
	if show then cloud:Show() else cloud:Hide() end
end

local function StopSparkle()
	landTime = nil
	if sparkleFrame then sparkleFrame:Hide() end
end

-- landing sparkle at the flyer's last spot, 4 frames then the last one held
local function UpdateSparkle(now)
	local t = now - landTime
	if t >= SPARKLE_TIME then
		iconFrame:Hide()
		StopSparkle()
		return
	end
	if t >= FLYER_KEEP and iconFrame:IsShown() then
		iconFrame:Hide()
	elseif iconFrame:IsShown() then
		SetFlap(now)
	end
	local i = math.min(3, math.floor(t / SPARKLE_STEP))
	sparkle:SetTexCoord(i * 0.25, (i + 1) * 0.25, 0, 1)
end

local function StopAnims()
	pulseAnim:Stop()
	fadeAnim:Stop()
	status:SetAlpha(1)
	frame:SetAlpha(1)
	StopSparkle()
	flapIndex = nil
end

-- this character's totals under the bar (TT.charTotals, filled by Core)
local function UpdateTotals()
	if not totalsText then return end
	local t = TT.charTotals
	if not (t and TT.db.bar.showTotals) then
		totalsText:Hide()
		return
	end
	if t.copper ~= lastCopper then
		lastCopper = t.copper
		lastMoneyText = TT.FormatMoney(t.copper)
	end
	totalsText:SetText("|cffb0b0b0Spent|r " .. lastMoneyText .. "  |cff777777|||r  |cffb0b0b0Flown|r " .. TT.FormatLong(t.seconds))
	totalsText:Show()
end

local function Begin(newMode, fromName, toName, elapsed)
	mode = newMode
	doneToken = doneToken + 1
	StopAnims()
	startTime = GetTime() - (elapsed or 0)
	lastSec = nil
	estimate = "" -- StartFlight sets "~" again for a starter time
	local route = TT.ShortName(fromName) .. " > " .. TT.ShortName(toName)
	if newMode == "record" then
		leftText:SetText("Recording: " .. route)
	else
		leftText:SetText(route)
	end
	rightText:SetText("")
	UpdateTotals()
	frame:Show()
end

------------------------------------------------------------------------
-- OnUpdate (runs only while the frame is shown)
------------------------------------------------------------------------

local function OnUpdate()
	if mode == "done" then
		if landTime then UpdateSparkle(GetTime()) end
	elseif mode == "flight" or mode == "test" then
		local now = GetTime()
		if cloud then UpdateCloud(now) end
		local e = now - startTime
		if mode == "test" and e > total + 2 then
			startTime = now
			e = 0
		end
		status:SetValue(e < total and e or total)
		SetIconX(e < total and e / total or 1, now)
		local sec = math.floor(e)
		if sec ~= lastSec then
			lastSec = sec
			if e <= total then
				rightText:SetText(estimate .. TT.FormatTime(total - e) .. " / " .. estimate .. TT.FormatTime(total))
			else
				rightText:SetText(estimate .. "+" .. TT.FormatTime(e - total))
			end
			UpdateTotals()
		end
	elseif mode == "record" then
		local now = GetTime()
		SetIconX(0, now)
		local sec = math.floor(now - startTime)
		if sec ~= lastSec then
			lastSec = sec
			rightText:SetText(TT.FormatTime(sec))
			UpdateTotals()
		end
	end
end

------------------------------------------------------------------------
-- Building the frame
------------------------------------------------------------------------

function Bar:Create()
	if frame then return end
	local b = TT.db.bar

	if USE_CUSTOM_ART then
		frame = CreateFrame("Frame", "TaxiTimeBarFrame", UIParent)
	else
		frame = CreateFrame("Frame", "TaxiTimeBarFrame", UIParent, "BackdropTemplate")
		frame:SetBackdrop({
			bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
			edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
			tile = true, tileSize = 16, edgeSize = 12,
			insets = { left = 3, right = 3, top = 3, bottom = 3 },
		})
		frame:SetBackdropColor(0, 0, 0, 0.7)
		frame:SetBackdropBorderColor(0.6, 0.6, 0.6, 1)
	end
	frame:SetSize((b.width or 260) + 8, HEIGHT)
	frame:SetFrameStrata("MEDIUM")
	frame:SetClampedToScreen(true)

	frame:SetMovable(true)
	frame:RegisterForDrag("LeftButton")
	frame:SetScript("OnDragStart", function(self)
		if not TT.db.bar.locked then self:StartMoving() end
	end)
	frame:SetScript("OnDragStop", function(self)
		self:StopMovingOrSizing()
		SavePosition()
	end)

	status = CreateFrame("StatusBar", nil, frame)
	status:SetPoint("TOPLEFT", 4, -4)
	status:SetPoint("BOTTOMRIGHT", -4, 4)
	if USE_CUSTOM_ART then
		-- greyscale fill, tinted by SetColor
		status:SetStatusBarTexture(MEDIA .. "bar_fill")
		-- dark background behind the fill (on frame, so the pulse doesn't fade it)
		local bg = frame:CreateTexture(nil, "BACKGROUND")
		bg:SetAllPoints(status)
		bg:SetColorTexture(0, 0, 0, 0.6)
		-- brass frame, 3-slice from bar_frame.tga, drawn over the fill edges
		local border = CreateFrame("Frame", nil, frame)
		border:SetAllPoints()
		border:SetFrameLevel(status:GetFrameLevel() + 2)
		local left = border:CreateTexture(nil, "ARTWORK")
		left:SetTexture(MEDIA .. "bar_frame")
		left:SetTexCoord(0, 0.125, 0, 1)
		left:SetPoint("TOPLEFT")
		left:SetPoint("BOTTOMLEFT")
		left:SetWidth(CAP_W)
		local right = border:CreateTexture(nil, "ARTWORK")
		right:SetTexture(MEDIA .. "bar_frame")
		right:SetTexCoord(0.875, 1, 0, 1)
		right:SetPoint("TOPRIGHT")
		right:SetPoint("BOTTOMRIGHT")
		right:SetWidth(CAP_W)
		local mid = border:CreateTexture(nil, "ARTWORK")
		mid:SetTexture(MEDIA .. "bar_frame")
		mid:SetTexCoord(0.125, 0.875, 0, 1)
		mid:SetPoint("TOPLEFT", left, "TOPRIGHT")
		mid:SetPoint("BOTTOMRIGHT", right, "BOTTOMLEFT")
	else
		status:SetStatusBarTexture("Interface\\TargetingFrame\\UI-StatusBar")
	end
	status:SetMinMaxValues(0, 1)
	status:SetValue(0)

	rightText = status:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	rightText:SetPoint("RIGHT", -4, 0)
	rightText:SetJustifyH("RIGHT")

	leftText = status:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	leftText:SetPoint("LEFT", 4, 0)
	leftText:SetPoint("RIGHT", rightText, "LEFT", -6, 0)
	leftText:SetJustifyH("LEFT")
	leftText:SetWordWrap(false)

	-- totals line under the bar; it moves, fades and hides with the frame
	totalsText = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
	totalsText:SetPoint("TOP", frame, "BOTTOM", 0, -2)
	totalsText:SetJustifyH("CENTER")
	totalsText:SetWordWrap(false)
	-- keep the line on screen: the bar stays 14 px above the bottom edge
	frame:SetClampRectInsets(0, 0, 0, -14)

	iconFrame = CreateFrame("Frame", nil, frame)
	iconFrame:SetSize(ICON_SIZE, ICON_SIZE)
	iconFrame:SetFrameLevel(status:GetFrameLevel() + 5)
	icon = iconFrame:CreateTexture(nil, "ARTWORK")
	icon:SetAllPoints()
	local faction = UnitFactionGroup("player")
	icon:SetTexture(faction == "Horde" and ICON_HORDE or ICON_ALLIANCE)
	if USE_CUSTOM_ART then
		SetFlap(0)

		-- cloud: above the bar, behind the flyer (frame textures sit under child frames)
		cloud = frame:CreateTexture(nil, "BACKGROUND")
		cloud:SetTexture(MEDIA .. "cloud")
		cloud:SetSize(64, 32)
		cloud:Hide()

		-- landing sparkle: 128x32, 4 frames of 32x32
		sparkleFrame = CreateFrame("Frame", nil, frame)
		sparkleFrame:SetSize(32, 32)
		sparkleFrame:SetFrameLevel(iconFrame:GetFrameLevel() + 1)
		sparkle = sparkleFrame:CreateTexture(nil, "OVERLAY")
		sparkle:SetAllPoints()
		sparkle:SetTexture(MEDIA .. "sparkle")
		sparkle:SetTexCoord(0, 0.25, 0, 1)
		sparkleFrame:Hide()
	else
		icon:SetTexCoord(0.08, 0.92, 0.08, 0.92)
		if iconFrame.CreateMaskTexture then
			local mask = iconFrame:CreateMaskTexture()
			mask:SetTexture("Interface\\CharacterFrame\\TempPortraitAlphaMask", "CLAMPTOBLACKADDITIVE", "CLAMPTOBLACKADDITIVE")
			mask:SetAllPoints(icon)
			icon:AddMaskTexture(mask)
		end
	end

	-- pulsing "Recording" fill
	pulseAnim = status:CreateAnimationGroup()
	local pulse = pulseAnim:CreateAnimation("Alpha")
	pulse:SetFromAlpha(1)
	pulse:SetToAlpha(0.45)
	pulse:SetDuration(0.8)
	pulse:SetSmoothing("IN_OUT")
	pulseAnim:SetLooping("BOUNCE")

	-- fade-out after landing
	fadeAnim = frame:CreateAnimationGroup()
	local fade = fadeAnim:CreateAnimation("Alpha")
	fade:SetFromAlpha(1)
	fade:SetToAlpha(0)
	fade:SetDuration(1)
	fadeAnim:SetScript("OnFinished", function()
		frame:Hide()
		frame:SetAlpha(1)
		StopSparkle()
		mode = nil
	end)

	frame:SetScript("OnUpdate", OnUpdate)
	ApplyPosition()
	frame:EnableMouse(not b.locked)
	frame:Hide()
end

------------------------------------------------------------------------
-- Public functions (called from Core.lua)
------------------------------------------------------------------------

-- Known route: fill over the recorded time.
-- isEstimate = true for a starter-list time: the time text gets a "~" in front.
function Bar:StartFlight(fromName, toName, recorded, elapsed, isEstimate)
	total = (recorded and recorded > 0) and recorded or 1
	Begin("flight", fromName, toName, elapsed)
	estimate = isEstimate and "~" or ""
	SetColor(COLOR_FLIGHT)
	status:SetMinMaxValues(0, total)
	status:SetValue(0)
	iconFrame:Show()
	ShowCloud(true)
end

-- First flight of a route: full pulsing bar that counts up
function Bar:StartRecording(fromName, toName, elapsed)
	Begin("record", fromName, toName, elapsed)
	SetColor(COLOR_RECORD)
	status:SetMinMaxValues(0, 1)
	status:SetValue(1)
	iconFrame:Show()
	ShowCloud(false)
	pulseAnim:Play()
end

-- Landed. recordedDur = the new time if this flight was just recorded.
-- landed = true for a real landing at the destination (shows the sparkle).
function Bar:Finish(recordedDur, landed)
	if mode == "test" or not frame:IsShown() then
		if mode ~= "test" then mode = nil end
		return
	end
	pulseAnim:Stop()
	status:SetAlpha(1)
	mode = "done"
	UpdateTotals() -- includes this flight's last seconds and fare
	ShowCloud(false)
	if landed and sparkleFrame then
		-- flyer stays a moment, then the sparkle takes its place
		landTime = GetTime()
		sparkleFrame:ClearAllPoints()
		sparkleFrame:SetPoint("CENTER", status, "TOPLEFT", iconX, 8)
		sparkle:SetTexCoord(0, 0.25, 0, 1)
		sparkleFrame:Show()
	else
		iconFrame:Hide()
	end
	if recordedDur then
		SetColor(COLOR_DONE)
		status:SetMinMaxValues(0, 1)
		status:SetValue(1)
		leftText:SetText("Recorded")
		rightText:SetText(TT.FormatTime(recordedDur))
		doneToken = doneToken + 1
		local token = doneToken
		C_Timer.After(3, function()
			if token == doneToken and mode == "done" then fadeAnim:Play() end
		end)
	else
		fadeAnim:Play()
	end
end

-- Test bar (also shown while unlocked, so there is something to drag)
function Bar:ShowTest()
	if mode == "flight" or mode == "record" then return end
	total = 20
	Begin("test", "Stormwind, Elwynn", "Sentinel Hill, Westfall", 0)
	SetColor(COLOR_FLIGHT)
	status:SetMinMaxValues(0, total)
	iconFrame:Show()
	ShowCloud(true)
end

function Bar:HideTest()
	if mode == "test" then
		mode = nil
		frame:Hide()
	end
end

function Bar:ToggleTest()
	if mode == "test" then Bar:HideTest() else Bar:ShowTest() end
end

function Bar:SetLocked(locked)
	TT.db.bar.locked = locked and true or false
	-- locked: clicks go through the bar to the world
	frame:EnableMouse(not locked)
	if locked then
		Bar:HideTest()
	else
		Bar:ShowTest()
	end
end

-- /tt totals on|off (the setting itself is TaxiTimeDB.bar.showTotals)
function Bar:SetShowTotals(show)
	if not totalsText then return end
	if show then UpdateTotals() else totalsText:Hide() end
end

function Bar:ResetPosition()
	local d = TT.defaultsBar
	local b = TT.db.bar
	b.point, b.relPoint, b.x, b.y = d.point, d.relPoint, d.x, d.y
	ApplyPosition()
end
