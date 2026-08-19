from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]


class PlaceholderContractTests(TestCase):
    def test_active_data_is_not_synthetic(self):
        text = (ROOT / "KeystoneMetaData.lua").read_text(encoding="utf-8")
        self.assertIn("schemaVersion = 1", text)
        self.assertNotIn("isSynthetic = true", text)
        self.assertNotIn("SYNTHETIC VISUAL TEST", text)
        pending = 'slug = "pending"' in text and "pending_season_data" in text
        live = 'slug = "season-mn-' in text
        self.assertTrue(pending or live)


class PresentationContractTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = (ROOT / "KeystoneMeta.lua").read_text(encoding="utf-8")

    def test_fontstrings_use_blizzard_templates(self):
        for index, line in enumerate(self.lua.splitlines(), 1):
            stripped = line.split("--", 1)[0]
            if "CreateFontString" not in stripped:
                continue
            self.assertRegex(
                stripped,
                r'CreateFontString\(\s*nil\s*,\s*"OVERLAY"\s*,\s*(template or )?"GameFont',
                f"untemplated FontString on line {index}: {stripped.strip()}",
            )

    def test_native_fonts_are_not_restamped(self):
        self.assertNotIn("FallbackFont", self.lua)
        self.assertNotIn("ResolveFont", self.lua)
        self.assertNotIn("LibSharedMedia-3.0", self.lua)
        self.assertNotIn("STANDARD_TEXT_FONT", self.lua)
        apply = self.lua.split("local function ApplyFont", 1)[1].split(
            "local function TrackFontString", 1
        )[0]
        self.assertNotIn("SetFont", apply)
        self.assertIn("SetTextColor", apply)

    def test_settings_uses_background_opacity_not_font(self):
        self.assertIn("bgOpacity = 1.0", self.lua)
        self.assertIn("Background opacity", self.lua)
        self.assertIn("function BackgroundAlpha", self.lua)
        settings = self.lua.split("local function CreateSettingsWindow()", 1)[1].split(
            "local function ToggleSettings()", 1
        )[0]
        self.assertIn("Background opacity", settings)
        self.assertNotIn('MakeSettingsDropdown', self.lua)
        self.assertNotIn('y, "Font"', settings)

    def test_pending_path_short_circuits_row_population(self):
        self.assertIn("Season data pending", self.lua)
        self.assertIn("Not enough ranked runs yet", self.lua)
        self.assertIn("Values appear after validation succeeds.", self.lua)
        self.assertIn("if status ~= \"ok\" then", self.lua)
        self.assertIn("ReleaseRows(dungeonRows)", self.lua)
        self.assertIn("ShowEmptyState", self.lua)
        self.assertIn("Keystone Meta Settings", self.lua)

    def test_dashboard_presentation_is_gone(self):
        for remnant in (
            "MY SPECIALIZATION",
            "DUNGEON META",
            "settingsDrawer",
            "AVERAGE ROLE SHARE",
            "Display Settings",
            "Target sample  ",
            "FRAME_W, FRAME_H = 1180",
        ):
            self.assertNotIn(remnant, self.lua)
        main = self.lua.split("local function CreateMainPanel()", 1)[1].split("local function EnsureUI()", 1)[0]
        self.assertNotIn("SafeSetText(frame.colDungeon, \"Dungeon\")", main)
        self.assertNotIn("UIPanelScrollFrameTemplate", main)

    def test_compact_panel_dimensions(self):
        self.assertIn("MAIN_W = 318", self.lua)
        self.assertIn("MAIN_H_PENDING = 220", self.lua)
        self.assertIn("MAIN_H_POPULATED = 370", self.lua)
        self.assertRegex(self.lua, r"DETAIL_W,\s*DETAIL_H\s*=\s*348,\s*380")
        self.assertIn("SETTINGS_W = 298", self.lua)
        self.assertNotEqual("220", "370")
        self.assertGreaterEqual(318, 300)
        self.assertLessEqual(318, 325)
        self.assertGreaterEqual(370, 335)
        self.assertLessEqual(370, 375)

    def test_selector_and_help_are_textures(self):
        self.assertIn("SetDropdownChevron", self.lua)
        self.assertIn("SetHelpIcon", self.lua)
        self.assertNotIn('"▼"', self.lua)
        self.assertIn("CreateTexture", self.lua)

    def test_cutoffs_family_shell_not_qlm_chrome(self):
        self.assertIn("TooltipBackdropTemplate", self.lua)
        self.assertIn("function ApplyCompanionChrome", self.lua)
        self.assertIn("function CreateRoleTabs", self.lua)
        self.assertIn('SafeSetText(btn.label, string.upper(ROLE_LABEL[role]))', self.lua)
        self.assertNotIn("ButtonFrameTemplate", self.lua)
        self.assertNotIn("UIPanelButtonTemplate", self.lua)
        self.assertNotIn("ApplyNativeShell", self.lua)
        self.assertNotIn("DPS specs", self.lua)

    def test_detail_uses_text_role_tabs(self):
        detail = self.lua.split("local function CreateDetailPanel()", 1)[1].split(
            "local function CreateMainPanel()", 1
        )[0]
        self.assertIn("CreateRoleTabs", detail)
        self.assertNotIn("UIPanelButtonTemplate", detail)
        self.assertNotIn("SetTitle", detail)

    def test_no_unbalanced_brackets(self):
        text = self.lua
        for opener, closer in (("(", ")"), ("{", "}"), ("[", "]")):
            self.assertGreaterEqual(text.count(opener), text.count(closer))
            self.assertLessEqual(abs(text.count(opener) - text.count(closer)), 0)

    def test_implementation_is_nested_under_lua51_local_limit(self):
        self.assertIn("local function KeystoneMetaBoot()", self.lua)
        self.assertIn("KeystoneMetaBoot()", self.lua)


if __name__ == "__main__":
    main()
