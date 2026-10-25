# Repository Guidelines

## 项目结构与模块职责

本仓库为 Linux、macOS 和 Windows Codex 桌面版提供可回退的开屏动画与背景。Linux 目标为 `26.1002.52244 / build 13536 / x86_64`；macOS 源码支持 `26.1021.31345 / build 21828 / arm64` 与 `26.1013.31256 / build 20586 / arm64`。已发布的 macOS `v0.1.1` DMG 仅适配 build 20586，已在 macOS 26.6.2 验证；合入 main 不扩大已发布附件的兼容范围。

已合入的 `feat/windows-support` 分支增加同版本 Windows x64 Owl 适配（MSIX `26.1002.7124.0`）。`desktop_windows.py` 使用 pywebview/WebView2；`manage_windows.py` 管理复制、完整性哈希、独立开始菜单快捷方式和回退；`patch_windows.py` 验证 Windows 构建并复用经过唯一匹配检查的主窗口补丁。Windows 使用 Python 3.12+（推荐 3.13）；命令及边界见 `WINDOWS.md`。不要改写 WindowsApps、官方可执行文件或真实账户目录。

- `src/boot.js`、`src/boot.css`：动画层、播放退出逻辑和样式；启动窗口模式由 `tools/patch_app.py` 的主进程补丁处理。
- `src/background.css`：常驻背景融合与输入区样式；仅打包本地选中的图片，保留内容层可读性与交互。
- `ui/`：Codexflare 动画/背景编辑界面；`tools/desktop.py` 显示 GTK/WebKit 独立窗口，`tools/editor.py` 提供回环服务，`tools/animation.py` 保存配置，`tools/background.py` 验证 PNG 并管理忽略目录中的图片索引。
- `assets/default.mp4`：默认开屏原片；`assets/default.webm`：约十秒 VP9 / Opus 播放版本。`assets/default1.png` / `assets/default2.png` 为内置背景，默认选中第一张，`assets/boot.webm` 保留为旧光轨示例。
- macOS 使用 `tools/desktop_macos.py` 的 Cocoa/WKWebView 窗口、`manage_macos.py` 的独立 `.app` 副本、`original_macos.py` 的原入口安装与恢复，以及 `patch_macos.py` 的精确构建锚点；签名时更新 ASAR header 与 framework integrity digest，不关闭完整性检查。
- `tools/`：`generate_demo.py` 生成素材，`patch_app.py` 修改 ASAR 副本，`manage.py` 管理安装与回退，`native_smoke.py` 验证原生窗口。
- `tests/`：Python 单元测试、Node 动画测试及原生探针；`VALIDATION.md` 记录验收证据和边界。
- 源码版 `.local/` 存放运行副本与回退信息，`work/` 存放截图和测试输出；两者均被 Git 忽略。
- `packaging/` 定义 RPM、DEB、macOS DMG 启动器和安装说明；`tools/build_dmg.py` 生成自包含 DMG。`tools/paths.py` 让安装版使用用户数据目录（默认 `~/.local/share/codexflare`），源码版使用 `.local/`。`dist/` 为忽略的发布产物。

## 构建、测试与本地运行

在仓库根目录执行；源码运行需要 Python 3.11+ 和目标版本 Codex，无 npm 构建步骤。macOS DMG 已内嵌 Python / PyObjC，使用者无需另装这两个依赖。

| 命令 | 用途 |
| --- | --- |
| `python tools/editor.py` | 打开独立桌面编辑窗口，必要时自动使用系统 Python |
| `/usr/bin/python3 tools/desktop_smoke.py` | 使用隔离配置验证真实编辑窗口及视频播放 |
| `python tools/background_smoke.py` | 用真实应用 CSS 和模拟会话验证本地图片背景、像素分区及交互，不读取真实账户 |
| `python tools/background_smoke.py --startup` | 验证真实视频片尾衔接与背景首显，覆盖普通工作区和全宽右侧面板 |
| `python -m unittest discover -s tests -v` | 检查归档补丁、安装保护及回退 |
| `node --test tests/test_boot.cjs tests/test_editor_ui.cjs tests/test_window_mode.cjs` | 检查动画生命周期、失败退出与编辑器交互 |
| `/usr/bin/python3 tools/generate_demo.py` | 重新生成旧光轨示例，不覆盖 default；需要 Pillow、NumPy、FFmpeg/ffprobe、libvpx-vp9 和脚本指定的 DejaVuSans 字体 |
| `python tools/manage.py install` | 创建定制副本并更新用户菜单入口 |
| `python tools/manage.py status` | 检查副本及入口状态 |
| `python tools/manage.py launch` | 启动副本，来源变化时回退到原版 |
| `python tools/manage.py uninstall` | 恢复原菜单入口，保留副本与备份 |
| `python tools/native_smoke.py` | 基于已安装副本打开隔离普通窗口，验证动画与应用就绪过渡并保存截图 |
| `python tools/build_rpm.py` | 从已提交的 HEAD 构建 RPM、SRPM、源码归档与校验文件 |
| `python tools/rpm_smoke.py dist/codexflare-0.1.0-1.noarch.rpm` | 检查包内容、只读资源、用户配置及隔离 RPM 安装/卸载 |
| `python tools/build_deb.py --ref v0.1.0` | 用当前检出的 DEB 模板打包指定已提交版本的应用，输出 DEB 和独立校验文件 |
| `python tools/deb_smoke.py dist/codexflare_0.1.0-1_all.deb` | 检查 DEB 内容、依赖、只读资源与用户配置 |
| `.venv/bin/python tools/build_dmg.py --release` | 在 Apple Silicon 上从干净、已提交的 HEAD 构建 DMG；源码归档不包含未跟踪文件 |

