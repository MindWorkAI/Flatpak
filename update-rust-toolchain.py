#!/usr/bin/env python3
"""Find the Rust toolchain which AI Studio builds with, for the module 'rust-toolchain' of the manifest.

Line 6 of AI Studio's metadata.txt names the Rust toolchain of all its builds, e.g., '1.100.0 (commit
0ef1bc386)'. The Flatpak builds with the same toolchain instead of the Rust extension of Flathub, which
often lags behind by several versions. Rust publishes a manifest for each release,
https://static.rust-lang.org/dist/channel-rust-<version>.toml, which names the archive and its checksum
for every target. update-dependencies downloads that manifest, and this script reads the archives of
both Linux architectures from it, after it checked that the manifest describes the very toolchain of
metadata.txt, commit included.
"""
from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path


TOOLCHAIN_PATTERN = re.compile(r"^(?P<version>[0-9]+\.[0-9]+\.[0-9]+) \(commit (?P<commit>[0-9a-f]{7,40})\)$")
RELEASE_PATTERN = re.compile(r"^(?P<version>[0-9]+\.[0-9]+\.[0-9]+) \((?P<commit>[0-9a-f]{7,40}) [0-9]{4}-[0-9]{2}-[0-9]{2}\)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
DIST_URL = "https://static.rust-lang.org/dist/"

# The architectures of the Flatpak and the targets Rust names them by:
TARGETS = {
    "x86_64": "x86_64-unknown-linux-gnu",
    "aarch64": "aarch64-unknown-linux-gnu",
}


class ToolchainError(ValueError):
    pass


def parse_toolchain(line: str) -> tuple[str, str]:
    """Reads the version and the commit from line 6 of metadata.txt."""
    match = TOOLCHAIN_PATTERN.fullmatch(line.strip())
    if match is None:
        raise ToolchainError(
            f"line 6 of metadata.txt names no Rust toolchain: {line!r}; expected e.g. '1.100.0 (commit 0ef1bc386)'"
        )
    return match["version"], match["commit"]


def read_archives(line: str, channel_manifest: str) -> dict[str, tuple[str, str]]:
    """Reads the archive and its SHA-256 checksum for each architecture of the Flatpak."""
    version, commit = parse_toolchain(line)
    try:
        manifest = tomllib.loads(channel_manifest)
    except tomllib.TOMLDecodeError as error:
        raise ToolchainError(f"the manifest of Rust {version} is no valid TOML: {error}") from error

    rust = manifest.get("pkg", {}).get("rust", {})
    release = RELEASE_PATTERN.fullmatch(str(rust.get("version", "")))
    if release is None:
        raise ToolchainError(f"the manifest of Rust {version} names no release of rust: {rust.get('version')!r}")

    # metadata.txt keeps the short hash which rustc prints; the manifest may name a longer one:
    if release["version"] != version or not release["commit"].startswith(commit):
        raise ToolchainError(
            f"the manifest describes Rust {release['version']} (commit {release['commit']}), "
            f"but metadata.txt names Rust {version} (commit {commit})"
        )

    archives: dict[str, tuple[str, str]] = {}
    for architecture, target in TARGETS.items():
        package = rust.get("target", {}).get(target, {})
        url = str(package.get("xz_url", ""))
        sha256 = str(package.get("xz_hash", ""))
        if package.get("available") is not True or not url.startswith(DIST_URL) or SHA256_PATTERN.fullmatch(sha256) is None:
            raise ToolchainError(f"the manifest of Rust {version} has no archive for {target}")
        archives[architecture] = (url, sha256)
    return archives


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find the Rust toolchain which AI Studio builds with.")
    commands = parser.add_subparsers(dest="command", required=True)

    version = commands.add_parser("version", help="print the version which line 6 of metadata.txt names")
    version.add_argument("line", help="line 6 of metadata.txt")

    archives = commands.add_parser("archives", help="print '<architecture> <url> <sha256>' for each architecture")
    archives.add_argument("line", help="line 6 of metadata.txt")
    archives.add_argument("manifest", type=Path, help="the downloaded channel-rust-<version>.toml")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "version":
            print(parse_toolchain(args.line)[0])
        else:
            try:
                channel_manifest = args.manifest.read_text(encoding="utf-8")
            except OSError as error:
                raise ToolchainError(f"cannot read the manifest {args.manifest}: {error}") from error

            for architecture, (url, sha256) in read_archives(args.line, channel_manifest).items():
                print(architecture, url, sha256)
    except ToolchainError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())