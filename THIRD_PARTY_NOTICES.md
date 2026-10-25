# 第三方与素材说明

## 名称与应用

Codexflare 是独立的非官方项目，与 OpenAI 无隶属、赞助或背书关系。OpenAI、Codex、ChatGPT 等名称仅用于说明兼容目标，不因本项目的代码或素材许可而授予其商标使用权。

本项目的源码、RPM 与 macOS DMG 不包含 OpenAI 的应用程序、Electron 运行时或用户账户数据。使用时从用户已安装的兼容应用创建本地副本；这些第三方程序仍受其各自许可与使用条款约束，不能依据 Codexflare 的 MIT 许可再分发。

## 运行依赖

Python、GTK、PyGObject、WebKitGTK、GStreamer 和可选的 FFmpeg 由操作系统或用户提供，未内嵌于 Codexflare 的 RPM。它们及所使用的编解码器保留各自许可；请参阅对应发行版软件包的许可说明。开发时的 Node.js、Pillow、NumPy 亦由环境提供。

macOS 源码运行所需的 Python 与 PyObjC 由用户安装。v0.1.1 DMG 则内嵌独立的 Python 运行环境、PyObjC 的 Cocoa / WebKit 绑定以及 PyInstaller bootloader / runtime；这些依赖保留各自许可，不因随 Codexflare 分发而改为 MIT。依赖版本记录在 DMG 内的 `构建信息.json`。

- Python 许可文本位于 `Codexflare.app/Contents/Resources/licenses/Python.txt`。
- PyObjC 的 MIT 许可与 PyInstaller 的许可、bootloader 分发例外一起保存在同一 `licenses/` 目录；目录内 `说明.txt` 列出来源和依赖版本。
- Codexflare 自身代码许可为该目录内的 `Codexflare-MIT.txt`；媒体许可保留在 `Codexflare.app/Contents/Resources/assets/LICENSE`。
- DMG 不内嵌 FFmpeg 或 ffprobe。默认媒体可直接使用；自定义视频导入与新图片的进一步缩图需要用户另行安装媒体工具。

## 内置媒体与标志

- `assets/default.mp4` 及其 `default.webm` 播放版、`default1.png`、`default2.png` 由项目维护者提供。
- `assets/boot.webm` 为 `tools/generate_demo.py` 生成的旧版光轨示例。
- 上述媒体及文档截图中的媒体内容采用 [单独素材许可](assets/LICENSE)，不能仅依据根目录 MIT 许可使用。
- `ui/mark.svg` 是项目绘制的六瓣几何标志，macOS 的 `ui/mark.icns` 由它生成，两者适用 MIT；该许可不授予第三方商标权。
- DMG 中的 `default1.png` 与 `default2.png` 使用 Lanczos 等比例缩至 3840×2160 范围，修改说明随包保存在 `licenses/说明.txt`；素材许可仍适用。

素材许可仅授予许可人拥有的权利，不声明已取得任何第三方商标或生成平台的额外授权。用户自行导入的素材不会上传或随项目分发，其权利由导入者负责。

## 参考来源

开屏思路参考 [powerofjinbo/claude-](https://github.com/powerofjinbo/claude-/tree/ef3a656e15594f6b8e73e9550ff385bb52813ce8)，未复制其素材或实现代码。窗口与归档处理参考 Electron 的 [BrowserWindow](https://www.electronjs.org/docs/latest/api/browser-window) 和 [ASAR Integrity](https://www.electronjs.org/docs/latest/tutorial/asar-integrity) 文档。

## macOS 运行依赖与格式参考

- Python 运行环境与许可来源：https://www.python.org/
- PyObjC（MIT）提供 Cocoa / WebKit 绑定；源码用户自行安装，DMG 内嵌相应依赖并附许可。https://github.com/ronaldoussoren/pyobjc
- PyInstaller 用于生成 DMG 内的独立应用；随包附带其许可及 bootloader 分发例外。https://pyinstaller.org/
- 无签名回调按 Clang/Apple Block ABI 的公开布局调用固定类型回调，不依赖 PyObjC 私有符号。https://clang.llvm.org/docs/Block-ABI-Apple.html
- ASAR 头与 framework 摘要遵循 Electron 的完整性格式；本项目更新摘要，不关闭校验。https://www.electronjs.org/docs/latest/tutorial/asar-integrity 和 https://github.com/electron/electron/blob/main/shell/common/asar/integrity_digest.mm
