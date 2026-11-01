# Agent 配置接口 / Agent configuration

[English](#english) · [返回主页](../README.md)

从 Codexflare 0.2.0 源码开始可用；已发布的 v0.1.0 RPM / DEB 不含此接口。以下命令在仓库根目录运行；Windows 使用 `py -3`，macOS 使用已安装依赖的 `.venv/bin/python`。Linux 0.2.0+ 安装包可将 `python3 tools/manage.py` 替换为 `codexflare-manage`。无需改动编辑界面。

```sh
python3 tools/manage.py configure show
python3 tools/manage.py configure check
```

`show` 读取当前配置；`check` 报告平台、Codex 版本、依赖和可应用状态。退出码 `0` 表示检查通过、`2` 表示当前不可应用；安装时仍会检查精确构建与补丁锚点。其他错误返回 `1` 和 JSON 错误信息。检查不可应用时仍可预览、导入和保存。

把需要修改的字段写入 UTF-8 文件 `patch.json`：

```json
{"muted": true, "background": {"opacity": 0.12}}
```

```sh
python3 tools/manage.py configure set patch.json
python3 tools/manage.py configure set patch.json --save
```

第一条仅预览，返回修改前后值，不写配置。第二条保存，嵌套背景字段也只更新指定项，保留其他设置。文件最多 4 KiB；参数范围与编辑器一致，未知字段、无效值和找不到的素材会被拒绝。编辑器打开时不可使用命令行保存或导入，请先正常关闭编辑器；读取和预览仍可进行。

```sh
python3 tools/manage.py configure import-video "/path/to/video.mp4"
python3 tools/manage.py configure import-background "/path/to/background.png"
```

视频不超过 100 MiB / 30 秒，转换需要 FFmpeg 和 ffprobe；PNG 不超过 40 MiB。导入返回 `media.id`，不会自动选中。将该标识写入 `video` 或 `background.image` 字段，再预览、保存。素材仅在本地处理。

保存**不等于应用**。准备应用时正常退出定制 Codex，再执行：

```sh
python3 tools/manage.py install
python3 tools/manage.py status
```

需要恢复入口时执行 `python3 tools/manage.py uninstall`，设置、媒体和备份仍保留。不要终止用户当前会话或绕过版本检查。配置损坏时先备份并诊断，不能用默认值自动覆盖。

默认视频与背景可以随 Codexflare 使用，不能作为独立付费素材库销售，见[素材许可](../assets/LICENSE)。开放配置接口不依赖购买 Skill。

<a id="english"></a>
## English

Available in Codexflare 0.2.0 source and later. The published v0.1.0 RPM / DEB packages do not include this interface. Run the commands above from the repository root; use `py -3` on Windows or the configured `.venv/bin/python` on macOS. A Linux 0.2.0+ package can use `codexflare-manage` in place of `python3 tools/manage.py`.

`configure show` reads the current settings. `configure check` reports the platform, supported Codex version, dependencies, and whether applying is available. Its exit code is `0` when available or `2` when unavailable; installation still checks the exact build and patch anchors. Other errors return `1` with a JSON error. Previewing, importing, and saving remain available on unsupported Codex builds.

Write only the fields you want to change into a UTF-8 JSON file, at most 4 KiB. `configure set patch.json` previews the before/after values without writing; add `--save` to save. Nested background fields preserve all unspecified settings. The same validation as the editor applies. Close the editor before saving or importing from the CLI; reads and previews remain available while it is open.

`configure import-video FILE` accepts a video up to 100 MiB / 30 seconds and needs FFmpeg plus ffprobe. `configure import-background FILE` accepts a PNG up to 40 MiB. Each returns a `media.id` without selecting it. Put that ID in `video` or `background.image`, then preview and save. Media stays local.

Saving does **not** apply changes. When ready, quit the customized Codex normally, run `install`, and inspect `status`. Use `uninstall` to restore the entry while keeping settings, media, and backups. Never terminate an active user session or bypass version checks. Back up and diagnose damaged settings instead of silently replacing them with defaults.

The [media license](../assets/LICENSE) allows bundled assets to accompany Codexflare, not to be sold as a standalone asset library. This open configuration interface does not require purchasing a Skill.
