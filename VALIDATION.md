# 验收记录

本文按工作阶段保留历史证据。早期“待应用”“未推送”和后台状态仅描述当时的检查点，不代表当前安装或发布状态。macOS `v0.1.1` 发布范围与复测见文末及 `docs/releases/v0.1.1.md`；Linux 继续使用已发布的 `v0.1.0`。

日期：2026-10-25（Asia/Taipei）。目标：Codex 26.1002.52244 / build 13536，Fedora KDE / Wayland，应用使用 XWayland。

## v0.1.0 RPM 与开源发布

- 完善安装、应用、卸载、构建及兼容说明；代码与文档文字采用 MIT，内置视频、背景及其截图内容按独立素材许可允许随 Codexflare 分发。包内保留 `LICENSE`、`MEDIA-LICENSE` 和第三方说明。
- RPM 安装到 `/usr/share/codexflare`，通过 `.packaged` 标识使用 `$XDG_DATA_HOME/codexflare`（默认 `~/.local/share/codexflare`）；源码继续使用 `.local/`。用户 desktop 覆盖遵循 XDG；持久启动器在 RPM 被移除后回到系统 `/usr/bin/chatgpt`。不包含系统应用副本，也不自动修改用户 Codex 入口。
- Python **63 项**：默认 Python 通过 60 项，3 项 GTK 测试由系统 Python 补齐；Node **57/57**。覆盖安装版只读目录、同一配置位置、导入背景打包、卸载后的参数转发与原有恢复逻辑。
- `rpmbuild -ba` 成功生成 noarch RPM、SRPM，另提供 Git 提交对应源码归档与 SHA256 校验。`rpm -K` 摘要校验通过。`rpmlint` **0 错误、3 警告**：自定义素材许可不在 Fedora 已批准许可列表（RPM/SRPM 各一项），以及安装标识是隐藏文件；未把素材错误标为 MIT，也未屏蔽这些警告。
- `work/rpm-smoke-t0w5bh67/`：包内无脚本/触发器、无系统应用或用户数据；desktop 与许可证验证通过。实际解包后的代码树设为只读，临时 HOME/XDG 中完成默认素材读取、0600 配置保存、HTTP 修改和无令牌拒绝，代码资源哈希不变。在用户命名空间内用独立 RPM 根目录与数据库完成真实安装、查询和卸载。
- `work/desktop-smoke-ktfr5eh0/`：从上述 RPM 的只读解包目录加载实际 Python/UI/素材，通过 GTK 原生窗口、视频/PNG 导入、两张内置背景、播放/静音、保存、关闭保护与服务退出。默认 1280×900、最小 1000×720，标题栏及最大化/还原均通过；已查看截图。

未向主机安装 RPM，未覆盖当前定制副本或重启真实会话。隔离 RPM 事务使用 `--nodeps`，验证了安装/卸载文件行为，没有验证全新机器的 DNF 依赖下载；当前机器已有所需桌面与媒体依赖。首版未作 GPG 签名。真实账户冷启动及其他发行版/应用构建不在本次验收范围。

## 片尾衔接与背景预处理（最新，待应用）

- 将工作区就绪检测和两帧绘制准备前移到视频播放期间，图片只解码一次。片尾重新检查当前内容节点及其交互状态，已准备完成便直接淡出；节点替换、图片失败、Esc、减少动态效果及 20 秒等待上限仍有保护。全宽右侧页面恢复时，以可操作的右页判断就绪，不再等待已被设为 `inert` 的主会话。
- 为目标构建提前预载 RPC、主入口、初始模块、主路由及两个样式资源；只预取，不改变脚本执行和 CSS 挂载顺序。构建前验证归档资源存在，保留 CSP、上下文隔离及原初始化流程。
- 大图仅在构建副本时经 FFmpeg 按比例缩至 3840×2160 范围，保留透明度与位深；原件、选择及参数不变。default1：25237663 → 6036943 字节、3840×2156；default2：23568760 → 5920314 字节、2869×2160。缺少 FFmpeg 使用原图，其他处理错误阻止本次构建。
- Python **57 项**：默认 Python 通过 54 项，3 项 GTK 测试由系统 Python 补测通过；Node **57/57**（动画 36、UI 15、窗口 6）。覆盖预载资源、缩图/透明度/失败、提前准备、节点替换和右页就绪判断。
- 完整应用隔离登录测试 `work/native-smoke-jdkbjmg6/` 通过：41 个样本、39 个播放样本，无 `waiting-app` 样本；首个采样到界面可交互且背景准备完成为 **4.37 秒**，视频完整播放后正常退出。此前单次旧版基线为 `work/native-smoke-a0irkylg/`，界面可交互采样约 7.38 秒；两次并非受控性能基准，缓存和初始化波动未排除，不能据此承诺固定加速幅度。
- 新增 `background_smoke.py --startup`，使用归档中的实际视频、处理后 PNG 和背景 CSS，以及真实应用布局样式。模拟工作区在播放约 1 秒后挂载，分别覆盖普通主区、主区 inert 的全宽右页。最终 `work/background-smoke-0y0zo_b4/` 两种布局片尾到淡出为 **0.3 / 0.2 ms**，淡出保留原有约 230 ms；首次可采集截图完成于遮罩移除后 **76 / 51 ms**，与约 512 ms 后截图的背景区差异均为 **0**。禁用背景对照平均差 **3.85 / 3.99** 色阶，证明确实绘制了图片。已查看首显截图。
- 常规背景回归 `work/background-smoke-y6lf2gct/` 通过：12 组滚动、窄窗口、右侧面板、输入区及无障碍检查均通过，最低文字/按钮对比度 **9.20:1**。首轮 `work/background-smoke-0wrgx93c/` 在分数缩放下出现 18/88504 个像素单通道 ±1 的差异，含负差；未遮罩负对照为 56016 像素、最大 199 色阶，证据见该目录 `scroll-rounding-evidence.json`。仅将滚动输入区的像素断言与已有黑底测试统一为允许一个色阶舍入，并加强负对照；未改生产背景样式。

未重装正在运行的 `.local/runtime`，未关闭真实会话，真实配置仍保留声音开启及全屏选择。测试候选单独使用静音和普通窗口。完全退出 Codex 后，在 Codexflare 刷新状态并重新应用生效。真实账户冷启动、远端会话恢复及最早 51–76 ms 内的逐帧合成未验证；网络或后端仍慢时会继续显示等待，不能保证任何视频长度都能覆盖初始化。

## 开屏右下角英文提示（上一轮）

- 原跳过按钮改为非交互 `span.skip-hint`，文案 `Press Esc to skip`，12 px、距右侧和底部各 16 px；去除背景、边框、焦点与点击处理，保留 Esc 键跳过。
- Node 开屏测试 **31/31** 通过，覆盖提示点击不退出、无按钮以及 Esc 正常释放遮罩；`git diff --check` 通过。
- 隔离原生测试 `work/native-smoke-rgnwjan9/` 通过：41 个样本、39 个播放样本，正常播放结束；40 个提示样本均为 SPAN、12 px、不可聚焦、无按钮、无边框及透明背景，位置实测距右 15.90 / 底部 16.29 CSS px（分数缩放）。已查看 `playing.png`。
- 为避免测试声音干扰，仅候选设为静音、恢复普通窗口；真实声音与窗口设置未改变，运行中的安装副本未覆盖。真实账户冷启动未复测，退出 Codex 后需重新应用。

