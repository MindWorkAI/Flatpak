# Flatpak packaging for MindWork AI Studio

This repository builds MindWork AI Studio as a Flatpak. The manifest
is `org.mindworkai.AIStudio.yml`; `plugins/pandoc` holds the optional
Pandoc plugin.

## How the manifest works

Flatpak builds offline: `flatpak-builder` must not download anything
during the build. Therefore, generated files list all Rust and .NET
dependencies as sources:

- `cargo-sources.json`: the crates of the AI Studio runtime
- `dotnet-sources.json`: the NuGet packages of the AI Studio app
- `tauri-cli-sources.json`: the crates of the Tauri CLI

The manifest has three modules:

- `rust-toolchain` installs the Rust toolchain which the other two
  modules build with. Its cleanup removes everything it installs, so
  the toolchain does not ship with the app.
- `tauri-cli` builds the Tauri CLI, which only the build of AI Studio
  needs. Its cleanup removes everything it installs as well.
- `mind-work-ai-studio` builds AI Studio with that Rust toolchain and
  the .NET extension of the SDK. The .NET server is self-contained, so
  the Flatpak needs no .NET runtime of its own.

The .NET server brings the .NET runtime which line 5 of `metadata.txt`
of AI Studio names, whatever version the .NET extension of the SDK
has: the project file of AI Studio sets `RuntimeFrameworkVersion` from
that line, and `update-dependencies` stops when `dotnet-sources.json`
lacks the runtime packs of that version.

Likewise, AI Studio builds with the Rust toolchain which line 6 of
`metadata.txt` names, like all its other builds, instead of the Rust
extension of Flathub, which often lags behind by several versions.
`update-dependencies` reads the archives of that toolchain from the
manifest of its Rust release, `channel-rust-<version>.toml`, and
`update-rust-toolchain.py` stops when that manifest describes another
version or commit than the line.

## Updating

Every release of AI Studio updates this repository automatically: the
job `sync_flatpak_repo` of the release pipeline in
[MindWorkAI/AI-Studio](https://github.com/MindWorkAI/AI-Studio) sets
the new tag and commit as well as the PDFium archives, regenerates the
three source files and the archives of the Rust toolchain with
`update-dependencies`, and merges the result as the pull request
"Sync AI Studio vX.Y.Z".

Run `update-dependencies` yourself only after changing the manifest by
hand, e.g., when raising the tag of the Tauri CLI. The script reads the
versions of AI Studio and the Tauri CLI from the manifest, regenerates
all three source files, and writes the archives of the Rust toolchain.
It needs:

- `git`, `curl`, `python3` (3.11 or newer), `uv`, and `yq` (the one by
  mikefarah, v4)
- `flatpak` with `org.freedesktop.Sdk//25.08` and
  `org.freedesktop.Sdk.Extension.dotnet10//25.08` from Flathub, since
  the .NET generator restores the NuGet packages inside that SDK

## Building

The workflow "Build Flatpak" (`.github/workflows/flatpak.yml`) builds
the app and the Pandoc plugin for x86_64 and aarch64 and attaches the
bundles to its run. Start it manually on the branch you want to test.

To build locally, run in the top level directory of this repository:

```sh
flatpak-builder build \
  --default-branch=stable \
  --install-deps-from=flathub \
  --user \
  --force-clean \
  --repo=repo \
  --disable-rofiles-fuse \
  org.mindworkai.AIStudio.yml
```

Keep the branch `stable`: the Pandoc plugin builds against the app on
that branch. The command builds into the local `repo` directory
without uploading the Flatpak anywhere. Install the test build with

```sh
flatpak --user install ./repo org.mindworkai.AIStudio
```

or turn it into a bundle:

```sh
flatpak build-bundle \
  --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
  repo AIStudio.flatpak org.mindworkai.AIStudio stable
```

### Building in a container

Without a local Flatpak installation, e.g., on macOS, the image of the
workflow works as well: `ghcr.io/flathub-infra/flatpak-github-actions:gnome-50`,
started with `--privileged`. Inside the container,
`--install-deps-from=flathub` fails, because updating the preinstalled
GNOME SDK fails on overlayfs ("Invalid cross-device link"). Leave the
option out and install the SDK extensions explicitly instead:

```sh
flatpak install --system -y flathub \
  org.freedesktop.Sdk//25.08 \
  org.freedesktop.Sdk.Extension.dotnet10//25.08
```

The image matches the architecture of the host. To build for x86_64
on Apple Silicon, pull the amd64 image by its digest and start it with
`--platform linux/amd64`: the build then runs under Rosetta and takes
about three times as long.
