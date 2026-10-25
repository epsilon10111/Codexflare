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

请先安装 Codex。当前源码按应用结构检测兼容性，不再要求版本号完全相同；下表列出已有原生验收记录的构建。资源、窗口流程或背景结构无法识别时会拒绝应用，仍可预览和保存。

使用 `python tools/manage.py check` 可只读检查当前应用。已发布的 v0.1.0 安装包仍保留原有精确版本限制。

| 平台 | 原生验收基线 / build | 安装方式 |
| --- | --- | --- |
| Linux x86_64 | `26.1002.52244 / 13536` | [RPM](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare-0.1.0-1.noarch.rpm) · [DEB](https://github.com/epsilon10111/Codexflare/releases/download/v0.1.0/codexflare_0.1.0-1_all.deb) |
| macOS Apple Silicon | `26.1021.31345 / 21828` | [源码安装](docs/guide.zh-CN.md#macos) |
| Windows x64 | `26.1002.52244 / 13536` | [源码安装](docs/guide.zh-CN.md#windows) |

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

## 三步开始

1. **选择素材**：使用内置视频、背景，或导入自己的文件。
2. **调节并保存**：预览画面，选择启动窗口模式，点击「保存设置」。
3. **应用到 Codex**：退出 Codex，刷新状态并应用；Linux 使用原菜单入口，macOS / Windows 使用新建的 Codexflare 入口。

保存后需要重新应用，才能更新启动副本。开场视频不能保证覆盖所有网络与初始化等待。

**macOS / Windows 使用独立登录数据，可能需要重新登录。** macOS 副本采用 ad-hoc 签名，Windows 副本的厂商签名失效，部分原生服务或签名策略可能限制使用；详见[平台说明](docs/guide.zh-CN.md)。

## 文档与许可

[参数与素材](docs/guide.zh-CN.md#settings) · [配置与卸载](docs/guide.zh-CN.md#uninstall) · [开发与构建](docs/guide.zh-CN.md#development) · [验证范围](VALIDATION.md)

代码采用 [MIT](LICENSE)；默认视频、图片及截图中的素材按[独立素材许可](assets/LICENSE)随 Codexflare 分发。

非官方项目，与 OpenAI 无隶属或背书关系。发行包不包含 Codex、ChatGPT 或 Electron 程序文件。
