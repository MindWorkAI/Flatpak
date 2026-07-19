# Flatpak packaging for AI-Studio

Repository for development work on the AI-Studion flatpak.

## Quick notes

Before the app can be built as a Flatpak, all the necessary Rust
and .NET dependencies must be extracted and prepared for the
offline build. Flatpak does not allow downloading of data during
the build process.

To do this, there's the `update-dependencies` script. It extracts
the required versions of AI-Studio and tauri-cli from the
manifest, and updates supplemental sources files. Run this
inside the provided distrobox, to make sure you've everything
in place.

## Manually building

To build the flatpak, enter the distrobox and run

```sh
flatpak-builder build \
  --default-branch=beta \
  --install-deps-from=flathub \
  --user \
  --force-clean \
  --repo=repo \
  --disable-rofiles-fuse \
  org.mindworkai.AIStudio.yml
```

in the top level directory of this repository. Depending on your
hardware you may have to add something like `--jobs=2` to get
past the webkitgtk build. As long as AI-Studio is on tauri v1,
this large build is required, because it relies on ancient
versions that are not available in the flatpak SDKs anymore.

The command above builds to a local `repo` directory without
uploading the flatpak anywhere. You can install the local test
build using

```sh
flatpak --user install ./repo org.mindworkai.AIStudio
```

in your host shell.
