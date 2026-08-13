#!/usr/bin/env python3
"""Validate the AppStream release entry that AI Studio ships for a release.

The entry itself is written in the AI Studio repository by its build script
('dotnet run update-metainfo', which also runs as part of 'dotnet run release').
It has to live there, because the Flatpak build installs the metainfo from the
tagged AI Studio commit rather than from this repository. This script is the
guard in front of that: it fails the release pipeline when the metainfo of the
tagged commit does not describe the release that is being synced.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


class MetainfoError(ValueError):
    pass


def validate_version(version: str) -> str:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise MetainfoError(
            f"invalid release version {version!r}; expected three numeric components"
        )
    return version


def validate_date(date: str) -> str:
    try:
        parsed = dt.date.fromisoformat(date)
    except ValueError as error:
        raise MetainfoError(
            f"invalid release date {date!r}; expected a real date in YYYY-MM-DD format"
        ) from error
    if parsed.isoformat() != date:
        raise MetainfoError(
            f"invalid release date {date!r}; expected YYYY-MM-DD format"
        )
    return date


def load_metainfo(path: Path) -> tuple[ET.ElementTree, ET.Element]:
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as error:
        raise MetainfoError(f"cannot read valid metainfo XML from {path}: {error}") from error

    releases = tree.getroot().find("releases")
    if releases is None:
        raise MetainfoError(f"metainfo XML in {path} has no <releases> element")
    return tree, releases


def check_metainfo(path: Path, version: str, date: str) -> None:
    version = validate_version(version)
    date = validate_date(date)
    _, releases = load_metainfo(path)
    all_releases = releases.findall("release")
    if not all_releases:
        raise MetainfoError(f"metainfo XML in {path} has no releases")

    current = all_releases[0]
    expected = {"type": "stable", "version": version, "date": date}
    actual = {name: current.get(name) for name in expected}
    if actual != expected:
        raise MetainfoError(
            f"top metainfo release is {actual}, expected {expected}"
        )
    if sum(release.get("version") == version for release in all_releases) != 1:
        raise MetainfoError(f"release version {version!r} is not unique")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the current stable AppStream release entry."
    )
    parser.add_argument("version")
    parser.add_argument("date")
    parser.add_argument(
        "--check",
        action="store_true",
        help="accepted for compatibility with the release pipeline; validating is the only mode",
    )
    parser.add_argument("--metainfo", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        check_metainfo(args.metainfo, args.version, args.date)
    except MetainfoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())