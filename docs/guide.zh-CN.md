# Codexflare 使用指南

**简体中文** · [English](guide.en.md) · [返回首页](../README.md)

## 兼容范围

Codexflare 是非官方的本地外观编辑器，不附带 Codex、ChatGPT 或 Electron。请先安装 Codex。当前源码按结构检测兼容性；下表是已有原生验收记录的构建，不是版本白名单。

| 平台 | 原生验收基线 / build | 原应用位置 |
| --- | --- | --- |
| Linux x86_64 | `26.1002.52244 / 13536` | `/usr/lib/chatgpt` |
| macOS arm64 | `26.1021.31345 / 21828` | `/Applications/Codex.app` 或 `/Applications/ChatGPT.app` |
| Windows x64 | `26.1002.52244 / 13536` | Microsoft Store / MSIX `26.1002.7124.0` |

**v0.1.0 的 RPM / DEB 仅适用于 Linux；macOS 与 Windows 请使用当前 `main` 源码。** 创建副本约需 Linux / macOS 1.6 GB、Windows 2–3 GB，更新还需临时空间。已发布的 v0.1.0 包仍使用精确版本校验。当前源码用 `python tools/manage.py check`（macOS 使用 `.venv/bin/python`）只读检查来源，不安装副本。


资源文件名中的 hash、主进程局部变量名和背景 CSS-module hash 可自动识别。窗口流程必须符合已识别的结构，背景需具有可识别的工作区、输入框和 FooterFade；无法唯一匹配时会停止。系统架构、Windows 应用身份、完整性和签名检查仍保留。结构检查通过不等于完成该构建的原生验收。

官方应用更新后，旧副本仍会回退原版。重新运行检查，通过后再次「应用到 Codex」即可重建副本；不会自动修改官方应用或继承账户目录。

<a id="linux"></a>

## 安装 Linux 发布包

