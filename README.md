<p align="center">
  <img src="ui/mark.svg" width="72" alt="Codexflare 标志">
</p>

<h1 align="center">Codexflare</h1>

<p align="center">自定义 Codex 的开场动画、工作区背景与启动窗口。<br>Linux · macOS · Windows</p>

<p align="center"><strong>简体中文</strong> · <a href="README.en.md">English</a></p>

<p align="center">
  <a href="https://github.com/epsilon10111/Codexflare/releases/tag/v0.1.0">Linux 下载</a> ·
  <a href="https://github.com/epsilon10111/Codexflare/releases/tag/v0.1.1">macOS DMG</a> ·
  <a href="docs/guide.zh-CN.md">使用指南</a> ·
  <a href="AGENTS.md">参与贡献</a>
</p>

## 功能一览

### 视频编辑

预览并调节速度、亮度、对比度、饱和度与声音。

<a href="docs/images/animation-editor.png"><img src="docs/images/animation-editor.png" width="100%" alt="视频编辑器，展示默认视频和播放参数"></a>

### 背景编辑

选择内置图片或上传 PNG，调整透明度、位置与大小。

<a href="docs/images/background-editor.png"><img src="docs/images/background-editor.png" width="100%" alt="背景编辑器，展示图片选择和融合参数"></a>

### 开场动画

播放时准备工作区，支持静音和 Esc 跳过。

<a href="docs/images/startup-preview.png"><img src="docs/images/startup-preview.png" width="100%" alt="隔离应用启动实拍，右下角显示 Press Esc to skip"></a>

### 工作区背景

图片向左渐隐，主对话与右侧分支共享背景。

<a href="docs/images/workspace-preview.png"><img src="docs/images/workspace-preview.png" width="100%" alt="使用真实应用 CSS 的模拟主对话与子代理工作区"></a>

<sub>点击图片查看原图。编辑器与开场均为实拍；工作区示例使用真实应用 CSS 与模拟会话，不含私人聊天。</sub>

支持**全屏、恢复上次窗口、居中小窗口**三种启动方式。内置一段视频与两张背景，素材只在本地处理，应用改动可回退。

## 下载与安装

请先安装 Codex。当前源码按应用结构检测兼容性，不再要求版本号完全相同；下表列出已有原生验收记录的构建。资源、窗口流程或背景结构无法识别时会拒绝应用，仍可预览和保存。

使用 `python tools/manage.py check` 可只读检查当前应用。已发布的 v0.1.0 安装包仍保留原有精确版本限制。

