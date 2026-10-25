<p align="center">
  <img src="ui/mark.svg" width="72" alt="Codexflare logo">
</p>

<h1 align="center">Codexflare</h1>

<p align="center">Customize Codex startup animations, workspace backgrounds and window modes.<br>Linux · macOS · Windows</p>

<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong></p>

<p align="center">
  <a href="https://github.com/epsilon10111/Codexflare/releases/tag/v0.1.0">Linux downloads</a> ·
  <a href="https://github.com/epsilon10111/Codexflare/releases/tag/v0.1.1">macOS DMG</a> ·
  <a href="docs/guide.en.md">User guide</a> ·
  <a href="docs/guide.en.md#development">Contribute</a>
</p>

## A look inside

### Video editor

Preview speed, brightness, contrast, saturation and sound.

<a href="docs/images/animation-editor.png"><img src="docs/images/animation-editor.png" width="100%" alt="Video editor showing the bundled animation and playback controls"></a>

### Background editor

Choose a built-in image or import a PNG. Set opacity, position and size.

<a href="docs/images/background-editor.png"><img src="docs/images/background-editor.png" width="100%" alt="Background editor showing image selection and blending controls"></a>

### Startup animation

The workspace loads during playback. Press Esc to skip.

<a href="docs/images/startup-preview.png"><img src="docs/images/startup-preview.png" width="100%" alt="Isolated app launch with a Press Esc to skip hint"></a>

### Workspace background

A gentle fade to the left, shared across the conversation and side panel.

<a href="docs/images/workspace-preview.png"><img src="docs/images/workspace-preview.png" width="100%" alt="Simulated main and subagent conversations rendered with the actual app CSS"></a>

<sub>Click an image for full size. The editor and startup images are actual captures. The workspace example uses real app CSS and simulated conversations, with no private chats.</sub>

Launch **fullscreen, at the previous window size, or in a centered window**. One video and two backgrounds are included. Media stays on your computer, and applied changes can be rolled back.

## Download and install

Install Codex separately first. Current source checks application structure instead of requiring an exact version match. The table lists builds with native validation records. Unrecognized resources, window flows, or background layouts prevent application; previews and saved settings remain available.

Run `python tools/manage.py check` for a read-only compatibility check. Published v0.1.0 packages retain their original exact-version restrictions.