## 静音按钮与内置默认背景（待应用）

- 预览标题增加「静音 / 声音开启」按钮，`muted` 默认 `true`，保存、应用与实际开屏使用同一设置；历史配置缺少该字段时继续静音。参数重置、素材切换和刷新保留声音偏好。
- 为 `assets/default.webm` 从原 MP4 补回 Opus 音轨，原 VP9 画面直接复制；1920×1080、30 fps、10.039 秒、3880164 字节，完整 FFmpeg 解码通过。SHA256：`bea07ac4207b64bc2ea8d81aa901f86c0d19046a86287c19dffa4addcea40c49`。
- 视频导入保留可选音轨，统一转为 Opus；无音轨仍可导入。原片仍严格限于 30 秒，编码产物允许额外 50 ms 的帧边界与封装延迟，防止 30 秒有声原片被错误拒绝。真实 FFmpeg 上传测试覆盖两种情况。
- 用户新 PNG 原样保存，随后按用户选择保留为 `assets/default1.png`：7296×4096、25237663 字节，SHA256：`cc2c91cd006181761d3831bcf3010468e5f32c482f7c8b4188e10cb7fd540bd2`，与 Downloads 源图逐字节一致。内置 ID 为 `default`；同时提供 `assets/default2.png`（5440×4096、23568760 字节，SHA256 `86310518691eee8e2292cc6f6b58f81b5bd2b32c4193507b7188e302da4690f6`），两张均可选择，旧 `legacy` 及导入图片继续兼容。
- 已备份并保存本地配置，启用默认背景，保留原视频调节与窗口模式；背景 18% 不透明度、位置 80%、大小 70%。构建候选归档中的视频、图片与仓库素材逐字节一致。
- Python **49 项**：默认 Python 通过 46 项，3 项 GTK 测试使用系统 Python 补测通过；Node **52/52** 通过。`git diff --check` 通过。
- 静音完整应用测试 `work/native-smoke-7fetdg72/` 通过：40 个样本、38 个播放样本，所有样本未输出音频；背景约 516 ms 完成解码，约 10.38 s 开始揭幕时已 ready。使用隔离登录页，不读取真实账户。

- GTK/WebKit 完整自检 `work/desktop-smoke-j1cbclqr/` 通过：两张内置背景实际解码宽度分别 7296 / 5440，选择、保存和切回默认均成功；静音切换、保存、刷新及导入保持偏好通过，窗口与服务正常退出。已查看截图，README 使用本轮视口截图。
- 原生验证发现 WebKit 会自动改变媒体元素的 `muted` 属性；改由独立设置变量保存偏好，并在换源、元数据就绪及音量事件时同步播放器。诊断日志证实该变化没有可信用户点击；此前悬停曾受指针移动干扰，测试现于采样前重发原生指针事件，未删除样式和悬停断言。
- 新默认背景回归 `work/background-smoke-t7wavche/` 通过：使用真实应用 CSS 与模拟会话，侧栏、窄窗口、透明输入框、无文字泄漏及无障碍检查均通过；默认及 50% 强度下文字/按钮最低实测对比度 9.20:1。已查看右侧分支截图。

- 当前实际运行时自报 Electron / Chromium `155.0.8059.27`；标准 `autoplayPolicy` 设置未解决有声自动播放拒绝。最终保留所有原 webPreferences，主进程仅对已启用声音的开屏主窗口，在 `dom-ready` 用一次手势上下文派发固定事件；视频仍受跳过、减少动态效果与超时保护。没有全局放宽自动播放。
- 最终纯生产有声候选 `work/native-smoke-7su_lai1/` 通过：41 个样本、39 个有效播放样本、38 个音频活动样本，正常结束。42 个活跃音频流采样全部进入独立 null sink，`audio-routing.json` 确认默认输出前后一致且临时设备已卸载。未试听真实扬声器。
- 初期有声拒绝记录保留于 `work/native-smoke-auofiq04/`，NotAllowedError 诊断于 `work/native-smoke-9bfjc7ya/`。桥接曾导致真实 `return await loadURL(...), R` 提前返回，无样本运行记录在 `work/native-smoke-xq8ni1ve/`；已移入 URL IIFE 修复，测试同步真实返回结构，最终生产运行通过。

未覆盖运行中的 `.local/runtime`，未停止真实会话。重新打开 Codexflare；完全退出 Codex 后刷新状态并应用，随后从原菜单入口启动。真实账户冷启动及实际扬声器输出未验证。

## 默认开屏素材替换（上一轮，待应用）

- 用户提供的 MP4 原样复制为 `assets/default.mp4`（22433641 字节），SHA256 为 `f5c5c13205ec641a46c500ba747f8039e7d7181a82a7eebe7f8e97b16f0db5db`，与 Downloads 原文件一致；原文件未修改。
- 复用既有导入流程生成 `assets/default.webm`：无声 VP9、1920×1080、30 fps、10.033 秒、3717194 字节，完整 FFmpeg 解码通过。原 MP4 的音轨保留，实际开屏继续静音。
- 默认视频标识仍为 `default`，路径与展示名称更新，静态元数据与 ffprobe 一致；未新增播放时的 FFmpeg 依赖。未注入配置时的脚本默认时长同步更新，超时上限为 15 秒，避免旧的 8 秒保护截断新片。构建归档中的视频与 `assets/default.webm` 字节一致。
- 当前已保存选项本来就是 `video: default`，因此无需覆盖配置；背景、窗口和视频调节参数保持不变。旧 `assets/boot.webm` 及生成脚本保留为示例，生成它不会覆盖新默认素材。
- Python **44 项**（41 项默认 Python，加 3 项系统 GTK 补测）、Node **42/42** 通过。原生 GTK/WebKit 自检 `work/desktop-smoke-xz8vkzm5/` 通过，实际默认视频解码播放、导入、参数保存及关闭保护均正常；已查看截图并同步 README。

- 完整应用原生启动 `work/native-smoke-h50oozpi/` 通过：41 个样本、39 个有效播放样本，视频完整播放到 10.033 秒后正常揭幕，没有触发旧超时；背景就绪及普通窗口检查通过。此测试使用隔离登录页。

未覆盖正在运行的安装副本或重启真实会话；完全退出 Codex 后，在 Codexflare 刷新状态并应用，新的默认片才会进入实际安装。

## 启动窗口模式与轻薄输入框（待应用）

