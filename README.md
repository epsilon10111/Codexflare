# Codexflare

**为 Linux Codex 桌面版定制启动动画。**

Codexflare 是一个轻量级本地动画编辑器。在独立桌面窗口中选择内置或自定义视频，实时调整播放速度与画面，再应用到可回退的 Codex 副本。

![Codexflare 独立桌面编辑器](docs/images/editor.png)

## 功能

- **独立桌面窗口**：使用系统 GTK / WebKit，黑白六瓣几何界面、自绘标题栏和 CSS 交互动效，无需浏览器标签页或额外 Electron 运行时。
- **自定义视频**：内置四秒「CODEX 光轨」，支持导入 MP4、MOV、WebM 等视频；素材仅在本机处理。
- **实时预览**：调节播放速度、亮度、对比度、饱和度，选择铺满裁切或完整显示。
- **可回退安装**：生成本地应用副本并切换用户菜单入口，可随时恢复原入口。
- **播放保护**：动画静音，支持 Esc / 按钮跳过、播放失败退出和减少动态效果偏好。

## 兼容范围与依赖

目前仅适配 **Codex 26.1002.52244 / build 13536 / Linux x86_64**，原应用路径为 `/usr/lib/chatgpt`。已在 Fedora KDE / Wayland（通过 XWayland）验证；其他 Codex 构建、Linux 桌面及 Windows / macOS 未验证。

这是非官方工具，不分发 OpenAI 的程序文件。未适配的 Codex 版本仍可使用编辑器预览和保存，不能应用补丁。

| 用途 | 依赖 |
| --- | --- |
| 打开编辑器 | Python 3.11+、GTK 3、PyGObject、WebKit2 4.1，以及系统 WebKit 的 VP9 / WebM 解码支持 |
| 导入自定义视频 | FFmpeg、ffprobe、`libvpx-vp9` 编码器 |
| 应用动画 | 已安装的目标版本 Codex，约 1.6 GB 本地副本空间 |
| 开发测试 | Python 标准库 `unittest`、Node.js 内置 `node:test` |

使用发行版提供的 GTK / WebKit 及媒体组件，无 npm 构建步骤。若当前 Python 环境缺少 GI，启动器会尝试使用 `/usr/bin/python3`。

## 快速开始

```bash
git clone https://github.com/epsilon10111/Codexflare.git
cd Codexflare
python3 tools/editor.py
```

启动后直接打开本地窗口。内部服务仅监听 `127.0.0.1`，关闭窗口后结束；无需手动打开服务地址。

1. 选择内置视频，或点击「上传视频」导入素材。
2. 调节参数，在预览区检查效果。
3. 点击「保存设置」保留草稿配置；点击「应用到 Codex」保存并重建定制副本。
4. 完全退出 Codex 后，从原来的 ChatGPT / Codex 菜单入口重新打开。

**保存设置不会改变已安装的启动动画，需要再次点击「应用到 Codex」。** 定制 Codex 正在运行时会拒绝重新应用，可先保存设置。工具不会关闭你的会话；仅关闭 Codex 窗口可能会留在托盘，请正常退出应用后再操作。

动画全屏播放，结束后应用保持全屏，可通过应用或 KDE 窗口菜单退出全屏。唤起已有实例时不重复播放。

## 视频与参数

| 参数 | 范围 |
| --- | --- |
| 播放速度 | 0.5–2× |
| 亮度 | 25–200% |
| 对比度 | 50–200% |
| 饱和度 | 0–200% |
| 画面适配 | 铺满裁切 / 完整显示 |

导入文件最大 **100 MiB**，原片最长 **30 秒**。支持的容器和编码取决于本机 FFmpeg；导入后转换为无声 VP9 WebM，30 fps，宽不超过 1920、高不超过 1080，保持比例且不放大。原始文件保持不变。

设置保存在 `.local/animation.json`，导入素材保存在 `.local/media/`。重置参数不会替换所选视频，恢复原版入口也不会删除素材和设置。视频预览保留原片颜色，黑白风格只作用于编辑界面。

## 安装、启动与回退

也可以在仓库根目录使用命令行：

```bash
python3 tools/manage.py install    # 使用已保存的配置创建并启用定制副本
python3 tools/manage.py status     # 查看副本和入口状态
python3 tools/manage.py launch     # 启动定制副本，异常时回退原版
python3 tools/manage.py uninstall  # 恢复原菜单入口
```

安装器将系统应用复制到 `.local/runtime/`，只修改副本中的 `app.asar`，并更新用户级 `~/.local/share/applications/chatgpt.desktop`。原入口存在时会备份，检测到入口被其他操作修改时拒绝覆盖。

- 不改写系统 `/usr/lib/chatgpt`、`/usr/bin/chatgpt` 或用户登录、聊天数据；直接运行 `/usr/bin/chatgpt` 仍打开原版。
- 卸载恢复入口，保留副本、备份、设置和素材，不停止运行中的进程。
- 系统 Codex 更新后，启动器检测来源变化并打开原版；新版本需要重新审查适配。
- 菜单入口引用仓库的绝对路径。启用期间不要移动或删除仓库；迁移前先恢复原版入口。

## 开发与验证

```text
ui/                  编辑界面、样式与六瓣标志
src/                 注入 Codex 的启动动画层
assets/boot.webm      内置四秒无声视频
tools/               桌面窗口、视频处理、安装与验证工具
tests/               Python / Node 回归测试
.local/              本地配置、素材与运行副本（不提交）
work/                测试截图与临时产物（不提交）
```

```bash
python3 -m unittest discover -s tests -v
node --test tests/test_boot.cjs tests/test_editor_ui.cjs
/usr/bin/python3 tools/desktop_smoke.py
```

桌面自检在隔离配置下验证真实窗口、播放、导入、保存及关闭，不改变真实 Codex 安装。Python 若缺少 GI，会跳过桌面测试；请使用具备 GTK / WebKit 的系统 Python 补测。

已安装副本可用 `python3 tools/native_smoke.py` 验证全屏动画，或用 `--runtime /绝对路径/runtime` 指定预构建副本。该测试会短暂打开隔离的全屏窗口，不退出当前真实会话。

重新生成内置视频可运行 `/usr/bin/python3 tools/generate_demo.py`，额外需要 Pillow、NumPy、FFmpeg / ffprobe、libvpx-vp9 和脚本指定的 DejaVuSans 字体。

贡献规范见 [AGENTS.md](AGENTS.md)，界面设计见 [DESIGN.md](DESIGN.md)，测试证据及未验证项见 [VALIDATION.md](VALIDATION.md)。真实账户冷启动、其他版本和长期运行仍需另行验证。

## 参考

开屏思路参考 [powerofjinbo/claude-](https://github.com/powerofjinbo/claude-/tree/ef3a656e15594f6b8e73e9550ff385bb52813ce8)；本项目自行生成素材，通过 Codex 本地副本的启动页播放，没有复制其素材或实现代码。窗口和归档处理参考 [Electron BrowserWindow](https://www.electronjs.org/docs/latest/api/browser-window) 与 [ASAR Integrity](https://www.electronjs.org/docs/latest/tutorial/asar-integrity)。
