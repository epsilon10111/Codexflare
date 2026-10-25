# Repository Guidelines

## 项目结构与模块职责

本仓库为 Linux Codex 桌面版生成可回退的开屏动画副本，当前仅适配 `26.1002.52244 / build 13536 / x86_64`。

- `src/boot.js`、`src/boot.css`：动画层、播放退出逻辑和样式。
- `ui/`：黑白六边形编辑界面；`tools/desktop.py` 用 GTK/WebKit 显示独立窗口，`tools/editor.py` 提供内部回环服务，`tools/animation.py` 验证并保存配置。
- `assets/boot.webm`：生成的四秒无声 VP9 视频。
- `tools/`：`generate_demo.py` 生成素材，`patch_app.py` 修改 ASAR 副本，`manage.py` 管理安装与回退，`native_smoke.py` 验证原生窗口。
- `tests/`：Python 单元测试、Node 动画测试及原生探针；`VALIDATION.md` 记录验收证据和边界。
- `.local/` 存放运行副本与回退信息，`work/` 存放截图和测试输出；两者均被 Git 忽略。

## 构建、测试与本地运行

在仓库根目录执行；安装需要 Python 3.11+ 和目标版本 Codex，无 npm 构建步骤。

| 命令 | 用途 |
| --- | --- |
| `python tools/editor.py` | 打开独立桌面编辑窗口，必要时自动使用系统 Python |
| `/usr/bin/python3 tools/desktop_smoke.py` | 使用隔离配置验证真实编辑窗口及视频播放 |
| `python -m unittest discover -s tests -v` | 检查归档补丁、安装保护及回退 |
| `node --test tests/test_boot.cjs tests/test_editor_ui.cjs` | 检查动画生命周期、失败退出与编辑器交互 |
| `/usr/bin/python3 tools/generate_demo.py` | 重新生成视频；需要 Pillow、NumPy、FFmpeg/ffprobe、libvpx-vp9 和脚本指定的 DejaVuSans 字体 |
| `python tools/manage.py install` | 创建定制副本并更新用户菜单入口 |
| `python tools/manage.py status` | 检查副本及入口状态 |
| `python tools/manage.py launch` | 启动副本，来源变化时回退到原版 |
| `python tools/manage.py uninstall` | 恢复原菜单入口，保留副本与备份 |
| `python tools/native_smoke.py` | 基于已安装副本打开隔离全屏测试窗口并保存截图 |

## 编码风格与命名

Python 使用四空格缩进、`snake_case` 函数和大写常量；JavaScript/CSS 使用两空格缩进，JavaScript 使用 `camelCase` 和分号。沿用所在文件的引号风格。仓库未配置格式化或 lint 工具；保持局部修改，复用现有辅助函数。修改参数范围时同步检查配置验证、UI 和动画运行时，保留基于时长和速度的超时保护。

## 测试要求

Python 使用标准库 `unittest`，文件命名为 `test_*.py`，方法命名为 `test_*`；JavaScript 使用内置 `node:test` 和严格断言。没有覆盖率百分比门槛；行为变更应补充回归测试，覆盖跳过、播放失败、减少动态效果或安装恢复等受影响路径。

窗口或视频变更还需在图形桌面运行原生测试，检查实际窗口边界和播放前后截图。单元测试与隔离登录页均不能证明真实账户冷启动正常；在 `VALIDATION.md` 明确记录未验证项。

编辑器改动还需在实际 GTK/WebKit 窗口验证上传、预览、保存、关闭与错误提示。HTTP 测试使用临时目录和安装函数替身，不应改动真实菜单入口。遵循 `DESIGN.md` 的黑白六瓣几何风格、字号与减少动态效果规则，视频保留原色；自绘标题栏保留 GTK 的窗口操作和关闭保护。

## 提交与 Pull Request

提交使用简短类型前缀，沿用 `feat: 添加 Codex 全屏开屏动画 demo` 的风格，例如 `fix: 修复动画超时退出`、`docs: 更新验证说明`。PR 应说明问题、改动、目标构建和实际测试结果；有关联 issue 时附链接，视觉变更附截图或短视频。

## 安全与配置边界

仅修改 `.local/` 内的应用副本及受保护的用户菜单入口，不改写 `/usr/lib/chatgpt`、用户登录数据或聊天目录。不提交应用二进制副本、测试 profile 或日志。保留版本检查、唯一匹配校验、CSP、上下文隔离和备份恢复逻辑；升级适配必须重新审查补丁。安装前正常退出定制副本，测试不得终止用户当前会话。
