#!/usr/bin/env python3

"""Generate Flatpak NuGet sources after restoring every project successfully."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence


NUGET_SOURCE = "https://api.nuget.org/v3-flatcontainer"


class PackageError(RuntimeError):
    """Raised when the restored NuGet cache is inconsistent or malformed."""


def decode_sha512(path: Path) -> str:
    try:
        digest = base64.b64decode(path.read_text(encoding="ascii").strip(), validate=True)
    except (OSError, UnicodeError, binascii.Error) as error:
        raise PackageError(f"invalid NuGet SHA-512 file '{path}': {error}") from error

    if len(digest) != 64:
        raise PackageError(
            f"invalid NuGet SHA-512 file '{path}': expected 64 bytes, got {len(digest)}"
        )
    return digest.hex()


def sources_from_cache(package_cache: Path, destdir: str) -> list[dict[str, str]]:
    packages: dict[tuple[str, str], dict[str, str]] = {}

    for checksum_path in package_cache.glob("*/*/*.nupkg.sha512"):
        package_name = checksum_path.parent.parent.name.lower()
        version = checksum_path.parent.name.lower()
        identity = (package_name, version)
        filename = f"{package_name}.{version}.nupkg"
        sha512 = decode_sha512(checksum_path)
        source = {
            "type": "file",
            "url": f"{NUGET_SOURCE}/{package_name}/{version}/{filename}",
            "sha512": sha512,
            "dest": destdir,
            "dest-filename": filename,
        }

        previous = packages.get(identity)
        if previous is not None and previous["sha512"] != sha512:
            raise PackageError(
                f"conflicting SHA-512 hashes for NuGet package {package_name} {version}: "
                f"{previous['sha512']} and {sha512}"
            )
        packages[identity] = source

    if not packages:
        raise PackageError(f"no NuGet packages found in '{package_cache}'")

    return [packages[identity] for identity in sorted(packages)]


def restore_command(
    project: Path,
    package_cache: Path,
    freedesktop: str,
    dotnet: str,
    dotnet_args: Sequence[str],
) -> list[str]:
    return [
        "flatpak",
        "run",
        "--env=DOTNET_CLI_TELEMETRY_OPTOUT=true",
        "--env=DOTNET_SKIP_FIRST_TIME_EXPERIENCE=true",
        "--command=sh",
        f"--runtime=org.freedesktop.Sdk//{freedesktop}",
        "--share=network",
        "--filesystem=host",
        f"org.freedesktop.Sdk.Extension.dotnet{dotnet}//{freedesktop}",
        "-c",
        (
            f'PATH="${{PATH}}:/usr/lib/sdk/dotnet{dotnet}/bin" '
            f'LD_LIBRARY_PATH="${{LD_LIBRARY_PATH}}:/usr/lib/sdk/dotnet{dotnet}/lib" '
            'exec dotnet restore "$@"'
        ),
        "--",
        str(project),
        "--packages",
        str(package_cache),
        *dotnet_args,
    ]


def restore_projects(
    projects: Iterable[Path],
    package_cache: Path,
    freedesktop: str,
    dotnet: str,
    dotnet_args: Sequence[str],
) -> None:
    for project in projects:
        print(f"Restoring {project}...", flush=True)
        command = restore_command(project, package_cache, freedesktop, dotnet, dotnet_args)
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"restore failed for '{project}' with exit code {error.returncode}"
            ) from error
        print(f"Restored {project}", flush=True)


def write_json_atomically(output: Path, sources: list[dict[str, str]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(sources, temporary, indent=4)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="output JSON sources file")
    parser.add_argument("project", nargs="+", type=Path, help="project files to restore")
    parser.add_argument("--freedesktop", "-f", default="25.08")
    parser.add_argument("--dotnet", "-d", default="9")
    parser.add_argument("--destdir", default="nuget-sources")
    parser.add_argument(
        "--dotnet-args",
        "-a",
        nargs=argparse.REMAINDER,
        default=[],
        help="additional arguments passed to dotnet restore",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output.resolve()

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".flatpak-dotnet-packages-", dir=output.parent
        ) as temporary_directory:
            package_cache = Path(temporary_directory)
            restore_projects(
                args.project,
                package_cache,
                args.freedesktop,
                args.dotnet,
                args.dotnet_args,
            )
            sources = sources_from_cache(package_cache, args.destdir)
            write_json_atomically(output, sources)
    except (OSError, PackageError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote {len(sources)} NuGet sources to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
