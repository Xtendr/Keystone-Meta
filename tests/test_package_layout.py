import importlib.util
import tempfile
import zipfile
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_zip", Path(__file__).resolve().parent / "validate_zip.py")
VALIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATE)


class PackageLayoutTests(TestCase):
    def test_pkgmeta_packages_as_keystonemeta_with_curse_id(self):
        text = (ROOT / ".pkgmeta").read_text(encoding="utf-8")
        self.assertIn("package-as: KeystoneMeta", text)
        self.assertIn("curse-project-id: 1660185", text)

    def test_toc_has_curse_project_id(self):
        text = (ROOT / "KeystoneMeta.toc").read_text(encoding="utf-8")
        self.assertIn("## X-Curse-Project-ID: 1660185", text)
        self.assertIn("## Interface: 120100", text)
        self.assertIn("KeystoneMetaDB", text)

    def test_valid_zip_has_single_top_level_addon_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "KeystoneMeta-0.1.0.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("KeystoneMeta/KeystoneMeta.toc", "## Interface: 120100\n")
                archive.writestr("KeystoneMeta/KeystoneMeta.lua", "-- addon\n")
            VALIDATE.validate_zip(path)

    def test_rejects_zip_containing_synthetic_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "synthetic.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("KeystoneMeta/KeystoneMeta.toc", "## Interface: 120100\n")
                archive.writestr(
                    "KeystoneMeta/KeystoneMetaData.lua",
                    "KeystoneMetaData = { isSynthetic = true }\n",
                )
            with self.assertRaises(SystemExit):
                VALIDATE.validate_zip(path)

    def test_rejects_zip_with_extra_top_level_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("KeystoneMeta/KeystoneMeta.toc", "## Interface: 120100\n")
                archive.writestr("Extra/README.md", "nope\n")
            with self.assertRaises(SystemExit):
                VALIDATE.validate_zip(path)


if __name__ == "__main__":
    main()
