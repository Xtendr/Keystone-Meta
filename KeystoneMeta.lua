-- KeystoneMeta.lua
-- Compact Mythic+ representation companion. Consumes packaged KeystoneMetaData only.
-- Author : Xtendr
-- License: MIT

local ADDON_NAME = "KeystoneMeta"

local DB_DEFAULTS = {
    minimap = { hide = false },
    uiScale = 1.0,
    bgOpacity = 1.0,
    font = "Friz Quadrata TT",
    fontOutline = "NONE",
    compactRows = false,
    followCurrentSpec = true,
    showDailyMovement = true,
    defaultView = "myspec",
    defaultRole = "auto",
    selectedSpecId = nil,
    selectedDungeonId = nil,
    selectedRole = "dps",
    windowPosition = nil,
    attachedOffset = nil,
    settingsPosition = nil,
    autoShowWithChallenges = true,
}

local DISCLAIMER = "Keystone Meta shows specialization representation among sampled top-ranked completed Mythic+ runs. Representation does not measure success rate or prove specialization strength."

local C = {
    gold      = { 1.00, 0.82, 0.00, 1 },
    goldDim   = { 0.78, 0.64, 0.28, 0.90 },
    text      = { 0.90, 0.90, 0.88, 1 },
    muted     = { 0.80, 0.80, 0.78, 1 },
    muted2    = { 0.70, 0.70, 0.68, 1 },
    green     = { 0.30, 0.80, 0.30, 1 },
    red       = { 0.80, 0.34, 0.30, 1 },
    hover     = { 0.64, 0.36, 0.86, 0.10 },
    selected  = { 0.64, 0.36, 0.86, 0.16 },
    element   = { 0.17, 0.17, 0.17, 1.00 },
    surface   = { 0.12, 0.12, 0.12, 1.00 },
    bg        = { 0.08, 0.08, 0.08, 0.95 },
    border    = { 0.78, 0.64, 0.28, 0.90 },
    inset     = { 0.06, 0.04, 0.08, 0.90 },
    purple    = { 0.64, 0.36, 0.86, 1 },
}

local BD_EDGE = {
    bgFile = "Interface\\Buttons\\WHITE8x8",
    edgeFile = "Interface\\Buttons\\WHITE8x8",
    edgeSize = 1,
}
local BD_PLAIN = { bgFile = "Interface\\Buttons\\WHITE8x8" }

local CHEVRON_ASSET = "Interface\\AddOns\\KeystoneMeta\\Assets\\chevron_right"

local MAIN_W = 318
local MAIN_H_PENDING = 220
local MAIN_H_POPULATED = 370
local MAIN_H_MAX = 480
local DETAIL_W, DETAIL_H = 348, 380
local SETTINGS_W = 340
local SETTINGS_LABEL_W = 118
local PAD = 12
local TOP_PAD = 10
local TITLE_H = 18
local SUBTITLE_GAP = 2
local SUBTITLE_H = 12
local AFTER_HEADER = 6
local SPEC_ROW_H = 26
local AFTER_SPEC = 2
local SUMMARY_H = 14
local AFTER_SUMMARY = 6
local SECTION_H = 16
local AFTER_SECTION = 2
local AFTER_LIST = 6
local FOOTER_H = 16
local BOTTOM_PAD = 10
local FOOTER_LINE_GAP = 8
local SCROLL_GUTTER = 26
local POPULATED_CHROME = TOP_PAD + TITLE_H + SUBTITLE_GAP + SUBTITLE_H + AFTER_HEADER
    + SPEC_ROW_H + AFTER_SPEC + SUMMARY_H + AFTER_SUMMARY
    + SECTION_H + AFTER_SECTION + AFTER_LIST + FOOTER_H + FOOTER_LINE_GAP + BOTTOM_PAD
local DIVIDER = { 0.25, 0.25, 0.25, 0.70 }
local ROW_H, ROW_H_COMPACT = 28, 24
local SHORT_COL_W = 48
local SHARE_COL_W = 44
local DELTA_COL_W = 42
local ROW_INSET = 8
local DETAIL_CHROME = TOP_PAD + TITLE_H + SUBTITLE_GAP + SUBTITLE_H + AFTER_HEADER + 26 + BOTTOM_PAD
local TITLE_SIZE = 14
local SPEC_SIZE = 13
local HEADER_SIZE = 12
local ROW_SIZE = 12
local META_SIZE = 12
local SCREEN_MARGIN = 16
local ATTACH_GAP = 10
local ACTION_BAR_CLEARANCE = 140
local TOOLTIP_MAX_WIDTH = 280
local TOOLTIP_EST_H = 160
local EMPTY_CELL = "--"
local SCOPE_SEP = "  ·  "

local ROLE_ORDER = { "tank", "healer", "dps" }
local ROLE_LABEL = { tank = "Tank", healer = "Healer", dps = "DPS" }

-- Lua 5.1 allows 200 locals per function. Keep constants above and the
-- rest of the addon inside this nested function so the main chunk stays under the cap.
local function KeystoneMetaBoot()

local mainFrame
local detailFrame
local settingsFrame
local dropdownCatcher
local challengesHooked = false
local holdStandaloneUntilReanchor = false
local dismissedThisChallengesSession = false
local hidingWithParent = false
local cutoffsWatched = false

local viewState = {
    specId = nil,
    dungeonId = nil,
    role = "dps",
}

local refreshFns = {}
local fontStrings = {}
local dungeonRows = {}
local specRows = {}

local RefreshUI
local PositionPanels
local HideMenus
local ApplyAnchor
local UpdateMinimapButton
local StyleScroll
local ShowMain
local ApplyCompanionVisibility
local specMenuOpen = false
local fallbackSpecMenus = {}

local function mixBD(frame)
    if not frame.SetBackdrop then
        Mixin(frame, BackdropTemplateMixin)
    end
end

local function paint(frame, color, border)
    mixBD(frame)
    frame:SetBackdrop(BD_EDGE)
    frame:SetBackdropColor(color[1], color[2], color[3], color[4] or 1)
    local b = border or C.border
    frame:SetBackdropBorderColor(b[1], b[2], b[3], b[4] or 1)
end

local function fill(frame, color)
    mixBD(frame)
    frame:SetBackdrop(BD_PLAIN)
    frame:SetBackdropColor(color[1], color[2], color[3], color[4] or 1)
end

local function BackgroundAlpha()
    local saved = KeystoneMetaDB
    local alpha = type(saved) == "table" and saved.bgOpacity
    if type(alpha) ~= "number" then
        return 1
    end
    if alpha < 0.20 then
        return 0.20
    end
    if alpha > 1 then
        return 1
    end
    return alpha
end

local function CompanionIsDismissed()
    if dismissedThisChallengesSession then
        return true
    end
    local saved = KeystoneMetaDB
    return type(saved) == "table" and saved.autoShowWithChallenges == false
end

local function SetCompanionDismissed(hidden)
    dismissedThisChallengesSession = hidden and true or false
    local saved = KeystoneMetaDB
    if type(saved) == "table" then
        saved.autoShowWithChallenges = not hidden
    end
end

local function ApplyGoldOutline(frame)
    if not frame then
        return
    end
    local outline = frame.outline
    if not outline then
        outline = CreateFrame("Frame", nil, frame, "BackdropTemplate")
        outline:SetAllPoints(frame)
        mixBD(outline)
        outline:SetBackdrop({
            edgeFile = "Interface\\Buttons\\WHITE8x8",
            edgeSize = 1,
        })
        outline:EnableMouse(false)
        frame.outline = outline
    end
    outline:SetFrameLevel((frame:GetFrameLevel() or 0) + 50)
    outline:SetBackdropColor(0, 0, 0, 0)
    outline:SetBackdropBorderColor(C.border[1], C.border[2], C.border[3], C.border[4] or 1)
end

local function ApplyCompanionChrome(frame)
    frame:SetToplevel(true)
    frame:SetClampedToScreen(true)
    frame:EnableMouse(true)
    local alpha = BackgroundAlpha()
    -- TooltipBackdropTemplate already matches Cutoffs. Fade the existing
    -- Center fill; do not replace it with an opaque color texture.
    if frame.NineSlice then
        if frame.NineSlice.Center and frame.NineSlice.Center.SetAlpha then
            frame.NineSlice.Center:SetAlpha(alpha)
        end
        if frame.Bg and frame.Bg.SetAlpha then
            frame.Bg:SetAlpha(alpha)
        end
        if frame.outline then
            ApplyGoldOutline(frame)
        end
        return
    end
    mixBD(frame)
    frame:SetBackdrop(BD_EDGE)
    frame:SetBackdropColor(C.bg[1], C.bg[2], C.bg[3], alpha)
    if frame.outline then
        frame:SetBackdropBorderColor(C.bg[1], C.bg[2], C.bg[3], alpha)
        ApplyGoldOutline(frame)
    else
        frame:SetBackdropBorderColor(C.border[1], C.border[2], C.border[3], C.border[4] or 1)
    end
end

local function CreateCompanionFrame(name, parent, strata)
    local frame
    local ok = pcall(function()
        frame = CreateFrame("Frame", name, parent, "TooltipBackdropTemplate")
    end)
    if not ok or not frame then
        frame = CreateFrame("Frame", name, parent, "BackdropTemplate")
    end
    ApplyCompanionChrome(frame)
    if strata then
        frame:SetFrameStrata(strata)
    end
    return frame
end

local function CreateThinDivider(parent)
    local line = parent:CreateTexture(nil, "BACKGROUND")
    line:SetHeight(1)
    line:SetColorTexture(DIVIDER[1], DIVIDER[2], DIVIDER[3], DIVIDER[4])
    return line
end

local function ApplyCompanionRowChrome(row)
    local hi = row:CreateTexture(nil, "BACKGROUND")
    hi:SetAllPoints()
    hi:SetColorTexture(C.hover[1], C.hover[2], C.hover[3], C.hover[4])
    hi:Hide()
    row._highlight = hi

    row.selected = row:CreateTexture(nil, "BACKGROUND", nil, -1)
    row.selected:SetAllPoints()
    row.selected:SetColorTexture(C.selected[1], C.selected[2], C.selected[3], C.selected[4])
    row.selected:Hide()

    row.accent = row:CreateTexture(nil, "ARTWORK")
    row.accent:SetPoint("TOPLEFT")
    row.accent:SetPoint("BOTTOMLEFT")
    row.accent:SetWidth(2)
    row.accent:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.85)
    row.accent:Hide()
end

local function CreateChromeCloseButton(parent, onClick)
    local btn = CreateFrame("Button", nil, parent)
    btn:SetSize(18, 18)
    btn:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -6, -8)
    btn:SetFrameLevel(parent:GetFrameLevel() + 5)
    local label = btn:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    label:SetPoint("CENTER", 0, 1)
    label:SetText("x")
    label:SetTextColor(C.muted[1], C.muted[2], C.muted[3], 1)
    if label.SetShadowOffset then
        label:SetShadowOffset(0, 0)
    end
    if label.SetShadowColor then
        label:SetShadowColor(0, 0, 0, 0)
    end
    btn.label = label
    btn:SetScript("OnEnter", function()
        label:SetTextColor(C.gold[1], C.gold[2], C.gold[3], 1)
    end)
    btn:SetScript("OnLeave", function()
        label:SetTextColor(C.muted[1], C.muted[2], C.muted[3], 1)
    end)
    btn:SetScript("OnClick", onClick)
    return btn
end

local function PanelHeightForStatus(status)
    if status == "ok" then
        return MAIN_H_POPULATED
    end
    return MAIN_H_PENDING
end

local function db()
    return KeystoneMetaDB
end

local function copyDefaults()
    if type(KeystoneMetaDB) ~= "table" then
        KeystoneMetaDB = {}
    end
    for key, value in pairs(DB_DEFAULTS) do
        if KeystoneMetaDB[key] == nil then
            if type(value) == "table" then
                local clone = {}
                for childKey, childValue in pairs(value) do
                    clone[childKey] = childValue
                end
                KeystoneMetaDB[key] = clone
            else
                KeystoneMetaDB[key] = value
            end
        end
    end
    KeystoneMetaDB.font = "Friz Quadrata TT"
    KeystoneMetaDB.fontOutline = "NONE"
end

local function InCombat()
    return InCombatLockdown and InCombatLockdown()
end

local function IsAddonLoaded(name)
    if C_AddOns and C_AddOns.IsAddOnLoaded then
        return C_AddOns.IsAddOnLoaded(name)
    end
    if IsAddOnLoaded then
        return IsAddOnLoaded(name)
    end
    return false
end

local function GetData()
    local data = KeystoneMetaData
    if type(data) ~= "table" or data.schemaVersion ~= 1 then
        return nil
    end
    return data
end