- 共享设置区新增 `windowMode`：`restore`（默认）、`fullscreen`、`centered`。旧配置自动使用恢复模式，保存和应用沿用既有流程；切换页签、刷新或重置视频／背景不会意外重置窗口偏好。
- 主进程仅标记普通首次启动的可见主窗口。全屏通过一次 `setFullScreen(true)` 进入；居中模式请求工作区内的 1100×760，并限制初始及后续最小尺寸；后台、辅助、独立 Page 和后续新窗口保留原行为。恢复模式仅在确有已保存边界时阻止登录页晚覆盖，保留原有最大化恢复。
- Python **44 项**：默认 Python 通过 41 项，3 项 GTK 测试使用系统 Python 补测通过；Node **42/42**，其中 4 项窗口行为测试也由 Python 补丁测试调用。真实来源主脚本的三模式唯一匹配、语法和重复补丁拒绝通过；`git diff --check` 通过。
- 原生编辑器 `work/desktop-smoke-g8_0bbty/` 通过：三种选项可选择并落盘，跨页及参数重置保留偏好，最小窗口中控件可达；视频／图片导入、预览、保存、关闭确认与错误提示仍通过。已查看窗口截图，README 使用这张不含私人图片的截图。
- 三种完整应用测试均使用隔离 profile，预置 `(150,100,980,700)` 普通窗口边界；播放和背景就绪门控均通过：
  - 恢复：`work/native-smoke-qocjk2n2/`，17 个样本，最终 `(148,98,984,702)`，没有跳成登录页默认尺寸。
  - 居中：`work/native-smoke-010bdatc/`，17 个样本，最终 `(912,378,1103,764)`，工作区 2926×1520，中心误差小于 1 DIP。
  - 全屏：`work/native-smoke-nh3960eq/`，23 个样本，实际边界与显示器同为 `(0,0,2926,1646)`，没有只检查全屏布尔值。
- 当前 KDE/XWayland、缩放因子 1.3125 下，普通窗口请求尺寸与回读尺寸存在 2–4 DIP 差，内容区与外框 API 回读一致。验收允许最多 4 DIP 尺寸差，居中位置独立限于 2 DIP；未将其归因于已证明的窗口边框，也未向系统加入补偿。早期恢复测试曾因登录页覆盖失败，已修复；居中测试曾因严格 2 DIP 尺寸断言失败，差值保留在 `work/native-smoke-7o70at_c/`。
- 深色输入框改用 48% 表面底色、6px 模糊和细内边线，文字本身保持不透明；Codexflare 模拟预览同步。浅色、三种无障碍偏好、附件拖入及特殊编辑器保留原表面反馈。
- 背景原生回归 `work/background-smoke-97j2c_og/` 通过：主输入框 19688/94939、分支输入框 41140/44472 像素随背景变化，证明图片实际透入；默认及 50% 背景强度下，实测文字／按钮最低对比度 **9.48:1**。12 组滚动测试无文字泄漏，主区／分支交互、浅色与无障碍恢复通过；已目视窄窗和分支截图。

未重装正在运行的 `.local/runtime`，未修改真实配置、登录数据或系统应用。完全退出 Codex 后，在重新打开的 Codexflare 中选择模式、保存、刷新状态并应用，再启动 Codex 生效。真实账户冷启动、原生最大化恢复、多显示器热插拔与极小屏幕实机尚未验证；保存的最大化状态、负坐标显示器及极小工作区有模拟回归。

## Codexflare 背景编辑与无缝启动（运行副本待应用）

- 原生窗口、页面标题与用户菜单显示名统一为 **Codexflare**。菜单原文件已备份于 `.local/codex-animation-studio.desktop.before-codexflare`，`desktop-file-validate` 通过。README 截图更新为本轮不含私人图片的原生窗口截图。
- 新增「常驻背景」页签，支持 PNG 上传、选择、启用、实时预览及不透明度／位置／大小调节；与动画共用保存和应用。图片按 SHA256 存在 `.local/backgrounds/`，旧的 `.local/background.png` 自动兼容；不自动提交或上传私人素材。
- 后端验证 PNG 边界、CRC、参数范围及图片标识；保存和安装复验选中图片。上传不覆盖已保存选择，缺失图片保留标识与恢复提示；关闭背景后可保存，刷新保留草稿。
- Python 共 **42 项**：默认 Python 通过 39 项，跳过的 3 项 GTK 测试由系统 Python 补测通过；最终 Node **36/36**。覆盖图片导入／权限／保存／嵌入／关闭、缺图恢复、启动解码等待、失败、跳过和超时。
- 原生 GTK/WebKit 编辑器自检 `work/desktop-smoke-l4ve9hcw/` 通过：真实文件选择信号导入测试 PNG，调节到 26%／86%／92%，预览和保存一致；关闭未保存窗口可取消，损坏 PNG 显示错误，禁用后可保存并正常退出。实际窗口标题、默认及最小尺寸、视频导入播放仍通过；已查看背景和动画页截图。后续仅修正缺图占位和操作提示，以 Node 回归验证，未重复完整 GTK 测试。
- 输入框黑边定位到原应用的 FooterFade 填充和渐变。仅替换常规会话外围遮挡，并给会话文字加随滚动视口移动的渐隐遮罩；实际输入框、代码块、Home 和 compact 保持原样。目标 Chromium 实测支持滚动时间线和容器高度单位；不支持时保留原填充。
- 最终背景验收 `work/background-smoke-82aqphpg/` 通过。12 组宽窗／窄窗／侧栏、正向／反向、中段／底部组合中，输入区域文字泄漏差分和输入框像素差分均为 **0**，容器、会话、输入框边界不变；去掉遮罩的负对照确实出现文字泄漏。恢复原 FooterFade 后，黑边区域 **37218/38295** 像素变化，证实本轮覆盖实际遮挡。右侧背景连续、点击、配置参数和三种无障碍模式均通过；已目视窄窗和滚动截图。浅色遮罩边缘最高有 1 色阶舍入差，未见色块。
- 已打开真实本地 Codexflare 窗口并停留在「常驻背景」，读取原有图片验证自然宽度 7296、标题一致且无预览错误；证据为 `work/codexflare-background-live/`。此检查只读取现有配置，没有保存或安装。
- 页面头部增加高优先级图片 preload，开场脚本立即并行解码；保留图片引用，主界面就绪后再次确认解码，再等待两个绘制帧才淡出；跳过和超时后迟到的解码回调不会复活遮罩。失败仍释放遮罩，视频结束后的等待上限仍为 20 秒。
- 最终完整应用原生启动 `work/native-smoke-g8ak94n6/` 通过：24 个样本、16 个有效播放样本，约 **533 ms** 的采样中已完成 7296×4096 图片解码；约 **6.12 s** 才开始揭幕，遮罩移除后背景状态为 ready。全部保持普通窗口；此运行使用隔离登录页，未读取真实账户。

真实 Codex 仍使用运行中的旧副本；依照仓库要求“安装前正常退出定制副本”，未覆盖 `.local/runtime` 或关闭当前会话。退出 Codex 后，在保持打开的 Codexflare 中点击「刷新状态」再「应用到 Codex」，重新打开才生效。真实账户冷启动和全部嵌入页面未验证；主动跳过、解码失败或等待超时仍可能露出原有加载页。

## 窗口、启动过渡与背景融合修复（待安装）

