from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
GENERATOR_PATH = REPOSITORY / "flatpak-dotnet-generator.py"
SPEC = importlib.util.spec_from_file_location("flatpak_dotnet_generator", GENERATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


def add_package(cache: Path, name: str, version: str, digest: bytes) -> None:
    package = cache / name / version
    package.mkdir(parents=True)
    (package / f"{name}.{version}.nupkg.sha512").write_text(
        base64.b64encode(digest).decode("ascii"), encoding="ascii"
    )


class CacheConversionTests(unittest.TestCase):
    def test_converts_deduplicates_and_sorts_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache = Path(temporary_directory)
            add_package(cache, "z.package", "1.0.0", b"z" * 64)
            add_package(cache, "A.Package", "2.0.0", b"a" * 64)
            add_package(cache, "a.package", "1.0.0", b"b" * 64)

            sources = generator.sources_from_cache(cache, "packages")

        self.assertEqual(
            [source["dest-filename"] for source in sources],
            [
                "a.package.1.0.0.nupkg",
                "a.package.2.0.0.nupkg",
                "z.package.1.0.0.nupkg",
            ],
        )
        self.assertEqual(sources[0]["sha512"], (b"b" * 64).hex())
        self.assertEqual(sources[0]["dest"], "packages")
        self.assertEqual(
            sources[0]["url"],
            "https://api.nuget.org/v3-flatcontainer/a.package/1.0.0/a.package.1.0.0.nupkg",
        )

    def test_deduplicates_identical_package_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_cache = root / "first"
            second_cache = root / "second"
            add_package(first_cache, "Package", "1.0.0", b"a" * 64)
            add_package(second_cache, "package", "1.0.0", b"a" * 64)

            class CombinedCache:
                def glob(self, pattern: str) -> list[Path]:
                    return [*first_cache.glob(pattern), *second_cache.glob(pattern)]

                def __str__(self) -> str:
                    return str(root)

            sources = generator.sources_from_cache(CombinedCache(), "nuget-sources")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["dest-filename"], "package.1.0.0.nupkg")

    def test_rejects_conflicting_hashes_for_same_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_cache = root / "first"
            second_cache = root / "second"
            add_package(first_cache, "Package", "1.0.0", b"a" * 64)
            add_package(second_cache, "package", "1.0.0", b"b" * 64)

            class CombinedCache:
                def glob(self, pattern: str) -> list[Path]:
                    return [
                        *first_cache.glob(pattern),
                        *second_cache.glob(pattern),
                    ]

                def __str__(self) -> str:
                    return str(root)

            with self.assertRaisesRegex(generator.PackageError, "conflicting SHA-512"):
                generator.sources_from_cache(CombinedCache(), "nuget-sources")

    def test_atomic_output_is_byte_identical(self) -> None:
        sources = [
            {
                "type": "file",
                "url": "https://example.test/package.nupkg",
                "sha512": "01" * 64,
                "dest": "nuget-sources",
                "dest-filename": "package.1.0.0.nupkg",
            }
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "sources.json"
            generator.write_json_atomically(output, sources)
            first = output.read_bytes()
            generator.write_json_atomically(output, sources)
            second = output.read_bytes()

        self.assertEqual(first, second)
        self.assertEqual(json.loads(first), sources)


class RestoreFailureTests(unittest.TestCase):
    def test_failed_restore_leaves_existing_output_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            bin_directory = root / "bin"
            bin_directory.mkdir()
            flatpak = bin_directory / "flatpak"
            flatpak.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
            flatpak.chmod(0o755)
            output = root / "sources.json"
            original = b"existing output\n"
            output.write_bytes(original)
            project = root / "Broken.csproj"
            project.touch()

            environment = {"PATH": f"{bin_directory}:{Path('/usr/bin')}"}
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR_PATH),
                    str(output),
                    str(project),
                    "--dotnet-args",
                    "--no-cache",
                ],
                capture_output=True,
                text=True,
                env=environment,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("restore failed", result.stderr)
            self.assertIn(str(project), result.stderr)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
