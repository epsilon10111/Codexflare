# Repository Guidelines

## 项目结构与模块职责

本仓库为 Linux、macOS 和 Windows Codex 桌面版提供可回退的开屏动画与背景。Linux 目标为 `26.1002.52244 / build 13536 / x86_64`；macOS 源码支持 `26.1021.31345 / build 21828 / arm64` 与 `26.1013.31256 / build 20586 / arm64`。已发布的 macOS `v0.1.1` DMG 仅适配 build 20586，已在 macOS 26.6.2 验证；合入 main 不扩大已发布附件的兼容范围。

Windows x64 Owl 原版增强的原生验收基线为 MSIX `26.1021.3705.0`（内部 26.1021.31345 / build 21828）；旧 build 13536 保留为历史参考，不作为版本白名单。`desktop_windows.py` 使用 pywebview/WebView2；`manage_windows.py` 默认只安装指向现有标准版的启动器，`windows_inject.py` 用私有匿名管道加入外观；不复制整套应用，不创建第二套真实账户目录。`patch_windows.py` 按结构发现资源，其归档补丁仍用于构建验证。Windows 使用 Python 3.12+；命令及边界见 `WINDOWS.md`。不要改写 WindowsApps、官方可执行文件、真实账户目录或关闭签名、CSP、单实例保护。

- `src/boot.js`、`src/boot.css`：动画层、播放退出逻辑和样式；启动窗口模式由 `tools/patch_app.py` 的主进程补丁处理。
- `src/background.css`：常驻背景融合与输入区样式；仅打包本地选中的图片，保留内容层可读性与交互。
- `ui/`：Codexflare 动画/背景编辑界面；`tools/desktop.py` 显示 GTK/WebKit 独立窗口，`tools/editor.py` 提供回环服务，`tools/animation.py` 保存配置，`tools/background.py` 验证 PNG 并管理忽略目录中的图片索引。
- `assets/default.mp4`：默认开屏原片；`assets/default.webm`：约十秒 VP9 / Opus 播放版本。`assets/default1.png` / `assets/default2.png` 为内置背景，默认选中第一张，`assets/boot.webm` 保留为旧光轨示例。
- macOS 使用 `tools/desktop_macos.py` 的 Cocoa/WKWebView 窗口、`manage_macos.py` 的独立 `.app` 副本、`original_macos.py` 的原入口安装与恢复，以及 `window_patch.py` 的结构匹配和 `patch_macos.py` 的原生验收参考数据；签名时更新 ASAR header 与 framework integrity digest，不关闭完整性检查。
- `tools/`：`generate_demo.py` 生成素材，`patch_app.py` 修改 ASAR 副本，`manage.py` 管理安装与回退，`native_smoke.py` 验证原生窗口。
- `tests/`：Python 单元测试、Node 动画测试及原生探针；`VALIDATION.md` 记录验收证据和边界。
- 源码版 `.local/` 存放运行副本与回退信息，`work/` 存放截图和测试输出；两者均被 Git 忽略。
- `packaging/` 定义 RPM、DEB、macOS DMG 启动器和安装说明；`tools/build_dmg.py` 生成自包含 DMG。`tools/paths.py` 让安装版使用用户数据目录（默认 `~/.local/share/codexflare`），源码版使用 `.local/`。`dist/` 为忽略的发布产物。

版本号仅记录来源和原生验收基线；当前源码按结构识别兼容性，不把下列已验收构建作为版本白名单。

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
| `python tools/manage.py check` | 只读检查来源的资源、窗口与背景结构 |
| `python tools/manage.py install` | 应用已保存设置：Windows 启用原版启动器，Linux/macOS 独立模式创建定制副本 |
| `python tools/manage.py status` | 检查应用来源及增强入口状态 |
| `python tools/manage.py launch` | 通过增强入口启动，来源变化时回退到原版 |
| `python tools/manage.py uninstall` | 停用增强入口，Linux 恢复原入口；保留配置、已有副本与备份 |
| `python tools/manage.py configure show` | JSON 读取配置；`set patch.json` 预览局部修改，增加 `--save` 保存；写入前关闭编辑器 |
