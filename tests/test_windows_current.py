import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tools import patch_app, patch_macos, patch_windows as windows


CURRENT_MAIN = (
    'await z.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}));'
    'V.createPrimaryWindow({title:O.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n});'
    'minWidth:A?.width,minHeight:A?.height,webPreferences:F},z=new O.BrowserWindow(R);'
    'let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height),!0){}};'
    'let i=A5e(t);if((0,q.default)(this.primaryWindowMode,t)){};'
    'We.deepLinks.registerProtocolClient();'
)


def write_archive(path, files):
    header, payload = {'files': {}}, bytearray()
    for name, data in files.items():
        parent = header
        *folders, leaf = name.split('/')
        for folder in folders:
            parent = parent['files'].setdefault(folder, {'files': {}})
        parent['files'][leaf] = {'size': len(data), 'offset': str(len(payload))}
        payload.extend(data)
    raw = json.dumps(header).encode()
    padding = b'\0' * (-len(raw) % 4)
    size = 4 + len(raw) + len(padding)
    path.write_bytes(struct.pack('<4I', 4, size + 4, size, len(raw)) + raw + padding + payload)


class CurrentWindowsPatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = {'name': 'openai-codex-electron', 'version': windows.CURRENT_VERSION,
                        'codexBuildNumber': windows.CURRENT_BUILD, 'codexWindowsPackageIdentity': 'OpenAI.Codex'}
        self.files = {
            'package.json': json.dumps(self.package).encode(),
            windows.CURRENT_MAIN: CURRENT_MAIN.encode(),
            'webview/index.html': b'<head></head><body></body>',
            **{f'webview/assets/{name}': b'preload fixture' for name in windows.CURRENT_STARTUP_PRELOADS},
            **{f'webview/assets/{name}': b'.fixture {}' for name in patch_macos.BACKGROUND_STYLES},
        }
        selectors = (*patch_macos.BACKGROUND_CLASSES.values(),
                     '_background_106nk_2', '_fade_106nk_2', '_surface_106nk_2')
        self.files['webview/assets/' + patch_macos.BACKGROUND_STYLES[0]] = '\n'.join(
            f'.{name} {{}}' for name in selectors).encode()
        self.source, self.target = self.root / 'source.asar', self.root / 'target.asar'
        video = self.root / 'video.webm'
        video.write_bytes(b'video fixture')
        self.enterContext(patch.object(patch_app, 'video_path', return_value=video))
        self.enterContext(patch.object(patch_app, 'video_info', return_value={'duration': 4}))
        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(b'\0\xff\xff\xff\xff')) + chunk(b'IEND', b''))
        self.enterContext(patch.object(patch_app.background, 'load_selected',
                                      return_value=(png, patch_app.background.validate_png(png))))
        self.settings = {'video': 'default', 'windowMode': 'restore', 'muted': True}
        self.enterContext(patch.object(patch_app, 'load_settings', side_effect=lambda: self.settings.copy()))

    def test_selects_only_exact_legacy_and_current_builds(self):
        current = windows.select_build(self.package)
        self.assertEqual(current.MAIN, windows.CURRENT_MAIN)
        self.assertIs(current.patch_main, patch_macos.patch_main)
        self.assertIs(current.patch_background_css, patch_macos.patch_background_css)
        legacy_package = self.package | {'version': windows.VERSION, 'codexBuildNumber': windows.BUILD}
        legacy = windows.select_build(legacy_package)
        self.assertEqual(legacy.MAIN, windows.MAIN)
        self.assertIs(legacy.patch_main, windows.patch_main)
        self.assertIsNone(legacy.patch_background_css)
        for package in (self.package | {'version': windows.VERSION},
                        legacy_package | {'version': windows.CURRENT_VERSION},
                        *(self.package | {key: 'future'} for key in self.package)):
            with self.subTest(package=package), self.assertRaisesRegex(ValueError, '仅支持'):
                windows.select_build(package)

    def test_current_archive_six_playback_modes_preserve_source(self):
        write_archive(self.source, self.files)
        before = self.source.read_bytes()
        for mode in ('restore', 'centered', 'fullscreen'):
            for muted in (True, False):
                with self.subTest(mode=mode, muted=muted):
                    self.settings.update(windowMode=mode, muted=muted)
                    target = self.root / f'{mode}-{muted}.asar'
                    result = patch_app.patch_archive(self.source, target, platform='win32')
                    archive = patch_app.Asar(target)
                    main = archive.read(windows.CURRENT_MAIN).decode()
                    self.assertEqual(result['version'], windows.CURRENT_VERSION)
                    self.assertIn('codexBootAnimation', main)
                    self.assertEqual('codex-boot-play' in main, not muted)
                    self.assertNotIn('We.deepLinks.registerProtocolClient()', main)
                    self.assertIn(f'`{mode}`', main)
                    html = archive.read('webview/index.html').decode()
                    for name in windows.CURRENT_STARTUP_PRELOADS:
                        self.assertIn(f'./assets/{name}', html)
                    css = archive.read('webview/assets/codex-background.css').decode()
                    self.assertIn('_WorkspaceContent_azz1c_2', css)
                    self.assertIn('_ComposerLayoutRoot_1q7o3_2', css)
                    self.assertIn('._background_106nk_2._fade_106nk_2.from-surface', css)
                    self.assertNotIn('_WorkspaceContent_yl8z4_2', css)
                    self.assertEqual(self.source.read_bytes(), before)

    def test_changed_or_duplicate_anchors_fail_before_output(self):
        anchor = 'await z.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}))'
        for main in (CURRENT_MAIN.replace(anchor, 'changedLoadURL()'), CURRENT_MAIN + anchor):
            with self.subTest(main=main):
                write_archive(self.source, self.files | {windows.CURRENT_MAIN: main.encode()})
                before = self.source.read_bytes()
                with self.assertRaisesRegex(ValueError, '匹配不是唯一'):
                    patch_app.patch_archive(self.source, self.target, platform='win32')
                self.assertFalse(self.target.exists())
                self.assertEqual(self.source.read_bytes(), before)

    def test_missing_resources_and_changed_background_selectors_fail_before_output(self):
        missing = 'webview/assets/' + windows.CURRENT_STARTUP_PRELOADS[0]
        cases = [({key: value for key, value in self.files.items() if key != missing}, '启动预载资源缺失'),
                 (self.files | {missing: b''}, '启动预载资源为空'),
                 (self.files | {'webview/assets/' + patch_macos.BACKGROUND_STYLES[0]: b'.changed {}'},
                  'Background selector missing')]
        for files, message in cases:
            with self.subTest(message=message):
                write_archive(self.source, files)
                before = self.source.read_bytes()
                with self.assertRaisesRegex(ValueError, message):
                    patch_app.patch_archive(self.source, self.target, platform='win32')
                self.assertFalse(self.target.exists())
                self.assertEqual(self.source.read_bytes(), before)

    def test_unsupported_package_and_repatch_are_rejected(self):
        bad_package = self.package | {'codexBuildNumber': windows.BUILD}
        write_archive(self.source, self.files | {'package.json': json.dumps(bad_package).encode()})
        with self.assertRaisesRegex(ValueError, '仅支持'):
            patch_app.patch_archive(self.source, self.target, platform='win32')
        self.assertFalse(self.target.exists())
        write_archive(self.source, self.files)
        patch_app.patch_archive(self.source, self.target, platform='win32')
        second = self.root / 'second.asar'
        with self.assertRaisesRegex(ValueError, '匹配不是唯一'):
            patch_app.patch_archive(self.target, second, platform='win32')
        self.assertFalse(second.exists())
