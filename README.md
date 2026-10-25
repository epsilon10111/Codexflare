# codex-boot-animation

Codex Linux 桌面版的本地开屏 demo：打开主窗口时自动全屏，播放 4 秒的 CODEX 视频，随后进入仍保持全屏的应用。视频直接替代启动页里的 OpenAI Logo；不是另开播放器盖在应用上。

当前只适配 **26.1002.52244 / build 13536 / Linux x86_64**，安装位置为 `/usr/lib/chatgpt`。这是非官方修改，只生成本机应用副本，不分发 OpenAI 的程序文件。

## 使用

```bash
cd /data/Workplace/codex-boot-animation
python tools/manage.py install
python tools/manage.py status
```

安装后，从应用菜单正常打开原来的 ChatGPT / Codex 入口即可。**已经运行的旧进程不会热替换；先从应用菜单完全退出，再重新打开。** 仅关闭窗口可能隐藏到托盘，不能确保结束旧进程。

也可以通过下面的入口启动，后面的文件路径或 `codex://` 链接会原样转发：

```bash
python tools/manage.py launch
```

- 动画自动铺满 Codex 所在显示器，视频使用 `object-fit: cover`；非 16:9 屏幕可能裁掉画面边缘。
- 点击右下角「跳过」或按 Esc 可立即跳过。播放失败或超时 8 秒会退出动画层。
- 尊重系统的「减少动态效果」偏好：开启时直接进入应用。
- 动画结束后应用保持全屏；可用应用的全屏切换命令或 KDE 窗口菜单退出全屏。
- 独立 Page、宠物、弹窗、后台预热和截图使用的隐藏窗口不显示动画。后台启动模式不抢先显示窗口。
- 已运行的实例被唤起时不重播视频；隐藏后重新显示的主窗口会进入全屏。

## 安装与回退的范围

安装器将当前系统应用完整复制到仓库的 `.local/runtime/`（约 1.6 GB），只在副本中修改 `app.asar`。随后写入用户级 `~/.local/share/applications/chatgpt.desktop`，使原菜单入口指向副本。若该文件原先存在，会保存原内容和权限；后续检测到它被其他操作修改时会拒绝覆盖。

系统 `/usr/lib/chatgpt`、`/usr/bin/chatgpt`、用户登录信息和聊天目录不做修改。直接执行 `/usr/bin/chatgpt` 仍打开原版。副本正常使用原有登录和聊天；在原版进程退出前，两者的单实例机制会转发到现有窗口。

```bash
python tools/manage.py uninstall
```

回退会恢复安装前的用户菜单入口，保留应用副本与备份，不停止进程、不删除用户数据。回退后同样需要完全退出定制进程，再从菜单打开原版。

系统应用更新后，启动器会检测到来源变化，**自动打开原版**，避免继续运行陈旧的定制副本。必须重新审查新版补丁后再适配；安装器遇到未知版本或补丁匹配不唯一会停止。重新安装前也必须退出正在运行的定制副本。

## 视频与实现

- `assets/boot.webm`：1920×1080、30 fps、4 秒、VP9、无声；蓝紫光轨与 CODEX 字样，完全由本仓库生成。
- `src/boot.js` / `src/boot.css`：独立于 React 根节点的动画层、跳过与失败退出。
- `tools/patch_app.py`：只针对已知构建的最小补丁，保留原 CSP、上下文隔离和导航限制，更新 ASAR 文件完整性字段。
- `tools/manage.py`：用户级安装、启动、版本变化回退和卸载。

重新生成视频需要系统已安装的 FFmpeg（libvpx-vp9）、Pillow 和 NumPy。安装和运行现成 demo 只需要 Python 3.11+ 及已安装的目标 Codex。

```bash
/usr/bin/python3 tools/generate_demo.py
python tools/manage.py install
```

替换 `assets/boot.webm` 后重新安装即可更换素材。demo 的超时为 8 秒，使用更长视频时需同步调整 `src/boot.js`。

## 验证

```bash
python -m unittest discover -s tests -v
node --test tests/test_boot.cjs
# 会短暂打开一个真正的全屏测试窗口，然后自动关闭。
python tools/native_smoke.py
```

原生测试复制已安装的定制运行时，使用独立的界面目录和 `CODEX_HOME`，禁用测试实例的默认协议注册。它记录原生全屏状态、显示器与窗口边界、视频解码尺寸及播放时间、动画退出和应用挂载情况，并保存播放中/播放后截图到 `work/native-smoke-*/`。测试结束清理测试运行时，不关闭当前真实会话。

当前验收记录见 [VALIDATION.md](VALIDATION.md)。单元测试不替代原生测试；独立登录页测试也不代表已验证当前真实账户的冷启动。

## 参考

参考了 [powerofjinbo/claude-](https://github.com/powerofjinbo/claude-/tree/ef3a656e15594f6b8e73e9550ff385bb52813ce8) 的视频开屏、跳过和超时退出思路。该项目以独立置顶窗口播放动画；本 demo 使用 Codex 用户级运行副本，在原启动页内播放，自行生成视频，没有复制其素材或实现代码。

原生窗口行为参照 [Electron BrowserWindow](https://www.electronjs.org/docs/latest/api/browser-window)，归档字段参照 [Electron ASAR Integrity](https://www.electronjs.org/docs/latest/tutorial/asar-integrity)。