- 移除补丁对全屏、最大化和登录窗口尺寸的覆盖，保留原应用窗口行为。应用模块继续与视频并行加载；视频结束后保留尾帧，主内容或登录控件可用才淡出，最多额外等待 20 秒。跳过、失败和超时仍释放遮罩。
- 就绪判断限定主内容区域，右侧插件或分支的局部加载不阻塞主会话。回归覆盖空壳、隐藏或 inert 主区、局部 Blossom、正常结束及超时；CSS 不再隐藏 React 局部加载反馈。
- Python 共 **37 项**：默认 Python 通过 34 项，跳过的 3 项 GTK 测试使用系统 Python 补测通过；最终 Node **25/25**，`git diff --check` 通过。
- 最新完整应用原生测试 `work/native-smoke-m5y6gonk/`：16 个样本，14 个正常播放样本，结束后遮罩移除、启动加载器消失且登录控件可操作。播放期间渲染器已初始化，全部采样保持普通可见窗口；未把 `rootChildren > 0` 单独当作就绪。
- 慢启动实验 `work/native-smoke-jilh4qsp/` 仅给隔离副本入口模块增加 6500 ms 延迟：48 个样本中 30 个处于 `waiting-app`，保留暂停的视频尾帧，直到登录页可用后正常揭幕。已查看 `waiting.png` 与普通启动的登录页截图。人为延迟实验不用于证明并行加载，后者由未延迟的原生运行验证。
- 背景主区底色统一为 `--color-surface`；深色使用滤色、浅色反相后正片叠底，消除黑底矩形。右侧分支仅移除 frame 和 tabs 两层填充，共享主区唯一背景，输入框、代码块和菜单保持底色。
- 最新背景验收 `work/background-smoke-33bt0bym/`：深浅模式的纯黑输入控制整幅像素差均为 **0**；面板开关前后比较的 504441 个背景像素差为 **0**。右侧图案可见，主区和分支代码、输入框内部像素差为 **0**，可信点击与输入通过。窄窗、浅色、三种无障碍模式及文本边界检查通过；已目视 `panel-open.png`。

当前真实会话运行于旧的 `.local/runtime`，本轮只构建和测试独立候选，没有覆盖运行中的副本或关闭会话。需完全退出后运行 `python3 tools/manage.py install` 才能生效。系统来源指纹不变；原图、预览和 profile 仍仅保存在本地忽略目录。真实账户的冷启动和所有嵌入页面未验证；主动跳过或等待超时仍可能露出应用原有加载页。

## 常驻图片背景验收

- 新增可选 `.local/background.png` 打包；PNG 签名、IHDR、尺寸、体积及 chunk 完整性校验通过后嵌入副本，原图保持不变。没有该文件时不注入背景。
- Python 共 **36 项**：默认 Python 通过 33 项，跳过的 3 项 GTK 测试使用系统 Python 补测通过；Node **17/17** 通过。新增回归覆盖默认无背景、有效图片嵌入、损坏图片拒绝和源归档不变。
- 包含背景的预构建副本通过原生启动测试，证据位于 `work/native-smoke-44zmye_u/`：18 个样本中 16 个有效播放、1 个动画结束；附加探针确认背景 CSS 被解析，原图解码为 7296×4096。结束截图仍处于隔离应用的加载画面，不作为真实聊天页验收。
- `python tools/background_smoke.py` 使用真实应用 CSS 和模拟对话在隔离 Electron 窗口验证。最新证据 `work/background-smoke-j2lbd5f8/`，包含宽/窄、浅色、高对比及背景关闭截图；已目视宽/窄与浅色效果。
- 默认背景 18% 不透明度、偏右且向左渐隐，位于内容底层，不接收指针事件。左侧 40% 的启用/关闭像素差为 **0**，右侧 30% 平均通道差约 **5.40/255**；代码块和输入框内部像素差为 **0**。可信鼠标点击和输入文本通过。
- 激活真实统一标签栏规则后，工作区底层透明；将它恢复为原不透明底色，再比较背景开/关，右侧像素差为 **0**，确认该遮挡层需要局部处理。未全局清空表面颜色变量。
- 窄窗口 10%、浅色 9%；高对比度、强制颜色及减少透明效果设置均隐藏图片。
- 已安装到 `.local/runtime`，状态检查确认定制副本可用、菜单入口由本工具持有。安装前后系统应用指纹、动画配置和原图哈希一致；归档内图片与原图一致，CSS 与源码一致。

此项验证使用模拟会话，不读取用户 profile，也不代表真实账户的所有聊天、Work、设置及嵌入式页面均已验证。未退出当前会话，安装后需正常重启应用生效。图片和预览截图均留在本地忽略目录，不进入 Git。

## Codexflare 提交前复核

- Python 共 **34 项**用例：默认 Python 通过 31 项、因缺少 GI 跳过 3 项；使用 `/usr/bin/python3` 补测后，桌面用例 **3/3** 通过。Node 动画与编辑器测试 **17/17** 通过。
- 重新执行完整桌面自检，输出位于 `work/desktop-smoke-abjx72hx/`，`passed`、文件选择、服务退出均为真；播放、导入、参数保存、默认/最小窗口、悬停反馈及标题栏操作通过。
- 已查看本次真实窗口截图，作为 README 的 `docs/images/editor.png`；临时配置、素材、日志和测试 profile 仍留在忽略目录中。
- 此次未重新安装定制副本或退出真实 Codex 会话，真实账户冷启动的验证边界保持不变。

## 大字体、自绘标题栏与动效验收（最新）

- 本轮桌面 Python 测试 **3/3**、编辑器 Node 测试 **4/4** 通过，`git diff --check` 通过。测试覆盖样式解析、导航限制及关闭时的未保存/写入保护。
- 最终完整自检：`work/desktop-smoke-_majq62k/`。`default.png` 和 `minimum.png` 包含真实 GTK 自绘标题栏；另存 WebKit 内容截图与 `result.json`。
- 默认窗口 **1280×900**、最小窗口 **1000×720**，标题栏实测 **39px**。三枚窗口按钮均可见且映射到窗口；直接采集图标区域，最小化、最大化、关闭分别有 **12/12/16** 个亮色像素。实际触发最大化按钮并还原，点击关闭按钮后经过 `try_close()` 一次，窗口和内部服务正常退出。
- 实测正文 **16px**、主标题 **28px**、区块标题 **18px**、参数标签 **16px**、按钮 **15px**、辅助文字 **13px**。默认窗口保存、应用、素材选择、上传、重置完整可见；最小窗口无横向溢出，并逐项检查滚动后控件可达。
- 通过本应用 WebKit 的原生指针事件触发真实 `:hover`，观察到按钮背景、边框和上移 1px 的变化。实际样式包含 320–340ms 入场、24s 局部轨道微动及 12s 星点明暗变化；视频颜色和参数逻辑保留。
- 默认视频播放、MP4 导入转码、四项参数与画面适配保存均通过；所有写入仅发生在临时测试目录，未改变真实配置、Codex 副本或入口。

截图检查曾发现 Breeze 主题通过透明 `Gtk.Image` 加按钮背景图绘制窗口图标，自定义背景导致图标消失。现仅在本应用 CSS 中恢复图标前景色，并用像素检查防止“对象存在但图标不可见”的误判。