DEB 工具在 v0.1.0 发布后加入，重建时保留包含工具的后续提交，通过 `--ref v0.1.0` 选择应用版本；不要移动原标签或覆盖已发布的 RPM、源码归档和校验文件。Debian / Ubuntu 的依赖可用性与实际桌面验收分开记录。

## 编码风格与命名

Python 使用四空格缩进、`snake_case` 函数和大写常量；JavaScript/CSS 使用两空格缩进，JavaScript 使用 `camelCase` 和分号。沿用所在文件的引号风格。仓库未配置格式化或 lint 工具；保持局部修改，复用现有辅助函数。修改参数范围时同步检查配置验证、UI 和动画运行时，保留基于时长和速度的超时保护。

## 测试要求

Python 使用标准库 `unittest`，文件命名为 `test_*.py`，方法命名为 `test_*`；JavaScript 使用内置 `node:test` 和严格断言。没有覆盖率百分比门槛；行为变更应补充回归测试，覆盖跳过、播放失败、减少动态效果或安装恢复等受影响路径。

窗口或视频变更还需在图形桌面运行原生测试，检查实际窗口边界和播放前后截图。单元测试与隔离登录页均不能证明真实账户冷启动正常；在 `VALIDATION.md` 明确记录未验证项。

Windows 原生验证：`python tools/windows_editor_smoke.py`；`python tools/windows_smoke.py --window-mode centered`，并覆盖 `fullscreen --sound` 和 `restore --seed-bounds 100 100 980 700`。测试仅在 `work/` 中创建副本与独立 profile，不注册菜单或协议；测试进程使用 no-reduced-motion 参数验证播放，实际启动尊重系统无障碍偏好。产物含应用副本，不得提交或分发。

编辑器改动还需在目标平台的实际 GTK/WebKit 或 Cocoa/WKWebView 窗口验证上传、预览、保存、关闭与错误提示。检查控件实际可见性，不能仅以 DOM 存在判定通过。HTTP 测试使用临时目录和安装函数替身，不应改动真实菜单入口或应用。遵循 `DESIGN.md` 的黑白六瓣几何风格、字号与减少动态效果规则，视频保留原色；保留平台窗口操作和关闭保护。

## 提交与 Pull Request

提交使用简短类型前缀，沿用 `feat: 添加 Codex 全屏开屏动画 demo` 的风格，例如 `fix: 修复动画超时退出`、`docs: 更新验证说明`。PR 应说明问题、改动、目标构建和实际测试结果；有关联 issue 时附链接，视觉变更附截图或短视频。

每个后续提交（包括合并提交）都必须包含共同作者尾注 `Co-authored-by: Frank Shi <frank20050415@sjtu.edu.cn>`；对应已核实的仓库协作者为 `Frank0415`。不得为补写尾注而改写已发布标签或其他历史提交。

`v0.1.1` 最初从 `release/macos-build20586` 独立发布，此后将功能合入 main 并保留其他平台及 build 21828 的适配。保留 `v0.1.0`、`v0.1.1` 标签和已发布资产，不覆盖旧附件；原 macOS 定向 Release 不设为 latest。正式 DMG 使用 `--release` 构建，源码归档与发布提交一致，发布说明包含精确目标构建、依赖、签名限制和验收边界。

## 安全与配置边界

Linux 与 macOS 独立副本模式仅修改各自数据目录内的应用副本及受保护的用户入口，不改写 `/usr/lib/chatgpt` 或 `/Applications` 中的原应用。macOS 原入口模式遵循下节的备份与退出保护。所有模式均不得改写用户登录数据或聊天目录，不提交官方应用二进制副本、测试 profile 或日志。保留版本检查、唯一匹配校验、CSP、上下文隔离和备份恢复逻辑；升级适配必须重新审查补丁。安装前正常退出定制副本，测试不得终止用户当前会话。

## macOS 验证与边界

使用 `.venv/bin/python` 与 `requirements-macos.txt`。执行 `tools/macos_editor_smoke.py` 验证真实编辑器，再执行 `tools/native_smoke.py --runtime ".local/Codexflare Runtime.app"` 验证隔离应用。Node 测试增加 `tests/test_window_mode_macos.cjs`。原生测试只修改隔离副本，不改写 `/Applications`，不继承供应商 Keychain/team entitlements，也不终止用户原版会话。签名相关原生功能的限制须保留在 README 与 VALIDATION 中。

macOS DMG 默认使用 `tools/original_macos.py` 原入口模式；源码默认使用独立副本，首次执行 `original_macos.py prepare` 后显式启用原入口模式。原入口模式可在原应用正常退出后原子替换原路径；运行期间只备份和构建候选，绝不结束会话。保持独立、完整且签名验证通过的官方备份，复核原包、候选和版本未改变，再执行安装或恢复。原入口模式保留 bundle ID、图标、协议和默认配置路径，但不伪造或继承供应商签名特权。系统需要 App 管理授权时，应授权实际发起修改的 App，以系统提示为准；不要求完全磁盘访问或关闭安全保护。测试仍使用隔离身份和测试 profile，不读取真实账号。
