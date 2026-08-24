import importlib.util
import re
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]

SPEC_VALIDATE = importlib.util.spec_from_file_location("validate_zip", ROOT / "tests" / "validate_zip.py")
VALIDATE = importlib.util.module_from_spec(SPEC_VALIDATE)
SPEC_VALIDATE.loader.exec_module(VALIDATE)

SPEC_PLACE = importlib.util.spec_from_file_location("placement_math", ROOT / "tests" / "placement_math.py")
PLACE = importlib.util.module_from_spec(SPEC_PLACE)
SPEC_PLACE.loader.exec_module(PLACE)

SPEC_FIXTURE = importlib.util.spec_from_file_location("use_visual_fixture", ROOT / "tools" / "use_visual_fixture.py")
FIXTURE = importlib.util.module_from_spec(SPEC_FIXTURE)
SPEC_FIXTURE.loader.exec_module(FIXTURE)


class PlacementMathTests(TestCase):
    def test_pending_and_populated_heights(self):
        self.assertEqual(220, PLACE.panel_height_for_status("pending_season_data"))
        self.assertEqual(220, PLACE.panel_height_for_status("insufficient_data"))
        self.assertEqual(220, PLACE.panel_height_for_status("missing"))
        self.assertEqual(370, PLACE.panel_height_for_status("ok"))
        self.assertNotEqual(
            PLACE.panel_height_for_status("pending_season_data"),
            PLACE.panel_height_for_status("ok"),
        )

    def test_hidden_cutoffs_is_ignored(self):
        self.assertFalse(PLACE.cutoffs_is_usable(None))
        self.assertFalse(PLACE.cutoffs_is_usable({"shown": False, "right": 900}))
        self.assertTrue(PLACE.cutoffs_is_usable({"shown": True, "right": None}))
        self.assertTrue(PLACE.cutoffs_is_usable({"shown": True, "right": 900}))

    def test_horizontal_space_check(self):
        self.assertTrue(PLACE.has_horizontal_space(800, 1600, PLACE.MAIN_W, 1.0))
        self.assertFalse(PLACE.has_horizontal_space(1300, 1600, PLACE.MAIN_W, 1.0))
        self.assertFalse(PLACE.has_horizontal_space(None, 1600, PLACE.MAIN_W, 1.0))

    def test_choose_placement_never_stacks_vertically(self):
        self.assertEqual(
            "attach_challenges",
            PLACE.choose_placement(True, 800, None, 1600, PLACE.MAIN_W, 1.0),
        )
        self.assertEqual(
            "attach_cutoffs",
            PLACE.choose_placement(True, 800, {"shown": True, "right": 900}, 1600, PLACE.MAIN_W, 1.0),
        )
        self.assertEqual(
            "attach_cutoffs",
            PLACE.choose_placement(True, 800, {"shown": True, "right": 1300}, 1600, PLACE.MAIN_W, 1.0),
        )
        self.assertEqual(
            "attach_challenges",
            PLACE.choose_placement(True, 1300, {"shown": False, "right": 900}, 1600, PLACE.MAIN_W, 1.0),
        )
        self.assertEqual(
            "pending_attach",
            PLACE.choose_placement(True, None, None, 1600, PLACE.MAIN_W, 1.0),
        )
        self.assertEqual(
            "standalone",
            PLACE.choose_placement(False, 800, {"shown": True, "right": 900}, 1600, PLACE.MAIN_W, 1.0),
        )
        self.assertNotIn("below", PLACE.choose_placement(True, 800, {"shown": True, "right": 900}, 1600))

    def test_clamp_rect_stays_inside_parent(self):
        left, bottom = PLACE.clamp_rect(-40, -20, PLACE.MAIN_W, 236, 0, 0, 1600, 900)
        self.assertGreaterEqual(left, 16)
        self.assertGreaterEqual(bottom, 16)
        self.assertLessEqual(left + PLACE.MAIN_W, 1600 - 16)
        self.assertLessEqual(bottom + 236, 900 - 16)

    def test_default_standalone_avoids_bottom_action_bar(self):
        left, bottom = PLACE.default_standalone_point(1600, 900, PLACE.MAIN_W, 236)
        self.assertGreaterEqual(bottom, 140)
        self.assertGreater(left, 800)

    def test_detail_flips_when_right_side_is_tight(self):
        self.assertEqual("right", PLACE.choose_detail_side(200, 580, 0, 1600))
        self.assertEqual("left", PLACE.choose_detail_side(1100, 1480, 0, 1600))
        self.assertEqual("standalone", PLACE.choose_detail_side(600, 980, 500, 1100))

    def test_detail_prefers_left_when_right_covers_objectives(self):
        self.assertEqual(
            "left",
            PLACE.choose_detail_side(500, 818, 0, 1600, objectives_left=830, objectives_right=1100),
        )

    def test_tooltip_side_avoids_objectives_when_other_side_has_room(self):
        self.assertEqual(
            "left",
            PLACE.choose_tooltip_side(
                900, 1210, 700, 672,
                objectives_rect={"left": 1280, "right": 1580, "top": 860, "bottom": 200},
            ),
        )
        self.assertEqual(
            "right",
            PLACE.choose_tooltip_side(
                200, 510, 700, 672,
                objectives_rect={"left": 0, "right": 180, "top": 860, "bottom": 200},
            ),
        )

    def test_tooltip_side_does_not_cover_most_of_main_panel(self):
        self.assertEqual(
            "right",
            PLACE.choose_tooltip_side(
                900, 1218, 700, 672,
                main_rect={"left": 620, "right": 938, "top": 720, "bottom": 350},
            ),
        )


class LuaPlacementContractTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = (ROOT / "KeystoneMeta.lua").read_text(encoding="utf-8")

    def test_lua_exposes_named_helpers(self):
        for name in (
            "PanelHeightForStatus",
            "HasHorizontalSpace",
            "ClampRect",
            "ClampFrameToUIParent",
            "ChoosePlacement",
            "CutoffsIsUsable",
            "ScheduleReanchor",
            "DefaultStandalonePoint",
            "ChooseDetailSide",
            "SaveSettingsPosition",
            "SetDropdownChevron",
            "OpenSpecMenu",
            "BuildSpecMenuDescription",
            "SelectSpecId",
            "PlaceOwnedMenu",
            "PopulatedPanelHeight",
            "ApplyCompanionChrome",
            "CreateCompanionFrame",
            "UpdateContainedScroll",
            "ChooseTooltipSide",
            "CreateRoleTabs",
        ):
            self.assertIn(f"function {name}", self.lua)

    def test_no_vertical_cutoffs_anchor(self):
        self.assertNotIn('KeystoneCutoffsPanel, "BOTTOMLEFT"', self.lua)
        self.assertNotIn('KeystoneCutoffsPanel, "BOTTOMRIGHT"', self.lua)
        self.assertNotIn('"BOTTOMLEFT", 0, -6', self.lua)
        self.assertIn('SetPoint("TOPLEFT", _G.KeystoneCutoffsPanel, "TOPRIGHT"', self.lua)

    def test_cutoffs_usable_when_shown(self):
        self.assertIn("function CutoffsIsUsable", self.lua)
        self.assertIn("panel:IsShown()", self.lua)

    def test_challenges_auto_shows_and_hides_companion(self):
        show = self.lua.split("local function OnChallengesShow()", 1)[1].split(
            "local function OnChallengesHide()", 1
        )[0]
        hide = self.lua.split("local function OnChallengesHide()", 1)[1].split(
            "local function WatchCutoffs()", 1
        )[0]
        self.assertIn("ShowMain()", show)
        self.assertIn("ScheduleReanchor()", show)
        self.assertIn("CompanionIsDismissed()", show)
        self.assertIn("HideMain()", hide)
        self.assertIn("hidingWithParent = true", hide)
        self.assertNotIn("dismissedThisChallengesSession = false", hide)
        self.assertNotIn("RestoreStandalonePosition()", hide)
        toggle = self.lua.split("local function ToggleWindow()", 1)
        if len(toggle) < 2:
            toggle = self.lua.split("ToggleWindow = function()", 1)
        toggle = toggle[1].split("local function ReevaluatePlacement()", 1)[0]
        self.assertIn("SetCompanionDismissed(not CompanionIsDismissed())", toggle)
        self.assertIn("ApplyCompanionVisibility()", toggle)
        visibility = self.lua.split("ApplyCompanionVisibility = function()", 1)[1].split(
            "ToggleWindow = function()", 1
        )
        if len(visibility) < 2:
            visibility = self.lua.split("ApplyCompanionVisibility = function()", 1)[1].split(
                "local function ToggleWindow()", 1
            )[0]
        else:
            visibility = visibility[0]
        self.assertIn("IsChallengesVisible()", visibility)
        self.assertIn("ShowMain()", visibility)
        self.assertIn("HideMain()", visibility)
        main = self._create_main_panel()
        on_hide = main.split('frame:SetScript("OnHide"', 1)[1].split("frame.close", 1)[0]
        self.assertNotIn("SetCompanionDismissed", on_hide)
        self.assertIn("SetCompanionDismissed(true)", main)
        self.assertNotIn("settingsBtn", main)
        self.assertNotIn("CreateChromeSettingsButton", self.lua)
        self.assertIn("Show with Group Finder", self.lua)
        hook = self.lua.split("local function HookChallenges()", 1)[1].split(
            "local function InitializeMinimap()", 1
        )[0]
        self.assertIn("PVEFrame:HookScript(\"OnShow\"", hook)
        self.assertIn("PVEFrame:HookScript(\"OnHide\", OnChallengesHide)", hook)
        self.assertIn("ChallengesFrame:IsShown()", hook)
        self.assertIn("OnChallengesShow()", hook)

    def test_pending_and_populated_constants(self):
        self.assertIn("MAIN_H_PENDING = 220", self.lua)
        self.assertIn("MAIN_H_POPULATED = 370", self.lua)
        self.assertIn("MAIN_W = 318", self.lua)
        self.assertIn("SETTINGS_W = 340", self.lua)
        self.assertIn("MAIN_H_MAX = 480", self.lua)
        self.assertIn("TOOLTIP_MAX_WIDTH = 280", self.lua)

    def test_selector_uses_texture_not_unicode(self):
        self.assertIn("function SetDropdownChevron", self.lua)
        self.assertIn("KeystoneMeta\\\\Assets\\\\chevron_right", self.lua)
        self.assertIn("specChevron = frame.specHit:CreateTexture", self.lua)
        self.assertNotIn("specChevron = CreateFS", self.lua)
        self.assertNotIn("UI-ChatIcon-ScrollDown-Up", self.lua)
        self.assertNotIn('"▼"', self.lua)
        self.assertNotIn('"▲"', self.lua)
        self.assertNotIn('"⌄"', self.lua)

    def test_dropdown_is_overlay_and_does_not_resize_main(self):
        self.assertIn("function OpenSpecMenu", self.lua)
        self.assertIn("MenuUtil.CreateContextMenu", self.lua)
        self.assertIn('SetPoint("TOPLEFT", anchor, "BOTTOMLEFT"', self.lua)
        self.assertIn('SetPoint("BOTTOMLEFT", anchor, "TOPLEFT"', self.lua)
        self.assertNotIn("RestorePendingLayout", self.lua)
        self.assertNotIn("MAIN_H_PENDING + extra", self.lua)
        self.assertNotIn("frame:SetHeight(MAIN_H_PENDING +", self.lua)
        click = self.lua.split("frame.specHit:SetScript(\"OnClick\"", 1)[1].split("frame.specHit:SetScript(\"OnEnter\"", 1)[0]
        self.assertNotIn("SetHeight", click)
        self.assertIn("OpenSpecMenu(frame.specHit)", click)

    def test_pending_footer_does_not_claim_real_runs(self):
        self.assertIn("PendingFooterText()", self.lua)
        self.assertIn("Awaiting first Raider.IO snapshot", self.lua)
        self.assertIn("FreshnessLabel()", self.lua)
        self.assertIn("parts[#parts + 1] = fresh", self.lua)
        self.assertNotIn("Updated daily", self.lua)
        self.assertNotIn('SafeSetText(mainFrame.footer, "Raider.IO")', self.lua)

    def test_methodology_tooltip_is_bounded(self):
        self.assertNotIn("https://raider.io", self.lua)
        self.assertIn("Source: Raider.IO", self.lua)
        self.assertIn("TOOLTIP_MAX_WIDTH = 280", self.lua)
        self.assertNotIn("TOOLTIP_MIN_WIDTH", self.lua)
        self.assertIn("function AnchorTooltipOutside", self.lua)
        self.assertIn("function ChooseTooltipSide", self.lua)
        self.assertIn("GetObjectivesRect", self.lua)

    def test_pending_hides_populated_rows(self):
        self.assertIn("ReleaseRows(dungeonRows)", self.lua)
        self.assertIn('if status ~= "ok" then', self.lua)
        self.assertIn("CloseDetail()", self.lua)
        self.assertIn("mainFrame.list:Hide()", self.lua)
        self.assertIn("ShowEmptyState", self.lua)

    def test_populated_row_fields(self):
        for field in ("row.short", "row.name", "row.share", "row.delta"):
            self.assertIn(field, self.lua)
        self.assertNotIn("row.bar", self.lua)
        self.assertNotIn("row.sep", self.lua)
        self.assertIn("showDailyMovement", self.lua)
        self.assertIn("Dungeon Representation", self.lua)
        self.assertIn('string.format("Average %s%s"', self.lua)
        self.assertIn("did not appear in this sample", self.lua)
        self.assertNotIn("DPS specs", self.lua)

    def test_panel_text_has_no_outline_control(self):
        self.assertIn("SetShadowOffset(0, 0)", self.lua)
        self.assertNotIn("Font outline", self.lua)
        self.assertNotIn("THICKOUTLINE", self.lua)
        self.assertIn("SHORT_COL_W = 48", self.lua)
        self.assertIn('return "pending_attach"', self.lua)

    def test_insufficient_cells_never_use_zero_percent(self):
        self.assertIn("EMPTY_CELL = \"--\"", self.lua)
        self.assertIn("SafeSetText(row.share, EMPTY_CELL)", self.lua)
        self.assertNotIn('SafeSetText(row.share, "0%")', self.lua)
        self.assertNotIn('SafeSetText(row.share, "0.0%")', self.lua)

    def test_settings_position_persists(self):
        self.assertIn("settingsPosition", self.lua)
        self.assertIn("function SaveSettingsPosition", self.lua)
        self.assertIn("function PlaceSettingsWindow", self.lua)

    def test_frames_clamp_to_screen(self):
        self.assertIn("function ClampFrameToUIParent", self.lua)
        self.assertGreaterEqual(self.lua.count("ClampFrameToUIParent("), 4)

    def test_detail_popout_flips(self):
        self.assertIn("function ChooseDetailSide", self.lua)
        self.assertIn('side == "right"', self.lua)
        self.assertIn('side == "left"', self.lua)

    def test_first_dungeon_click_shows_detail_before_refresh(self):
        click = self.lua.split("row:SetScript(\"OnClick\", function(self)", 1)[1].split(
            "return row", 1
        )[0]
        open_path = click.split("viewState.dungeonId = self.dungeonId", 1)[1]
        self.assertLess(open_path.find("detailFrame:Show()"), open_path.find("RefreshUI()"))
        self.assertNotIn("PositionPanels()", open_path.split("RefreshUI()", 1)[0])

    def test_settings_content_fills_the_window(self):
        settings = self.lua.split("local function CreateSettingsWindow()", 1)[1].split(
            "local function ToggleSettings()", 1
        )[0]
        self.assertIn('makeTabButton("display", "Display"', settings)
        self.assertIn('makeTabButton("customize", "Customize"', settings)
        self.assertIn("ApplyGoldOutline(win)", settings)
        self.assertIn("Show with Group Finder", settings)
        self.assertIn("MakeSettingsCheckbox", settings)
        self.assertIn("MakeSettingsSlider", settings)
        self.assertIn("MakeSettingsButton", settings)
        self.assertIn("Reset Panel Position", settings)
        self.assertNotIn("MakeSettingsDropdown", settings)
        self.assertIn("Background opacity", settings)
        self.assertNotIn('y, "Font"', settings)
        self.assertIn("UI-CheckBox-Check", self.lua)
        self.assertNotIn("WowStyle1DropdownTemplate", self.lua)
        self.assertNotIn("UICheckButtonTemplate", self.lua)
        self.assertNotIn("UISliderTemplate", self.lua)
        self.assertIn("SetThumbTexture", self.lua)
        minimap = self.lua.split("local function InitializeMinimap()", 1)[1].split(
            "UpdateMinimapButton = function()", 1
        )[0]
        self.assertIn('button == "RightButton"', minimap)
        self.assertIn("ToggleWindow()", minimap)
        self.assertIn("ToggleSettings()", minimap)
        self.assertIn("Left-click:|r Open settings", minimap)
        self.assertIn("Right-click:|r Toggle Group Finder panel", minimap)

    def test_footer_does_not_wrap(self):
        main = self._create_main_panel()
        self.assertIn("frame.footer:SetWordWrap(false)", main)
        self.assertNotIn("frame.fresh", main)
        self.assertNotIn("GameFontDisableSmall", self.lua)

    def _create_main_panel(self):
        return self.lua.split("local function CreateMainPanel()", 1)[1].split("local function EnsureUI()", 1)[0]

    def test_main_dungeon_list_has_no_scrollframe(self):
        main = self._create_main_panel()
        self.assertNotIn("UIPanelScrollFrameTemplate", main)
        self.assertNotIn("ScrollBox", main)
        self.assertNotIn("ScrollBar", main)
        self.assertNotIn('CreateFrame("ScrollFrame"', main)
        self.assertIn('frame.list = CreateFrame("Frame", nil, listHost)', main)
        self.assertNotIn("InsetFrameTemplate", main)
        self.assertNotIn("ButtonFrameTemplate", main)
        self.assertNotIn("UIPanelScrollFrameTemplate", main)

    def test_root_spec_menu_is_hierarchical_not_flat(self):
        desc = self.lua.split("local function BuildSpecMenuDescription", 1)[1].split(
            "local function PlaceOwnedMenu", 1
        )[0]
        self.assertIn("CurrentClassSpecs()", desc)
        self.assertIn('CreateButton("Browse all specializations")', desc)
        self.assertIn("CollectSpecsByClass()", desc)
        self.assertNotIn("ipairs(CollectSpecs())", desc)
        self.assertIn("AddSpecRadio(rootDescription, spec)", desc)
        self.assertIn("AddSpecRadio(browse, spec)", desc)
        self.assertIn("browse:CreateTitle(group.name)", desc)
        self.assertNotIn("AddSpecRadio(classBtn, spec)", desc)
        self.assertNotIn("browse:CreateButton(group.name)", desc)

    def test_selecting_menu_entry_updates_specialization(self):
        select = self.lua.split("local function SelectSpecId(specId)", 1)[1].split(
            "local function SpecIsSelected", 1
        )[0]
        self.assertIn("viewState.specId = specId", select)
        self.assertIn("db().selectedSpecId = specId", select)
        self.assertIn("db().followCurrentSpec = false", select)
        self.assertIn("RefreshUI()", select)

    def test_outside_click_catcher_cannot_intercept_menu_rows(self):
        self.assertIn('dropdownCatcher:SetFrameStrata("DIALOG")', self.lua)
        self.assertNotIn('dropdownCatcher:SetFrameStrata("TOOLTIP")', self.lua)
        open_fn = self.lua.split("local function OpenSpecMenu(anchor)", 1)[1].split(
            "local function MakeSettingsCheckbox", 1
        )[0]
        menuutil = open_fn.split("if MenuUtil and MenuUtil.CreateContextMenu then", 1)[1].split(
            "OpenSpecMenuFallback", 1
        )[0]
        self.assertNotIn("ShowCatcher", menuutil)
        self.assertIn("MenuUtil.CreateContextMenu", menuutil)

    def test_eight_season_rows_render_without_scroll(self):
        refresh = self.lua.split("local function RefreshMainPanel()", 1)[1].split(
            "local function RefreshDetailPanel()", 1
        )[0]
        self.assertIn("for _, entry in ipairs(SortedDungeons()) do", refresh)
        self.assertIn("AcquireRow(dungeonRows, mainFrame.list, BuildDungeonRow)", refresh)
        self.assertNotIn("mainFrame.scroll", refresh)
        self.assertIn("PopulatedPanelHeight()", refresh)

    def test_no_runtime_dependency_on_reference_addons(self):
        self.assertNotIn("QuickLoadoutManager", self.lua)
        self.assertNotIn("QuickLoadoutManagerDB", self.lua)
        self.assertNotIn("Interface\\AddOns\\QuickLoadoutManager", self.lua)
        self.assertNotIn("Interface\\AddOns\\KeystoneCutoffs", self.lua)
        self.assertNotIn("ButtonFrameTemplate", self.lua)
        self.assertNotIn("InsetFrameTemplate", self.lua)
        self.assertNotIn("UIPanelButtonTemplate", self.lua)
        self.assertNotIn("function ApplyNativeShell", self.lua)
        self.assertNotIn("function CreateListHeader", self.lua)
        self.assertIn("TooltipBackdropTemplate", self.lua)
        self.assertIn("function ApplyCompanionChrome", self.lua)
        chrome = self.lua.split("local function ApplyCompanionChrome(frame)", 1)[1].split(
            "local function CreateCompanionFrame", 1
        )[0]
        self.assertIn("if frame.NineSlice then", chrome)
        self.assertIn("NineSlice.Center:SetAlpha", chrome)
        self.assertNotIn("Center:SetColorTexture", chrome)
        self.assertLess(chrome.find("if frame.NineSlice then"), chrome.find("SetBackdropColor"))
        self.assertNotIn("WowStyle1DropdownTemplate", self.lua)
        self.assertNotIn("UISliderTemplate", self.lua)
        self.assertNotIn("UICheckButtonTemplate", self.lua)
        self.assertIn("UI-CheckBox-Check", self.lua)
        self.assertNotIn("SettingsCheckboxTemplate", self.lua)

    def test_uses_copied_local_assets_only(self):
        self.assertIn("Interface\\\\AddOns\\\\KeystoneMeta\\\\Assets\\\\chevron_right", self.lua)
        self.assertNotIn("Interface\\\\AddOns\\\\KeystoneCutoffs\\\\Assets", self.lua)
        self.assertTrue((ROOT / "Assets" / "chevron_right.tga").exists())

    def test_footer_divider_has_line_gap(self):
        self.assertIn("FOOTER_LINE_GAP = 8", self.lua)
        self.assertIn("FOOTER_H + FOOTER_LINE_GAP", self.lua)
        main = self._create_main_panel()
        self.assertIn(
            'listHost:SetPoint("BOTTOMRIGHT", -PAD, BOTTOM_PAD + FOOTER_H + FOOTER_LINE_GAP + AFTER_LIST)',
            main,
        )
        self.assertIn(
            'frame.footerDivider:SetPoint("BOTTOMLEFT", PAD, BOTTOM_PAD + FOOTER_H + FOOTER_LINE_GAP)',
            main,
        )
        self.assertIn('footerBar:SetPoint("BOTTOMLEFT", PAD, BOTTOM_PAD)', main)
        self.assertNotIn("FOOTER_H + 4", main)
        self.assertNotIn("BOTTOM_PAD - 2", main)

    def test_main_highlight_uses_view_state(self):
        refresh = self.lua.split("local function RefreshMainPanel()", 1)[1].split(
            "local function RefreshDetailPanel()", 1
        )[0]
        self.assertIn("viewState.dungeonId", refresh)
        self.assertIn("detailFrame:IsShown()", refresh)
        self.assertNotIn("detailFrame.dungeonId", refresh)

    def test_challenges_visible_consults_pveframe(self):
        fn = self.lua.split("local function IsChallengesVisible()", 1)[1].split(
            "local function CutoffsIsUsable()", 1
        )[0]
        self.assertIn("PVEFrame", fn)
        self.assertIn("PVEFrame:IsShown()", fn)
        self.assertIn("ChallengesFrame:IsShown()", fn)

    def test_spec_hit_is_dropdown_control(self):
        main = self._create_main_panel()
        self.assertIn("frame.specHit:SetBackdrop(BD_EDGE)", main)
        self.assertIn("mixBD(frame.specHit)", main)
        self.assertIn('frame.specChevron:SetPoint("RIGHT", -6, 0)', main)
        chevron = self.lua.split("local function SetDropdownChevron", 1)[1].split(
            "local function SetHelpIcon", 1
        )[0]
        self.assertIn("SetSize(18, 18)", chevron)
        self.assertNotIn("SetSize(14, 14)", chevron)

    def test_attached_drag_saves_offset_without_shift(self):
        main = self._create_main_panel()
        drag = main.split('frame:SetScript("OnDragStop"', 1)[1].split(
            'frame:SetScript("OnHide"', 1
        )[0]
        self.assertIn("db().attachedOffset", drag)
        self.assertIn("ApplyAnchor()", drag)
        self.assertNotIn("_shiftDrag", drag)
        self.assertNotIn("IsShiftKeyDown", drag)
        start = main.split('frame:SetScript("OnDragStart"', 1)[1].split(
            'frame:SetScript("OnDragStop"', 1
        )[0]
        self.assertNotIn("_shiftDrag", start)
        self.assertNotIn("IsShiftKeyDown", start)

    def test_detail_scrollbar_stays_inside_inset(self):
        detail = self.lua.split("local function CreateDetailPanel()", 1)[1].split(
            "local function CreateMainPanel()", 1
        )[0]
        self.assertIn("UIPanelScrollFrameTemplate", detail)
        self.assertIn("-SCROLL_GUTTER", detail)
        self.assertIn("UpdateContainedScroll", self.lua)
        self.assertIn("bar:SetShown(overflow)", self.lua)
        main = self._create_main_panel()
        self.assertNotIn("UIPanelScrollFrameTemplate", main)


