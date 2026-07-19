from __future__ import annotations

import importlib.util
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
UPDATER_PATH = REPOSITORY / "update-metainfo.py"
SPEC = importlib.util.spec_from_file_location("update_metainfo", UPDATER_PATH)
assert SPEC is not None and SPEC.loader is not None
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


INITIAL_METAINFO = """<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>org.mindworkai.AIStudio</id>
  <releases>
    <release type="stable" version="26.7.2" date="2026-07-07">
      <description><p>Previous update</p></description>
    </release>
    <release type="stable" version="26.6.1" date="2026-06-16">
      <description><p>First release</p></description>
    </release>
  </releases>
</component>
"""


class UpdateMetainfoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "metainfo.xml"
        self.path.write_text(INITIAL_METAINFO, encoding="utf-8")

    def releases(self) -> list[ET.Element]:
        releases = ET.parse(self.path).getroot().find("releases")
        assert releases is not None
        return releases.findall("release")

    def test_adds_new_release_before_existing_history(self) -> None:
        updater.update_metainfo(self.path, "26.7.3", "2026-07-15")

        releases = self.releases()
        self.assertEqual(
            [release.get("version") for release in releases],
            ["26.7.3", "26.7.2", "26.6.1"],
        )
        self.assertEqual(releases[0].get("type"), "stable")
        self.assertEqual(releases[0].get("date"), "2026-07-15")
        self.assertEqual(releases[0].findtext("description/p"), "Update")
        self.assertEqual(releases[1].findtext("description/p"), "Previous update")

    def test_promotes_existing_release_without_replacing_its_description(self) -> None:
        updater.update_metainfo(self.path, "26.6.1", "2026-06-17")

        releases = self.releases()
        self.assertEqual(
            [release.get("version") for release in releases], ["26.6.1", "26.7.2"]
        )
        self.assertEqual(releases[0].get("date"), "2026-06-17")
        self.assertEqual(releases[0].findtext("description/p"), "First release")

    def test_repeated_update_is_byte_identical(self) -> None:
        updater.update_metainfo(self.path, "26.7.3", "2026-07-15")
        first = self.path.read_bytes()
        updater.update_metainfo(self.path, "26.7.3", "2026-07-15")

        self.assertEqual(self.path.read_bytes(), first)
        self.assertEqual(
            sum(release.get("version") == "26.7.3" for release in self.releases()), 1
        )

    def test_rejects_invalid_version_without_modifying_file(self) -> None:
        original = self.path.read_bytes()
        with self.assertRaises(updater.MetainfoError):
            updater.update_metainfo(self.path, "v26.7", "2026-07-15")
        self.assertEqual(self.path.read_bytes(), original)

    def test_rejects_invalid_date_without_modifying_file(self) -> None:
        original = self.path.read_bytes()
        with self.assertRaises(updater.MetainfoError):
            updater.update_metainfo(self.path, "26.7.3", "2026-02-30")
        self.assertEqual(self.path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
