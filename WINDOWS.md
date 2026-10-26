# Windows：增强现有标准版

分支：`feat/windows-support`。Windows 默认安装只创建一个启动现有标准版的快捷方式，应用的 EXE、ASAR、厂商签名保持不变。不复制 ChatGPT，不创建另一套登录或后端数据目录。编辑器仍使用 pywebview / WebView2。

## 兼容与依赖

- Windows x64 正式版的当前原生验收基线：Microsoft Store 包 **OpenAI.Codex 26.1021.3705.0**，显示名 ChatGPT，内部版本 **26.1021.31345 / build 21828**。当前源码按结构检测兼容性，不以版本号为白名单。
- 旧 **26.1002.52244 / build 13536**（Store 26.1002.7124.0）保留为历史参考；本轮原生验证以当前构建为准，旧构建新启动方式未重新做真机验收。
- Python **3.12+ x64**。编辑器依赖 `requirements-windows.txt` 和系统 WebView2；启动管道使用 Python 标准库，不安装新浏览器或 Electron。
- 自定义视频导入需要 PATH 中的 FFmpeg/ffprobe（VP9 / Opus）；默认视频与 PNG 不依赖 FFmpeg。
- 使用 `.venv\Scripts\python.exe tools/manage.py check` 只读检查资源、窗口与背景结构，无法唯一识别时拒绝应用。结构检查通过不等于完成原生验收；仍不支持 Beta、ARM64 或普通 Electron 包。

## 使用

```powershell
git clone --branch feat/windows-support https://github.com/epsilon10111/Codexflare.git
cd Codexflare
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe tools/editor.py
```

1. 选择开屏视频、背景及参数，保存并点击「应用到 Codex」。应用设置会验证素材、保存本次启用的设置并创建启动快捷方式。
2. 保存当前工作，正常退出已有 ChatGPT（关闭窗口后如仍在托盘，也需退出）。工具不会强制停止它。
3. 从开始菜单 **Codex (Codexflare)** 启动。这个入口调用已安装标准版的 `ChatGPT.exe`，使用其原有账户和数据。启动器需在应用运行期间保留；不要结束其 Python 进程。

原来的 Store/固定图标仍可用，直接从原图标启动不会加载 Codexflare 效果。这里新增的是快捷方式，不是第二份 ChatGPT 安装。源码和虚拟环境是启动器的依赖，启用期间不要移动或删除。

```powershell
.\.venv\Scripts\python.exe tools/manage.py check
.\.venv\Scripts\python.exe tools/manage.py status
.\.venv\Scripts\python.exe tools/manage.py install
.\.venv\Scripts\python.exe tools/manage.py launch
.\.venv\Scripts\python.exe tools/manage.py uninstall
```

`uninstall` 只删除本工具创建且未被修改的快捷方式，保留素材与配置，不停止当前应用。已经打开的窗口会在正常退出后结束本次效果。旧版副本安装状态需重新应用才能转入原版模式；旧副本和旧独立 profile 不自动删除，以免丢失其中的数据。

## 数据与原理

| 路径 | 用途 |
| --- | --- |
| `.local/animation.json`、`media/`、`backgrounds/` | 编辑设置与用户导入的素材 |
| `.local/install-windows.json` | 启用时设置、来源指纹与快捷方式校验值 |

默认路径不再创建 `runtime-windows/`、`profile-windows/` 或 `codex-home-windows/`。启动器通过 Windows 自带的 `Invoke-CommandInDesktopPackage -PreventBreakaway` 进入已注册标准版的包上下文，再用私有匿名管道启动原 EXE；两阶段检查包身份，失败就停止，不降级成无包身份的进程。不会安装、注册或复制应用。

沿用系统基础环境，仅传递已有的 `CODEX_HOME`、`CODEX_ELECTRON_USER_DATA_PATH`、`CODEXFLARE_SOURCE_APP` 和 `XDG_DATA_HOME` 路径，不传递整份环境或密钥。默认不设置独立账户目录或 `--user-data-dir`；测试才使用 `work/` 内的临时 profile。

外观代码通过父子进程私有匿名管道注入主窗口。没有监听 HTTP/WebSocket 调试端口，不向远程服务发送素材，不改变 CSP、上下文隔离、Node 开关或 ASAR 校验。原版单实例锁保持启用，已有原版进程运行时要求用户正常退出，避免误把注入连接到另一份会话。

背景在内存中使用一个本地 Blob 短地址，CSS 与预加载共用它，避免大图 data URL 被原版模块加载器反复扫描。地址随页面释放，不写入原版资源目录。

恢复模式由原版管理窗口；当前构建的隔离登录页会重新设置尺寸，不能据此保证指定历史尺寸恢复。居中模式按当前屏幕 DPI 换算 1100×760 并限制到工作区。全屏在工作区就绪后进入，初始化最初阶段仍可能是普通窗口；刷新会退出 HTML 全屏。

仅增强普通主窗口的根路由冷启动；深链接、宠物和独立辅助窗口不注入。刷新和重新打开主窗口保留背景，不重复播放开屏。为兼容原版初始化，注入在页面恢复运行后执行，不能保证完全遮住最早的原版启动帧。

默认通过 `Get-AppxPackage OpenAI.Codex` 查找安装位置。自定义位置必须属于已注册的标准版 MSIX 包，可指定到 `app` 目录或 MSIX 根目录，并保存在安装状态中：

```powershell
$env:CODEXFLARE_SOURCE_APP = 'D:\Apps\Codex\app'
.\.venv\Scripts\python.exe tools/editor.py
```

来源发生更新时，启动器会回退启动未增强的标准版；重新运行结构检查，通过后才能再次应用，检查失败则需适配对应结构。没有覆盖 WindowsApps 或关闭签名检查的修复步骤。

## 验证边界

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:PYTHON = (Resolve-Path '.venv\Scripts\python.exe').Path
node --test tests/test_boot.cjs tests/test_editor_ui.cjs tests/test_window_mode.cjs tests/test_window_mode_macos.cjs
.\.venv\Scripts\python.exe tools/windows_editor_smoke.py
```

原版测试必须在同一包身份内运行（每次等待 `work/windows-original-smoke-*/result.json` 出现，再开始下一项）：

```powershell
$package = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
$pythonw = (Resolve-Path '.venv\Scripts\pythonw.exe').Path
$smoke = (Resolve-Path 'tools\windows_smoke.py').Path
Invoke-CommandInDesktopPackage -PackageFamilyName $package.PackageFamilyName -AppId App -Command $pythonw -Args ('"' + $smoke + '" --window-mode centered') -PreventBreakaway
```

另外逐项替换参数为 `--window-mode fullscreen --sound`、`--window-mode restore`、`--exit-path skipped`、`--exit-path media-error`、`--exit-path reduced-motion`。`--seed-bounds` 保留为严格诊断选项；当前未登录页不保证保留该种子尺寸，失败不能算作恢复通过。

原生测试使用当前已签名 EXE 和隔离测试 profile；不注册额外应用，不读取真实账户。开屏与背景尊重系统减少动态效果、减少透明度与高对比度设置。真实账户冷启动、登录、长期会话及未来 MSIX 更新需分别验收；隔离页面与模拟工作区通过不代表这些项目通过。

微软说明包上下文命令提供身份和虚拟资源访问，但其 token 不保证与普通激活完全相同；麦克风、摄像头、通知等受隐私设置影响的功能还需单独验收。[官方说明](https://learn.microsoft.com/en-us/powershell/module/appx/invoke-commandindesktoppackage?view=windowsserver2025-ps)

具体已运行用例、窗口模式限制与结果见 [验收记录](VALIDATION.md)。
