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
    from .build_layout import discover_layout
else:
    import animation as animation_config
    import background
    from animation import load_settings, video_info, video_path
    from paths import ROOT
    from build_layout import discover_layout

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
    if __package__:
        from .window_patch import patch_main as patch_window
    else:
        from window_patch import patch_main as patch_window
    return patch_window(text, window_mode, muted)


def patch_html(text, *, background=False, preloads=STARTUP_PRELOADS):
    if 'codex-boot.js' in text or 'codex-background.css' in text:
        raise ValueError('启动页已经包含动画补丁')
    startup_links = ''
    for name in preloads:
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


def patch_archive(source_asar, target_asar, *, platform='linux'):
    if platform == 'win32':
        if __package__:
            from . import patch_windows as build
        else:
            import patch_windows as build
        version, patcher = build.VERSION, build.patch_main
    elif platform == 'darwin':
        if __package__:
            from . import patch_macos as build
        else:
            import patch_macos as build
        version, patcher = build.VERSION, build.patch_main
    elif platform == 'linux':
        version, patcher = VERSION, patch_main
    else:
        raise ValueError(f'不支持的平台: {platform}')
    source = Asar(source_asar)
    package = json.loads(source.read('package.json'))
    if package['name'] != 'openai-codex-electron' or package['version'] != version:
        raise ValueError(f'仅支持 Codex {version} ({platform})；当前 {package.get("version")}')
    if platform == 'win32':
        build.require_supported(package)
    main, preloads = discover_layout(source)
    settings = load_settings()
    animation = settings | {'duration': video_info(settings['video'])['duration']}
    boot_script = replace_once((ROOT / 'src/boot.js').read_text(encoding='utf-8'),
        '/* CODEX_BOOT_SETTINGS */ null',
        json.dumps(animation, separators=(',', ':'), allow_nan=False))
    background_settings = background.validate_settings(settings.get('background', {}))
    background_data, background_info = background.load_selected(background_settings, animation_config.LOCAL)
    if background_info is not None:
        background_data, background_info = background.prepare_image(background_data, background_info)
    changes = {
        main: patcher(source.read(main).decode(), settings.get('windowMode', 'restore'),
                         settings.get('muted', True)).encode(),
        'webview/index.html': patch_html(source.read('webview/index.html').decode(),
                                       background=background_info is not None, preloads=preloads).encode(),
        'webview/assets/codex-boot.js': boot_script.encode(),
        'webview/assets/codex-boot.css': (ROOT / 'src/boot.css').read_bytes(),
        'webview/assets/codex-boot.webm': video_path(settings['video']).read_bytes(),
    }
    if background_info is not None:
        changes['webview/assets/codex-background.png'] = background_data
        variables = (f":root {{ --codex-bg-opacity: {background_settings['opacity']}; "
                     f"--codex-bg-position: {background_settings['position']}%; "
                     f"--codex-bg-scale: {background_settings['scale']}%; }}\n")
        style = (ROOT / 'src/background.css').read_text(encoding='utf-8')
        if platform == 'darwin':
            style = build.patch_background_css(style, source)
        changes['webview/assets/codex-background.css'] = (variables + style).encode()
    source.write_changes(target_asar, changes)
    with Path(source_asar).open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'version': version, 'source_sha256': digest, 'animation': animation, 'background': background_info}