未修改系统减少动态效果偏好；当前系统值为关闭，开启状态的端到端映射未验证，CSS 已包含静止退化规则。标题栏拖动、边缘手工拖拽和最小化的完整人工操作未另测，保留 GTK 标准实现；最大化、还原、程序化缩放及关闭已实测。设计参考与取舍见 `DESIGN.md`。

## 独立桌面窗口与黑白界面验收

- 启动入口改为系统 GTK 3 / WebKit2 4.1 独立窗口，不再打开浏览器；从无 GI 的默认 Python 启动时，已确认自动切换到 `/usr/bin/python3`。关闭测试窗口后，本地服务正常退出。
- 当前系统 Python 单测 **32/32**、Node 测试 **17/17** 通过；新增同源导航边界测试。最后两项纯界面调整后重新通过 **4/4** 编辑器交互测试与完整桌面自检。
- 最终桌面自检位于 `work/desktop-smoke-b1rj8lns/`：`default.png`、`desktop.png` 和 `result.json`。实际截图 **1180×820**，WebKit 的缩放后视口 **907×630**；读取实际 DOMRect，确认保存、应用、视频选择和上传按钮完整位于首屏。
- 默认 VP9 视频解码为 1920×1080；0.5× 速度、125% 亮度、110% 对比度、80% 饱和度和完整显示均在实际播放元素生效并成功保存。文件选择信号选中测试 MP4 后，真实转码为 320×180 视频并播放，原参数保留。
- 自检仅使用临时配置及素材目录，结束前恢复临时默认设置，并通过 `try_close()` 关闭窗口、验证服务退出；未安装或恢复真实 Codex。新增的编辑器菜单入口通过 `desktop-file-validate`。
- 已查看最终截图：六瓣原创几何标志、六边形细线与滑块、黑白界面和静止星点；预览保持视频原色。移除重复的原生视频控件，参数重置位于标题旁，主要操作固定在参数面板底部。

本机 WebKit 原 Wayland 路径曾报协议错误，XWayland 的 DMA-BUF 路径曾报 GBM 分配失败；最终只在编辑器进程内启用 XWayland 与兼容渲染，未更改系统显示配置。其他桌面、显示缩放组合及实际用户点击文件对话框的完整流程未另测；自检通过 WebKit 文件选择信号注入测试路径。

## 图形编辑器增量验收

- Python 测试 **31/31**、Node 测试 **17/17** 通过；覆盖参数范围、原子保存、媒体损坏恢复、请求来源与令牌保护、视频范围读取、运行中拒绝安装、安装失败状态，以及原有安装/回退和动画行为。
- HTTP 上传测试使用真实 FFmpeg 转码，校验视频尺寸、持久化、0600 媒体权限及失败后的临时文件清理。工具数据目录限制为 0700，防止其他本机用户读取上传素材及嵌入后的归档。
- 在应用内浏览器实际导入 MP4，确认转为 320×180、3 秒无声 WebM；调节到 0.5×、105% 亮度、完整显示后，读取实际 video 的 playbackRate、filter、objectFit 与解码尺寸，均符合设置。
- 界面保存后刷新，所选视频与参数恢复；从头播放成功，播放状态正确。完成后恢复默认视频与默认参数。390px 窄屏无横向溢出，桌面布局和控制台已检查。
- 使用独立预构建副本运行 `python tools/native_smoke.py --runtime work/editor-qa/native-runtime`：`work/native-smoke-t_himm7m/` 共 **25** 个样本，**23** 个有效播放样本、**1** 个动画结束且遮罩移除样本。自定义视频分辨率、0.5× 速度、105% 亮度、完整显示、窗口实际边界及应用挂载断言均通过。
- 已查看原生播放中与播放后截图，结束画面为隔离登录页。原生测试按实际视频与速度调整采样期限；30 秒视频以 0.5× 播放的预算计算通过单元测试，未实际运行这一最长组合。
- 编辑器截图保存在 `work/editor-qa/editor-ui.png`；原生截图和样本保留在上述测试目录。预构建测试运行时在验收后清理。

本次没有重装用户当前的定制副本或切换真实菜单入口；安装/回退通过隔离测试验证，实际播放通过预构建副本验证。没有退出当前真实会话，真实账户冷启动、其他 Codex 构建和所有输入编码组合未验证。

## 最初 demo 已验证（基线）

- Python 单元测试 **12/12** 通过：ASAR 往返、来源保护、补丁重复应用拒绝、版本变化回退、重复安装、桌面入口参数、原文件/权限恢复及用户改动保护。
- Node 动画测试 **12/12** 通过：自动播放、正常结束、Esc/按钮跳过、媒体错误、play 拒绝、8 秒超时、减少动态效果、隐藏窗口等待、body 延迟出现和 React 根节点替换。
- 视频：VP9、1920×1080、30 fps、4.000 秒、无音轨；FFmpeg 完整解码成功。
- 最终原生测试 `work/native-smoke-31wjl5tm/`：28 个样本，13 个正常播放样本（播放时间 > 0.5 秒），12 个片尾动画层已移除的样本，断言全部通过。
- 第一份原生样本起，主窗口报告可见且全屏，窗口边界与显示器边界一致，逻辑尺寸 **2926×1646**。动画层覆盖完整视口；分数缩放的 DOMRect 与整数视口差小于 1 个逻辑像素。
- 视频实际解码尺寸为 1920×1080，播放时间递增；到 4 秒结束，动画层移除，应用 React 根节点已挂载，窗口仍全屏。
- 已查看原生播放中与播放后截图。隔离 profile 的播放后画面是登录页，不是当前真实账户。
- 实际执行一次 `uninstall`：用户级覆盖被撤回，GIO 解析回 `/usr/share/applications/chatgpt.desktop`。随后重新安装，最终状态为定制副本可用且入口由本工具持有。
- `desktop-file-validate` 没有错误；原系统文件的双主分类仅产生提示。GIO 确认正常菜单入口解析到用户级启动器。
- 原系统应用进程 PID 9610 保持运行，未为测试关闭当前会话。

## 测试中发现并修复

首次隔离测试只有环境变量而没有 Chromium 的 `--user-data-dir`，被底层浏览器转发到现有实例；第二次因工具终端缺少 DISPLAY / D-Bus 环境而退出。测试脚本现在同时隔离底层浏览器 profile 与 Codex profile，并从当前用户的 systemd 桌面环境中只提取显示相关变量。

随后发现此构建的 `fullscreen:true` 初始设置只报告全屏标志，实际窗口仍是 1280×821；首次绘制后重新进入全屏才得到真实显示器尺寸。修复后原生测试通过。测试保留实际边界断言，没有仅以 API 布尔值作为通过条件。

## 验证边界

未退出当前真实账户的 Codex，也未验证其冷启动后的登录态、历史聊天和所有插件功能。定制副本使用原有 profile 路径，这一行为来自代码检查；实际冷启动需用户完全退出当前应用后从菜单重新打开确认。

