<p align="center">
  <img src="ui/mark.svg" width="72" alt="Codexflare 标志">
</p>

<h1 align="center">Codexflare</h1>

<p align="center">自定义 Codex 的开场动画、工作区背景与启动窗口。<br>Linux · macOS · Windows</p>

<p align="center"><strong>简体中文</strong> · <a href="README.en.md">English</a></p>

<p align="center">
  <a href="https://github.com/epsilon10111/Codexflare/releases/latest">下载</a> ·
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

补丁仅适配下表中的 Codex 构建；其他版本可预览和保存，不能应用。请先安装对应的 Codex。

| 平台 | Codex 版本 / build | 安装方式 |
| --- | --- | --- |
| Linux x86_64 | `26.1002.52244 / 13536` | [RPM](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare-0.1.0-1.noarch.rpm) · [DEB](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare_0.1.0-1_all.deb) |
| macOS Apple Silicon | `26.1021.31345 / 21828` | [源码安装](docs/guide.zh-CN.md#macos) |
| Windows x64 | `26.1021.31345 / 21828` | [源码安装](docs/guide.zh-CN.md#windows) |

Linux 要求原应用位于 `/usr/lib/chatgpt`；Windows 当前目标为 MSIX `26.1021.3705.0`，保留旧 `26.1002.52244 / 13536` 的构建校验，但未重新原生验证旧构建。RPM 面向 Fedora，DEB 面向 Debian 12+ / Ubuntu 24.04+。

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

## 三步开始

1. **选择素材**：使用内置视频、背景，或导入自己的文件。
2. **调节并保存**：预览画面，选择启动窗口模式，点击「保存设置」。
3. **应用到 Codex**：Linux / macOS 先退出定制应用并刷新状态；Windows 可直接应用设置。正常退出当前应用后，Linux 使用原菜单入口，macOS 使用 Codexflare 入口，Windows 使用开始菜单 **Codex (Codexflare)**。

保存后需要重新应用，下次冷启动才会使用新设置。Windows 原 Store / 固定图标仍按普通方式启动。开场视频不能保证覆盖所有网络与初始化等待。

**Windows 直接增强现有标准版，不安装第二份应用。** 启动器保留原 MSIX 包身份、默认数据路径及官方文件签名；源码与 Python 环境需保留，启动器随应用运行。真实账户冷启动及麦克风、摄像头、通知仍需另验，见 [Windows 指南](WINDOWS.md)。macOS 仍使用独立登录数据与 ad-hoc 签名，可能需要重新登录，部分原生服务可能受限；详见[平台说明](docs/guide.zh-CN.md)。

## 文档与许可

[参数与素材](docs/guide.zh-CN.md#settings) · [配置与卸载](docs/guide.zh-CN.md#uninstall) · [开发与构建](docs/guide.zh-CN.md#development) · [验证范围](VALIDATION.md)

代码采用 [MIT](LICENSE)；默认视频、图片及截图中的素材按[独立素材许可](assets/LICENSE)随 Codexflare 分发。

非官方项目，与 OpenAI 无隶属或背书关系。发行包不包含 Codex、ChatGPT 或 Electron 程序文件。
