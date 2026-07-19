#!/usr/bin/env python3
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


def release_blocks(xml: str) -> list[tuple[int, int, ET.Element]]:
    releases_start = re.search(r"<releases\b[^>]*>", xml)
    releases_end = re.search(r"</releases>", xml)
    if (
        releases_start is None
        or releases_end is None
        or releases_end.start() < releases_start.end()
    ):
        raise MetainfoError("metainfo XML has no well-formed <releases> block")

    blocks: list[tuple[int, int, ET.Element]] = []
    content_start = releases_start.end()
    content = xml[content_start:releases_end.start()]
    for start_match in re.finditer(r"(?m)^[ \t]*<release\b", content):
        start = content_start + start_match.start()
        opening_end = xml.find(">", start, releases_end.start())
        if opening_end == -1:
            raise MetainfoError("release element has no closing angle bracket")
        if xml[start:opening_end].rstrip().endswith("/"):
            end = opening_end + 1
        else:
            closing_start = xml.find("</release>", opening_end, releases_end.start())
            if closing_start == -1:
                raise MetainfoError("release element has no closing tag")
            end = closing_start + len("</release>")

        while end < len(xml) and xml[end] in " \t":
            end += 1
        if xml.startswith("\r\n", end):
            end += 2
        elif end < len(xml) and xml[end] == "\n":
            end += 1

        try:
            element = ET.fromstring(xml[start:end].strip())
        except ET.ParseError as error:
            raise MetainfoError(f"invalid release XML: {error}") from error
        blocks.append((start, end, element))
    return blocks


def set_attribute(opening_tag: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(\s{re.escape(name)}=)(['\"])(.*?)\2")
    if pattern.search(opening_tag):
        return pattern.sub(
            lambda match: f'{match.group(1)}"{value}"', opening_tag, count=1
        )
    suffix = "/>" if opening_tag.rstrip().endswith("/>") else ">"
    return opening_tag.rstrip()[:-len(suffix)] + f' {name}="{value}"{suffix}'


def update_metainfo(path: Path, version: str, date: str) -> None:
    version = validate_version(version)
    date = validate_date(date)
    load_metainfo(path)
    xml = path.read_text(encoding="utf-8")
    blocks = release_blocks(xml)
    matching = [block for block in blocks if block[2].get("version") == version]

    if matching:
        current = xml[matching[0][0]:matching[0][1]]
        opening_end = current.find(">") + 1
        opening_tag = current[:opening_end]
        opening_tag = set_attribute(opening_tag, "type", "stable")
        opening_tag = set_attribute(opening_tag, "date", date)
        current = opening_tag + current[opening_end:]
    else:
        indent = "    "
        if blocks:
            indent = re.match(r"[ \t]*", xml[blocks[0][0]:blocks[0][1]]).group()
        current = (
            f'{indent}<release type="stable" version="{version}" date="{date}">\n'
            f"{indent}  <description>\n"
            f"{indent}    <p>Update</p>\n"
            f"{indent}  </description>\n"
            f"{indent}</release>\n"
        )

    for start, end, _ in reversed(matching):
        xml = xml[:start] + xml[end:]

    releases_start = re.search(r"<releases\b[^>]*>", xml)
    assert releases_start is not None
    insertion_point = releases_start.end()
    if xml.startswith("\r\n", insertion_point):
        insertion_point += 2
    elif xml.startswith("\n", insertion_point):
        insertion_point += 1
    else:
        current = "\n" + current
    xml = xml[:insertion_point] + current + xml[insertion_point:]
    path.write_text(xml, encoding="utf-8")


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
        description="Add or promote the current stable AppStream release."
    )
    parser.add_argument("version")
    parser.add_argument("date")
    parser.add_argument("--check", action="store_true", help="validate without modifying XML")
    parser.add_argument("--metainfo", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.check:
            check_metainfo(args.metainfo, args.version, args.date)
        else:
            update_metainfo(args.metainfo, args.version, args.date)
            check_metainfo(args.metainfo, args.version, args.date)
    except MetainfoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