未测试其他 Codex 版本、其他 Linux 桌面、Windows/macOS、显示器热插拔或长期运行。仅支持声明的当前构建。真实系统升级未执行；升级回退逻辑通过隔离单元测试验证。

截图、失败日志和独立测试 profile 留在忽略的 `work/` 内；系统应用副本和入口回退信息位于忽略的 `.local/`。两者不进入 Git，也不包含在源码归档中。

## macOS branch checkpoint — 2026-10-25 (WIP)

Branch: `feat/macos-support`. This snapshot is not a completed macOS release.

- Added a Cocoa/WKWebView editor, separate-profile `.app` copy manager, launcher, macOS patch anchors, and regression/smoke tests.
- Target under development: macOS arm64 Codex `26.1016.61520`, build `21421`. The installed app updated from build `20770` during development; old anchors were replaced rather than bypassing version checks.
- All six window-mode/audio variants matched the current main bundle and passed `node --check` before the latest signing changes.
- The initial native launch exposed the Electron framework's additional embedded ASAR integrity digest. Digest updating is now implemented but has not yet passed a fresh-copy native launch test.
- The Cocoa smoke test currently fails on a missing PyObjC block-signature helper symbol. Editor playback and close behavior are not yet validated.
- The last full Python test run had 74 tests, three GTK-only skips, and one fallback-test error. The fallback was subsequently corrected, but the later integrity-digest change also requires updating the mocked bundle fixtures before rerunning the suite.
- No original application or real account profile was patched. Copies, logs, test profiles and the Python environment remain in ignored directories and are not committed.

## macOS 26.1021.31345 / build 21828 — 2026-10-25

此节替代上面的 macOS WIP 状态；历史 checkpoint 保留供追溯。

环境：macOS 26.5.2（25F84）、Apple Silicon arm64、Python 3.14.5、PyObjC 12.2.2、Node 24.16.0。来源为 `/Applications/ChatGPT.app`，安装管理器同时识别 `/Applications/Codex.app`。不支持的版本、build、架构或非唯一补丁锚点均拒绝安装。

### 已完成

- Cocoa / WKWebView 原生编辑器可启动。修复了无签名 WebKit block 回调，保留原生窗口操作、文件选择回调、同源导航限制、关闭写入保护和未保存确认。
- `tools/macos_editor_smoke.py` 在临时配置下验证 1920×1080 WebM 实际播放、参数保存、背景解码、浏览器 File 上传到实际 HTTP 服务、无效 PNG 错误提示及正常关闭；8 个样本，结果通过。文件选择器返回选择/取消的回调由单元测试覆盖，原生选择面板未进行人工点击验收。
- `.app` 副本同时更新 ASAR raw-header hash 和 framework 的 v1 integrity dictionary digest，再进行本地 ad-hoc 签名；`codesign --verify --deep --strict` 通过。没有关闭 ASAR 完整性 fuse 或改写原版。
- 定制副本使用独立 bundle ID、native product directory、UI profile 和 Codex 数据目录。移除副本的供应商 URL scheme 注册；保留原版入口。
- 已安装并确认 `manage.py status` 为“定制副本可用”，编辑器安装状态为 active/available。
- Python：80 个测试，77 通过，3 个 Linux GTK 专用测试跳过。Node：65 个测试通过。当前构建全部 6 种窗口模式/声音组合的主进程补丁唯一匹配并通过 `node --check`。

### 原生应用证据

- 默认恢复/静音动画：44 个样本，其中 40 个实际播放样本、1 个正常结束样本；背景到达 `ready`，遮罩移除，应用有可交互界面。
- 全屏/有声动画：47 个样本，其中 43 个播放样本、1 个正常结束样本；实际检测到 audible，音量配置生效。此机器原生全屏为屏幕顶部安全区域以下的内容边界，因此 macOS 验证接受 native display 或 work-area 边界，并始终要求原生 fullscreen 标志。
- 一次按 Esc 的运行正确释放了遮罩；一次重叠运行编辑器/全屏测试导致播放被暂停并超时。最终有声全屏验证独立运行并通过。
- 居中模式在原生采样中先创建为 1100×760、位置 (305,191)，随后本机 yabai 改为平铺最大化。严格持续窗口几何检查因此失败。未修改用户的 yabai 配置；窗口管理器仍可覆盖居中或恢复尺寸。窗口逻辑及非主窗口/后台启动边界由 Node 回归测试覆盖。

本地证据位于忽略的 `work/macos-editor/`、`work/native-smoke-xygsmaai/`、`work/native-smoke-2gl401y1/`、`work/python-tests.log` 和 `work/node-tests.log`。公开编辑器截图为 `docs/images/editor-macos.png`。应用截图、供应商应用、日志及测试 profile 不提交。

### 保留限制

- ad-hoc 副本不能继承 OpenAI 的 Developer ID / Keychain / app-group 身份；日志中可见签名验证的原生工具拒绝连接。电脑控制、通知、共享账号等签名相关功能不作兼容承诺。
- 本轮未执行真实账号登录或聊天操作，也未做长期稳定性测试。隔离登录/欢迎界面可交互不等于真实账户冷启动验收。
- 原版升级后仍须重新审查锚点；现有启动器检测到源应用变化会回退原版。

## macOS 背景与用户参考视频比对 — 2026-10-25

用户提供了 18.6 秒的实拍显示器视频：全屏原始开场动画结束后，工作区右侧保留低不透明度线稿，向左渐隐。视频、默认原始动画和 `default1.png` 为相同角色素材。未将拍摄的显示器画面作为应用媒体，也未提交用户的视频或抽帧。

发现并修复了 macOS 适配中遗漏的 CSS 模块映射：工作区、输入框和 FooterFade 的模块名已变化，旧 Linux 选择器不能移除当前构建的覆盖层。现在按受支持构建映射模块名，并在打包时检查真实 CSS 中的目标类是否存在。背景验证工具也已移植到 macOS：使用当前构建的 shared / initial / primary CSS 和当前 FooterFade 结构，不再使用 Linux 的旧布局 CSS。

本机保存的参考外观设置：默认原视频、1×、cover、全屏启动；默认线稿背景、opacity 0.18、position 80%、scale 70%。保留用户原有静音设置。仅本机配置改变，不修改所有用户的默认启动方式。

验证结果：

- `tools/background_smoke.py` 全部通过。右侧背景可见，左侧像素不受影响，代码块保持不透明；输入框 48% 表面与 6px 模糊生效。
- 右侧面板打开前后的背景位置/底色一致；输入与按钮事件仍可用。12 种滚动布局检查通过，输入区域不被滚动文字穿透。
- 0.18 与 0.5 背景不透明度下输入文字/按钮对比度均超过 9:1。浅色、高对比度、减少透明与 forced-colors 验证通过。
- `tools/background_smoke.py --startup` 的普通工作区、全宽右侧面板两种路径均通过。动画自然结束，背景在揭幕前为 ready；首帧与 500ms 后背景测量区域的差异为 0 像素。
- macOS 原生测试窗口使用 panel 类型，避免本机 yabai 在抓取 DOM 几何与像素之间异步平铺测试窗口。未修改用户窗口管理器规则。Retina 对比度采样使用迭代最大值，避免像素数组展开超过 JavaScript 参数数量限制。
- Python：82 个测试，79 通过、3 个 GTK 专用跳过。Node：65 个测试通过。