class SyntheticFixtureTests(TestCase):
    def test_fixture_is_unmistakably_synthetic(self):
        text = (ROOT / "tests" / "fixtures" / "synthetic" / "visual_snapshot.lua").read_text(encoding="utf-8")
        self.assertIn("isSynthetic = true", text)
        self.assertIn("SYNTHETIC VISUAL TEST", text)
        self.assertIn("Altar of Fangs", text)
        self.assertIn("insufficient_data", text)
        self.assertGreaterEqual(text.count("roleSharePct"), 8)
        self.assertGreaterEqual(len(re.findall(r"\[\d{4}\]\s*=\s*\{", text)), 8)

    def test_fixture_has_movement_variety_and_eight_dungeons(self):
        text = (ROOT / "tests" / "fixtures" / "synthetic" / "visual_snapshot.lua").read_text(encoding="utf-8")
        self.assertIn("deltaPercentagePoints = 1.4", text)
        self.assertIn("deltaPercentagePoints = -", text)
        self.assertIn("deltaPercentagePoints = 0.0", text)
        self.assertIn("Temple of Sethraliss", text)
        self.assertIn('status = "insufficient_data"', text)
        ids = re.findall(r"\[(900\d)\]\s*=\s*\{", text)
        self.assertEqual(8, len(set(ids)))

    def test_lua_lists_all_dungeons_including_insufficient(self):
        lua = (ROOT / "KeystoneMeta.lua").read_text(encoding="utf-8")
        refresh = lua.split("local function RefreshMainPanel()", 1)[1].split("local function RefreshDetailPanel()", 1)[0]
        populated = refresh.split("mainFrame.list:Show()", 1)[1]
        acquire_at = populated.find("AcquireRow(dungeonRows")
        useful_at = populated.find("DungeonUseful(entry.dungeon)")
        self.assertIn("for _, entry in ipairs(SortedDungeons()) do", populated)
        self.assertGreaterEqual(acquire_at, 0)
        self.assertGreater(useful_at, acquire_at)

    def test_active_data_blocks_packaging_when_synthetic(self):
        with self.assertRaises(SystemExit):
            VALIDATE.assert_not_synthetic("KeystoneMetaData = { isSynthetic = true }", "active")

    def test_active_production_placeholder_is_not_synthetic(self):
        VALIDATE.validate_release_data(ROOT / "KeystoneMetaData.lua")
        text = (ROOT / "KeystoneMetaData.lua").read_text(encoding="utf-8")
        self.assertNotIn("isSynthetic = true", text)

    def test_zip_with_synthetic_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "synthetic.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("KeystoneMeta/KeystoneMeta.toc", "## Interface: 120100\n")
                archive.writestr("KeystoneMeta/KeystoneMetaData.lua", "KeystoneMetaData = { isSynthetic = true }\n")
            with self.assertRaises(SystemExit):
                VALIDATE.validate_zip(path)

    def test_visual_fixture_enable_restore_and_nested_refuse(self):
        original = (ROOT / "KeystoneMetaData.lua").read_text(encoding="utf-8")
        try:
            self.assertEqual(0, FIXTURE.enable())
            active = (ROOT / "KeystoneMetaData.lua").read_text(encoding="utf-8")
            self.assertIn("isSynthetic = true", active)
            self.assertEqual(2, FIXTURE.enable())
            self.assertEqual(0, FIXTURE.restore())
            restored = (ROOT / "KeystoneMetaData.lua").read_text(encoding="utf-8")
            self.assertEqual(original, restored)
            self.assertFalse((ROOT / ".visual_fixture_backup" / "ACTIVE").exists())
        finally:
            if FIXTURE.BACKUP.exists():
                FIXTURE.restore()
            (ROOT / "KeystoneMetaData.lua").write_text(original, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
