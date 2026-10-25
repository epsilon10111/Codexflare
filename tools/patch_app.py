#!/usr/bin/env python3
"""只为已验证的 Linux 构建生成 ASAR 副本，不写入系统安装目录。"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct

ROOT = Path(__file__).resolve().parents[1]
VERSION = '26.1002.52244'
MAIN = '.vite/build/main-B6ZOwXa3.js'


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


def patch_main(text):
    # shortcut: 精确匹配此版本的压缩代码，升级后必须重新审查补丁位置。
    # 此构建只设 fullscreen 标志不改变实际边界，首帧后须重新进入全屏。
    text = replace_once(text,
        'minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);',
        'minWidth:A?.width,minHeight:A?.height,webPreferences:P,'
        '...(n&&!r?{fullscreen:!0,backgroundColor:`#03060e`}:{})},'
        'R=new m.BrowserWindow(L);'
        'n&&!r&&(R.on(`show`,()=>{R.isDestroyed()||(R.setFullScreen(!1),R.setFullScreen(!0))}),'
        'd&&R.once(`ready-to-show`,()=>{R.isDestroyed()||(R.setFullScreen(!1),R.setFullScreen(!0))}));')
    text = replace_once(text,
        'k&&R.once(`ready-to-show`,()=>{R.isDestroyed()||R.maximize()})',
        'k&&!(n&&!r)&&R.once(`ready-to-show`,()=>{R.isDestroyed()||R.maximize()})')
    text = replace_once(text,
        'await R.loadURL(t.o(f,{mcpAppSandboxLocalDevelopment:ee}))',
        'await R.loadURL((()=>{let e=new URL(t.o(f,{mcpAppSandboxLocalDevelopment:ee}));'
        'n&&!r&&d&&e.searchParams.set(`codexBootAnimation`,`1`);return e.toString()})())')
    # 仅普通启动提前显示，保留截图、预热等调用方的隐藏窗口语义。
    text = replace_once(text,
        'B.createPrimaryWindow({title:m.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n})',
        'B.createPrimaryWindow({title:m.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`?e:!0,'
        'initialRoute:t===`/`?void 0:t,opener:n})')
    text = replace_once(text, 'let i=Cje(t);if((0,W.default)(this.primaryWindowMode,t))',
        'let i=null;if((0,W.default)(this.primaryWindowMode,t))')
    return text


def patch_html(text):
    if 'codex-boot.js' in text:
        raise ValueError('启动页已经包含动画补丁')
    return replace_once(text, '</head>',
        '<link rel="stylesheet" href="./assets/codex-boot.css">\n'
        '<script src="./assets/codex-boot.js"></script>\n  </head>')


def patch_archive(source_asar, target_asar):
    source = Asar(source_asar)
    package = json.loads(source.read('package.json'))
    if package['name'] != 'openai-codex-electron' or package['version'] != VERSION:
        raise ValueError(f'仅支持 Codex {VERSION}；当前 {package.get("version")}')
    changes = {
        MAIN: patch_main(source.read(MAIN).decode()).encode(),
        'webview/index.html': patch_html(source.read('webview/index.html').decode()).encode(),
        'webview/assets/codex-boot.js': (ROOT / 'src/boot.js').read_bytes(),
        'webview/assets/codex-boot.css': (ROOT / 'src/boot.css').read_bytes(),
        'webview/assets/codex-boot.webm': (ROOT / 'assets/boot.webm').read_bytes(),
    }
    source.write_changes(target_asar, changes)
    with Path(source_asar).open('rb') as f:
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'version': VERSION, 'source_sha256': digest}