| 平台 | 原生验收基线 / build | 安装方式 |
| --- | --- | --- |
| Linux x86_64 | `26.1002.52244 / 13536` | [RPM](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare-0.1.0-1.noarch.rpm) · [DEB](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare_0.1.0-1_all.deb) |
| macOS Apple Silicon | `26.1021.31345 / 21828` | [main 源码安装](docs/guide.zh-CN.md#macos) |
| macOS Apple Silicon | `26.1013.31256 / 20586` | [v0.1.1 DMG](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.1/Codexflare-0.1.1-macOS-arm64-build20586.dmg) · [main 源码安装](docs/guide.zh-CN.md#macos) |
| Windows x64 | `26.1002.52244 / 13536` | [源码安装](docs/guide.zh-CN.md#windows) |

**已发布的 v0.1.1 DMG 仅支持 build 20586**，已在 macOS 26.6.2 验证；main 源码保留 build 21828 并增加 20586。合入 main 不改变该 DMG 的兼容范围，已发布标签和附件保持不变。macOS 原应用通常位于 `/Applications/ChatGPT.app` 或 `/Applications/Codex.app`。

Linux 要求原应用位于 `/usr/lib/chatgpt`；Windows 对应 MSIX `26.1002.7124.0`。RPM 面向 Fedora，DEB 面向 Debian 12+ / Ubuntu 24.04+。

<details>
<summary><strong>Linux 快速安装</strong></summary>

下载对应安装包后，选择一组命令：

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

也可从应用菜单打开 Codexflare。首版包未签名；校验文件、依赖和卸载步骤见[安装指南](docs/guide.zh-CN.md#linux)。

</details>

<details>
<summary><strong>macOS DMG 与原 ChatGPT 入口</strong></summary>

从 [v0.1.1 Release](https://github.com/epsilon10111/Codexflare/releases/tag/v0.1.1) 下载 DMG 和同名 `.sha256` 文件，在下载目录校验：

```bash
shasum -a 256 -c Codexflare-0.1.1-macOS-arm64-build20586.dmg.sha256
```

将 `Codexflare.app` 拖到 **Applications** 后运行，不要直接在只读 DMG 内运行。DMG 内嵌 Python / PyObjC，默认使用原入口模式，数据保存在 `~/.local/share/codexflare`（或绝对路径 `XDG_DATA_HOME` 下的 `codexflare/`）。默认动画及已缩图背景可直接使用；自定义视频导入需要另行安装 FFmpeg / ffprobe，DMG 不内嵌这两个工具。

在 **系统设置 → 隐私与安全性 → App 管理** 中，授权实际发起修改的 App：通过 ChatGPT 任务执行时授权 **ChatGPT**；独立运行编辑器时授权 **Codexflare**，以系统弹窗为准。无需为此开启完全磁盘访问或关闭系统安全保护。[Apple 权限说明](https://support.apple.com/zh-cn/guide/mac-help/mchl211c911f/26/mac/26)

保存设置并点击「应用到 ChatGPT」后，可在原应用仍运行时准备候选；用 **Cmd+Q 完全退出 ChatGPT** 后，后台安装器才执行替换。以后仍从原 ChatGPT 图标启动，唤起已运行的实例不重播动画。该模式使用与 Linux 相同的媒体预处理、背景预加载、并行初始化和片尾就绪衔接实现，并保留原名称、图标、bundle ID、协议及默认配置路径；不复制登录或聊天数据。

安装器保留经签名和完整内容摘要校验的官方备份，安装与恢复前复核应用未被外部更新。卸载前先点击「恢复原版 ChatGPT」，正常退出并确认恢复完成，再删除 Codexflare。若旧源码版已修改原入口，先用旧编辑器完成恢复，再使用 DMG 版；不要直接搬运旧状态或备份。仅用过独立副本的用户无需恢复原应用。

源码版默认仍为独立副本模式，使用独立数据目录；安装步骤见[源码指南](docs/guide.zh-CN.md#macos)。main 源码用户可在仓库目录显式启用原入口模式：

```bash
.venv/bin/python tools/original_macos.py prepare
.venv/bin/python tools/original_macos.py wait-activate --relaunch
```

第二条命令等待目标应用正常退出；后续保存、应用和恢复可由编辑器处理。源码设置及备份在仓库 `.local/`，启用期间不要移动或删除仓库。更多 DMG 安装、恢复和构建说明见[安装说明](packaging/macos/安装说明.txt)与 [v0.1.1 发布记录](docs/releases/v0.1.1.md)。

**DMG 与修改后的应用使用 ad-hoc 签名，未做 Apple 公证。** 原入口保留配置路径，但不能继承 OpenAI Developer ID、共享 Keychain、通知或原生工具服务身份，仍可能需要重新登录。真实账户、签名相关服务和长期运行未验收；原版更新后必须重新适配，不得以旧备份覆盖新版本。

</details>

## 三步开始

1. **选择素材**：使用内置视频、背景，或导入自己的文件。
2. **调节并保存**：预览画面，选择启动窗口模式，点击「保存设置」。
3. **应用设置**：独立副本模式先退出 Codex，刷新状态并应用；Linux 使用原菜单入口，macOS / Windows 独立副本使用新建的 Codexflare 入口。macOS 原入口模式先应用，再用 Cmd+Q 完全退出并等待安装，之后从原图标启动。

保存后需要重新应用，才能更新启动副本。开场视频不能保证覆盖所有网络与初始化等待。

**macOS / Windows 的独立副本使用独立登录数据，可能需要重新登录。** macOS 原入口模式保留默认配置路径。macOS 修改后的应用采用 ad-hoc 签名，Windows 副本的厂商签名失效，部分原生服务或签名策略可能限制使用；独立副本说明见[平台指南](docs/guide.zh-CN.md)，原入口说明见上文。

## 文档与许可

[参数与素材](docs/guide.zh-CN.md#settings) · [配置与卸载](docs/guide.zh-CN.md#uninstall) · [开发与构建](docs/guide.zh-CN.md#development) · [验证范围](VALIDATION.md)

代码采用 [MIT](LICENSE)；默认视频、图片及截图中的素材按[独立素材许可](assets/LICENSE)随 Codexflare 分发。

非官方项目，与 OpenAI 无隶属或背书关系。发行包不包含 Codex、ChatGPT 或 Electron 程序文件。