从 [Release](https://github.com/epsilon10111/Codexflare/releases/latest) 下载安装包及对应校验文件，在下载目录执行。

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

安装包会安装 Python 3.11+、GTK 3、PyGObject、WebKit2 4.1 和 GStreamer 基础媒体依赖；也可从应用菜单打开 **Codexflare**。安装包本身不会修改 Codex。`noarch` / `all` 表示编辑器没有本机二进制，不扩大补丁兼容范围。首版包未签名，SHA256 仅用于下载完整性校验。

<a id="source"></a>

## 从源码运行

三个平台均从 `main` 克隆，无 npm 构建步骤：

```bash
git clone --branch main https://github.com/epsilon10111/Codexflare.git
cd Codexflare
```

### Linux

需要 Python 3.11+。Fedora 依赖为 `python3-gobject gtk3 webkit2gtk4.1 gstreamer1-plugins-base gstreamer1-plugins-good coreutils`；Debian / Ubuntu 对应 `python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gstreamer1.0-plugins-base gstreamer1.0-plugins-good coreutils`，使用系统包管理器安装。

```bash
python3 tools/editor.py
```

当前 Python 缺少 GI 时，启动器会尝试 `/usr/bin/python3`。编辑器使用独立 GTK / WebKit 窗口，内部服务仅监听 `127.0.0.1`，关闭窗口后结束。

<a id="macos"></a>

### macOS

先完成上方的[克隆仓库](#source)步骤。需要 Python 3.11+ 和 Apple Command Line Tools（`codesign` / `lipo`）；系统自带的旧 Python 可能不满足要求。Cocoa / WKWebView 依赖通过 PyObjC 安装：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-macos.txt
.venv/bin/python tools/editor.py
```

已安装 `uv` 时，可分别用 `uv venv --python python3 .venv` 和 `uv pip install --python .venv/bin/python -r requirements-macos.txt` 创建环境、安装依赖。

<a id="windows"></a>

### Windows

先完成上方的[克隆仓库](#source)步骤。需要 Python 3.12+（推荐 3.13 x64）和 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/)。在 PowerShell 中执行，无需管理员权限：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe tools/editor.py
```

pywebview 固定使用 WebView2，不回退到 IE。源码目录与虚拟环境是启动器的依赖，启用期间不要移动或删除；路径允许空格和中文。更多原生验证命令见 [Windows 技术指南（中文）](../WINDOWS.md)。

## 选择、保存和应用

1. 在「开场动画」选择视频，在「常驻背景」选择或上传 PNG，调节预览参数与启动窗口模式。
2. 点击「保存设置」。保存只更新配置，**需再次应用才会更新已安装的副本**。
3. 正常退出定制 Codex，在仍然打开的 Codexflare 中点击「刷新状态」，再点击「应用到 Codex」。Linux 首次应用前也请完全退出原版；仅关闭窗口可能仍留在托盘。
4. Linux 从原菜单入口启动；macOS 使用 `~/Applications/Codexflare Codex.app`；Windows 使用开始菜单 **Codex (Codexflare)**。

工具不会结束正在运行的会话。开场动画只在冷启动时播放，唤起已有实例不重播，也不重新调整窗口。视频期间并行准备工作区；若片尾仍在初始化，最多保留尾帧 20 秒，Esc、播放失败或超时会释放遮罩。网络或后端较慢时仍可能出现等待。

<a id="settings"></a>

## 参数与素材

| 设置 | 范围与默认值 |
| --- | --- |
| 视频 | 速度 0.5–2×；亮度 25–200%；对比度 50–200%；饱和度 0–200% |
| 播放 | 铺满裁切 / 完整显示；默认静音，可开启声音 |
| 背景 | 不透明度 0–50%（18%）；水平位置 50–100%（80%）；宽度 40–140%（70%） |
| 启动窗口 | 默认恢复上次大小、位置及最大化状态；也可全屏或居中 1100×760 逻辑像素，小屏自动缩小 |

视频上限 **100 MiB / 30 秒**。导入需要 PATH 中的 `ffmpeg`、`ffprobe`，以及 `libvpx-vp9` / `libopus` 编码器；Fedora 推荐包为 `ffmpeg-free`，Debian / Ubuntu 为 `ffmpeg`，实际编码支持取决于发行版。Ubuntu 的 FFmpeg 来自 `universe` 软件源。导入转换为不超过 1920×1080、30 fps 的 VP9 WebM，音轨转为 Opus；原片不变，无音轨的视频不会产生声音。内置视频无需转码即可播放。

背景只接受 **PNG，最大 40 MiB、单边 8192 像素、总计 6400 万像素**。内置 `default1.png` / `default2.png`，默认第一张。应用时，大图可经 FFmpeg 缩至 3840×2160 范围，仅处理副本，保留原图与透明度；缺少 FFmpeg 时使用原尺寸。

背景适合黑底线条素材：深色主题滤色融合，浅色主题反相混合，普通照片的观感可能改变。窄窗进一步淡化；减少透明度或高对比度偏好会隐藏背景，减少动态效果会跳过动画。关闭背景选项并重新应用即可撤回背景。平铺窗口管理器可能覆盖居中 / 恢复尺寸。

<a id="uninstall"></a>

## 配置、回退与卸载

| 安装方式 | 数据目录 |
| --- | --- |
| Linux RPM / DEB | `$XDG_DATA_HOME/codexflare/`；未设置或非绝对路径时为 `~/.local/share/codexflare/` |
| 所有源码方式 | 仓库内 `.local/` |

`animation.json` 保存配置，`media/` 与 `backgrounds/` 保存导入素材。Linux 副本为 `runtime/`，macOS 为 `Codexflare Runtime.app`，Windows 为 `runtime-windows/`。源码与安装包数据独立，切换方式前先移除旧入口。素材与设置在本地处理，不上传。

```bash
codexflare-manage status      # 检查副本与入口
codexflare-manage install     # 用已保存设置生成副本和入口
codexflare-manage launch      # 启动；来源更新时回退原版
codexflare-manage uninstall   # 恢复 / 移除入口，保留用户数据
```

源码方式将 `codexflare-manage` 替换为 `python3 tools/manage.py`；macOS 使用 `.venv/bin/python`，Windows 使用 `.\.venv\Scripts\python.exe`。管理工具拒绝覆盖运行中的副本或被外部修改的入口；卸载不结束进程，不删除配置、素材、备份或副本。

Linux 仅修改用户级 `chatgpt.desktop`，保留备份，不改写 `/usr/lib/chatgpt`、系统命令或账户数据。移除 RPM / DEB 前先执行 `codexflare-manage uninstall`，再执行 `sudo dnf remove codexflare` 或 `sudo apt remove codexflare`。若先删包，保留的 `launch.py` 会回退到系统 Codex。

**macOS 使用独立 profile 和本地 ad-hoc 签名。** 数据位于 `.local/profile` / `.local/codex-home`，首次可能需要重新登录。副本不能继承 OpenAI 的 Developer ID、共享 Keychain、通知或原生工具服务身份；检查签名的电脑控制服务可能拒绝连接。卸载只移除本工具创建的 `~/Applications/Codexflare Codex.app`，不修改 `/Applications` 或原版数据。自定义原应用位置可设置 `CODEXFLARE_SOURCE_APP=/完整路径/Codex.app`，后续命令保持同一路径。

**Windows 也使用独立账户目录。** 数据位于 `.local/profile-windows` / `.local/codex-home-windows`，需另行登录；原版入口、WindowsApps 和协议注册不变。更新副本 `ChatGPT.exe` 的 ASAR 完整性资源会使副本的厂商签名失效，签名强制策略可能拒绝运行；原版签名不变。自定义来源用 `$env:CODEXFLARE_SOURCE_APP = 'D:\Apps\Codex\app'`，也可指向 MSIX 根目录。卸载仅删除受保护的独立快捷方式；更新中断可能需要重装副本，官方入口仍可使用。

<a id="development"></a>

## 开发与构建

`ui/` 为编辑器界面，`src/` 为注入样式和动画，`tools/` 为平台管理及验证工具，`tests/` 为回归测试，`assets/` 为素材，`packaging/` 为 Linux 打包文件。贡献规范见 [AGENTS.md](../AGENTS.md)，界面原则见 [DESIGN.md](../DESIGN.md)。

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_*.cjs
/usr/bin/python3 tools/desktop_smoke.py                  # Linux 编辑器
python3 tools/background_smoke.py --startup             # Linux / macOS 背景与片尾
python3 tools/native_smoke.py                           # Linux 隔离应用
.venv/bin/python tools/macos_editor_smoke.py             # macOS 编辑器
.venv/bin/python tools/native_smoke.py --runtime ".local/Codexflare Runtime.app"
```

平台命令只在对应系统运行；macOS 的其余 Python 命令也使用 `.venv/bin/python`。Windows 原生命令见 [WINDOWS.md](../WINDOWS.md)。测试使用隔离数据，结果保存在忽略的 `work/`；应用副本、profile 和私人日志不得提交。

RPM 需要 `rpm-build` 与 `desktop-file-utils`；DEB 需要 `dpkg-deb` 与 `desktop-file-utils`。均仅打包已提交资源，默认 `HEAD`：

```bash
python3 tools/build_rpm.py --ref v0.1.0
python3 tools/rpm_smoke.py dist/codexflare-0.1.0-1.noarch.rpm
python3 tools/build_deb.py --ref v0.1.0
python3 tools/deb_smoke.py dist/codexflare_0.1.0-1_all.deb
```

`dist/` 中 RPM 产物含二进制包、SRPM、源码归档与 `SHA256SUMS`；DEB 产物含安装包与独立 `.deb.sha256`。运行包含默认 WebM 和两张 PNG；原 MP4、旧示例及开发工具留在源码中，不打包系统 Codex 或用户数据。

RPM 使用指定 ref 的 spec 和资源；DEB 使用当前检出的脚本 / Debian 模板及指定 ref 的应用资源。**DEB、macOS 与 Windows 支持在 v0.1.0 标签之后加入**，重建原 DEB 时保留当前工具并传入 `--ref v0.1.0`，不要检出旧标签后寻找新工具。不要移动原标签或覆盖已发布附件。

## 验证范围与许可

现有记录包含 Fedora 原生窗口、Ubuntu 24.04 容器安装、macOS 和 Windows 原生编辑器 / 隔离应用测试。它们不等于真实账户冷启动、会话恢复、签名相关服务及长期运行验收；Debian / Ubuntu 实机桌面也未验证。精确环境与未通过项见 [VALIDATION.md](../VALIDATION.md)。反馈问题请附系统、Codex 版本与复现步骤，勿附登录数据或私人聊天。

代码与文档文字采用 [MIT](../LICENSE)；内置媒体及截图中的媒体内容遵循[独立素材许可](../assets/LICENSE)，允许随 Codexflare 分发，不授予独立销售素材或发布到外部素材库的许可。项目与 OpenAI 无隶属或背书关系，第三方说明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
