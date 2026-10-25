# Windows 适配

分支：`feat/windows-support`。原生 WebView2 编辑器、视频与 PNG 导入、开场动画、工作区背景设置、三种启动窗口模式，以及可移除的独立开始菜单入口。沿用 Linux 的界面与素材，没有 npm 构建步骤。

## 兼容目标

- Windows x64 的正式版 Codex **26.1002.52244 / build 13536**，对应 Microsoft Store / MSIX 包 **26.1002.7124.0**。
- Python **3.12+**，推荐 **3.13 x64**；Microsoft Edge **WebView2 Runtime**。
- 不支持其他 Codex 构建、Beta、ARM64 或普通 Electron 包；构建、资源和补丁位置不匹配时拒绝安装。
- 仅分发源码；需用户已安装兼容 Codex。复制整个应用约需 2–3 GB，更新时还需一份临时空间。

## 安装与打开编辑器

在 PowerShell 中执行，无需管理员权限：

```powershell
git clone --branch feat/windows-support https://github.com/epsilon10111/Codexflare.git
cd Codexflare
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe tools/editor.py
```

若未安装 WebView2 Runtime，可从 [Microsoft 官方页面](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) 安装 Evergreen Runtime。编辑器固定使用 WebView2，不回退到旧版 IE。导入自定义视频还需将提供 VP9 / Opus 编码器的 `ffmpeg.exe`、`ffprobe.exe` 加入 PATH；内置视频和 PNG 导入不需要 FFmpeg。

1. 选择视频、背景和窗口模式，点击「保存设置」。
2. 首次安装可直接点击「应用到 Codex」。再次应用前，正常退出 **Codex (Codexflare)**，再刷新状态。
3. 从开始菜单 **Codex (Codexflare)** 启动定制副本；原来的 Codex 图标仍打开原版。

源码目录和 `.venv` 是启动器的依赖，启用期间请勿移动或删除。源码路径中可包含空格和中文。

## 数据、回退和边界

配置、素材及副本保存在仓库的 `.local/` 中：

| 路径 | 用途 |
| --- | --- |
| `animation.json`、`media/`、`backgrounds/` | 设置与导入素材 |
| `runtime-windows/` | 定制应用副本 |
| `install-windows.json` | 安装状态及快捷方式校验值 |
| `profile-windows/`、`codex-home-windows/` | 独立应用与后端数据，需要另行登录 |

```powershell
.\.venv\Scripts\python.exe tools/manage.py status
.\.venv\Scripts\python.exe tools/manage.py install
.\.venv\Scripts\python.exe tools/manage.py launch
.\.venv\Scripts\python.exe tools/manage.py uninstall
```

`uninstall` 仅删除本工具创建且未被他人修改的快捷方式，保留配置、素材与副本，不停止进程。官方应用升级后启动器回退到当前原版；需重新适配后才能再次应用。Windows 无法原子交换两个目录，更新中断时可能需要重新安装，官方入口仍可使用。

默认通过 `Get-AppxPackage OpenAI.Codex` 查找应用；自定义位置可指定到含 `resources/app.asar` 的应用目录，也可指定 MSIX 根目录：

```powershell
$env:CODEXFLARE_SOURCE_APP = 'D:\Apps\Codex\app'
.\.venv\Scripts\python.exe tools/editor.py
```

工具不改写 WindowsApps、原版程序、协议注册或原有登录数据。副本的 `ChatGPT.exe` 仅更新与新 ASAR 对应的完整性资源，保留 ASAR 校验、CSP、上下文隔离和禁用 Node 的渲染器设置。这会使**副本**的厂商签名失效；原版签名不变，启用签名强制策略的机器可能拒绝运行副本。

Windows 的减少动态效果会跳过开场动画；减少透明度或高对比度设置可能隐藏背景。这些无障碍偏好继续生效。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:PYTHON = (Resolve-Path '.venv\Scripts\python.exe').Path
node --test tests/test_boot.cjs tests/test_editor_ui.cjs tests/test_window_mode.cjs
.\.venv\Scripts\python.exe tools/windows_editor_smoke.py
.\.venv\Scripts\python.exe tools/windows_smoke.py --window-mode centered
.\.venv\Scripts\python.exe tools/windows_smoke.py --window-mode fullscreen --sound
.\.venv\Scripts\python.exe tools/windows_smoke.py --window-mode restore --seed-bounds 100 100 980 700
```

原生测试会短暂打开窗口。仅测试进程强制允许动画，便于验证播放；不改变系统设置。截图、样本和测试副本保留在忽略的 `work/` 中，可在测试结束后删除对应目录，不能上传应用副本或 profile。

已验证项目与未验证项见 [验收记录](VALIDATION.md)。真实账户登录、会话恢复和长期使用尚未验收；隔离登录页不代表这些流程通过。
