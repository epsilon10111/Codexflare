#!/usr/bin/env python3
"""只为已验证的 Linux 构建生成 ASAR 副本，不写入系统安装目录。"""
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

if __package__:
    from . import animation as animation_config, background
    from .animation import load_settings, video_info, video_path
    from .paths import ROOT
else:
    import animation as animation_config
    import background
    from animation import load_settings, video_info, video_path
    from paths import ROOT

VERSION = '26.1002.52244'
MAIN = '.vite/build/main-B6ZOwXa3.js'
# shortcut: 此构建的动态启动依赖；升级时重新核对模块及其样式文件。
STARTUP_PRELOADS = (
    'rpc-8fbc4c09eb98.js',
    'app-main-11766fcd548a.js',
    'app-initial-929a3344d5d0.js',
    'app-primary-b8154b86c096.js',
    'app-initial-c43288484373.css',
    'app-primary-c7f956fe5bad.css',
)


class Asar:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as f:
            size, header_size, payload_size, string_size = struct.unpack('<4I', f.read(16))
            if size != 4 or header_size != payload_size + 4 or not 0 < string_size <= payload_size - 4:
                raise ValueError('无效的 ASAR 头')
            self.header = json.loads(f.read(string_size))
            self.base = 8 + header_size
            if self.base > self.path.stat().st_size:
                raise ValueError('ASAR 数据被截断')

    def entry(self, name):
        entry = self.header
        for part in name.split('/'):
            entry = entry['files'][part]
        return entry

    def read(self, name):
        entry = self.entry(name)
        if entry.get('unpacked') or 'link' in entry:
            raise ValueError(f'不是打包的普通文件: {name}')
        with self.path.open('rb') as f:
            f.seek(self.base + int(entry['offset']))
            data = f.read(entry['size'])
        if len(data) != entry['size']:
            raise ValueError(f'ASAR 文件被截断: {name}')
        return data

    def write_changes(self, destination, changes):
        destination = Path(destination)
        if destination.resolve() == self.path.resolve():
            raise ValueError('必须输出到另一个文件，不能覆盖来源')
        header = copy.deepcopy(self.header)
        offset = self.path.stat().st_size - self.base
        for name, data in changes.items():
            parts = name.split('/')
            if any(p in ('', '.', '..') for p in parts):
                raise ValueError('无效归档路径')
            parent = header
            for part in parts[:-1]:
                parent = parent.setdefault('files', {}).setdefault(part, {'files': {}})
            block_size = 4 * 1024 * 1024
            parent['files'][parts[-1]] = {
                'size': len(data), 'offset': str(offset),
                'integrity': {
                    'algorithm': 'SHA256', 'hash': hashlib.sha256(data).hexdigest(),
                    'blockSize': block_size,
                    'blocks': [hashlib.sha256(data[i:i + block_size]).hexdigest()
                               for i in range(0, len(data), block_size)],
                },
            }
            offset += len(data)
        raw = json.dumps(header, ensure_ascii=False, separators=(',', ':')).encode()
        padding = b'\0' * (-len(raw) % 4)
        payload_size = 4 + len(raw) + len(padding)
        with self.path.open('rb') as source, destination.open('xb') as target:
            target.write(struct.pack('<4I', 4, payload_size + 4, payload_size, len(raw)))
            target.write(raw + padding)
            source.seek(self.base)
            shutil.copyfileobj(source, target, 4 * 1024 * 1024)
            for data in changes.values():
                target.write(data)
        result = Asar(destination)
        for name, data in changes.items():
            if result.read(name) != data:
                raise ValueError(f'归档写入校验失败: {name}')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'补丁匹配不是唯一一次，停止: {old[:70]}')
    return text.replace(old, new, 1)


