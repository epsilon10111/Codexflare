# Codexflare User Guide

[简体中文](guide.zh-CN.md) · **English** · [Back to overview](../README.en.md)

## Compatibility

Codexflare is an unofficial local appearance editor. It does not include Codex, ChatGPT, or Electron. Install a supported Codex build first; other builds allow previews and saved settings, but cannot be patched.

| Platform | Codex version / build | Original application |
| --- | --- | --- |
| Linux x86_64 | `26.1002.52244 / 13536` | `/usr/lib/chatgpt` |
| macOS arm64 | `26.1021.31345 / 21828` | `/Applications/Codex.app` or `/Applications/ChatGPT.app` |
| Windows x64 | `26.1021.31345 / 21828` | Microsoft Store / MSIX `26.1021.3705.0` |

**The v0.1.0 RPM and DEB are Linux packages. Use current `main` source for macOS and Windows.** Allow approximately 1.6 GB for a Linux / macOS copy, plus temporary space during updates. Windows creates only a shortcut to launch the installed standard app, without copying it. Windows build checks for `26.1002.52244 / 13536` (MSIX `26.1002.7124.0`) remain, but the older build has not been retested natively with the new launcher. Exact build checks determine compatibility.

<a id="linux"></a>

## Install a Linux release

Download a package and its matching checksum file from [Releases](https://github.com/epsilon10111/Codexflare/releases/latest), then run these commands in the download directory.

### Fedora

```bash
sha256sum --ignore-missing -c SHA256SUMS
sudo dnf install ./codexflare-0.1.0-1.noarch.rpm
codexflare
```

### Debian 12+ / Ubuntu 24.04+

```bash
sha256sum -c codexflare_0.1.0-1_all.deb.sha256
sudo apt install ./codexflare_0.1.0-1_all.deb
codexflare
```

Packages install Python 3.11+, GTK 3, PyGObject, WebKit2 4.1, and basic GStreamer media dependencies. You can also open **Codexflare** from the application menu. Installing a package does not modify Codex. `noarch` / `all` describe the editor's architecture-independent code, not wider patch compatibility. Initial packages are unsigned; SHA256 checks download integrity only.

<a id="source"></a>

## Run from source

Clone `main` on any supported platform. No npm build is required:

```bash
git clone --branch main https://github.com/epsilon10111/Codexflare.git
cd Codexflare
```

### Linux

Requires Python 3.11+. Install `python3-gobject gtk3 webkit2gtk4.1 gstreamer1-plugins-base gstreamer1-plugins-good coreutils` on Fedora, or `python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gstreamer1.0-plugins-base gstreamer1.0-plugins-good coreutils` on Debian / Ubuntu, using your system package manager.

```bash
python3 tools/editor.py
```

If the selected Python lacks GI, the launcher tries `/usr/bin/python3`. The editor opens a native GTK / WebKit window. Its internal server listens only on `127.0.0.1` and stops when the window closes.

<a id="macos"></a>

### macOS

Complete the [clone step](#source) above first. Requires Python 3.11+ and Apple Command Line Tools (`codesign` / `lipo`); an older system Python may not qualify. Install Cocoa / WKWebView bindings through PyObjC:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos.txt
.venv/bin/python tools/editor.py
```

With `uv` installed, use `uv venv --python python3 .venv` and `uv pip install --python .venv/bin/python -r requirements-macos.txt` instead to create the environment and install dependencies.

<a id="windows"></a>

### Windows

Complete the [clone step](#source) above first. Requires Python 3.12+ (3.13 x64 recommended) and [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/). Run in PowerShell without administrator privileges:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe tools/editor.py
```

pywebview uses WebView2 exclusively, without an IE fallback. Keep the source directory and virtual environment in place while the launcher is installed; paths may contain spaces and Chinese characters. Additional native validation commands are in the [Windows technical guide (Chinese)](../WINDOWS.md).

## Select, save, and apply

1. Choose a video under **开场动画** (Startup animation), select or upload a PNG under **常驻背景** (Background), then adjust the preview and startup window mode.
2. Click **保存设置** (Save settings). Saving updates configuration; **apply again so the next cold start uses the new settings**.
3. On Linux and macOS, quit the customized Codex normally, then click **刷新状态** (Refresh status) and **应用到 Codex** (Apply to Codex). On Linux, fully quit the original app before the first application too. Windows can apply settings while the original app is running.
4. Quit the current app normally, including any remaining tray process, then launch from the original menu entry on Linux, `~/Applications/Codexflare Codex.app` on macOS, or **Codex (Codexflare)** in the Windows Start menu. The original Windows Store or pinned icon still opens the standard app without enhancements.

The tool does not terminate active sessions. The Windows enhancement launcher refuses a duplicate launch while the original app is running. The animation runs on a cold start; activating an existing instance neither replays it nor changes its window mode. The workspace loads during playback. If initialization continues after the video, the last frame remains for up to 20 seconds. Esc, playback failure, or timeout releases the overlay. Slow network or backend startup can still cause a wait.

<a id="settings"></a>

## Settings and media

| Setting | Range and defaults |
| --- | --- |
| Video | Speed 0.5–2×; brightness 25–200%; contrast 50–200%; saturation 0–200% |
| Playback | Fill and crop / fit entirely; muted by default, with an audio toggle |
| Background | Opacity 0–50% (18%); horizontal position 50–100% (80%); width 40–140% (70%) |
| Startup window | Restore previous size, position, and maximized state by default; fullscreen or centered 1100×760 logical pixels, reduced on small displays |

Video imports are limited to **100 MiB / 30 seconds**. Importing requires `ffmpeg`, `ffprobe`, and the `libvpx-vp9` / `libopus` encoders on PATH. Recommended packages are `ffmpeg-free` on Fedora and `ffmpeg` on Debian / Ubuntu; available codecs depend on the distribution. Ubuntu provides FFmpeg in the `universe` repository. Imports become VP9 WebM at up to 1920×1080 and 30 fps, with Opus audio when present. Originals are unchanged; silent source files remain silent. Bundled video plays without transcoding.

Backgrounds accept **PNG only: up to 40 MiB, 8192 pixels per side, and 64 million pixels total**. Both `default1.png` and `default2.png` are bundled; the first is selected by default. When applying, FFmpeg can fit a display copy of large images within 3840×2160, preserving the original and transparency. Without FFmpeg, the original dimensions are used.

Background blending suits line art on black: dark themes use screen blending, while light themes invert and blend the image. Ordinary photographs may look different. Narrow windows fade the background further. Reduced transparency or high contrast hides it; reduced motion skips the animation. Disable the background and apply again to remove it. Tiling window managers may override centered or restored dimensions.

On Windows, restore mode leaves window management to the original app; the current isolated login page sets its own dimensions. Fullscreen starts after the workspace is ready, and reloading exits HTML fullscreen. Enhancements apply only to a cold start at the main window's root route, excluding deep links and auxiliary windows. See the [Windows guide (Chinese)](../WINDOWS.md) for the full limits.

<a id="uninstall"></a>

## Configuration, recovery, and removal

| Installation | Data directory |
| --- | --- |
| Linux RPM / DEB | `$XDG_DATA_HOME/codexflare/`; defaults to `~/.local/share/codexflare/` if unset or not absolute |
| Source on any platform | `.local/` inside the repository |

`animation.json` stores settings; `media/` and `backgrounds/` store imports. Runtime copies use `runtime/` on Linux and `Codexflare Runtime.app` on macOS. Windows stores applied settings, source and shortcut state in `install-windows.json`, without an application copy. Source and package installations have separate data; remove the old launcher before switching. Settings and media are processed locally, without uploads.

```bash
codexflare-manage status      # Check the source application and enhancement launcher
codexflare-manage install     # Enable saved settings; Linux/macOS build a copy
codexflare-manage launch      # Launch; fall back after the source application changes
codexflare-manage uninstall   # Restore / remove the entry; keep user data
```

For source installations, replace `codexflare-manage` with `python3 tools/manage.py`; use `.venv/bin/python` on macOS or `.\.venv\Scripts\python.exe` on Windows. Management refuses to overwrite a running runtime or externally modified launcher. Uninstalling does not stop processes or delete settings, media, backups, or runtime copies.

Linux changes only the user-level `chatgpt.desktop`, with a backup. It does not modify `/usr/lib/chatgpt`, system commands, or account data. Before removing a package, run `codexflare-manage uninstall`, followed by `sudo dnf remove codexflare` or `sudo apt remove codexflare`. If the package is removed first, the retained `launch.py` falls back to system Codex.

**macOS uses an independent profile and a local ad-hoc signature.** Data lives in `.local/profile` / `.local/codex-home`; a separate login may be required. The copy cannot inherit OpenAI's Developer ID, shared Keychain, notification, or native tool service identity. Services that verify signatures, such as computer control, may reject it. Uninstalling removes only the generated `~/Applications/Codexflare Codex.app` entry; `/Applications` and original account data stay unchanged. To select a different source app, set `CODEXFLARE_SOURCE_APP=/full/path/Codex.app` consistently for subsequent commands.

**Windows uses the installed standard app's package identity and original default data paths, without a second ChatGPT installation.** The original EXE, ASAR, vendor signature, WindowsApps and protocol registration stay unchanged. Appearance code uses private anonymous pipes, without a network debugging port. The default path creates no `runtime-windows/`, `profile-windows/` or `codex-home-windows/`. Keep the helper running with the app; do not terminate its Python process. Override the source with `$env:CODEXFLARE_SOURCE_APP = 'D:\Apps\Codex\app'` or an MSIX root directory belonging to a registered standard package. Uninstalling removes only the protected shortcut; current effects end when the app quits normally. Old copies and their separate data are not deleted automatically. After a source update, the launcher falls back to the unenhanced standard app until validation and application are repeated.

Package-context launch retains identity, but its token is not guaranteed to match ordinary activation. Real-account cold starts, microphone, camera, notifications and related functions still need separate validation; see the [Windows guide (Chinese)](../WINDOWS.md).

<a id="development"></a>

## Development and builds

`ui/` contains the editor, `src/` injected animation and styles, `tools/` platform management and validation, `tests/` regression tests, `assets/` media, and `packaging/` Linux package definitions. See [AGENTS.md](../AGENTS.md) for contribution rules and [DESIGN.md](../DESIGN.md) for interface principles; both are in Chinese.

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_*.cjs
/usr/bin/python3 tools/desktop_smoke.py                  # Linux editor
python3 tools/background_smoke.py --startup             # Linux / macOS background and handoff
python3 tools/native_smoke.py                           # Linux isolated application
.venv/bin/python tools/macos_editor_smoke.py             # macOS editor
.venv/bin/python tools/native_smoke.py --runtime ".local/Codexflare Runtime.app"
```

Run platform commands only on their respective systems; use `.venv/bin/python` for other macOS Python commands too. Windows native commands are in [WINDOWS.md (Chinese)](../WINDOWS.md). Tests use isolated data and write to ignored `work/` directories. Never commit application copies, profiles, or private logs.

RPM builds require `rpm-build` and `desktop-file-utils`; DEB builds require `dpkg-deb` and `desktop-file-utils`. Both package committed resources only, defaulting to `HEAD`:

```bash
python3 tools/build_rpm.py --ref v0.1.0
python3 tools/rpm_smoke.py dist/codexflare-0.1.0-1.noarch.rpm
python3 tools/build_deb.py --ref v0.1.0
python3 tools/deb_smoke.py dist/codexflare_0.1.0-1_all.deb
```

RPM output in `dist/` includes a binary package, SRPM, source archive, and `SHA256SUMS`; DEB output includes the package and a separate `.deb.sha256`. Runtime packages contain the default WebM and both PNG backgrounds. Original MP4, legacy demo, and development tools remain in source distributions. System Codex and user data are excluded.

RPM uses the chosen ref's spec and resources. DEB uses the checked-out build script / Debian templates with application resources from the chosen ref. **DEB tooling, macOS, and Windows support were added after the v0.1.0 tag.** To rebuild the original DEB, keep current tooling and pass `--ref v0.1.0`; the old tag does not contain the newer tools. Do not move the original tag or replace published assets.

## Validation and licensing

Existing records cover Fedora native windows, Ubuntu 24.04 container installation, and macOS / Windows native editors and isolated applications. These do not establish real-account cold-start, session recovery, signature-dependent service, or long-term reliability. Debian / Ubuntu physical desktops remain unverified. See [VALIDATION.md (Chinese)](../VALIDATION.md) for exact environments and limits. Report your OS, Codex version, and reproduction steps without account data or private conversations.

Code and documentation text use [MIT](../LICENSE). Bundled media and media shown in screenshots follow a [separate media license](../assets/LICENSE), permitting distribution with Codexflare without granting standalone sales or stock-library redistribution rights. The project is not affiliated with or endorsed by OpenAI. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for third-party information.
