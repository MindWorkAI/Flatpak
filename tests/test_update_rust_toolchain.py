from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPOSITORY / "update-rust-toolchain.py"
SPEC = importlib.util.spec_from_file_location("update_rust_toolchain", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
toolchain = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(toolchain)


LINE = "1.100.0 (commit 0ef1bc386)"
X86_64_URL = "https://static.rust-lang.org/dist/2026-11-12/rust-1.100.0-x86_64-unknown-linux-gnu.tar.xz"
X86_64_HASH = "98ee6bec240e1cfe944f17e7092412dc5ef6e008484bb668c6936d35a7d15acd"
AARCH64_URL = "https://static.rust-lang.org/dist/2026-11-12/rust-1.100.0-aarch64-unknown-linux-gnu.tar.xz"
AARCH64_HASH = "a21f6a21818df07c1e2e7addb570af5444b3fa9dd61e3a207f4fb1c5a5e665c9"


def channel_manifest(
    version: str = "1.100.0 (0ef1bc386 2026-11-09)",
    aarch64: str | None = None,
) -> str:
    """Builds a manifest in the shape of channel-rust-<version>.toml, with only the parts the script reads."""
    if aarch64 is None:
        aarch64 = f"""available = true
xz_url = "{AARCH64_URL}"
xz_hash = "{AARCH64_HASH}"
"""
    return f"""manifest-version = "2"
date = "2026-11-12"

[pkg.rust]
version = "{version}"

[pkg.rust.target.x86_64-unknown-linux-gnu]
available = true
xz_url = "{X86_64_URL}"
xz_hash = "{X86_64_HASH}"

[pkg.rust.target.aarch64-unknown-linux-gnu]
{aarch64}
[pkg.rust.target.x86_64-pc-windows-msvc]
available = true
xz_url = "https://static.rust-lang.org/dist/2026-11-12/rust-1.100.0-x86_64-pc-windows-msvc.tar.xz"
xz_hash = "{"0" * 64}"
"""


class ParseToolchainTests(unittest.TestCase):
    def test_reads_version_and_commit_of_metadata(self) -> None:
        self.assertEqual(toolchain.parse_toolchain(LINE), ("1.100.0", "0ef1bc386"))

    def test_ignores_the_line_break_of_the_line(self) -> None:
        self.assertEqual(toolchain.parse_toolchain(LINE + "\n"), ("1.100.0", "0ef1bc386"))

    def test_rejects_lines_which_name_no_toolchain(self) -> None:
        for line in ["", "1.100.0", "1.100.0 (0ef1bc386)", "1.100.0-nightly (commit 0ef1bc386)", "9.12.0"]:
            with self.subTest(line=line), self.assertRaises(toolchain.ToolchainError):
                toolchain.parse_toolchain(line)


class ReadArchivesTests(unittest.TestCase):
    def test_reads_the_archives_of_both_architectures(self) -> None:
        archives = toolchain.read_archives(LINE, channel_manifest())

        self.assertEqual(
            archives,
            {
                "x86_64": (X86_64_URL, X86_64_HASH),
                "aarch64": (AARCH64_URL, AARCH64_HASH),
            },
        )

    def test_accepts_a_longer_commit_hash_in_the_manifest(self) -> None:
        archives = toolchain.read_archives(LINE, channel_manifest(version="1.100.0 (0ef1bc3861a2b 2026-11-09)"))

        self.assertEqual(archives["x86_64"], (X86_64_URL, X86_64_HASH))

    def test_rejects_a_manifest_of_another_commit(self) -> None:
        # A rebuilt release, or a version which metadata.txt names with a typo, would otherwise bring
        # another compiler into the Flatpak than into all other builds, without a word:
        with self.assertRaisesRegex(toolchain.ToolchainError, "metadata.txt names Rust 1.100.0"):
            toolchain.read_archives(LINE, channel_manifest(version="1.100.0 (58cf8f9c3 2026-11-09)"))

    def test_rejects_a_manifest_of_another_version(self) -> None:
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.read_archives(LINE, channel_manifest(version="1.99.1 (0ef1bc386 2026-10-13)"))

    def test_rejects_a_manifest_without_the_archive_of_an_architecture(self) -> None:
        for aarch64 in [
            "",
            "available = false\n",
            f'available = true\nxz_url = "{AARCH64_URL}"\n',
            f'available = true\nxz_url = "{AARCH64_URL}"\nxz_hash = "not-a-checksum"\n',
            f'available = true\nxz_url = "https://example.invalid/rust.tar.xz"\nxz_hash = "{AARCH64_HASH}"\n',
        ]:
            with self.subTest(aarch64=aarch64), self.assertRaisesRegex(toolchain.ToolchainError, "aarch64-unknown-linux-gnu"):
                toolchain.read_archives(LINE, channel_manifest(aarch64=aarch64))

    def test_rejects_a_manifest_which_is_no_toml(self) -> None:
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.read_archives(LINE, "<html>Not Found</html>")


if __name__ == "__main__":
    unittest.main()