def patch_main(text, window_mode='restore', muted=True):
    if window_mode not in ('restore', 'fullscreen', 'centered'):
        raise ValueError('无效的启动窗口方式')
    if type(muted) is not bool:
        raise ValueError('静音开关必须是布尔值')
    # Owl 构建需要本地播放手势；固定事件只授权配置为有声的开屏主窗口。
    sound_bridge = ('' if muted else
        'n&&!r&&d&&R.webContents.once(`dom-ready`,async()=>{try{'
        'await R.webContents.executeJavaScript("document.dispatchEvent(new Event(`codex-boot-play`))",!0)'
        '}catch{}});')
    # shortcut: 精确匹配此版本的压缩代码，升级后必须重新审查补丁位置。
    text = replace_once(text,
        'await R.loadURL(t.o(f,{mcpAppSandboxLocalDevelopment:ee}))',
        'await R.loadURL((()=>{' + sound_bridge +
        'let e=new URL(t.o(f,{mcpAppSandboxLocalDevelopment:ee}));'
        'n&&!r&&d&&e.searchParams.set(`codexBootAnimation`,`1`);return e.toString()})())')
    # 仅普通启动提前显示，保留截图、预热等调用方的隐藏窗口语义。
    text = replace_once(text,
        'B.createPrimaryWindow({title:m.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n})',
        'B.createPrimaryWindow({title:m.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`?e:!0,'
        'initialRoute:t===`/`?void 0:t,opener:n,codexflareStartup:!e&&!B.getPrimaryWindow()})')
    if window_mode == 'restore':
        text = replace_once(text,
            'minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);',
            'minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);'
            'n&&!r&&d&&e.codexflareStartup&&w&&(R.codexflareWindowMode=`restore`);')
    else:
        text = replace_once(text,
            'minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);',
            'minWidth:A?.width,minHeight:A?.height,webPreferences:P},'
            f'codexflareMode=n&&!r&&d&&e.codexflareStartup?`{window_mode}`:null;'
            'if(codexflareMode){k=!1;'
            'if(codexflareMode===`centered`){'
            'let a=(Number.isFinite(L.x)&&Number.isFinite(L.y)?'
            'm.screen.getDisplayMatching(L):m.screen.getPrimaryDisplay()).workArea,'
            'w=Math.min(1100,a.width),h=Math.min(760,a.height);'
            'Object.assign(L,{width:w,height:h,x:a.x+Math.round((a.width-w)/2),'
            'y:a.y+Math.round((a.height-h)/2),'
            'minWidth:Math.min(L.minWidth??w,w),minHeight:Math.min(L.minHeight??h,h)})}}'
            'let R=new m.BrowserWindow(L);'
            'if(codexflareMode){R.codexflareWindowMode=codexflareMode;'
            'if(codexflareMode===`fullscreen`){let enter=()=>{R.isDestroyed()||R.setFullScreen(!0)};'
            'R.isVisible()?enter():R.once(`show`,enter)}}')
        if window_mode == 'centered':
            text = replace_once(text,
                'let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height)',
                'for(let n of e){let t=this.getPrimaryMinimumSize();'
                'if(n.codexflareWindowMode===`centered`){let a=m.screen.getDisplayMatching(n.getBounds()).workArea;'
                't={width:Math.min(t.width,a.width),height:Math.min(t.height,a.height)}}'
                'if(n.setMinimumSize(t.width,t.height)')
    # 登录界面的尺寸建议不能覆盖启动模式或已恢复的窗口边界。
    text = replace_once(text,
        'let i=Cje(t);if((0,W.default)(this.primaryWindowMode,t))',
        'let i=n.codexflareWindowMode?null:Cje(t);if((0,W.default)(this.primaryWindowMode,t))')
    return text


def patch_html(text, *, background=False):
    if 'codex-boot.js' in text or 'codex-background.css' in text:
        raise ValueError('启动页已经包含动画补丁')
    startup_links = ''
    for name in STARTUP_PRELOADS:
        if re.search(r'<link\b[^>]*\shref\s*=\s*[\"\']\./assets/' + re.escape(name) + r'[\"\']', text, re.I):
            continue
        # 仅预取 CSS；仍由原应用按原顺序挂载，避免改变层叠优先级。
        attributes = 'rel="preload" as="style"' if name.endswith('.css') else 'rel="modulepreload"'
        startup_links += f'<link {attributes} crossorigin href="./assets/{name}">\n'
    background_link = ('<link id="codex-background-preload" rel="preload" as="image" href="./assets/codex-background.png" fetchpriority="high">\n'
                       '<link rel="stylesheet" href="./assets/codex-background.css">\n') if background else ''
    return replace_once(text, '</head>',
        startup_links + background_link +
        '<link rel="stylesheet" href="./assets/codex-boot.css">\n'
        '<script src="./assets/codex-boot.js"></script>\n  </head>')


def patch_archive(source_asar, target_asar):
    source = Asar(source_asar)
    package = json.loads(source.read('package.json'))
    if package['name'] != 'openai-codex-electron' or package['version'] != VERSION:
        raise ValueError(f'仅支持 Codex {VERSION}；当前 {package.get("version")}')
    for name in STARTUP_PRELOADS:
        try:
            if not source.read(f'webview/assets/{name}'):
                raise ValueError(f'启动预载资源为空: {name}')
        except KeyError as error:
            raise ValueError(f'启动预载资源缺失: {name}') from error
    settings = load_settings()
    animation = settings | {'duration': video_info(settings['video'])['duration']}
    boot_script = replace_once((ROOT / 'src/boot.js').read_text(),
        '/* CODEX_BOOT_SETTINGS */ null',
        json.dumps(animation, separators=(',', ':'), allow_nan=False))
    background_settings = background.validate_settings(settings.get('background', {}))
    background_data, background_info = background.load_selected(background_settings, animation_config.LOCAL)
    if background_info is not None:
        background_data, background_info = background.prepare_image(background_data, background_info)
    changes = {
        MAIN: patch_main(source.read(MAIN).decode(), settings.get('windowMode', 'restore'),
                         settings.get('muted', True)).encode(),
        'webview/index.html': patch_html(source.read('webview/index.html').decode(),
                                       background=background_info is not None).encode(),
        'webview/assets/codex-boot.js': boot_script.encode(),
        'webview/assets/codex-boot.css': (ROOT / 'src/boot.css').read_bytes(),
        'webview/assets/codex-boot.webm': video_path(settings['video']).read_bytes(),
    }
    if background_info is not None:
        changes['webview/assets/codex-background.png'] = background_data
        variables = (f":root {{ --codex-bg-opacity: {background_settings['opacity']}; "
                     f"--codex-bg-position: {background_settings['position']}%; "
                     f"--codex-bg-scale: {background_settings['scale']}%; }}\n")
        changes['webview/assets/codex-background.css'] = variables.encode() + (ROOT / 'src/background.css').read_bytes()
    source.write_changes(target_asar, changes)
    with Path(source_asar).open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'version': VERSION, 'source_sha256': digest, 'animation': animation, 'background': background_info}
