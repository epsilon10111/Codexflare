import json
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from tools import patch_app, patch_macos, patch_windows as windows, windows_inject


CURRENT_MAIN = re.search(r'let fixture = `([\s\S]*?)\n`;',
    Path(__file__).with_name('test_window_mode_macos.cjs').read_text(encoding='utf-8'))[1].replace('\\`', '`')


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
        self.build = patch_macos.BUILDS[windows.CURRENT_VERSION]
        self.files = {
            'package.json': json.dumps(self.package).encode(),
            windows.CURRENT_MAIN: CURRENT_MAIN.encode(),
            'webview/index.html': b'<head></head><body></body>',
            **{f'webview/assets/{name}': b'preload fixture' for name in windows.CURRENT_STARTUP_PRELOADS},
            **{f'webview/assets/{name}': b'.fixture {}' for name in self.build['background_styles']},
        }
        selectors = (*self.build['background_classes'].values(),
                     '_background_106nk_2', '_fade_106nk_2', '_surface_106nk_2')
        self.files['webview/assets/' + self.build['background_styles'][0]] = '\n'.join(
            f'.{name} {{}}' for name in selectors).encode()
        self.files['webview/assets/' + windows.CURRENT_STARTUP_PRELOADS[4]] = b'._delayedBlossom_current_16 {}'
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

    def test_package_identity_is_required_without_a_version_allowlist(self):
        for version, build in ((windows.CURRENT_VERSION, windows.CURRENT_BUILD),
                               (windows.VERSION, windows.BUILD), ('99.1.1', '99999')):
            windows.require_supported(self.package | {'version': version, 'codexBuildNumber': build})
        for package in (self.package | {'name': 'other-app'},
                        self.package | {'codexWindowsPackageIdentity': 'other-package'},
                        self.package | {'version': ''}):
            with self.subTest(package=package), self.assertRaisesRegex(ValueError, '仅支持'):
                windows.require_supported(package)

    def test_injection_discovers_future_resource_names_and_loading_class(self):
        files = {re.sub(r'-[^/-]+\.(js|css)$', r'-future.\1', name): data
                 for name, data in self.files.items()}
        files['package.json'] = json.dumps(self.package | {'version': '99.1.1', 'codexBuildNumber': '99999'}).encode()
        (self.root / 'resources').mkdir()
        source = self.root / 'resources/app.asar'
        write_archive(source, files)
        before = source.read_bytes()
        with patch.object(windows_inject.animation, 'video_info', return_value={'duration': 4}), \
                patch.object(windows_inject.animation, 'video_path', return_value=self.root / 'video.webm'):
            script = windows_inject.prepare_script(self.root, self.settings, self.root)
        self.assertIn('_delayedBlossom_current_16', script)
        self.assertNotIn('_delayedBlossom_ovcb0_16', script)
        self.assertIn('_WorkspaceContent_azz1c_2', script)
        self.assertIn('URL.createObjectURL', script)
        self.assertEqual(source.read_bytes(), before)

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
                with self.assertRaisesRegex(ValueError, 'packaged loadURL'):
                    patch_app.patch_archive(self.source, self.target, platform='win32')
                self.assertFalse(self.target.exists())
                self.assertEqual(self.source.read_bytes(), before)

    def test_missing_resources_and_changed_background_selectors_fail_before_output(self):
        missing = 'webview/assets/' + windows.CURRENT_STARTUP_PRELOADS[0]
        cases = [({key: value for key, value in self.files.items() if key != missing}, '应用资源角色必须唯一'),
                 (self.files | {missing: b''}, '应用资源为空'),
                 (self.files | {'webview/assets/' + self.build['background_styles'][0]: b'.changed {}'},
                  '背景 CSS 角色必须唯一')]
        for files, message in cases:
            with self.subTest(message=message):
                write_archive(self.source, files)
                before = self.source.read_bytes()
                with self.assertRaisesRegex(ValueError, message):
                    patch_app.patch_archive(self.source, self.target, platform='win32')
                self.assertFalse(self.target.exists())
                self.assertEqual(self.source.read_bytes(), before)

    def test_unsupported_package_and_repatch_are_rejected(self):
        bad_package = self.package | {'codexWindowsPackageIdentity': 'other-package'}
        write_archive(self.source, self.files | {'package.json': json.dumps(bad_package).encode()})
        with self.assertRaisesRegex(ValueError, '仅支持'):
            patch_app.patch_archive(self.source, self.target, platform='win32')
        self.assertFalse(self.target.exists())
        write_archive(self.source, self.files)
        patch_app.patch_archive(self.source, self.target, platform='win32')
        second = self.root / 'second.asar'
        with self.assertRaisesRegex(ValueError, '已经包含'):
            patch_app.patch_archive(self.target, second, platform='win32')
        self.assertFalse(second.exists())