local function SortedDungeons()
    local list = {}
    local data = GetData()
    if not data or type(data.dungeons) ~= "table" then
        return list
    end
    for id, dungeon in pairs(data.dungeons) do
        if type(id) == "number" and type(dungeon) == "table" then
            list[#list + 1] = { id = id, dungeon = dungeon }
        end
    end
    table.sort(list, function(a, b)
        local left = a.dungeon.name or ""
        local right = b.dungeon.name or ""
        if left == right then
            return a.id < b.id
        end
        return left < right
    end)
    return list
end

local function PopulatedPanelHeight()
    local count = #SortedDungeons()
    if count < 1 then
        count = 8
    end
    local rowH = (db() and db().compactRows) and ROW_H_COMPACT or ROW_H
    local height = POPULATED_CHROME + count * rowH
    if height > MAIN_H_MAX then
        return MAIN_H_MAX
    end
    return height
end

local function RoleKey(blizzardRole)
    if blizzardRole == "TANK" then return "tank" end
    if blizzardRole == "HEALER" then return "healer" end
    return "dps"
end

local function SafeGetSpecialization()
    if C_SpecializationInfo and C_SpecializationInfo.GetSpecialization then
        local ok, spec = pcall(C_SpecializationInfo.GetSpecialization)
        if ok then return spec end
    end
    if GetSpecialization then
        local ok, spec = pcall(GetSpecialization)
        if ok then return spec end
    end
    return nil
end

local function SafeGetSpecInfo(specIndex)
    if C_SpecializationInfo and C_SpecializationInfo.GetSpecializationInfo then
        local ok, id, name, _, icon, role = pcall(C_SpecializationInfo.GetSpecializationInfo, specIndex)
        if ok and id then return id, name, icon, role end
    end
    if GetSpecializationInfo then
        local ok, id, name, _, icon, role = pcall(GetSpecializationInfo, specIndex)
        if ok and id then return id, name, icon, role end
    end
    return nil
end

local function SafeGetSpecByID(specId)
    if not specId then return nil end
    if GetSpecializationInfoByID then
        local ok, id, name, _, icon, role, classFile, className = pcall(GetSpecializationInfoByID, specId)
        if ok and id then
            return id, name, icon, role, classFile, className
        end
    end
    return specId, nil, nil, nil, nil, nil
end

local function PlayerSpec()
    local index = SafeGetSpecialization()
    if not index then return nil end
    local id, name, icon, role = SafeGetSpecInfo(index)
    if not id then return nil end
    local _, _, _, _, classFile, className = SafeGetSpecByID(id)
    return {
        id = id,
        name = name or ("Spec " .. id),
        icon = icon,
        role = RoleKey(role),
        className = className,
        classFile = classFile,
    }
end

local function CollectSpecs()
    local byId = {}
    local function store(id, name, icon, role, classFile, className)
        if not id then return end
        byId[id] = {
            id = id,
            name = name or ("Spec " .. id),
            icon = icon,
            role = role or "dps",
            className = className or "",
            classFile = classFile,
        }
    end

    local n = GetNumSpecializations and GetNumSpecializations() or 0
    for i = 1, n do
        local id, name, icon, role = SafeGetSpecInfo(i)
        local _, _, _, _, classFile, className = SafeGetSpecByID(id)
        store(id, name, icon, RoleKey(role), classFile, className)
    end

    local player = PlayerSpec()
    if player then
        store(player.id, player.name, player.icon, player.role, player.classFile, player.className)
    end

    for _, entry in ipairs(SortedDungeons()) do
        local roles = entry.dungeon.roles or {}
        for roleName, roleBlock in pairs(roles) do
            local specs = roleBlock and roleBlock.specs or {}
            for specId, spec in pairs(specs) do
                if type(specId) == "number" and type(spec) == "table" then
                    local _, name, icon, _, classFile, className = SafeGetSpecByID(specId)
                    store(
                        specId,
                        spec.name or name,
                        icon,
                        roleName,
                        classFile,
                        spec.className or className
                    )
                end
            end
        end
    end

    local list = {}
    for _, spec in pairs(byId) do
        list[#list + 1] = spec
    end
    table.sort(list, function(a, b)
        if a.role ~= b.role then return a.role < b.role end
        if a.name ~= b.name then return a.name < b.name end
        return a.id < b.id
    end)
    return list
end

local CLASS_MENU_ORDER = {
    "Death Knight",
    "Demon Hunter",
    "Druid",
    "Evoker",
    "Hunter",
    "Mage",
    "Monk",
    "Paladin",
    "Priest",
    "Rogue",
    "Shaman",
    "Warlock",
    "Warrior",
}

local function SafeGetNumSpecializations()
    if C_SpecializationInfo and C_SpecializationInfo.GetNumSpecializations then
        local ok, count = pcall(C_SpecializationInfo.GetNumSpecializations)
        if ok and type(count) == "number" then
            return count
        end
    end
    if GetNumSpecializations then
        local ok, count = pcall(GetNumSpecializations)
        if ok and type(count) == "number" then
            return count
        end
    end
    return 0
end

local function CurrentClassSpecs()
    local list = {}
    local count = SafeGetNumSpecializations()
    for i = 1, count do
        local id, name, icon, role = SafeGetSpecInfo(i)
        if id then
            local _, _, _, _, classFile, className = SafeGetSpecByID(id)
            list[#list + 1] = {
                id = id,
                name = name or ("Spec " .. id),
                icon = icon,
                role = RoleKey(role),
                classFile = classFile,
                className = className or "",
            }
        end
    end
    if #list == 0 then
        local player = PlayerSpec()
        if player then
            list[1] = player
        end
    end
    return list
end

local function CollectSpecsByClass()
    local groups = {}
    local byName = {}
    for _, spec in ipairs(CollectSpecs()) do
        local className = spec.className
        if type(className) ~= "string" or className == "" then
            className = spec.classFile or "Other"
        end
        local group = byName[className]
        if not group then
            group = { name = className, specs = {} }
            byName[className] = group
            groups[#groups + 1] = group
        end
        local seen = false
        for _, existing in ipairs(group.specs) do
            if existing.id == spec.id then
                seen = true
                break
            end
        end
        if not seen then
            group.specs[#group.specs + 1] = spec
        end
    end
    local order = {}
    for i, name in ipairs(CLASS_MENU_ORDER) do
        order[name] = i
    end
    table.sort(groups, function(a, b)
        local ia, ib = order[a.name] or 100, order[b.name] or 100
        if ia ~= ib then
            return ia < ib
        end
        return a.name < b.name
    end)
    for _, group in ipairs(groups) do
        table.sort(group.specs, function(a, b)
            if a.role ~= b.role then
                return a.role < b.role
            end
            if a.name ~= b.name then
                return a.name < b.name
            end
            return a.id < b.id
        end)
    end
    return groups
end

local function SpecMenuLabel(spec)
    local role = ROLE_LABEL[spec.role] or spec.role or "DPS"
    local name = spec.name or ("Spec " .. tostring(spec.id))
    if spec.icon then
        return string.format("|T%s:16:16:0:0|t %s - %s", spec.icon, name, role)
    end
    return string.format("%s - %s", name, role)
end

local function FindSpecMeta(specId)
    if specId then
        for _, spec in ipairs(CollectSpecs()) do
            if spec.id == specId then
                return spec
            end
        end
        local _, name, icon, role, classFile, className = SafeGetSpecByID(specId)
        return {
            id = specId,
            name = name or ("Spec " .. tostring(specId)),
            icon = icon,
            className = className or "",
            classFile = classFile,
            role = RoleKey(role),
        }
    end
    return {
        id = nil,
        name = "Specialization",
        icon = nil,
        className = "",
        classFile = nil,
        role = "dps",
    }
end

local function DungeonUseful(dungeon)
    local sample = dungeon and dungeon.sample or {}
    return sample.status == "ok" and (sample.validRuns or 0) > 0
end

local function SpecInDungeon(dungeon, specId, role)
    local roleBlock = dungeon and dungeon.roles and dungeon.roles[role]
    local spec = roleBlock and roleBlock.specs and roleBlock.specs[specId]
    if type(spec) == "table" then
        return spec
    end
    return nil
end

local function RoleSpecList(dungeon, role)
    local list = {}
    local roleBlock = dungeon and dungeon.roles and dungeon.roles[role]
    if not (roleBlock and roleBlock.specs) then
        return list
    end
    for specId, spec in pairs(roleBlock.specs) do
        if type(specId) == "number" and type(spec) == "table" then
            list[#list + 1] = { id = specId, spec = spec }
        end
    end
    table.sort(list, function(a, b)
        local ra, rb = a.spec.representationRank or 999, b.spec.representationRank or 999
        if ra ~= rb then return ra < rb end
        return a.id < b.id
    end)
    return list
end

local function SnapshotStatus()
    local data = GetData()
    if not data then
        return "pending_season_data"
    end
    if data.status == "pending_season_data" then
        return "pending_season_data"
    end
    if data.season and data.season.slug == "pending" then
        return "pending_season_data"
    end

    local anyUseful = false
    local anyInsufficient = false
    local anyDungeon = false
    for _, entry in ipairs(SortedDungeons()) do
        anyDungeon = true
        local sample = entry.dungeon.sample or {}
        if DungeonUseful(entry.dungeon) then
            anyUseful = true
        elseif sample.status == "insufficient_data" then
            anyInsufficient = true
        end
    end
    if anyUseful then
        return "ok"
    end
    if anyInsufficient then
        return "insufficient_data"
    end
    if not anyDungeon then
        return "pending_season_data"
    end
    return "pending_season_data"
end

local function FormatPct(value)
    if type(value) ~= "number" then return nil end
    return string.format("%.1f%%", value)
end

local function FormatDelta(value)
    if type(value) ~= "number" then return nil end
    if math.abs(value) < 0.05 then return EMPTY_CELL end
    if value > 0 then
        return string.format("+%.1f", value)
    end
    return string.format("-%.1f", math.abs(value))
end

local function DeltaColor(value)
    if type(value) ~= "number" or math.abs(value) < 0.05 then
        return C.muted
    end
    if value > 0 then
        return C.green
    end
    return C.red
end

local function FormatKey(value)
    if type(value) ~= "number" or value <= 0 then return nil end
    return string.format("+%d", value)
end

local function ClearFontShadow(fontString)
    if not fontString then
        return
    end
    if fontString.SetShadowOffset then
        fontString:SetShadowOffset(0, 0)
    end
    if fontString.SetShadowColor then
        fontString:SetShadowColor(0, 0, 0, 0)
    end
end

local function ApplyFont(fontString, size, color, flags)
    if not fontString then return end
    if color then
        fontString:SetTextColor(color[1], color[2], color[3], color[4] or 1)
    end
    ClearFontShadow(fontString)
end

local function TrackFontString(fs)
    if fs then
        fontStrings[#fontStrings + 1] = fs
    end
    return fs
end

local function CreateFS(parent, template, size, color)
    local fs = parent:CreateFontString(nil, "OVERLAY", template or "GameFontHighlight")
    ApplyFont(fs, size, color)
    return TrackFontString(fs)
end

local function SafeSetText(fontString, text)
    if not fontString then return end
    if not fontString.GetFont or not fontString:GetFont() then
        ApplyFont(fontString, ROW_SIZE, C.text)
    end
    fontString:SetText(text or "")
end

local function ClassColor(classFile)
    local colors = RAID_CLASS_COLORS and classFile and RAID_CLASS_COLORS[classFile]
    if colors then
        return { colors.r, colors.g, colors.b, 1 }
    end
    return C.text
end

local function SetRoleIcon(texture, role)
    texture:SetTexture("Interface\\LFGFrame\\UI-LFG-ICON-PORTRAITROLES")
    if role == "tank" then
        texture:SetTexCoord(0, 19 / 64, 22 / 64, 41 / 64)
    elseif role == "healer" then
        texture:SetTexCoord(20 / 64, 39 / 64, 1 / 64, 20 / 64)
    else
        texture:SetTexCoord(20 / 64, 39 / 64, 22 / 64, 41 / 64)
    end
end

local function SetDropdownChevron(texture, open)
    if not texture then return end
    texture:SetTexture(CHEVRON_ASSET)
    texture:SetTexCoord(0, 1, 0, 1)
    texture:SetSize(18, 18)
    texture:SetVertexColor(0.85, 0.85, 0.85, 0.95)
    if texture.SetRotation then
        texture:SetRotation(open and (math.pi / 2) or (-math.pi / 2))
    end
end

local function SetHelpIcon(texture)
    if not texture then return end
    texture:SetTexture("Interface\\COMMON\\help-i")
    if texture.GetTexture and not texture:GetTexture() then
        texture:SetTexture("Interface\\FriendsFrame\\InformationIcon")
    end
    texture:SetVertexColor(1, 0.86, 0.35, 1)
end

local function ParseGeneratedAt(text)
    if type(text) ~= "string" then return nil end
    local y, m, d, hh, mm = text:match("^(%d+)%-(%d+)%-(%d+) (%d+):(%d+) UTC$")
    if not y then return nil end
    return time({
        year = tonumber(y),
        month = tonumber(m),
        day = tonumber(d),
        hour = tonumber(hh),
        min = tonumber(mm),
        sec = 0,
    })
end

local function FreshnessLabel()
    local data = GetData()
    if not data then return nil end
    if SnapshotStatus() ~= "ok" then
        return nil
    end
    local stamp = ParseGeneratedAt(data.generatedAt)
    if not stamp then
        return data.generatedAt
    end
    local age = time() - stamp
    if age > 36 * 3600 then
        return "Stale"
    end
    if age < 3600 then
        return "Updated just now"
    end
    return string.format("Updated %dh ago", math.floor(age / 3600))
end

local function ScopeLabel()
    local data = GetData()
    local scope = data and data.scope or {}
    local affix = (scope.affixMode == "current") and "Current affixes" or "Full season"
    local world = (data and data.isSynthetic) and "SYNTHETIC VISUAL TEST" or "World"
    return table.concat({ world, affix }, SCOPE_SEP)
end

local function SampleCoverageLabel()
    local runs = {}
    for _, entry in ipairs(SortedDungeons()) do
        if DungeonUseful(entry.dungeon) then
            local valid = entry.dungeon.sample and entry.dungeon.sample.validRuns
            if type(valid) == "number" and valid > 0 then
                runs[#runs + 1] = valid
            end
        end
    end
    if #runs == 0 then
        return nil
    end
    local lowest, highest = runs[1], runs[1]
    for _, value in ipairs(runs) do
        if value < lowest then lowest = value end
        if value > highest then highest = value end
    end
    if lowest == highest then
        return string.format("%d runs/dungeon", highest)
    end
    return string.format("Up to %d runs/dungeon", highest)
end

local function PopulatedFooterText()
    local parts = {
        SampleCoverageLabel() or (tostring(SampleTarget()) .. " runs/dungeon"),
        "Raider.IO",
    }
    local fresh = FreshnessLabel()
    if fresh and fresh ~= "" then
        parts[#parts + 1] = fresh
    end
    return table.concat(parts, SCOPE_SEP)
end

local function PendingFooterText()
    return "Awaiting first Raider.IO snapshot"
end

local function SampleTarget()
    local data = GetData()
    local scope = data and data.scope or {}
    return tonumber(scope.targetRunsPerDungeon) or 500
end

local function CurrentSpecId()
    if db() and db().followCurrentSpec then
        local player = PlayerSpec()
        if player then return player.id end
    end
    return viewState.specId or (db() and db().selectedSpecId)
end

local function CurrentRole()
    local spec = FindSpecMeta(CurrentSpecId())
    return spec and spec.role or "dps"
end

local function AverageForSpec(specId, role)
    local shares, ranks = {}, {}
    local roleCount = 0
    for _, entry in ipairs(SortedDungeons()) do
        if DungeonUseful(entry.dungeon) then
            local spec = SpecInDungeon(entry.dungeon, specId, role)
            local roleBlock = entry.dungeon.roles and entry.dungeon.roles[role]
            local specCount = 0
            if roleBlock and roleBlock.specs then
                for _ in pairs(roleBlock.specs) do specCount = specCount + 1 end
            end
            roleCount = math.max(roleCount, specCount)
            if spec and type(spec.roleSharePct) == "number" then
                shares[#shares + 1] = spec.roleSharePct
                if type(spec.representationRank) == "number" then
                    ranks[#ranks + 1] = spec.representationRank
                end
            end
        end
    end
    local function mean(values)
        if #values == 0 then return nil end
        local sum = 0
        for _, value in ipairs(values) do sum = sum + value end
        return sum / #values
    end
    return {
        share = mean(shares),
        rank = mean(ranks),
        roleCount = roleCount,
        samples = #shares,
    }
end

local function HideCatcher()
    if not dropdownCatcher then return end
    dropdownCatcher:Hide()
    dropdownCatcher:EnableMouse(false)
end

local function EnsureCatcher()
    if dropdownCatcher then return dropdownCatcher end
    dropdownCatcher = CreateFrame("Frame", "KeystoneMetaMenuCatcher", UIParent)
    dropdownCatcher:SetAllPoints()
    -- DIALOG sits below TOOLTIP and below Blizzard MenuUtil frames.
    -- A TOOLTIP catcher previously intercepted spec-row clicks.
    dropdownCatcher:SetFrameStrata("DIALOG")
    dropdownCatcher:SetFrameLevel(1)
    dropdownCatcher:EnableMouse(false)
    dropdownCatcher:Hide()
    dropdownCatcher:SetScript("OnShow", function(self)
        self:EnableMouse(true)
    end)
    dropdownCatcher:SetScript("OnHide", function(self)
        self:EnableMouse(false)
    end)
    dropdownCatcher:SetScript("OnMouseDown", HideMenus)
    return dropdownCatcher
end

local function CloseBlizzardMenus()
    if Menu and Menu.GetManager then
        local manager = Menu.GetManager()
        if manager then
            if manager.CloseMenu then
                pcall(manager.CloseMenu, manager)
            end
            if manager.CloseMenus then
                pcall(manager.CloseMenus, manager)
            end
        end
    end
end

local function HideFallbackSpecMenus()
    for _, menu in ipairs(fallbackSpecMenus) do
        if menu and menu.Hide then
            menu:Hide()
        end
    end
end

local function MarkSpecMenuClosed()
    specMenuOpen = false
    if mainFrame and mainFrame.specChevron then
        SetDropdownChevron(mainFrame.specChevron, false)
    end
end

HideMenus = function()
    HideCatcher()
    CloseBlizzardMenus()
    HideFallbackSpecMenus()
    MarkSpecMenuClosed()
    if settingsFrame and settingsFrame.activeMenu then
        settingsFrame.activeMenu:Hide()
        settingsFrame.activeMenu = nil
    end
end

local function ShowCatcher(onClose)
    local catcher = EnsureCatcher()
    catcher:SetScript("OnMouseDown", onClose or HideMenus)
    catcher:Show()
end

local function Truncate(fs, text)
    SafeSetText(fs, text or "")
    fs:SetWordWrap(false)
end

local function ShowRowHighlight(row, shown)
    if not row or not row._highlight then
        return
    end
    row._highlight:SetShown(shown and true or false)
end

local function GetFrameRect(frame)
    if not frame or not frame.IsShown or not frame:IsShown() then
        return nil
    end
    local left, right, top, bottom = frame:GetLeft(), frame:GetRight(), frame:GetTop(), frame:GetBottom()
    if not (left and right and top and bottom) then
        return nil
    end
    return { left = left, right = right, top = top, bottom = bottom }
end

local function GetObjectivesRect()
    return GetFrameRect(_G.ObjectiveTrackerFrame) or GetFrameRect(_G.ObjectiveTrackerManager)
end

local function RectsOverlap(a, b)
    if not a or not b then
        return false
    end
    return a.left < b.right and a.right > b.left and a.bottom < b.top and a.top > b.bottom
end

local function OverlapArea(a, b)
    if not RectsOverlap(a, b) then
        return 0
    end
    local width = math.min(a.right, b.right) - math.max(a.left, b.left)
    local height = math.min(a.top, b.top) - math.max(a.bottom, b.bottom)
    return math.max(0, width) * math.max(0, height)
end

local function ChooseTooltipSide(
    ownerLeft, ownerRight, ownerTop, ownerBottom,
    parentLeft, parentRight, parentTop, parentBottom,
    tooltipW, tooltipH, mainRect, objectivesRect
)
    tooltipW = tooltipW or TOOLTIP_MAX_WIDTH
    tooltipH = tooltipH or TOOLTIP_EST_H
    parentLeft = parentLeft or 0
    parentRight = parentRight or 1600
    parentTop = parentTop or 900
    parentBottom = parentBottom or 0
    local function placed(side)
        local left, right
        if side == "right" then
            left = (ownerRight or 0) + 6
            right = left + tooltipW
        else
            right = (ownerLeft or 0) - 6
            left = right - tooltipW
        end
        local top = (ownerTop or parentTop) + 6
        return { left = left, right = right, top = top, bottom = top - tooltipH, side = side }
    end
    local function hasRoom(side)
        if side == "right" then
            return parentRight - (ownerRight or 0) >= (tooltipW + SCREEN_MARGIN)
        end
        return (ownerLeft or 0) - parentLeft >= (tooltipW + SCREEN_MARGIN)
    end
    local function score(rect)
        local value = 0
        if rect.side == "right" then
            value = value + (parentRight - (ownerRight or 0))
        else
            value = value + ((ownerLeft or 0) - parentLeft)
        end
        if rect.left < parentLeft + SCREEN_MARGIN or rect.right > parentRight - SCREEN_MARGIN then
            value = value - 10000
        end
        if objectivesRect and OverlapArea(rect, objectivesRect) > 0 then
            value = value - 5000
        end
        if mainRect then
            local mainArea = math.max(1, (mainRect.right - mainRect.left) * (mainRect.top - mainRect.bottom))
            local covered = OverlapArea(rect, mainRect)
            if covered > (mainArea * 0.45) then
                value = value - 8000
            else
                value = value - (covered * 0.02)
            end
        end
        return value
    end
    local right = placed("right")
    local left = placed("left")
    if objectivesRect then
        if OverlapArea(right, objectivesRect) > 0 and hasRoom("left") then
            return "left"
        end
        if OverlapArea(left, objectivesRect) > 0 and hasRoom("right") then
            return "right"
        end
    end
    if score(left) > score(right) then
        return "left"
    end
    return "right"
end

local function AnchorTooltipOutside(owner, tooltip)
    tooltip:ClearAllPoints()
    local parentLeft = (UIParent and UIParent:GetLeft()) or 0
    local parentRight = (UIParent and UIParent:GetRight()) or 1600
    local parentBottom = (UIParent and UIParent:GetBottom()) or 0
    local parentTop = (UIParent and UIParent:GetTop()) or 900
    local ownerLeft = owner:GetLeft()
    local ownerRight = owner:GetRight()
    local ownerTop = owner:GetTop()
    local ownerBottom = owner:GetBottom()
    if not (ownerLeft and ownerRight and ownerTop and ownerBottom) then
        tooltip:SetPoint("BOTTOMLEFT", owner, "TOPRIGHT", 6, 6)
        return
    end
    local width = math.min(tooltip:GetWidth() or TOOLTIP_MAX_WIDTH, TOOLTIP_MAX_WIDTH)
    local height = tooltip:GetHeight() or TOOLTIP_EST_H
    local side = ChooseTooltipSide(
        ownerLeft, ownerRight, ownerTop, ownerBottom,
        parentLeft, parentRight, parentTop, parentBottom,
        width, height, GetFrameRect(mainFrame), GetObjectivesRect()
    )
    if side == "left" then
        tooltip:SetPoint("BOTTOMRIGHT", owner, "TOPLEFT", -6, 6)
    else
        tooltip:SetPoint("BOTTOMLEFT", owner, "TOPRIGHT", 6, 6)
    end
    local tipLeft, tipBottom = tooltip:GetLeft(), tooltip:GetBottom()
    local tipRight, tipTop = tooltip:GetRight(), tooltip:GetTop()
    if tipLeft and tipBottom and tipRight and tipTop then
        local shiftX, shiftY = 0, 0
        if tipLeft < parentLeft + SCREEN_MARGIN then
            shiftX = (parentLeft + SCREEN_MARGIN) - tipLeft
        elseif tipRight > parentRight - SCREEN_MARGIN then
            shiftX = (parentRight - SCREEN_MARGIN) - tipRight
        end
        if tipBottom < parentBottom + SCREEN_MARGIN then
            shiftY = (parentBottom + SCREEN_MARGIN) - tipBottom
        elseif tipTop > parentTop - SCREEN_MARGIN then
            shiftY = (parentTop - SCREEN_MARGIN) - tipTop
        end
        if shiftX ~= 0 or shiftY ~= 0 then
            tooltip:ClearAllPoints()
            tooltip:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", tipLeft + shiftX, tipBottom + shiftY)
        end
    end
end

local function ClampOwnedTooltipLines(tooltip)
    local name = tooltip and tooltip.GetName and tooltip:GetName()
    local count = tooltip and tooltip.NumLines and tooltip:NumLines()
    if not name or not count then
        return
    end
    local pad = 12
    local inner = TOOLTIP_MAX_WIDTH - pad * 2
    local i = 1
    while i <= count do
        local left = _G[name .. "TextLeft" .. i]
        local right = _G[name .. "TextRight" .. i]
        if right and right.IsShown and right:IsShown() then
            right:ClearAllPoints()
            if left then
                right:SetPoint("TOP", left, "TOP", 0, 0)
            end
            right:SetPoint("RIGHT", tooltip, "RIGHT", -pad, 0)
            right:SetJustifyH("RIGHT")
            local leftW = 0
            if left and left.GetStringWidth then
                leftW = left:GetStringWidth() or 0
            end
            if right.SetWidth then
                right:SetWidth(math.max(48, inner - leftW - 8))
            end
            if right.SetWordWrap then
                right:SetWordWrap(true)
            end
        elseif left and left.SetWidth then
            left:SetWidth(inner)
            if left.SetWordWrap then
                left:SetWordWrap(true)
            end
        end
        i = i + 1
    end
end

local function FitOwnedTooltip(tooltip)
    if tooltip and tooltip.SetWidth and (tooltip:GetWidth() or 0) > TOOLTIP_MAX_WIDTH then
        tooltip:SetWidth(TOOLTIP_MAX_WIDTH)
    end
    ClampOwnedTooltipLines(tooltip)
end

local function ShowOwnedTooltip(owner, tooltip, builder)
    tooltip:SetOwner(owner, "ANCHOR_NONE")
    tooltip:ClearLines()
    if tooltip.SetMinimumWidth then
        tooltip:SetMinimumWidth(1)
    end
    builder(owner, tooltip)
    tooltip:Show()
    FitOwnedTooltip(tooltip)
    AnchorTooltipOutside(owner, tooltip)
end

local function WireTooltip(owner, builder)
    owner:SetScript("OnEnter", function(self)
        ShowRowHighlight(self, true)
        ShowOwnedTooltip(self, GameTooltip, builder)
    end)
    owner:SetScript("OnLeave", function(self)
        ShowRowHighlight(self, false)
        GameTooltip:Hide()
    end)
end

local function InfoTooltip(owner, tooltip)
    tooltip:SetOwner(owner, "ANCHOR_NONE")
    tooltip:ClearLines()
    if tooltip.SetMinimumWidth then
        tooltip:SetMinimumWidth(1)
    end
    tooltip:SetText("Keystone Meta", C.gold[1], C.gold[2], C.gold[3])
    tooltip:AddLine("Role share", C.gold[1], C.gold[2], C.gold[3])
    tooltip:AddLine("Share of this role's sampled seats.", 0.90, 0.90, 0.90, true)
    tooltip:AddLine("Run presence", C.gold[1], C.gold[2], C.gold[3])
    tooltip:AddLine("Share of sampled runs that included this spec.", 0.90, 0.90, 0.90, true)
    tooltip:AddLine("Highest key", C.gold[1], C.gold[2], C.gold[3])
    tooltip:AddLine("Highest timed key in the sample.", 0.90, 0.90, 0.90, true)
    tooltip:AddLine("Sample", C.gold[1], C.gold[2], C.gold[3])
    tooltip:AddLine("World, full season. Source: Raider.IO", C.muted[1], C.muted[2], C.muted[3], true)
    tooltip:AddLine("Representation shows popularity in the sampled runs. It does not measure specialization strength or success rate.", C.gold[1], C.gold[2], C.gold[3], true)
    tooltip:Show()
    FitOwnedTooltip(tooltip)
    AnchorTooltipOutside(owner, tooltip)
end

local function DungeonRowTooltip(row, tooltip)
    local dungeon = row.dungeon
    local specMeta = row.specMeta
    local spec = row.spec
    local title = (dungeon and dungeon.name or "Dungeon")
    if specMeta and specMeta.name then
        title = title .. " — " .. specMeta.name
    end
    tooltip:SetText(title, C.gold[1], C.gold[2], C.gold[3])

    if not DungeonUseful(dungeon) then
        local sample = dungeon and dungeon.sample or {}
        if sample.status == "insufficient_data" then
            tooltip:AddLine("Not enough ranked runs yet", 1, 1, 1, true)
        else
            tooltip:AddLine("Season data pending. Keystone Meta is waiting for its first validated Raider.IO snapshot.", 1, 1, 1, true)
        end
        tooltip:AddLine(" ", 1, 1, 1)
        tooltip:AddLine("Representation is popularity in the sample, not power.", 0.7, 0.7, 0.7, true)
        return
    end

    if spec then
        if type(spec.roleSharePct) == "number" then
            tooltip:AddDoubleLine("Role share", FormatPct(spec.roleSharePct), 0.7, 0.7, 0.7, 1, 1, 1)
        end
        if type(spec.representationRank) == "number" and specMeta then
            local count = 0
            local roleBlock = dungeon.roles and dungeon.roles[specMeta.role]
            if roleBlock and roleBlock.specs then
                for _ in pairs(roleBlock.specs) do
                    count = count + 1
                end
            end
            if count > 0 then
                tooltip:AddDoubleLine(
                    "Representation rank",
                    string.format("#%d of %d %s", spec.representationRank, count, ROLE_LABEL[specMeta.role] or specMeta.role),
                    0.7, 0.7, 0.7, 1, 1, 1
                )
            end
        end
        if type(spec.runPresencePct) == "number" then
            tooltip:AddDoubleLine("Run presence", FormatPct(spec.runPresencePct), 0.7, 0.7, 0.7, 1, 1, 1)
        end
        local key = FormatKey(spec.highestKey)
        if key then
            tooltip:AddDoubleLine("Highest key observed", key, 0.7, 0.7, 0.7, 1, 1, 1)
        end
        if type(spec.appearanceCount) == "number" and spec.appearanceCount > 0 then
            tooltip:AddDoubleLine("Appearances", tostring(spec.appearanceCount), 0.7, 0.7, 0.7, 1, 1, 1)
        end
        local sample = dungeon.sample or {}
        if type(sample.validRuns) == "number" and sample.validRuns > 0 then
            tooltip:AddDoubleLine("Sample", string.format("%d runs", sample.validRuns), 0.7, 0.7, 0.7, 1, 1, 1)
        end
        if db() and db().showDailyMovement and type(spec.deltaPercentagePoints) == "number" then
            local delta = spec.deltaPercentagePoints
            local text
            if math.abs(delta) < 0.05 then
                text = "unchanged since last update"
            elseif delta > 0 then
                text = string.format("+%.1f since last update", delta)
            else
                text = string.format("%.1f since last update", delta)
            end
            tooltip:AddDoubleLine("Change", text, 0.7, 0.7, 0.7, 1, 1, 1)
        end
    else
        tooltip:AddLine("This specialization did not appear in the sampled seats for this dungeon.", 1, 1, 1, true)
    end
    tooltip:AddLine(" ", 1, 1, 1)
    tooltip:AddLine("Representation is popularity in the sample, not power.", 0.7, 0.7, 0.7, true)
end

local function SpecRowTooltip(row, tooltip)
    local spec = row.spec
    local name = spec and spec.name or "Specialization"
    tooltip:SetText(name, C.gold[1], C.gold[2], C.gold[3])
    if type(spec.roleSharePct) == "number" then
        tooltip:AddDoubleLine("Role share", FormatPct(spec.roleSharePct), 0.7, 0.7, 0.7, 1, 1, 1)
    end
    if type(spec.runPresencePct) == "number" then
        tooltip:AddDoubleLine("Run presence", FormatPct(spec.runPresencePct), 0.7, 0.7, 0.7, 1, 1, 1)
    end
    local key = FormatKey(spec.highestKey)
    if key then
        tooltip:AddDoubleLine("Highest key observed", key, 0.7, 0.7, 0.7, 1, 1, 1)
    end
    if type(spec.appearanceCount) == "number" and spec.appearanceCount > 0 then
        tooltip:AddDoubleLine("Appearances", tostring(spec.appearanceCount), 0.7, 0.7, 0.7, 1, 1, 1)
    end
    local dungeon = row.dungeon
    local sample = dungeon and dungeon.sample or {}
    if type(sample.validRuns) == "number" and sample.validRuns > 0 then
        tooltip:AddDoubleLine("Sample", string.format("%d runs", sample.validRuns), 0.7, 0.7, 0.7, 1, 1, 1)
    end
    local seats = 0
    local role = viewState.detailRole or CurrentRole()
    if role == "tank" then seats = sample.resolvedTankSeats or 0
    elseif role == "healer" then seats = sample.resolvedHealerSeats or 0
    else seats = sample.resolvedDpsSeats or 0 end
    if seats > 0 then
        tooltip:AddDoubleLine("Resolved seats", tostring(seats), 0.7, 0.7, 0.7, 1, 1, 1)
    end
    tooltip:AddLine(" ", 1, 1, 1)
    tooltip:AddLine(DISCLAIMER, 0.7, 0.7, 0.7, true)
end

local function ReleaseRows(pool)
    for _, row in ipairs(pool) do
        row.busy = false
        row:Hide()
        row:EnableMouse(false)
    end
end

local function AcquireRow(pool, parent, factory)
    for _, row in ipairs(pool) do
        if not row.busy then
            row.busy = true
            row:SetParent(parent)
            row:EnableMouse(true)
            row:Show()
            return row
        end
    end
    local row = factory(parent)
    row.busy = true
    row:EnableMouse(true)
    pool[#pool + 1] = row
    return row
end

local function LayoutRows(container, pool, rowHeight)
    local y = 0
    local shown = 0
    for _, row in ipairs(pool) do
        if row.busy then
            row:ClearAllPoints()
            row:SetPoint("TOPLEFT", container, "TOPLEFT", 0, -y)
            row:SetPoint("TOPRIGHT", container, "TOPRIGHT", 0, -y)
            row:SetHeight(rowHeight)
            y = y + rowHeight
            shown = shown + 1
        end
    end
    container:SetHeight(math.max(rowHeight, shown * rowHeight))
    return shown
end

local function IsChallengesVisible()
    if not (ChallengesFrame and ChallengesFrame.IsShown and ChallengesFrame:IsShown()) then
        return false
    end
    if PVEFrame and PVEFrame.IsShown and not PVEFrame:IsShown() then
        return false
    end
    return true
end

local function CutoffsIsUsable()
    local panel = _G.KeystoneCutoffsPanel
    if not panel or not panel.IsShown or not panel:IsShown() then
        return false
    end
    return true
end

local function HasHorizontalSpace(anchorRight, panelWidth, scale)
    if not UIParent or not anchorRight then
        return false
    end
    local parentRight = UIParent:GetRight()
    if not parentRight then
        return false
    end
    local available = (parentRight - SCREEN_MARGIN) - (anchorRight + ATTACH_GAP)
    return available >= ((panelWidth or MAIN_W) * (scale or 1))
end

local function ClampRect(left, bottom, width, height, parentLeft, parentBottom, parentRight, parentTop, margin, scale)
    margin = margin or SCREEN_MARGIN
    scale = scale or 1
    local effW, effH = width * scale, height * scale
    local minLeft, minBottom = parentLeft + margin, parentBottom + margin
    local maxLeft, maxBottom = parentRight - margin - effW, parentTop - margin - effH
    if left < minLeft then left = minLeft end
    if left > maxLeft then left = maxLeft end
    if bottom < minBottom then bottom = minBottom end
    if bottom > maxBottom then bottom = maxBottom end
    if left < minLeft then left = minLeft end
    if bottom < minBottom then bottom = minBottom end
    return left, bottom
end

local function DefaultStandalonePoint(panelWidth, panelHeight, scale)
    local parentRight = (UIParent and UIParent:GetRight()) or 1600
    local parentTop = (UIParent and UIParent:GetTop()) or 900
    local parentLeft = (UIParent and UIParent:GetLeft()) or 0
    local parentBottom = (UIParent and UIParent:GetBottom()) or 0
    scale = scale or 1
    local left = parentRight - SCREEN_MARGIN - (panelWidth * scale) - 32
    local bottom = math.max(parentBottom + SCREEN_MARGIN + ACTION_BAR_CLEARANCE, (parentTop - parentBottom - panelHeight * scale) / 2)
    return ClampRect(left, bottom, panelWidth, panelHeight, parentLeft, parentBottom, parentRight, parentTop, SCREEN_MARGIN, scale)
end

local function ChoosePlacement(panelWidth, scale)
    if holdStandaloneUntilReanchor or not IsChallengesVisible() then
        return "standalone"
    end
    if CutoffsIsUsable() then
        return "attach_cutoffs"
    end
    local challengesRight = ChallengesFrame and ChallengesFrame.GetRight and ChallengesFrame:GetRight()
    if challengesRight == nil then
        return "pending_attach"
    end
    return "attach_challenges"
end

local function ClampFrameToUIParent(frame)
    if not frame or not UIParent then return end
    local left, bottom = frame:GetLeft(), frame:GetBottom()
    local right, top = frame:GetRight(), frame:GetTop()
    if not (left and bottom and right and top) then return end
    local parentLeft = UIParent:GetLeft() or 0
    local parentBottom = UIParent:GetBottom() or 0
    local parentRight = UIParent:GetRight() or left
    local parentTop = UIParent:GetTop() or top
    local width = right - left
    local height = top - bottom
    local newLeft, newBottom = ClampRect(left, bottom, width, height, parentLeft, parentBottom, parentRight, parentTop, SCREEN_MARGIN, 1)
    if math.abs(newLeft - left) > 0.5 or math.abs(newBottom - bottom) > 0.5 then
        frame:ClearAllPoints()
        frame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", newLeft, newBottom)
    end
end

local function SaveStandalonePosition()
    if not mainFrame or not db() then return end
    if IsChallengesVisible() then return end
    local left, bottom = mainFrame:GetLeft(), mainFrame:GetBottom()
    if not (left and bottom) then return end
    db().windowPosition = {
        point = "BOTTOMLEFT",
        relPoint = "BOTTOMLEFT",
        x = left,
        y = bottom,
    }
end

local function RestoreStandalonePosition()
    if not mainFrame then return end
    mainFrame:ClearAllPoints()
    mainFrame:SetParent(UIParent)
    local scale = (db() and db().uiScale) or 1
    local pos = db() and db().windowPosition
    if pos and pos.point then
        mainFrame:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x or 0, pos.y or 0)
    else
        local left, bottom = DefaultStandalonePoint(MAIN_W, mainFrame:GetHeight() or MAIN_H_PENDING, scale)
        mainFrame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", left, bottom)
    end
    ClampFrameToUIParent(mainFrame)
end

local function ScheduleReanchor()
    if not C_Timer or not C_Timer.After then
        return
    end
    C_Timer.After(0, function()
        if mainFrame and mainFrame:IsShown() and IsChallengesVisible() then
            ApplyAnchor()
        end
    end)
    C_Timer.After(0.15, function()
        if mainFrame and mainFrame:IsShown() and IsChallengesVisible() then
            ApplyAnchor()
        end
    end)
end

ApplyAnchor = function()
    if not mainFrame then return end
    mainFrame:SetParent(UIParent)
    mainFrame:SetFrameStrata("HIGH")
    local scale = (db() and db().uiScale) or 1
    mainFrame:SetScale(scale)
    local mode = ChoosePlacement(MAIN_W, scale)
    mainFrame:ClearAllPoints()
    local offset = (db() and db().attachedOffset) or {}
    local ox = offset.x or ATTACH_GAP
    local oy = offset.y or 0
    if mode == "attach_cutoffs" then
        mainFrame:SetPoint("TOPLEFT", _G.KeystoneCutoffsPanel, "TOPRIGHT", ox, oy)
    elseif mode == "attach_challenges" or mode == "pending_attach" then
        if ChallengesFrame then
            mainFrame:SetPoint("TOPLEFT", ChallengesFrame, "TOPRIGHT", ox, oy)
        else
            RestoreStandalonePosition()
            PositionPanels()
            return
        end
        if mode == "pending_attach" then
            ScheduleReanchor()
        end
    else
        RestoreStandalonePosition()
        PositionPanels()
        return
    end
    ClampFrameToUIParent(mainFrame)
    PositionPanels()
end

local function CloseDetail()
    if detailFrame then
        detailFrame:Hide()
        detailFrame.dungeonId = nil
    end
end

local function HideMain()
    HideMenus()
    CloseDetail()
    if mainFrame then
        mainFrame:Hide()
    end
    HideCatcher()
end

local function ShowEmptyState(block, status)
    block:Show()
    if status == "insufficient_data" then
        SafeSetText(block.title, "Not enough ranked runs yet")
        SafeSetText(block.body, "Waiting for a useful sample of\ncompleted ranked runs.")
        if block.note then
            SafeSetText(block.note, "Values appear after validation succeeds.")
        end
    else
        SafeSetText(block.title, "Season data pending")
        SafeSetText(block.body, "Waiting for the first validated\nRaider.IO snapshot.")
        if block.note then
            SafeSetText(block.note, "Values appear after validation succeeds.")
        end
    end
end

local function BuildDungeonRow(parent)
    local row = CreateFrame("Button", nil, parent)
    row:SetHeight(ROW_H)
    ApplyCompanionRowChrome(row)

    row.short = CreateFS(row, "GameFontNormalSmall", META_SIZE, C.goldDim)
    row.short:SetPoint("LEFT", ROW_INSET, 0)
    row.short:SetWidth(SHORT_COL_W)
    row.short:SetJustifyH("LEFT")

    row.name = CreateFS(row, "GameFontHighlight", ROW_SIZE, C.text)
    row.name:SetPoint("LEFT", ROW_INSET + SHORT_COL_W + 6, 0)
    row.name:SetPoint("RIGHT", -(ROW_INSET + SHARE_COL_W + 4 + DELTA_COL_W), 0)
    row.name:SetJustifyH("LEFT")

    row.share = CreateFS(row, "GameFontHighlight", ROW_SIZE, C.text)
    row.share:SetPoint("RIGHT", -(ROW_INSET + DELTA_COL_W + 4), 0)
    row.share:SetWidth(SHARE_COL_W)
    row.share:SetJustifyH("RIGHT")

    row.delta = CreateFS(row, "GameFontHighlight", ROW_SIZE, C.muted)
    row.delta:SetPoint("RIGHT", -ROW_INSET, 0)
    row.delta:SetWidth(DELTA_COL_W)
    row.delta:SetJustifyH("RIGHT")

    WireTooltip(row, DungeonRowTooltip)
    row:SetScript("OnClick", function(self)
        if not DungeonUseful(self.dungeon) then
            return
        end
        if detailFrame and detailFrame:IsShown() and detailFrame.dungeonId == self.dungeonId then
            CloseDetail()
            RefreshUI()
            return
        end
        viewState.dungeonId = self.dungeonId
        if db() then db().selectedDungeonId = self.dungeonId end
        viewState.detailRole = CurrentRole()
        if detailFrame then
            detailFrame:Show()
        end
        if RefreshUI then RefreshUI() end
    end)
    return row
end

local function BuildSpecRow(parent)
    local row = CreateFrame("Button", nil, parent)
    row:SetHeight(ROW_H)
    ApplyCompanionRowChrome(row)

    row.rank = CreateFS(row, "GameFontNormalSmall", ROW_SIZE, C.gold)
    row.rank:SetPoint("LEFT", 8, 0)
    row.rank:SetWidth(24)
    row.rank:SetJustifyH("LEFT")

    row.icon = row:CreateTexture(nil, "ARTWORK")
    row.icon:SetSize(18, 18)
    row.icon:SetPoint("LEFT", 34, 0)

    row.name = CreateFS(row, "GameFontHighlight", ROW_SIZE, C.text)
    row.name:SetPoint("LEFT", 56, 0)
    row.name:SetPoint("RIGHT", -116, 0)
    row.name:SetJustifyH("LEFT")

    row.share = CreateFS(row, "GameFontHighlight", ROW_SIZE, C.text)
    row.share:SetPoint("RIGHT", -58, 0)
    row.share:SetWidth(50)
    row.share:SetJustifyH("RIGHT")

    row.delta = CreateFS(row, "GameFontHighlight", ROW_SIZE, C.muted)
    row.delta:SetPoint("RIGHT", 0, 0)
    row.delta:SetWidth(54)
    row.delta:SetJustifyH("RIGHT")

    WireTooltip(row, SpecRowTooltip)
    return row
end

local function ApplyRowFonts(row)
    if row.short then ApplyFont(row.short, META_SIZE, C.goldDim) end
    if row.rank then ApplyFont(row.rank, ROW_SIZE, C.gold) end
    if row.name then ApplyFont(row.name, ROW_SIZE, C.text) end
    if row.share then ApplyFont(row.share, ROW_SIZE, C.text) end
    if row.delta then ApplyFont(row.delta, ROW_SIZE, C.muted) end
end

local function LayoutDungeonRow(row, showShare, showDelta)
    if not row then
        return
    end
    row.short:ClearAllPoints()
    row.short:SetPoint("LEFT", ROW_INSET, 0)
    row.short:SetWidth(SHORT_COL_W)
    local rightPad = ROW_INSET
    if showDelta and row.delta then
        row.delta:Show()
        row.delta:ClearAllPoints()
        row.delta:SetPoint("RIGHT", -rightPad, 0)
        row.delta:SetWidth(DELTA_COL_W)
        rightPad = rightPad + DELTA_COL_W + 4
    elseif row.delta then
        row.delta:Hide()
    end
    if showShare and row.share then
        row.share:Show()
        row.share:ClearAllPoints()
        row.share:SetPoint("RIGHT", -rightPad, 0)
        row.share:SetWidth(SHARE_COL_W)
        rightPad = rightPad + SHARE_COL_W + 4
    elseif row.share then
        row.share:Hide()
    end
    row.name:ClearAllPoints()
    row.name:SetPoint("LEFT", ROW_INSET + SHORT_COL_W + 6, 0)
    row.name:SetPoint("RIGHT", -rightPad, 0)
end

local function SpecHasNumericShare(specId, role)
    for _, entry in ipairs(SortedDungeons()) do
        if DungeonUseful(entry.dungeon) then
            local spec = SpecInDungeon(entry.dungeon, specId, role)
            if spec and type(spec.roleSharePct) == "number" then
                return true
            end
        end
    end
    return false
end

local function SpecHasAnyDelta(specId, role)
    if not (db() and db().showDailyMovement) then
        return false
    end
    for _, entry in ipairs(SortedDungeons()) do
        if DungeonUseful(entry.dungeon) then
            local spec = SpecInDungeon(entry.dungeon, specId, role)
            if spec and type(spec.deltaPercentagePoints) == "number" then
                return true
            end
        end
    end
    return false
end

local function FitTextWidth(fontString, fallback)
    if not fontString then
        return
    end
    local width = fallback or 8
    if fontString.GetStringWidth then
        width = math.max(width, (fontString:GetStringWidth() or 0) + 2)
    end
    fontString:SetWidth(width)
end

local function SelectSpecId(specId)
    viewState.specId = specId
    if db() then
        db().selectedSpecId = specId
        db().followCurrentSpec = false
    end
    HideFallbackSpecMenus()
    HideCatcher()
    MarkSpecMenuClosed()
    if RefreshUI then
        RefreshUI()
    end
end

local function SpecIsSelected(specId)
    return CurrentSpecId() == specId
end

local function AddSpecRadio(parent, spec)
    if not parent or not spec or not parent.CreateRadio then
        return
    end
    parent:CreateRadio(SpecMenuLabel(spec), SpecIsSelected, SelectSpecId, spec.id)
end

local function BuildSpecMenuDescription(_, rootDescription)
    local classSpecs = CurrentClassSpecs()
    for _, spec in ipairs(classSpecs) do
        AddSpecRadio(rootDescription, spec)
    end
    if rootDescription.CreateDivider then
        rootDescription:CreateDivider()
    end
    local browse = rootDescription:CreateButton("Browse all specializations")
    if browse and browse.CreateRadio then
        for _, group in ipairs(CollectSpecsByClass()) do
            if browse.CreateTitle then
                browse:CreateTitle(group.name)
            elseif browse.CreateDivider then
                browse:CreateDivider()
            end
            for _, spec in ipairs(group.specs) do
                AddSpecRadio(browse, spec)
            end
        end
    end
    if rootDescription.SetMinimumWidth then
        pcall(rootDescription.SetMinimumWidth, rootDescription, 220)
    end
    local closer = rootDescription.SetClosedCallback or rootDescription.SetCloseCallback
    if closer then
        pcall(closer, rootDescription, MarkSpecMenuClosed)
    end
end

local function PlaceOwnedMenu(menu, anchor, mode)
    menu:ClearAllPoints()
    menu:SetParent(UIParent)
    menu:SetFrameStrata("TOOLTIP")
    menu:SetToplevel(true)
    menu:SetClampedToScreen(true)
    local height = menu:GetHeight() or 80
    local width = menu:GetWidth() or 200
    if mode == "right" then
        local parentRight = (UIParent and UIParent:GetRight()) or 1600
        local anchorRight = (anchor.GetRight and anchor:GetRight()) or 0
        if (parentRight - anchorRight) >= (width + SCREEN_MARGIN) then
            menu:SetPoint("TOPLEFT", anchor, "TOPRIGHT", 2, 0)
        else
            menu:SetPoint("TOPRIGHT", anchor, "TOPLEFT", -2, 0)
        end
        return
    end
    local below = (anchor.GetBottom and anchor:GetBottom()) or 0
    local parentBottom = (UIParent and UIParent:GetBottom()) or 0
    if (below - parentBottom) >= (height + SCREEN_MARGIN) then
        menu:SetPoint("TOPLEFT", anchor, "BOTTOMLEFT", 0, -2)
        menu:SetPoint("TOPRIGHT", anchor, "BOTTOMRIGHT", 0, -2)
    else
        menu:SetPoint("BOTTOMLEFT", anchor, "TOPLEFT", 0, 2)
        menu:SetPoint("BOTTOMRIGHT", anchor, "TOPRIGHT", 0, 2)
    end
end

local function MakeFallbackMenu(name)
    local menu = CreateFrame("Frame", name, UIParent, "BackdropTemplate")
    paint(menu, C.surface, C.border)
    menu:SetFrameStrata("TOOLTIP")
    menu:SetFrameLevel(600)
    menu:SetClampedToScreen(true)
    menu:EnableMouse(true)
    menu:Hide()
    fallbackSpecMenus[#fallbackSpecMenus + 1] = menu
    menu:SetScript("OnHide", function()
        if menu == fallbackSpecMenus[1] then
            MarkSpecMenuClosed()
            HideCatcher()
        end
    end)
    menu:SetScript("OnKeyDown", function(self, key)
        if key == "ESCAPE" then
            HideMenus()
            if self.SetPropagateKeyboardInput then
                self:SetPropagateKeyboardInput(false)
            end
        elseif self.SetPropagateKeyboardInput then
            self:SetPropagateKeyboardInput(true)
        end
    end)
    return menu
end

local function FallbackMenuButton(parent, y, height, width, onClick)
    local item = CreateFrame("Button", nil, parent, "BackdropTemplate")
    fill(item, { 0, 0, 0, 0 })
    item:SetSize(width, height)
    item:SetPoint("TOPLEFT", 4, y)
    item.accent = item:CreateTexture(nil, "ARTWORK")
    item.accent:SetPoint("LEFT", 0, 0)
    item.accent:SetSize(2, height - 8)
    item.accent:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.85)
    item.accent:Hide()
    item.label = CreateFS(item, "GameFontHighlightSmall", 12, C.text)
    item.label:SetPoint("LEFT", 10, 0)
    item.label:SetPoint("RIGHT", -8, 0)
    item.label:SetJustifyH("LEFT")
    item:SetScript("OnEnter", function()
        item:SetBackdropColor(C.hover[1], C.hover[2], C.hover[3], C.hover[4])
    end)
    item:SetScript("OnLeave", function()
        item:SetBackdropColor(0, 0, 0, 0)
    end)
    item:SetScript("OnClick", onClick)
    return item
end

local function OpenSpecMenuFallback(anchor)
    HideFallbackSpecMenus()
    local ITEM_H = 24
    local root = fallbackSpecMenus[1] or MakeFallbackMenu("KeystoneMetaSpecMenu")
    local browseMenu = fallbackSpecMenus[2] or MakeFallbackMenu("KeystoneMetaSpecBrowse")
    if root.buttons then
        for _, btn in ipairs(root.buttons) do
            btn:Hide()
        end
    end
    root.buttons = root.buttons or {}
    local classSpecs = CurrentClassSpecs()
    local width = math.max(220, (anchor and anchor:GetWidth()) or (MAIN_W - PAD * 2))
    local y = -4
    local index = 0
    local function addRoot(label, active, click)
        index = index + 1
        local item = root.buttons[index]
        if not item then
            item = FallbackMenuButton(root, y, ITEM_H, width - 8, click)
            root.buttons[index] = item
        end
        item:SetScript("OnClick", click)
        item:SetWidth(width - 8)
        item:ClearAllPoints()
        item:SetPoint("TOPLEFT", 4, y)
        ApplyFont(item.label, 12, active and C.gold or C.text)
        SafeSetText(item.label, label)
        item.accent:SetShown(active and true or false)
        item:Show()
        y = y - ITEM_H
        return item
    end
    for _, spec in ipairs(classSpecs) do
        local captured = spec
        addRoot(SpecMenuLabel(captured), SpecIsSelected(captured.id), function()
            SelectSpecId(captured.id)
        end)
    end
    addRoot("Browse all specializations", false, function()
        if browseMenu:IsShown() then
            browseMenu:Hide()
            return
        end
        if browseMenu.buttons then
            for _, btn in ipairs(browseMenu.buttons) do
                btn:Hide()
            end
        end
        browseMenu.buttons = browseMenu.buttons or {}
        local groups = CollectSpecsByClass()
        local by = -4
        local bi = 0
        local browseWidth = 260
        for _, group in ipairs(groups) do
            bi = bi + 1
            local header = browseMenu.buttons[bi]
            if not header then
                header = FallbackMenuButton(browseMenu, by, ITEM_H, browseWidth - 8, function() end)
                browseMenu.buttons[bi] = header
            end
            header:ClearAllPoints()
            header:SetPoint("TOPLEFT", 4, by)
            header:SetWidth(browseWidth - 8)
            header:SetScript("OnClick", nil)
            header:EnableMouse(false)
            ApplyFont(header.label, 12, C.gold)
            SafeSetText(header.label, group.name)
            header.accent:Hide()
            header:Show()
            by = by - ITEM_H
            for _, spec in ipairs(group.specs) do
                bi = bi + 1
                local specRef = spec
                local item = browseMenu.buttons[bi]
                if not item then
                    item = FallbackMenuButton(browseMenu, by, ITEM_H, browseWidth - 8, nil)
                    browseMenu.buttons[bi] = item
                end
                item:ClearAllPoints()
                item:SetPoint("TOPLEFT", 4, by)
                item:SetWidth(browseWidth - 8)
                item:EnableMouse(true)
                local active = SpecIsSelected(specRef.id)
                ApplyFont(item.label, 12, active and C.gold or C.text)
                SafeSetText(item.label, SpecMenuLabel(specRef))
                item.accent:SetShown(active)
                item:SetScript("OnClick", function()
                    SelectSpecId(specRef.id)
                end)
                item:Show()
                by = by - ITEM_H
            end
        end
        browseMenu:SetSize(browseWidth, math.min(360, math.abs(by) + 4))
        PlaceOwnedMenu(browseMenu, root, "right")
        browseMenu:Show()
    end)
    root:SetSize(width, math.abs(y) + 4)
    PlaceOwnedMenu(root, anchor, "below")
    root:Show()
    ShowCatcher(HideMenus)
    pcall(function()
        if root.EnableKeyboard then
            root:EnableKeyboard(true)
        end
    end)
end

local function OpenSpecMenu(anchor)
    if specMenuOpen then
        HideMenus()
        return
    end
    HideCatcher()
    if settingsFrame and settingsFrame.activeMenu then
        settingsFrame.activeMenu:Hide()
        settingsFrame.activeMenu = nil
    end
    HideFallbackSpecMenus()
    specMenuOpen = true
    if mainFrame and mainFrame.specChevron then
        SetDropdownChevron(mainFrame.specChevron, true)
    end
    if MenuUtil and MenuUtil.CreateContextMenu then
        local ok, menu = pcall(MenuUtil.CreateContextMenu, anchor, BuildSpecMenuDescription)
        if ok then
            if menu and menu.HookScript then
                menu:HookScript("OnHide", MarkSpecMenuClosed)
            end
            return
        end
    end
    OpenSpecMenuFallback(anchor)
end

local function MakeSettingsCheckbox(parent, yOff, labelText, getter, setter)
    local ROW_H = 22
    local row = CreateFrame("Button", nil, parent)
    row:SetSize(SETTINGS_W - 28, ROW_H)
    row:SetPoint("TOPLEFT", parent, "TOPLEFT", 14, yOff)

    local box = CreateFrame("Frame", nil, row, "BackdropTemplate")
    box:SetSize(16, 16)
    box:SetPoint("LEFT", 0, 0)
    mixBD(box)
    box:SetBackdrop(BD_EDGE)
    box:SetBackdropColor(C.element[1], C.element[2], C.element[3], 1)
    box:SetBackdropBorderColor(DIVIDER[1], DIVIDER[2], DIVIDER[3], 1)

    local check = box:CreateTexture(nil, "OVERLAY")
    check:SetTexture("Interface\\Buttons\\UI-CheckBox-Check")
    check:SetSize(18, 18)
    check:SetPoint("CENTER", 0, 0)
    check:SetVertexColor(C.gold[1], C.gold[2], C.gold[3])

    local lbl = CreateFS(row, "GameFontHighlightSmall", 12, C.text)
    lbl:SetPoint("LEFT", box, "RIGHT", 8, 0)
    lbl:SetJustifyH("LEFT")
    lbl:SetWordWrap(false)
    SafeSetText(lbl, labelText)

    local function refresh()
        check:SetShown(getter() and true or false)
    end

    row:SetScript("OnClick", function()
        setter(not getter())
        refresh()
        RefreshUI()
        pcall(PlaySound, SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_ON or 856)
    end)
    row:SetScript("OnEnter", function()
        box:SetBackdropBorderColor(C.gold[1], C.gold[2], C.gold[3], 1)
    end)
    row:SetScript("OnLeave", function()
        box:SetBackdropBorderColor(DIVIDER[1], DIVIDER[2], DIVIDER[3], 1)
    end)
    refreshFns[#refreshFns + 1] = refresh
    refresh()
    return ROW_H
end

local function MakeSettingsSlider(parent, yOff, labelText, minVal, maxVal, step, getter, setter)
    local ROW_H = 24
    local TRACK_H = 10
    local THUMB_W = 10
    local THUMB_H = 16
    local VALUE_W = 40
    local GAP = 10

    local row = CreateFrame("Frame", nil, parent)
    row:SetPoint("TOPLEFT", parent, "TOPLEFT", 14, yOff)
    row:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -14, yOff)
    row:SetHeight(ROW_H)

    local lbl = CreateFS(row, "GameFontHighlightSmall", 12, C.text)
    lbl:SetPoint("LEFT", 0, 0)
    lbl:SetWidth(SETTINGS_LABEL_W)
    lbl:SetJustifyH("LEFT")
    lbl:SetWordWrap(false)
    SafeSetText(lbl, labelText)

    local valueFs = CreateFS(row, "GameFontHighlightSmall", 12, C.gold)
    valueFs:SetPoint("RIGHT", 0, 0)
    valueFs:SetWidth(VALUE_W)
    valueFs:SetHeight(ROW_H)
    valueFs:SetJustifyH("RIGHT")
    valueFs:SetJustifyV("MIDDLE")

    local track = CreateFrame("Frame", nil, row, "BackdropTemplate")
    track:SetPoint("LEFT", lbl, "RIGHT", GAP, 0)
    track:SetPoint("RIGHT", valueFs, "LEFT", -GAP, 0)
    track:SetHeight(TRACK_H)
    mixBD(track)
    track:SetBackdrop(BD_EDGE)
    track:SetBackdropColor(C.element[1], C.element[2], C.element[3], 1)
    track:SetBackdropBorderColor(DIVIDER[1], DIVIDER[2], DIVIDER[3], 1)

    local slider = CreateFrame("Slider", nil, track)
    slider:SetOrientation("HORIZONTAL")
    slider:SetPoint("LEFT", track, THUMB_W / 2, 0)
    slider:SetPoint("RIGHT", track, -THUMB_W / 2, 0)
    slider:SetHeight(TRACK_H)
    slider:SetMinMaxValues(minVal, maxVal)
    slider:SetValueStep(step)
    slider:SetObeyStepOnDrag(true)

    local thumb = slider:CreateTexture(nil, "OVERLAY")
    thumb:SetSize(THUMB_W, THUMB_H)
    thumb:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1)
    slider:SetThumbTexture(thumb)

    local updating = false
    local function refresh()
        updating = true
        local cur = getter()
        slider:SetValue(cur)
        SafeSetText(valueFs, string.format("%.2f", cur))
        updating = false
    end
    slider:SetScript("OnValueChanged", function(_, val)
        if updating then return end
        val = math.floor(val / step + 0.5) * step
        setter(val)
        SafeSetText(valueFs, string.format("%.2f", val))
        RefreshUI()
    end)
    slider:SetScript("OnEnter", function()
        track:SetBackdropBorderColor(C.gold[1], C.gold[2], C.gold[3], 0.9)
    end)
    slider:SetScript("OnLeave", function()
        track:SetBackdropBorderColor(DIVIDER[1], DIVIDER[2], DIVIDER[3], 1)
    end)
    refreshFns[#refreshFns + 1] = refresh
    refresh()
    return ROW_H
end

local function MakeSettingsButton(parent, yOff, labelText, onClick)
    local ROW_H = 24
    local btn = CreateFrame("Button", nil, parent, "BackdropTemplate")
    btn:SetSize(SETTINGS_W - 28, ROW_H)
    btn:SetPoint("TOPLEFT", parent, "TOPLEFT", 14, yOff)
    mixBD(btn)
    btn:SetBackdrop(BD_EDGE)
    btn:SetBackdropColor(C.element[1], C.element[2], C.element[3], 1)
    btn:SetBackdropBorderColor(DIVIDER[1], DIVIDER[2], DIVIDER[3], 0.6)

    local lbl = CreateFS(btn, "GameFontHighlightSmall", 12, C.text)
    lbl:SetPoint("CENTER")
    SafeSetText(lbl, labelText)

    btn:SetScript("OnEnter", function()
        btn:SetBackdropBorderColor(C.gold[1], C.gold[2], C.gold[3], 0.9)
    end)
    btn:SetScript("OnLeave", function()
        btn:SetBackdropBorderColor(DIVIDER[1], DIVIDER[2], DIVIDER[3], 0.6)
    end)
    btn:SetScript("OnClick", function()
        if onClick then
            onClick()
        end
        pcall(PlaySound, SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_ON or 856)
    end)
    return ROW_H
end

local function SaveSettingsPosition()
    if not settingsFrame or not db() then return end
    local left, bottom = settingsFrame:GetLeft(), settingsFrame:GetBottom()
    if not (left and bottom) then return end
    db().settingsPosition = {
        point = "BOTTOMLEFT",
        relPoint = "BOTTOMLEFT",
        x = left,
        y = bottom,
    }
end

local function PlaceSettingsWindow()
    if not settingsFrame then return end
    settingsFrame:ClearAllPoints()
    settingsFrame:SetParent(UIParent)
    local pos = db() and db().settingsPosition
    if pos and pos.point then
        settingsFrame:SetPoint(pos.point, UIParent, pos.relPoint or pos.point, pos.x or 0, pos.y or 0)
    else
        settingsFrame:SetPoint("CENTER", UIParent, "CENTER", 0, 0)
    end
    ClampFrameToUIParent(settingsFrame)
end

local function CreateSettingsWindow()
    if settingsFrame then return end

    local BAR_H = 30
    local TAB_BAR_H = 26
    local win = CreateFrame("Frame", "KeystoneMetaSettingsFrame", UIParent, "BackdropTemplate")
    settingsFrame = win
    win:SetWidth(SETTINGS_W)
    win:SetFrameStrata("DIALOG")
    win:SetToplevel(true)
    win:SetMovable(true)
    win:EnableMouse(true)
    win:SetClampedToScreen(true)
    ApplyGoldOutline(win)
    ApplyCompanionChrome(win)
    win:Hide()
    tinsert(UISpecialFrames, "KeystoneMetaSettingsFrame")

    local titleBar = CreateFrame("Frame", nil, win)
    titleBar:SetHeight(BAR_H)
    titleBar:SetPoint("TOPLEFT", win, "TOPLEFT", 1, -1)
    titleBar:SetPoint("TOPRIGHT", win, "TOPRIGHT", -1, -1)
    titleBar:SetFrameLevel(win:GetFrameLevel() + 3)
    titleBar:EnableMouse(true)
    titleBar:RegisterForDrag("LeftButton")
    titleBar:SetScript("OnDragStart", function() win:StartMoving() end)
    titleBar:SetScript("OnDragStop", function()
        win:StopMovingOrSizing()
        ClampFrameToUIParent(win)
        SaveSettingsPosition()
    end)

    local titleBg = titleBar:CreateTexture(nil, "BACKGROUND")
    titleBg:SetAllPoints()
    titleBg:SetColorTexture(C.surface[1], C.surface[2], C.surface[3], 1)

    local titleTxt = CreateFS(titleBar, "GameFontNormal", 13, C.gold)
    titleTxt:SetPoint("LEFT", 12, 0)
    titleTxt:SetJustifyH("LEFT")
    titleTxt:SetWordWrap(false)
    SafeSetText(titleTxt, "|cFFFFD100Keystone Meta|r |cFF555555— Settings|r")
    win.title = titleTxt

    win.close = CreateChromeCloseButton(win, function()
        HideMenus()
        win:Hide()
    end)
    win.close:SetFrameLevel(win:GetFrameLevel() + 10)

    local sep = CreateThinDivider(win)
    sep:SetPoint("TOPLEFT", win, "TOPLEFT", 1, -BAR_H)
    sep:SetPoint("TOPRIGHT", win, "TOPRIGHT", -1, -BAR_H)

    local tabContainers = {}
    local tabButtons = {}
    local function showTab(name)
        for key, frm in pairs(tabContainers) do
            frm:SetShown(key == name)
        end
        for key, btn in pairs(tabButtons) do
            btn.underline:SetShown(key == name)
            ApplyFont(btn.label, 13, key == name and C.gold or C.muted2)
        end
    end

    local function makeTabButton(name, labelText, xOff)
        local b = CreateFrame("Button", nil, win)
        b:SetSize(92, TAB_BAR_H)
        b:SetPoint("TOPLEFT", win, "TOPLEFT", xOff, -BAR_H - 4)
        b.label = CreateFS(b, "GameFontNormal", 13, C.muted2)
        b.label:SetPoint("CENTER", 0, 2)
        SafeSetText(b.label, labelText)
        b.underline = b:CreateTexture(nil, "OVERLAY")
        b.underline:SetHeight(2)
        b.underline:SetPoint("BOTTOMLEFT", 6, 0)
        b.underline:SetPoint("BOTTOMRIGHT", -6, 0)
        b.underline:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 1)
        b.underline:Hide()
        b:SetScript("OnClick", function()
            showTab(name)
            pcall(PlaySound, SOUNDKIT and SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_ON or 856)
        end)
        b:SetScript("OnEnter", function()
            if not b.underline:IsShown() then
                ApplyFont(b.label, 13, C.text)
            end
        end)
        b:SetScript("OnLeave", function()
            if not b.underline:IsShown() then
                ApplyFont(b.label, 13, C.muted2)
            end
        end)
        tabButtons[name] = b
        return b
    end

    makeTabButton("display", "Display", 14)
    makeTabButton("customize", "Customize", 112)

    local tabSep = CreateThinDivider(win)
    tabSep:SetPoint("TOPLEFT", win, "TOPLEFT", 1, -BAR_H - 4 - TAB_BAR_H)
    tabSep:SetPoint("TOPRIGHT", win, "TOPRIGHT", -1, -BAR_H - 4 - TAB_BAR_H)

    local function makeTabFrame(name)
        local f = CreateFrame("Frame", nil, win)
        f:SetPoint("TOPLEFT", win, "TOPLEFT", 0, -BAR_H - 5 - TAB_BAR_H)
        f:SetWidth(SETTINGS_W)
        f:SetHeight(1)
        tabContainers[name] = f
        return f
    end

    local display = makeTabFrame("display")
    local customize = makeTabFrame("customize")

    local function sectionLabel(parent, text, yOff)
        local fs = CreateFS(parent, "GameFontNormalSmall", 11, C.gold)
        fs:SetPoint("TOPLEFT", parent, "TOPLEFT", 14, yOff)
        fs:SetWordWrap(false)
        SafeSetText(fs, text)
        return fs
    end

    local function divider(parent, yOff)
        local line = CreateThinDivider(parent)
        line:SetPoint("TOPLEFT", parent, "TOPLEFT", 14, yOff)
        line:SetPoint("TOPRIGHT", parent, "TOPRIGHT", -14, yOff)
        return line
    end

    local dy = -10
    sectionLabel(display, "DISPLAY", dy)
    dy = dy - 18
    dy = dy - MakeSettingsCheckbox(display, dy, "Show with Group Finder", function()
        return not CompanionIsDismissed()
    end, function(v)
        SetCompanionDismissed(not v)
        ApplyCompanionVisibility()
    end) - 6
    dy = dy - MakeSettingsCheckbox(display, dy, "Follow current specialization", function()
        return db() and db().followCurrentSpec
    end, function(v)
        if db() then db().followCurrentSpec = v end
    end) - 6
    dy = dy - MakeSettingsCheckbox(display, dy, "Compact rows", function()
        return db() and db().compactRows
    end, function(v)
        if db() then db().compactRows = v end
    end) - 6
    dy = dy - MakeSettingsCheckbox(display, dy, "Daily movement", function()
        return db() and db().showDailyMovement
    end, function(v)
        if db() then db().showDailyMovement = v end
    end) - 6
    dy = dy - MakeSettingsCheckbox(display, dy, "Show Minimap Button", function()
        return db() and not (db().minimap and db().minimap.hide)
    end, function(v)
        if db() then
            db().minimap = db().minimap or {}
            db().minimap.hide = not v
            if UpdateMinimapButton then UpdateMinimapButton() end
        end
    end) - 10
    display:SetHeight(math.abs(dy))

    local cy = -10
    sectionLabel(customize, "PANEL", cy)
    cy = cy - 18
    cy = cy - MakeSettingsSlider(customize, cy, "UI scale", 0.80, 1.20, 0.05, function()
        return (db() and db().uiScale) or 1
    end, function(v)
        if db() then db().uiScale = v end
    end) - 6
    cy = cy - MakeSettingsSlider(customize, cy, "Background opacity", 0.20, 1.00, 0.05, function()
        return BackgroundAlpha()
    end, function(v)
        if db() then db().bgOpacity = v end
        ApplyCompanionChrome(win)
        if mainFrame then ApplyCompanionChrome(mainFrame) end
        if detailFrame then ApplyCompanionChrome(detailFrame) end
    end) - 10
    divider(customize, cy)
    cy = cy - 14
    sectionLabel(customize, "POSITION", cy)
    cy = cy - 18
    cy = cy - MakeSettingsButton(customize, cy, "Reset Panel Position", function()
        if db() then
            db().windowPosition = nil
            db().attachedOffset = nil
        end
        holdStandaloneUntilReanchor = false
        if mainFrame and mainFrame:IsShown() then
            ApplyAnchor()
            PositionPanels()
        end
    end) - 8
    local hintFs = CreateFS(customize, "GameFontHighlightSmall", 11, C.muted2)
    hintFs:SetPoint("TOPLEFT", customize, "TOPLEFT", 14, cy)
    hintFs:SetPoint("TOPRIGHT", customize, "TOPRIGHT", -14, cy)
    hintFs:SetJustifyH("LEFT")
    hintFs:SetWordWrap(true)
    SafeSetText(hintFs, "Tip: Drag the Keystone Meta panel to reposition it.")
    cy = cy - 32
    customize:SetHeight(math.abs(cy))

    win:SetSize(SETTINGS_W, BAR_H + 1 + TAB_BAR_H + 1 + math.max(display:GetHeight(), customize:GetHeight()) + 8)
    win:SetScript("OnHide", HideMenus)
    ApplyGoldOutline(win)
    showTab("display")
end

local function ToggleSettings()
    CreateSettingsWindow()
    if settingsFrame:IsShown() then
        settingsFrame:Hide()
        return
    end
    for _, fn in ipairs(refreshFns) do
        fn()
    end
    PlaceSettingsWindow()
    settingsFrame:Show()
    ClampFrameToUIParent(settingsFrame)
end

local function CreateEmptyBlock(parent)
    local block = CreateFrame("Frame", nil, parent)
    if block.SetClipsChildren then
        block:SetClipsChildren(true)
    end
    block.icon = block:CreateTexture(nil, "ARTWORK")
    block.icon:SetSize(12, 12)
    block.icon:SetPoint("TOP", 0, -10)
    block.icon:SetTexture("Interface\\FriendsFrame\\InformationIcon")
    block.icon:SetVertexColor(0.78, 0.64, 0.28, 0.80)
    block.title = CreateFS(block, "GameFontNormal", 14, C.gold)
    block.title:SetPoint("TOP", block.icon, "BOTTOM", 0, -4)
    block.title:SetJustifyH("CENTER")
    block.body = CreateFS(block, "GameFontHighlight", 12, C.muted)
    block.body:SetPoint("TOP", block.title, "BOTTOM", 0, -4)
    block.body:SetWidth(MAIN_W - 48)
    block.body:SetJustifyH("CENTER")
    block.body:SetWordWrap(true)
    block.note = CreateFS(block, "GameFontNormalSmall", 11, C.muted2)
    block.note:SetPoint("TOP", block.body, "BOTTOM", 0, -4)
    block.note:SetWidth(MAIN_W - 48)
    block.note:SetJustifyH("CENTER")
    block.note:SetWordWrap(true)
    block:Hide()
    return block
end

StyleScroll = function(scroll)
    local bar = scroll.ScrollBar or (scroll.GetName and scroll:GetName() and _G[scroll:GetName() .. "ScrollBar"])
    if not bar then
        return scroll
    end
    if bar.Top then bar.Top:Hide() end
    if bar.Bottom then bar.Bottom:Hide() end
    if bar.Middle then bar.Middle:Hide() end
    if bar.Background then
        bar.Background:SetAlpha(0.15)
    end
    if bar.ScrollUpButton then
        bar.ScrollUpButton:SetAlpha(0)
        bar.ScrollUpButton:SetSize(1, 1)
    end
    if bar.ScrollDownButton then
        bar.ScrollDownButton:SetAlpha(0)
        bar.ScrollDownButton:SetSize(1, 1)
    end
    local thumb = bar.GetThumbTexture and bar:GetThumbTexture()
    if thumb then
        thumb:SetTexture()
        thumb:SetColorTexture(C.goldDim[1], C.goldDim[2], C.goldDim[3], 0.90)
        if thumb.SetWidth then
            thumb:SetWidth(6)
        end
    end
    return scroll
end

local function UpdateContainedScroll(scroll, child)
    if not scroll then
        return
    end
    local viewH = scroll:GetHeight() or 0
    local contentH = (child and child:GetHeight()) or 0
    local overflow = contentH > (viewH + 1)
    local bar = scroll.ScrollBar
    if bar then
        bar:SetShown(overflow)
    end
    if not overflow and scroll.SetVerticalScroll then
        scroll:SetVerticalScroll(0)
    end
    scroll:EnableMouseWheel(overflow)
    if overflow then
        scroll:SetScript("OnMouseWheel", function(self, delta)
            local current = self:GetVerticalScroll() or 0
            local maxScroll = math.max(0, contentH - viewH)
            local step = ROW_H * 3
            self:SetVerticalScroll(math.max(0, math.min(maxScroll, current - (delta * step))))
        end)
    else
        scroll:SetScript("OnMouseWheel", nil)
    end
end

local function CreateRoleTabs(parent)
    local bar = CreateFrame("Frame", nil, parent)
    bar:SetHeight(20)
    bar.buttons = {}
    local x = 0
    for _, role in ipairs(ROLE_ORDER) do
        local btn = CreateFrame("Button", nil, bar)
        btn:SetSize(58, 20)
        btn:SetPoint("LEFT", x, 0)
        btn.label = CreateFS(btn, "GameFontNormalSmall", 11, C.muted)
        btn.label:SetPoint("LEFT", 0, 1)
        btn.label:SetJustifyH("LEFT")
        SafeSetText(btn.label, string.upper(ROLE_LABEL[role]))
        btn.underline = btn:CreateTexture(nil, "ARTWORK")
        btn.underline:SetHeight(1)
        btn.underline:SetPoint("BOTTOMLEFT", 0, 1)
        btn.underline:SetPoint("BOTTOMRIGHT", -10, 1)
        btn.underline:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.90)
        btn.underline:Hide()
        btn.role = role
        btn:SetScript("OnEnter", function()
            if viewState.detailRole ~= role then
                ApplyFont(btn.label, 11, C.text)
            end
        end)
        btn:SetScript("OnLeave", function()
            local active = (viewState.detailRole or CurrentRole()) == role
            ApplyFont(btn.label, 11, active and C.gold or C.muted)
        end)
        btn:SetScript("OnClick", function()
            viewState.detailRole = role
            RefreshUI()
        end)
        bar.buttons[role] = btn
        x = x + 64
    end
    return bar
end

local function CreateDetailPanel()
    if detailFrame then return end
    local frame = CreateCompanionFrame("KeystoneMetaDetailFrame", UIParent, "HIGH")
    detailFrame = frame
    frame:SetSize(DETAIL_W, DETAIL_H)
    frame:Hide()
    tinsert(UISpecialFrames, "KeystoneMetaDetailFrame")
    frame.close = CreateChromeCloseButton(frame, CloseDetail)

    frame.title = CreateFS(frame, "GameFontNormal", 13, C.gold)
    frame.title:SetPoint("TOPLEFT", PAD, -TOP_PAD)
    frame.title:SetPoint("RIGHT", frame.close, "LEFT", -6, 0)
    frame.title:SetJustifyH("LEFT")
    SafeSetText(frame.title, "Dungeon")

    frame.scope = CreateFS(frame, "GameFontHighlightSmall", META_SIZE, C.muted)
    frame.scope:SetPoint("TOPLEFT", PAD, -(TOP_PAD + TITLE_H + SUBTITLE_GAP))
    frame.scope:SetPoint("TOPRIGHT", -PAD, -(TOP_PAD + TITLE_H + SUBTITLE_GAP))
    frame.scope:SetHeight(SUBTITLE_H)
    frame.scope:SetJustifyH("LEFT")
    frame.scope:SetWordWrap(false)

    frame.roleTabs = CreateRoleTabs(frame)
    frame.roleTabs:SetPoint("TOPLEFT", PAD, -(TOP_PAD + TITLE_H + SUBTITLE_GAP + SUBTITLE_H + AFTER_HEADER))
    frame.roleTabs:SetPoint("TOPRIGHT", -PAD, -(TOP_PAD + TITLE_H + SUBTITLE_GAP + SUBTITLE_H + AFTER_HEADER))
    frame.roleButtons = frame.roleTabs.buttons

    local listTop = TOP_PAD + TITLE_H + SUBTITLE_GAP + SUBTITLE_H + AFTER_HEADER + 20 + 6
    local listHost = CreateFrame("Frame", nil, frame)
    listHost:SetPoint("TOPLEFT", PAD, -listTop)
    listHost:SetPoint("BOTTOMRIGHT", -PAD, BOTTOM_PAD)
    frame.listInset = listHost

    local scroll = CreateFrame("ScrollFrame", nil, listHost, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", listHost, "TOPLEFT", 0, 0)
    scroll:SetPoint("BOTTOMRIGHT", listHost, "BOTTOMRIGHT", -SCROLL_GUTTER, 0)
    StyleScroll(scroll)
    frame.scroll = scroll

    frame.list = CreateFrame("Frame", nil, scroll)
    frame.list:SetSize(DETAIL_W - PAD * 2 - SCROLL_GUTTER, 10)
    scroll:SetScrollChild(frame.list)

    frame.empty = CreateEmptyBlock(listHost)
    frame.empty:ClearAllPoints()
    frame.empty:SetAllPoints(listHost)
end

local function CreateMainPanel()
    if mainFrame then return end
    local frame = CreateCompanionFrame("KeystoneMetaFrame", UIParent, "HIGH")
    mainFrame = frame
    frame:SetSize(MAIN_W, MAIN_H_PENDING)
    frame:SetMovable(true)
    frame:RegisterForDrag("LeftButton")
    frame:Hide()
    tinsert(UISpecialFrames, "KeystoneMetaFrame")

    frame:SetScript("OnDragStart", function(self)
        self:StartMoving()
    end)
    frame:SetScript("OnDragStop", function(self)
        self:StopMovingOrSizing()
        if IsChallengesVisible() then
            local mode = ChoosePlacement(MAIN_W, (db() and db().uiScale) or 1)
            local anchor
            if mode == "attach_cutoffs" then
                anchor = _G.KeystoneCutoffsPanel
            elseif mode == "attach_challenges" or mode == "pending_attach" then
                anchor = ChallengesFrame
            end
            if anchor and anchor.GetRight and self:GetLeft() and anchor:GetRight() and self:GetTop() and anchor:GetTop() then
                if db() then
                    db().attachedOffset = {
                        x = self:GetLeft() - anchor:GetRight(),
                        y = self:GetTop() - anchor:GetTop(),
                    }
                end
            end
            holdStandaloneUntilReanchor = false
            ApplyAnchor()
        else
            holdStandaloneUntilReanchor = true
            SaveStandalonePosition()
            ClampFrameToUIParent(self)
            SaveStandalonePosition()
        end
        PositionPanels()
    end)
    frame:SetScript("OnHide", function()
        HideMenus()
        CloseDetail()
        HideCatcher()
    end)

    frame.close = CreateChromeCloseButton(frame, function()
        SetCompanionDismissed(true)
        HideMain()
    end)

    frame.title = CreateFS(frame, "GameFontNormalLarge", TITLE_SIZE, C.gold)
    frame.title:SetPoint("TOPLEFT", PAD, -TOP_PAD)
    frame.title:SetPoint("RIGHT", frame.close, "LEFT", -6, 0)
    frame.title:SetJustifyH("LEFT")
    SafeSetText(frame.title, "Keystone Meta")

    frame.scope = CreateFS(frame, "GameFontHighlightSmall", META_SIZE, C.muted)
    frame.scope:SetPoint("TOPLEFT", PAD, -(TOP_PAD + TITLE_H + SUBTITLE_GAP))
    frame.scope:SetPoint("TOPRIGHT", -PAD, -(TOP_PAD + TITLE_H + SUBTITLE_GAP))
    frame.scope:SetHeight(SUBTITLE_H)
    frame.scope:SetJustifyH("LEFT")
    frame.scope:SetWordWrap(false)

    local specTop = TOP_PAD + TITLE_H + SUBTITLE_GAP + SUBTITLE_H + AFTER_HEADER
    frame.specHit = CreateFrame("Button", nil, frame)
    frame.specHit:SetPoint("TOPLEFT", PAD, -specTop)
    frame.specHit:SetPoint("TOPRIGHT", -PAD, -specTop)
    frame.specHit:SetHeight(SPEC_ROW_H)
    mixBD(frame.specHit)
    frame.specHit:SetBackdrop(BD_EDGE)
    frame.specHit:SetBackdropColor(C.surface[1], C.surface[2], C.surface[3], 0.55)
    frame.specHit:SetBackdropBorderColor(C.goldDim[1], C.goldDim[2], C.goldDim[3], 0.70)

    local specHi = frame.specHit:CreateTexture(nil, "BACKGROUND")
    specHi:SetPoint("TOPLEFT", 1, -1)
    specHi:SetPoint("BOTTOMRIGHT", -1, 1)
    specHi:SetColorTexture(C.hover[1], C.hover[2], C.hover[3], C.hover[4])
    specHi:Hide()
    frame.specHit._highlight = specHi

    frame.specIcon = frame.specHit:CreateTexture(nil, "ARTWORK")
    frame.specIcon:SetSize(22, 22)
    frame.specIcon:SetPoint("LEFT", 6, 0)

    frame.specChevron = frame.specHit:CreateTexture(nil, "ARTWORK")
    frame.specChevron:SetPoint("RIGHT", -6, 0)
    SetDropdownChevron(frame.specChevron, false)

    frame.specName = CreateFS(frame.specHit, "GameFontHighlight", SPEC_SIZE, C.text)
    frame.specName:SetPoint("LEFT", frame.specIcon, "RIGHT", 8, 0)
    frame.specName:SetJustifyH("LEFT")

    frame.specRole = CreateFS(frame.specHit, "GameFontHighlightSmall", 11, C.muted)
    frame.specRole:SetPoint("LEFT", frame.specName, "RIGHT", 8, 0)
    frame.specRole:SetPoint("RIGHT", frame.specChevron, "LEFT", -6, 0)
    frame.specRole:SetJustifyH("LEFT")
    frame.specRole:SetWordWrap(false)

    frame.specHit:SetScript("OnClick", function()
        OpenSpecMenu(frame.specHit)
    end)
    frame.specHit:SetScript("OnEnter", function(self)
        ShowRowHighlight(self, true)
        if frame.specChevron then
            frame.specChevron:SetVertexColor(C.gold[1], C.gold[2], C.gold[3], 1)
        end
    end)
    frame.specHit:SetScript("OnLeave", function(self)
        ShowRowHighlight(self, false)
        SetDropdownChevron(frame.specChevron, specMenuOpen)
        GameTooltip:Hide()
    end)

    local summaryTop = specTop + SPEC_ROW_H + AFTER_SPEC
    frame.summary = CreateFS(frame, "GameFontHighlightSmall", META_SIZE, C.muted)
    frame.summary:SetPoint("TOPLEFT", PAD, -summaryTop)
    frame.summary:SetPoint("TOPRIGHT", -PAD, -summaryTop)
    frame.summary:SetHeight(SUMMARY_H)
    frame.summary:SetJustifyH("LEFT")
    frame.summaryHit = CreateFrame("Frame", nil, frame)
    frame.summaryHit:SetPoint("TOPLEFT", PAD, -summaryTop)
    frame.summaryHit:SetPoint("TOPRIGHT", -PAD, -summaryTop)
    frame.summaryHit:SetHeight(SUMMARY_H)
    WireTooltip(frame.summaryHit, function(_, tooltip)
        tooltip:SetText("Representation", 1, 0.82, 0)
        tooltip:AddLine("Average and rank use valid displayed dungeon cells only.", 1, 1, 1, true)
    end)

    local sectionTop = summaryTop + SUMMARY_H + AFTER_SUMMARY
    frame.sectionDivider = CreateThinDivider(frame)
    frame.sectionDivider:SetPoint("TOPLEFT", PAD, -sectionTop)
    frame.sectionDivider:SetPoint("TOPRIGHT", -PAD, -sectionTop)

    frame.section = CreateFS(frame, "GameFontNormal", HEADER_SIZE, C.gold)
    frame.section:SetPoint("TOPLEFT", PAD, -(sectionTop + 4))
    frame.section:SetPoint("TOPRIGHT", -PAD, -(sectionTop + 4))
    frame.section:SetHeight(SECTION_H)
    frame.section:SetJustifyH("LEFT")
    SafeSetText(frame.section, "Dungeon Representation")

    local listTop = sectionTop + 4 + SECTION_H + AFTER_SECTION
    local listHost = CreateFrame("Frame", nil, frame)
    listHost:SetPoint("TOPLEFT", PAD, -listTop)
    listHost:SetPoint("BOTTOMRIGHT", -PAD, BOTTOM_PAD + FOOTER_H + FOOTER_LINE_GAP + AFTER_LIST)
    if listHost.SetClipsChildren then
        listHost:SetClipsChildren(true)
    end
    frame.listInset = listHost

    frame.list = CreateFrame("Frame", nil, listHost)
    frame.list:SetPoint("TOPLEFT", listHost, "TOPLEFT", 0, 0)
    frame.list:SetPoint("TOPRIGHT", listHost, "TOPRIGHT", 0, 0)
    frame.list:SetPoint("BOTTOMLEFT", listHost, "BOTTOMLEFT", 0, 0)
    frame.list:SetPoint("BOTTOMRIGHT", listHost, "BOTTOMRIGHT", 0, 0)

    frame.empty = CreateEmptyBlock(listHost)
    frame.empty:ClearAllPoints()
    frame.empty:SetAllPoints(frame.list)

    frame.footerDivider = CreateThinDivider(frame)
    frame.footerDivider:SetPoint("BOTTOMLEFT", PAD, BOTTOM_PAD + FOOTER_H + FOOTER_LINE_GAP)
    frame.footerDivider:SetPoint("BOTTOMRIGHT", -PAD, BOTTOM_PAD + FOOTER_H + FOOTER_LINE_GAP)

    local footerBar = CreateFrame("Frame", nil, frame)
    footerBar:SetPoint("BOTTOMLEFT", PAD, BOTTOM_PAD)
    footerBar:SetPoint("BOTTOMRIGHT", -PAD, BOTTOM_PAD)
    footerBar:SetHeight(FOOTER_H)
    frame.footerBar = footerBar

    frame.info = CreateFrame("Button", nil, footerBar)
    frame.info:SetSize(16, 16)
    frame.info:SetPoint("RIGHT", 0, 0)
    frame.info:SetHighlightTexture("Interface\\Buttons\\UI-Common-MouseHilight", "ADD")
    if frame.info:GetHighlightTexture() then
        frame.info:GetHighlightTexture():SetAlpha(0.35)
    end
    frame.info.icon = frame.info:CreateTexture(nil, "ARTWORK")
    frame.info.icon:SetSize(12, 12)
    frame.info.icon:SetPoint("CENTER")
    SetHelpIcon(frame.info.icon)
    frame.info:SetScript("OnEnter", function(self)
        InfoTooltip(self, GameTooltip)
    end)
    frame.info:SetScript("OnLeave", function()
        GameTooltip:Hide()
    end)

    frame.footer = CreateFS(footerBar, "GameFontHighlightSmall", META_SIZE, C.muted)
    frame.footer:SetPoint("LEFT", 0, 0)
    frame.footer:SetPoint("RIGHT", frame.info, "LEFT", -8, 0)
    frame.footer:SetJustifyH("LEFT")
    frame.footer:SetJustifyV("MIDDLE")
    frame.footer:SetWordWrap(false)
    SafeSetText(frame.footer, PendingFooterText())
end

local function EnsureUI()
    CreateMainPanel()
    CreateDetailPanel()
end

local function ChooseDetailSide(mainLeft, mainRight, parentLeft, parentRight, scale, objectivesLeft, objectivesRight)
    local need = DETAIL_W * (scale or 1) + SCREEN_MARGIN
    local rightRoom = mainRight and parentRight and (parentRight - mainRight) >= need
    local leftRoom = mainLeft and parentLeft and (mainLeft - parentLeft) >= need
    local rightHitsObj = false
    if objectivesLeft and objectivesRight and mainRight then
        local placedLeft = mainRight + 4
        local placedRight = placedLeft + (DETAIL_W * (scale or 1))
        rightHitsObj = placedLeft < objectivesRight and placedRight > objectivesLeft
    end
    if rightHitsObj and leftRoom then
        return "left"
    end
    if rightRoom then
        return "right"
    end
    if leftRoom then
        return "left"
    end
    return "standalone"
end

PositionPanels = function()
    if not mainFrame then return end
    local scale = (db() and db().uiScale) or 1
    mainFrame:SetScale(scale)
    ClampFrameToUIParent(mainFrame)
    if not detailFrame then return end
    detailFrame:SetScale(scale)
    if not detailFrame:IsShown() then return end
    detailFrame:ClearAllPoints()
    detailFrame:SetParent(UIParent)
    detailFrame:SetFrameStrata(mainFrame:GetFrameStrata())
    detailFrame:SetFrameLevel(mainFrame:GetFrameLevel() + 2)
    local objectives = GetObjectivesRect()
    local side = ChooseDetailSide(
        mainFrame:GetLeft(),
        mainFrame:GetRight(),
        UIParent and UIParent:GetLeft(),
        UIParent and UIParent:GetRight(),
        scale,
        objectives and objectives.left,
        objectives and objectives.right
    )
    if side == "right" then
        detailFrame:SetPoint("TOPLEFT", mainFrame, "TOPRIGHT", 4, 0)
    elseif side == "left" then
        detailFrame:SetPoint("TOPRIGHT", mainFrame, "TOPLEFT", -4, 0)
    else
        local dLeft, dBottom = DefaultStandalonePoint(DETAIL_W, DETAIL_H, scale)
        detailFrame:SetPoint("BOTTOMLEFT", UIParent, "BOTTOMLEFT", dLeft, dBottom)
    end
    ClampFrameToUIParent(detailFrame)
end

local function RefreshRoleButtons()
    if not detailFrame or not detailFrame.roleButtons then return end
    local selected = viewState.detailRole or CurrentRole()
    for role, btn in pairs(detailFrame.roleButtons) do
        local active = role == selected
        if btn.label then
            ApplyFont(btn.label, 11, active and C.gold or C.muted)
        end
        if btn.underline then
            btn.underline:SetShown(active)
        end
    end
end

local function RefreshMainPanel()
    if not mainFrame then return end
    local specId = CurrentSpecId()
    local specMeta = FindSpecMeta(specId)
    local role = specMeta.role or "dps"
    viewState.role = role

    if mainFrame.title then
        ApplyFont(mainFrame.title, TITLE_SIZE, C.gold)
        SafeSetText(mainFrame.title, "Keystone Meta")
    end

    if specMeta.icon then
        mainFrame.specIcon:SetTexture(specMeta.icon)
    else
        mainFrame.specIcon:SetColorTexture(C.goldDim[1], C.goldDim[2], C.goldDim[3], 0.55)
    end
    ApplyFont(mainFrame.specName, SPEC_SIZE, ClassColor(specMeta.classFile))
    SafeSetText(mainFrame.specName, specMeta.name or "Specialization")
    FitTextWidth(mainFrame.specName, 40)
    ApplyFont(mainFrame.specRole, 11, C.muted)
    SafeSetText(mainFrame.specRole, ROLE_LABEL[role] or role)
    FitTextWidth(mainFrame.specRole, 36)
    SetDropdownChevron(mainFrame.specChevron, specMenuOpen)

    ApplyFont(mainFrame.scope, META_SIZE, C.muted)
    SafeSetText(mainFrame.scope, ScopeLabel())
    if mainFrame.section then
        ApplyFont(mainFrame.section, HEADER_SIZE, C.gold)
        SafeSetText(mainFrame.section, "Dungeon Representation")
    end

    ReleaseRows(dungeonRows)
    local status = SnapshotStatus()
    local showList = status == "ok"
    if showList then
        mainFrame:SetHeight(PopulatedPanelHeight())
    else
        mainFrame:SetHeight(PanelHeightForStatus(status))
    end
    if mainFrame.section then
        mainFrame.section:SetShown(showList)
    end
    if mainFrame.sectionDivider then
        mainFrame.sectionDivider:SetShown(showList)
    end
    if mainFrame.summaryHit then
        mainFrame.summaryHit:SetShown(showList)
    end
    if mainFrame.summary then
        mainFrame.summary:SetShown(showList)
    end
    if status ~= "ok" then
        CloseDetail()
        mainFrame.list:Hide()
        ShowEmptyState(mainFrame.empty, status)
        ApplyFont(mainFrame.summary, META_SIZE, C.muted)
        SafeSetText(mainFrame.summary, "")
        ApplyFont(mainFrame.footer, META_SIZE, C.muted)
        SafeSetText(mainFrame.footer, PendingFooterText())
        if mainFrame.info then
            mainFrame.info:Show()
        end
        return
    end

    mainFrame.empty:Hide()
    mainFrame.list:Show()

    local hasShare = SpecHasNumericShare(specId, role)
    local hasDelta = SpecHasAnyDelta(specId, role)
    local rowHeight = (db() and db().compactRows) and ROW_H_COMPACT or ROW_H
    local selectedId = (detailFrame and detailFrame:IsShown())
        and (viewState.dungeonId or (db() and db().selectedDungeonId))
    for _, entry in ipairs(SortedDungeons()) do
        local row = AcquireRow(dungeonRows, mainFrame.list, BuildDungeonRow)
        ApplyRowFonts(row)
        LayoutDungeonRow(row, hasShare, hasDelta)
        row.dungeonId = entry.id
        row.dungeon = entry.dungeon
        row.specMeta = specMeta
        row.spec = SpecInDungeon(entry.dungeon, specId, role)
        Truncate(row.short, entry.dungeon.shortName or "")
        Truncate(row.name, entry.dungeon.name or ("Dungeon " .. entry.id))
        local selected = selectedId == entry.id
        if row.selected then
            row.selected:SetShown(selected)
        end
        if row.accent then
            row.accent:SetShown(selected)
        end
        if hasShare then
            if DungeonUseful(entry.dungeon) and row.spec and type(row.spec.roleSharePct) == "number" then
                ApplyFont(row.share, ROW_SIZE, C.text)
                SafeSetText(row.share, FormatPct(row.spec.roleSharePct))
            else
                ApplyFont(row.share, ROW_SIZE, C.muted)
                SafeSetText(row.share, EMPTY_CELL)
            end
        end
        if hasDelta then
            local delta = row.spec and row.spec.deltaPercentagePoints
            ApplyFont(row.delta, ROW_SIZE, DeltaColor(delta))
            SafeSetText(row.delta, FormatDelta(delta) or EMPTY_CELL)
        end
    end
    LayoutRows(mainFrame.list, dungeonRows, rowHeight)

    local avg = AverageForSpec(specId, role)
    ApplyFont(mainFrame.summary, META_SIZE, C.muted)
    if not hasShare then
        SafeSetText(mainFrame.summary, string.format("%s did not appear in this sample", specMeta.name or "This specialization"))
        if mainFrame.summary then
            mainFrame.summary:Show()
        end
        if mainFrame.summaryHit then
            mainFrame.summaryHit:Show()
        end
    elseif avg.samples > 0 and avg.share then
        local rankText = ""
        if avg.rank and avg.roleCount > 0 then
            rankText = string.format("  ·  Rank %d of %d", math.floor(avg.rank + 0.5), avg.roleCount)
        elseif avg.rank then
            rankText = string.format("  ·  Rank %d", math.floor(avg.rank + 0.5))
        end
        SafeSetText(mainFrame.summary, string.format("Average %s%s", FormatPct(avg.share), rankText))
        if mainFrame.summary then
            mainFrame.summary:Show()
        end
        if mainFrame.summaryHit then
            mainFrame.summaryHit:Show()
        end
    else
        SafeSetText(mainFrame.summary, "")
        if mainFrame.summary then
            mainFrame.summary:Hide()
        end
        if mainFrame.summaryHit then
            mainFrame.summaryHit:Hide()
        end
    end
    ApplyFont(mainFrame.footer, META_SIZE, C.muted)
    SafeSetText(mainFrame.footer, PopulatedFooterText())
    if mainFrame.info then
        mainFrame.info:Show()
    end
end

local function RefreshDetailPanel()
    if not detailFrame or not detailFrame:IsShown() then
        return
    end

    local dungeonId = viewState.dungeonId or (db() and db().selectedDungeonId)
    local dungeon, foundId
    for _, entry in ipairs(SortedDungeons()) do
        if entry.id == dungeonId then
            dungeon = entry.dungeon
            foundId = entry.id
            break
        end
    end

    if not DungeonUseful(dungeon) then
        CloseDetail()
        return
    end

    detailFrame.dungeonId = foundId
    local role = viewState.detailRole or CurrentRole()
    viewState.detailRole = role
    RefreshRoleButtons()

    if detailFrame.title then
        ApplyFont(detailFrame.title, 13, C.gold)
        SafeSetText(detailFrame.title, dungeon.name or "Dungeon")
    end
    ApplyFont(detailFrame.scope, META_SIZE, C.muted)
    local sample = dungeon.sample or {}
    local runs = sample.validRuns
    local runText = (type(runs) == "number" and runs > 0) and (tostring(runs) .. " runs") or (tostring(SampleTarget()) .. " runs")
    local data = GetData()
    local affix = (data and data.scope and data.scope.affixMode == "current") and "Current Affixes" or "Full season"
    SafeSetText(detailFrame.scope, string.format("World · %s · %s", affix, runText))

    ReleaseRows(specRows)
    local specs = RoleSpecList(dungeon, role)
    if #specs == 0 then
        detailFrame.scroll:Hide()
        local roleStatus = (sample.status == "insufficient_data") and "insufficient_data" or SnapshotStatus()
        ShowEmptyState(detailFrame.empty, roleStatus)
        detailFrame:SetHeight(math.min(DETAIL_H, DETAIL_CHROME + ROW_H * 4))
        return
    end

    detailFrame.empty:Hide()
    detailFrame.scroll:Show()
    local selectedSpec = CurrentSpecId()
    local rowHeight = (db() and db().compactRows) and ROW_H_COMPACT or ROW_H
    local showDelta = false
    if db() and db().showDailyMovement then
        for _, item in ipairs(specs) do
            if item.spec and type(item.spec.deltaPercentagePoints) == "number" then
                showDelta = true
                break
            end
        end
    end
    for _, item in ipairs(specs) do
        local row = AcquireRow(specRows, detailFrame.list, BuildSpecRow)
        ApplyRowFonts(row)
        row.spec = item.spec
        row.dungeon = dungeon
        local isSelected = item.id == selectedSpec
        row.selected:SetShown(isSelected)
        local _, name, icon, _, classFile = SafeGetSpecByID(item.id)
        if icon then
            row.icon:SetTexture(icon)
        else
            row.icon:SetColorTexture(C.goldDim[1], C.goldDim[2], C.goldDim[3], 0.45)
        end
        row.accent:SetColorTexture(C.gold[1], C.gold[2], C.gold[3], 0.85)
        ApplyFont(row.rank, ROW_SIZE, C.gold)
        SafeSetText(row.rank, item.spec.representationRank and tostring(item.spec.representationRank) or "")
        ApplyFont(row.name, ROW_SIZE, ClassColor(classFile))
        Truncate(row.name, item.spec.name or name or ("Spec " .. item.id))
        if type(item.spec.roleSharePct) == "number" then
            ApplyFont(row.share, ROW_SIZE, C.text)
            SafeSetText(row.share, FormatPct(item.spec.roleSharePct))
        else
            ApplyFont(row.share, ROW_SIZE, C.muted)
            SafeSetText(row.share, EMPTY_CELL)
        end
        if showDelta then
            local delta = item.spec.deltaPercentagePoints
            ApplyFont(row.delta, ROW_SIZE, DeltaColor(delta))
            SafeSetText(row.delta, FormatDelta(delta) or EMPTY_CELL)
            row.delta:Show()
        elseif row.delta then
            row.delta:Hide()
        end
    end
    local shown = LayoutRows(detailFrame.list, specRows, rowHeight)
    local desired = DETAIL_CHROME + math.max(shown, 1) * rowHeight
    detailFrame:SetHeight(math.min(DETAIL_H, math.max(DETAIL_CHROME + ROW_H, desired)))
    UpdateContainedScroll(detailFrame.scroll, detailFrame.list)
end

RefreshUI = function()
    if not mainFrame then return end
    for _, fn in ipairs(refreshFns) do
        fn()
    end
    ApplyCompanionChrome(mainFrame)
    if detailFrame then ApplyCompanionChrome(detailFrame) end
    if settingsFrame then ApplyCompanionChrome(settingsFrame) end
    RefreshMainPanel()
    RefreshDetailPanel()
    PositionPanels()
end

ShowMain = function()
    EnsureUI()
    local player = PlayerSpec()
    if player and (not viewState.specId or (db() and db().followCurrentSpec)) then
        viewState.specId = player.id
        viewState.role = player.role
    end
    mainFrame:Show()
    if IsChallengesVisible() then
        holdStandaloneUntilReanchor = false
    end
    ApplyAnchor()
    RefreshUI()
    ClampFrameToUIParent(mainFrame)
    if IsChallengesVisible() then
        ScheduleReanchor()
    end
end

ApplyCompanionVisibility = function()
    if CompanionIsDismissed() then
        HideMain()
        return
    end
    if IsChallengesVisible() then
        ShowMain()
    end
end

local function ToggleWindow()
    SetCompanionDismissed(not CompanionIsDismissed())
    ApplyCompanionVisibility()
    if settingsFrame and settingsFrame:IsShown() then
        for _, fn in ipairs(refreshFns) do
            fn()
        end
    end
end

local function ReevaluatePlacement()
    holdStandaloneUntilReanchor = false
    if mainFrame and mainFrame:IsShown() then
        ApplyAnchor()
        PositionPanels()
    end
end

local function OnChallengesShow()
    EnsureUI()
    holdStandaloneUntilReanchor = false
    if CompanionIsDismissed() then
        return
    end
    ShowMain()
    ScheduleReanchor()
end

local function OnChallengesHide()
    holdStandaloneUntilReanchor = false
    hidingWithParent = true
    HideMain()
    hidingWithParent = false
end

local function WatchCutoffs()
    local panel = _G.KeystoneCutoffsPanel
    if not panel or cutoffsWatched then
        return
    end
    cutoffsWatched = true
    if panel.HookScript then
        panel:HookScript("OnShow", function()
            if mainFrame and mainFrame:IsShown() and IsChallengesVisible() then
                ReevaluatePlacement()
                ScheduleReanchor()
            end
        end)
        panel:HookScript("OnHide", function()
            if mainFrame and mainFrame:IsShown() and IsChallengesVisible() then
                ReevaluatePlacement()
            end
        end)
    end
end

local function HookChallenges()
    if challengesHooked or not ChallengesFrame then
        return
    end
    challengesHooked = true
    hooksecurefunc(ChallengesFrame, "Show", OnChallengesShow)
    hooksecurefunc(ChallengesFrame, "Hide", OnChallengesHide)
    if ChallengesFrame.HookScript then
        ChallengesFrame:HookScript("OnShow", OnChallengesShow)
        ChallengesFrame:HookScript("OnHide", OnChallengesHide)
    end
    WatchCutoffs()
    if PVEFrame and PVEFrame.HookScript then
        PVEFrame:HookScript("OnShow", function()
            if ChallengesFrame and ChallengesFrame.IsShown and ChallengesFrame:IsShown() then
                OnChallengesShow()
            end
        end)
        PVEFrame:HookScript("OnHide", OnChallengesHide)
    end
    if ChallengesFrame.IsShown and ChallengesFrame:IsShown() then
        OnChallengesShow()
    end
end

local function InitializeMinimap()
    local LDB = LibStub and LibStub("LibDataBroker-1.1", true)
    local Icon = LibStub and LibStub("LibDBIcon-1.0", true)
    if not LDB or not Icon then return end
    local dataObj = LDB:NewDataObject(ADDON_NAME, {
        type = "launcher",
        text = "Keystone Meta",
        icon = "Interface\\AddOns\\KeystoneMeta\\Assets\\KeystoneMeta_logo",
        OnClick = function(_, button)
            if button == "RightButton" then
                ToggleWindow()
            else
                ToggleSettings()
            end
        end,
        OnTooltipShow = function(tt)
            tt:AddLine("|cFFFFD100Keystone Meta|r")
            tt:AddLine("|cFFFFFFFFLeft-click:|r Open settings", 0.85, 0.85, 0.85)
            tt:AddLine("|cFFFFFFFFRight-click:|r Toggle Group Finder panel", 0.85, 0.85, 0.85)
        end,
    })
    KeystoneMetaDB.minimap = KeystoneMetaDB.minimap or { hide = false }
    if not Icon:IsRegistered(ADDON_NAME) then
        Icon:Register(ADDON_NAME, dataObj, KeystoneMetaDB.minimap)
    end
    UpdateMinimapButton()
end

UpdateMinimapButton = function()
    local Icon = LibStub and LibStub("LibDBIcon-1.0", true)
    if not Icon then return end
    if KeystoneMetaDB.minimap and KeystoneMetaDB.minimap.hide then
        Icon:Hide(ADDON_NAME)
    else
        Icon:Show(ADDON_NAME)
    end
end

local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:RegisterEvent("PLAYER_SPECIALIZATION_CHANGED")
eventFrame:RegisterEvent("PLAYER_REGEN_ENABLED")
eventFrame:RegisterEvent("UI_SCALE_CHANGED")
eventFrame:RegisterEvent("DISPLAY_SIZE_CHANGED")

eventFrame:SetScript("OnEvent", function(_, event, arg1)
    if event == "ADDON_LOADED" and arg1 == "Blizzard_ChallengesUI" then
        HookChallenges()
        WatchCutoffs()
    elseif event == "ADDON_LOADED" and arg1 == "KeystoneCutoffs" then
        WatchCutoffs()
    elseif event == "PLAYER_LOGIN" then
        copyDefaults()
        InitializeMinimap()
        local player = PlayerSpec()
        if player then
            viewState.specId = player.id
            viewState.role = player.role
        end
        if db() and db().selectedDungeonId then
            viewState.dungeonId = db().selectedDungeonId
        end
        EnsureUI()
        ApplyAnchor()
        WatchCutoffs()
        if IsAddonLoaded("Blizzard_ChallengesUI") then
            HookChallenges()
        end
        if C_Timer and C_Timer.After then
            C_Timer.After(1, WatchCutoffs)
        end
    elseif event == "PLAYER_SPECIALIZATION_CHANGED" then
        if arg1 and arg1 ~= "player" then return end
        local player = PlayerSpec()
        if player and db() and db().followCurrentSpec then
            viewState.specId = player.id
            viewState.role = player.role
            if mainFrame and mainFrame:IsShown() then
                RefreshUI()
            end
        end
    elseif event == "PLAYER_ENTERING_WORLD" or event == "PLAYER_REGEN_ENABLED" then
        WatchCutoffs()
        if mainFrame and mainFrame:IsShown() then
            ApplyAnchor()
            RefreshUI()
        end
    elseif event == "UI_SCALE_CHANGED" or event == "DISPLAY_SIZE_CHANGED" then
        if mainFrame and mainFrame:IsShown() then
            ApplyAnchor()
            PositionPanels()
        end
    end
end)

SLASH_KEYSTONEMETA1 = "/kmeta"
SLASH_KEYSTONEMETA2 = "/keystonemeta"
SlashCmdList["KEYSTONEMETA"] = function()
    ToggleWindow()
end

end
KeystoneMetaBoot()