本地证据：`work/background-smoke-wtjdq6l3/result.json`、`work/background-smoke-7uhn3mj0/result.json`；公开模拟工作区截图 `docs/images/background-macos.png`。验证使用真实应用样式与模拟会话，未读取真实聊天。所匹配的是屏幕内的素材、构图、透明度与转场；拍屏的透视、显示器色彩和环境灯光不构成已验证的逐像素一致性。


## 本地 macOS build 20586 安装验证 — 2026-10-25

本地分支 `local/macos-build-20586` 基于上游 `feat/macos-support` 的 `62ab61c`；本节仅适用于本机 arm64 Codex `26.1013.31256 / 20586`，不代表上游发布支持。环境为 macOS 26.6.2、Python 3.12.14、PyObjC 12.2.2、FFmpeg/ffprobe 9.0。

- 更新版本、主脚本和预加载资产的精确锚点，以及 Electron、窗口边界、窗口模式和协议注册的压缩符号；保留所有版本、唯一匹配和完整性校验。恢复窗口使用局部 `C`，回归测试确保不误用路径模块 `S`。
- 实际 ASAR 的三种窗口模式 × 两种声音设置均唯一匹配，并通过 Node 语法校验。Node 全套 66/66 通过；Python 80 项中 77 通过、3 项 Linux GTK 专用测试跳过。
- 原生 Cocoa/WKWebView 编辑器：8 个样本，通过视频播放、保存、背景解码/上传、无效 PNG 错误提示和正常关闭检查。
- 最终安装位置 `~/Applications/Codexflare`，独立入口为 `~/Applications/Codexflare Codex.app`；额外提供 `Codexflare Editor.app`。原先工作目录过长导致 Unix socket EINVAL，迁至短路径后复测消失。
- 最终原生 smoke 48 个样本：40 个视频播放样本，4 个正常结束样本；视频 1920×1080、10.039 秒、默认静音；恢复隔离配置的 1100×760 窗口边界，背景 ready 后揭幕并进入可交互登录页。证据位于 `work/native-smoke-4leqcl4l`。
- `codesign --verify --deep --strict` 通过；安装状态为定制副本可用；原版应用 ASAR、可执行文件及 Info.plist 的文件指纹与安装前一致。没有退出原版会话。
- 最终两个 Finder 启动入口均实测打开：定制版显示登录页，编辑器识别已安装且正在运行的定制版。

真实账户登录、真实会话背景、长期运行及签名相关电脑控制/通知/Keychain 功能没有验收。独立副本需要单独登录，ad-hoc 签名的兼容性限制仍然适用。全屏/有声已通过语义单测，本机未重复其原生窗口测试。

## 本地更新、退出状态和图标修复 — 2026-10-25

此节记录本次发布前的本机修复检查点。已快进到上游 `main` 的 `25f3b0c`（合入 macOS 支持与背景修复），保留本机 `26.1013.31256 / 20586 / arm64` 的精确锚点。用户保存的全屏、静音、视频和背景参数逐项比对未改变。

- 复现到定制版主进程退出后，Frameworks 内的 `browser_crashpad_handler` 仍存活，被错误当成正在运行。现在只排除该残留报告进程，主进程、renderer、GPU 等仍阻止覆盖安装。返回编辑器自动刷新状态，不覆盖草稿、不禁用首击，迟到响应不能覆盖写操作结果。
- 原生 UI 实际单击“应用到 Codex”后出现“已应用”提示。使用安装副本与独立测试 profile 复测：运行时按钮禁用，正常退出后剩余两个 crashpad 进程但 `running_pids=[]`；返回编辑器自动恢复可应用，未点击“刷新状态”。
- 原生测试另复现了编辑器窗口关闭后进程等待事件的问题。异步 WebKit 回调中的 `NSApplication.stop_()` 现在追加空的应用事件唤醒主循环；重新验证实际编辑器关闭后进程消失，再从 Finder 双击成功重开。
- `ui/mark.icns` 直接由 Linux 同源 `ui/mark.svg` 生成，含 16–1024 像素的 10 种表示；运行副本、Codex 启动器和编辑器均使用该图标。Finder 截图检查两个入口均显示六瓣 Logo。图标写入发生在签名前，未关闭完整性检查。
- Python 全套 90 项：87 通过，3 项 Linux GTK 专用跳过；Node 全套 69/69 通过。全部 6 种窗口模式/声音组合的真实主脚本补丁通过唯一匹配及 Node 语法检查。
- 修复后的 Cocoa/WKWebView 编辑器 smoke：8 个样本，视频播放、参数保存、背景解码、PNG 上传、无效 PNG 提示与关闭通过，进程正常结束。
- 背景隔离验证通过：左右像素分区、代码不透明表面、输入交互、两种面板布局、12 种滚动布局和无障碍状态。启动背景验证的普通工作区/全宽面板两条路径均通过，动画自然结束且背景 ready；揭幕首帧与 500ms 后背景区域差异均为 0 像素。
- 实际全屏/静音原生 smoke：42 个样本、39 个播放样本、1 个结束样本；1920×1080 视频播放 10.039 秒后释放遮罩，背景 ready、应用可交互，原生 fullscreen 标志与窗口边界通过。
- `codesign --verify --deep --strict` 通过，原版 ASAR、可执行文件及 Info.plist 的指纹与安装前一致。没有退出原版会话。

证据：`work/followup/` 下测试日志、`macos-editor-fixed/result.json`、`lifecycle.json`；背景测试 `work/background-smoke-8u4kr0uj/`，启动衔接 `work/background-smoke-z63g8g2u/`，全屏原生测试 `work/native-smoke-rg8a1xyb/`。失败的首次编辑器关闭测试没有完成结果，修复后的复测才计入通过。

本轮未进行真实账号登录、聊天及长期运行；背景检查使用真实构建 CSS 与模拟会话。ad-hoc 签名相关功能的既有限制不变。该检查点发生于代码提交和发布之前。

## 本机原 ChatGPT 入口模式 — 2026-10-25

用户明确要求点击原来的 ChatGPT 图标即可使用动画、背景及 Linux 同款优化。本节取代此前“本机只使用独立入口”的使用方式；构建仍精确限定 `26.1013.31256 / 20586 / arm64`。