| Platform | Native validation baseline / build | Get started |
| --- | --- | --- |
| Linux x86_64 | `26.1002.52244 / 13536` | [RPM](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare-0.1.0-1.noarch.rpm) · [DEB](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare_0.1.0-1_all.deb) |
| macOS Apple Silicon | `26.1021.31345 / 21828` | [Run from main source](docs/guide.en.md#macos) |
| macOS Apple Silicon | `26.1013.31256 / 20586` | [v0.1.1 DMG](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.1/Codexflare-0.1.1-macOS-arm64-build20586.dmg) · [Run from main source](docs/guide.en.md#macos) |
| Windows x64 | `26.1002.52244 / 13536` | [Run from source](docs/guide.en.md#windows) |

**The published v0.1.1 DMG supports build 20586 only** and was validated on macOS 26.6.2. The main source retains build 21828 and adds 20586. Integration into main does not expand the compatibility of that DMG; published tags and assets remain unchanged. The macOS source app is usually `/Applications/ChatGPT.app` or `/Applications/Codex.app`.

Linux expects Codex at `/usr/lib/chatgpt`; Windows targets MSIX `26.1002.7124.0`. The RPM targets Fedora, and the DEB targets Debian 12+ / Ubuntu 24.04+.

<details>
<summary><strong>Quick install on Linux</strong></summary>

Download the matching package, then use one set of commands:

```bash
# Fedora
sudo dnf install ./codexflare-0.1.0-1.noarch.rpm
codexflare
```

```bash
# Debian / Ubuntu
sudo apt install ./codexflare_0.1.0-1_all.deb
codexflare
```

You can also open Codexflare from the application menu. These initial packages are unsigned; see the [installation guide](docs/guide.en.md#linux) for checksums, dependencies and removal.

</details>

<details>
<summary><strong>macOS DMG and the original ChatGPT entry</strong></summary>

Download the DMG and its matching `.sha256` file from the [v0.1.1 Release](https://github.com/epsilon10111/Codexflare/releases/tag/v0.1.1), then verify them in the download directory:

```bash
shasum -a 256 -c Codexflare-0.1.1-macOS-arm64-build20586.dmg.sha256
```

Drag `Codexflare.app` into **Applications** and run it there, rather than inside the read-only DMG. The DMG bundles Python / PyObjC and defaults to original-entry mode. Its data lives in `~/.local/share/codexflare` (or `codexflare/` under an absolute `XDG_DATA_HOME`). The default animation and resized backgrounds work out of the box. Importing custom videos requires separately installed FFmpeg / ffprobe; neither tool is bundled.

Under **System Settings → Privacy & Security → App Management**, authorize the app that performs the modification: **ChatGPT** when running through a ChatGPT task, or **Codexflare** when running the standalone editor. Follow the app name shown by the system prompt. This does not require Full Disk Access or disabling system protections. [Apple permission guide](https://support.apple.com/guide/mac-help/mchl211c911f/26/mac/26)

Save settings and click Apply to ChatGPT (应用到 ChatGPT). Preparation can run while the original app is open; the installer waits for you to **fully quit ChatGPT with Cmd+Q** before replacing it. Continue launching from the original ChatGPT icon. Activating an already running instance does not replay the animation. This mode shares Linux's media preprocessing, background preload, parallel initialization and ready-state transition. It retains the original name, icon, bundle ID, protocols and default configuration path without copying login or chat data.

The installer keeps an official backup verified by signature and full-content hashes, and checks for external app updates before installation or restoration. Before uninstalling, click Restore original ChatGPT (恢复原版 ChatGPT), quit normally, confirm restoration has finished, then delete Codexflare. If an older source installation modified the original entry, restore it with that editor before using the DMG. Do not copy old state or backup files between installations. Users of independent copies do not need to restore the original app.

Source installations still default to an independent copy and separate data. Follow the [source guide](docs/guide.en.md#macos) to install dependencies. From a main source checkout, explicitly enable original-entry mode with:

```bash
.venv/bin/python tools/original_macos.py prepare
.venv/bin/python tools/original_macos.py wait-activate --relaunch
```

The second command waits for the target app to quit normally. Later saves, applications and restoration can be handled by the editor. Source settings and backups live in the repository's `.local/`; do not move or delete that checkout while enabled. See the [installation instructions, Chinese](packaging/macos/安装说明.txt) and [v0.1.1 release record, Chinese](docs/releases/v0.1.1.md) for further DMG installation, restoration and build details.

**The DMG app and modified application use ad-hoc signatures and are not Apple-notarized.** Retaining the original configuration path does not retain OpenAI Developer ID, shared Keychain, notification or native service privileges; another login may still be necessary. Real-account behavior, signature-dependent services and long-running sessions have not been validated. App updates require new compatibility work; never overwrite an updated app with an old backup.

</details>

## Three steps to your setup

1. **Choose your media.** Pick a bundled video and background, or import your own files.
2. **Adjust and save.** Preview the result, choose a window mode, then click Save settings (保存设置).
3. **Apply your settings.** For an independent copy, quit Codex, refresh its status and apply. On Linux, use the original menu entry; for macOS and Windows independent copies, use the new Codexflare entry. In macOS original-entry mode, apply first, fully quit with Cmd+Q and wait for installation, then launch from the original icon.

Reapply after saving to update the customized copy. A startup video cannot guarantee that all network and initialization delays are hidden.

**Independent copies on macOS and Windows use separate login data, so you may need to sign in again.** macOS original-entry mode retains the default configuration path. Modified macOS apps use ad-hoc signatures; the Windows copy loses its vendor signature. Some native services or signature policies may restrict use. See the [platform guide](docs/guide.en.md) for independent copies, and the section above for original-entry mode.

## Documentation and licensing

[Settings and media](docs/guide.en.md#settings) · [Data and removal](docs/guide.en.md#uninstall) · [Development and builds](docs/guide.en.md#development) · [Validation record, Chinese](VALIDATION.md)

Code is licensed under [MIT](LICENSE). Bundled videos, images and media shown in screenshots are distributed with Codexflare under a [separate media license](assets/LICENSE).

An unofficial project, not affiliated with or endorsed by OpenAI. Releases do not include Codex, ChatGPT or Electron binaries.
