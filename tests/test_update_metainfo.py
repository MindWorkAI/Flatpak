from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
UPDATER_PATH = REPOSITORY / "update-metainfo.py"
SPEC = importlib.util.spec_from_file_location("update_metainfo", UPDATER_PATH)
assert SPEC is not None and SPEC.loader is not None
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


METAINFO_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>org.mindworkai.AIStudio</id>
  <releases>
{releases}
  </releases>
</component>
"""

CURRENT_RELEASE = """    <release type="stable" version="26.7.3" date="2026-07-21">
      <description>
        <ul>
          <li>Fixed the Flatpak page showing an outdated version.</li>
        </ul>
      </description>
    </release>"""

PREVIOUS_RELEASE = """    <release type="stable" version="26.7.2" date="2026-07-07">
      <description>
        <ul>
          <li>Improved reading large files.</li>
        </ul>
      </description>
    </release>"""


class CheckMetainfoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "metainfo.xml"

    def write(self, *releases: str) -> None:
        self.path.write_text(
            METAINFO_TEMPLATE.format(releases="\n".join(releases)), encoding="utf-8"
        )

    def test_accepts_current_release_on_top_of_the_history(self) -> None:
        self.write(CURRENT_RELEASE, PREVIOUS_RELEASE)

        updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

    def test_rejects_history_that_was_not_updated_for_the_release(self) -> None:
        # This is the failure the release pipeline reported for v26.8.1: the app was
        # tagged, but its metainfo still described the previous release.
        self.write(CURRENT_RELEASE, PREVIOUS_RELEASE)

        with self.assertRaises(updater.MetainfoError) as error:
            updater.check_metainfo(self.path, "26.8.1", "2026-08-13")

        self.assertIn("expected", str(error.exception))

    def test_rejects_release_with_a_different_date(self) -> None:
        self.write(CURRENT_RELEASE)

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "26.7.3", "2026-07-22")

    def test_rejects_release_which_is_not_stable(self) -> None:
        self.write(CURRENT_RELEASE.replace('type="stable"', 'type="development"', 1))

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

    def test_rejects_release_which_is_not_on_top(self) -> None:
        self.write(PREVIOUS_RELEASE, CURRENT_RELEASE)

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

    def test_rejects_version_which_appears_more_than_once(self) -> None:
        self.write(CURRENT_RELEASE, PREVIOUS_RELEASE, CURRENT_RELEASE)

        with self.assertRaises(updater.MetainfoError) as error:
            updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

        self.assertIn("not unique", str(error.exception))

    def test_rejects_metainfo_without_any_release(self) -> None:
        self.write()

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

    def test_rejects_metainfo_without_releases_element(self) -> None:
        self.path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n<component/>\n', encoding="utf-8"
        )

        with self.assertRaises(updater.MetainfoError) as error:
            updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

        self.assertIn("<releases>", str(error.exception))

    def test_rejects_metainfo_which_is_no_valid_xml(self) -> None:
        self.path.write_text("<component>", encoding="utf-8")

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "26.7.3", "2026-07-21")

    def test_rejects_invalid_version(self) -> None:
        self.write(CURRENT_RELEASE)

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "v26.7", "2026-07-21")

    def test_rejects_invalid_date(self) -> None:
        self.write(CURRENT_RELEASE)

        with self.assertRaises(updater.MetainfoError):
            updater.check_metainfo(self.path, "26.7.3", "2026-02-30")


if __name__ == "__main__":
    unittest.main()