- 新增 `tools/original_macos.py`：先验证并完整备份官方应用，再从备份构建候选；原应用正常退出后才原子替换 `/Applications/ChatGPT.app`。安装前检查原包、备份与候选内容摘要和签名，重复确认进程状态；中断恢复、签名失败回退、来源变化拒绝覆盖及并发锁均有回归覆盖。安装器不结束用户进程。
- 原入口模式保留原 bundle ID、native product directory、名称、图标与 URL 协议，不设置独立 `CODEX_HOME` 或 UI profile。重新签名仍为 ad-hoc，不继承供应商团队、Keychain 或 app-group 特权。真实账户目录未读取或改写。
- 两个平台共用动画、背景与媒体预处理实现：视频导入限制为 1080p/30fps 的 VP9/Opus，背景限制在 3840×2160 范围；模块/CSS 与背景预加载、并行应用初始化、背景解码就绪门控、230ms 淡入及超时/跳过/减少动态效果路径保留。
- 编辑器识别原入口模式：ChatGPT 运行时可以准备设置，点击“应用到 ChatGPT”后显示“已准备，等待 ChatGPT 退出”；不会将排队状态显示成“已应用”。实际 Cocoa/WKWebView 窗口完成一次点击应用，后台 worker 锁及等待状态已核对。
- Python 全套 114 项：111 通过，3 项 Linux GTK 专用跳过；Node 71/71 通过。`git diff --check` 通过。
- 第一份候选的隔离原生测试通过：42 个样本、39 个实际播放样本、1 个结束样本；1920×1080、10.039 秒、全屏、静音，背景 ready 后移除遮罩，窗口可交互。测试副本使用隔离身份和测试 profile，并移除协议注册，避免改变真实入口与回调。
- 实际编辑器点击应用重建后的最终候选另行复测通过：43 个样本、40 个播放样本、1 个结束样本，参数与原保存设置一致。最终候选的 21 项检查全部通过，实际内容摘要与 pending 记录匹配；与第一份候选摘要不同，未假定两包等同。最终原生证据为 `work/native-smoke-qoo83rif/`，核查记录为 `work/original-entry/final-candidate-checks.json`。
- 最终候选另通过 `background_smoke.py --startup`：普通工作区与全宽面板两种布局均自然播放结束，背景在揭幕前 ready；揭幕后首帧与 500ms 后背景区域均为 0 像素差异，关闭背景的对照有明确像素变化。证据 `work/background-smoke-phw1vh1j/`；工作区使用真实构建样式与模拟会话。

截至本节记录时，安装状态为 `queued / active=false / worker_running=true`；官方原路径内容仍与备份一致。后台等待器已带 `--relaunch` 启动，用户用 Cmd+Q 完全退出原 ChatGPT 后才进行替换并自动重新打开。**原路径替换后的真实账户冷启动仍待该次退出后验收，不能计为已通过。** 原入口保留不代表供应商签名身份保留；登录、电脑控制、通知、共享 Keychain 及长期运行尚未验证。编辑器“恢复原版 ChatGPT”可排队恢复已验证的官方备份，遇到来源更新则拒绝覆盖。

证据位于 `work/original-entry/`；原生测试记录为 `work/native-smoke-z7f8p_tn/`。该检查点发生于代码提交和发布之前。

## macOS DMG 发布前试构建与脱离开发目录验证 — 2026-10-25

此节的未发布试构建产物为 `dist/Codexflare-0.1.0-macOS-arm64-build20586.dmg`（不属于已发布的 Linux v0.1.0），约 105 MiB，仅适配 arm64 与 build 20586。自包含 Python 3.12.14 / PyObjC 12.2.2，不含官方应用、个人配置、备份或 FFmpeg。两张默认背景在构建时预缩至 3840×2156 / 2869×2160；默认 WebM 可直接播放。打包源码与素材许可均保留，另含当前检出的源码归档。

- 使用 PyInstaller 6.22.3 onedir 打包，带 Linux 同源 `mark.icns`、Applications 链接、中文安装说明及 `NSAppBundlesUsageDescription`。安装说明区分 ChatGPT 会话执行和独立 Codexflare 执行，要求在“隐私与安全性 → App 管理”中授权实际执行修改的 App；不要求完全磁盘访问或关闭全局安全保护。
- 冻结后的 worker 和管理命令经应用自身的 `--original` / `--manage` 路由执行；后台 worker 使用独立 PyInstaller 环境。首次打包版默认原入口模式，配置写入 `~/.local/share/codexflare`。相关 62 个 Python 回归测试通过。
- 初版功能测试虽通过，截图发现 header、预览和设置面板的 CSS 入场动画停留在透明状态。移除这三个核心区域的装饰性淡入，并为原生 smoke 增加 opacity、visibility、display、尺寸与 viewport 相交检查；实际窗口复测显示 Logo、背景预览、滑块和应用按钮完整可见。
- 最终 DMG 的 `hdiutil verify` 通过；只读挂载后复制到含空格的新路径并卸载镜像，`codesign --verify --deep --strict`、自检、两种 status 命令与无待办 worker 路由通过。PATH 限制为系统路径时，资源及预缩背景仍可用，不依赖开发目录的 Python 或 FFmpeg。
- 最终包原生 smoke 7 个样本通过：核心区域始终可见、1920×1080 视频实际播放、设置保存、背景解码及 PNG 上传、无效 PNG 提示、窗口关闭。截图人工核对通过。没有用打包版再次修改真实 ChatGPT。

该未发布试构建的 SHA-256：`b6b79c71666c3236fdb2bffa713907a6e4eea3facacde2761c73f5cd48b56024`。证据为 `work/dmg-build-final.log`、`work/dmg-final-verification/checks.json` 和 `work/dmg-final-verification/native-editor/`。首次验证脚本曾错误地把文字格式的 `manage status` 当作 JSON 解析，调整测试解析后通过；这不是应用故障。

未做 Developer ID 签名或 Apple 公证；首次下载后的 Gatekeeper 流程、其他 macOS 版本和真实账户未在本轮重新验收。源码版迁移须先用旧编辑器恢复官方应用，不能直接迁移旧状态文件。自定义视频导入和新图进一步缩图需用户另装 FFmpeg。

## v0.1.1 macOS 发布准备 — 2026-10-25

发布分支为 `release/macos-build20586`，基于 `25f3b0c`，仅适配 `26.1013.31256 / 20586 / arm64`。远程 `main` 已新增其他平台和构建支持，本次不合并或覆盖这些改动。保留已发布的 `v0.1.0` 标签与附件，macOS 定向版本不设为 Latest。

- 发布前全套 Python 119 项：116 通过、3 项 Linux GTK 专用跳过；Node 71/71 通过。相关日志位于忽略的 `work/release-python-tests.log`、`work/release-node-tests.log`。
- `build_dmg.py --release` 对未提交树的拒绝检查通过；正式包要求干净 HEAD，并在打包源码时再次确认提交和工作树未变化。源码归档仅含该提交的跟踪内容，归档所有者不使用构建机账户；构建信息记录 commit、dirty 状态、Python 和依赖版本。
- README、安装说明及许可文档已明确 App 管理的授权主体、源码原入口模式的迁移步骤和目标构建；清理了公开文档中的个人绝对路径。
- 上节试构建已完成脱离开发目录及原生编辑器验证。正式 v0.1.1 包在上述提交后重建，上传前另做只读挂载、签名、自检、源码对应和原生编辑器复核；最终摘要随 GitHub Release 的 `SHA256SUMS` 发布，避免将试构建摘要当成正式下载摘要。

本次不再修改真实 ChatGPT 或中断用户会话；真实账户、长期运行及 Apple 公证等未验收项仍以本文件和发布说明为准。
