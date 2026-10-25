import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import patch_app
from patch_app import Asar, patch_archive, patch_html, patch_main, replace_once


def make_archive(path):
    files = {'a.txt': {'size': 3, 'offset': '0'},
             'native.node': {'size': 42, 'unpacked': True}}
    raw = json.dumps({'files': files}).encode()
    padding = b'\0' * (-len(raw) % 4)
    size = 4 + len(raw) + len(padding)
    path.write_bytes(struct.pack('<4I', 4, size + 4, size, len(raw)) + raw + padding + b'abc')


def png_chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def make_png(width=1, height=1, depth=8, color=6):
    return (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, color, 0, 0, 0))
            + png_chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff\xff')) + png_chunk(b'IEND', b''))


class PatchTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / 'src').mkdir()
        (self.root / '.local').mkdir()
        (self.root / 'assets').mkdir()
        for name in ('default1.png', 'default2.png'):
            (self.root / 'assets' / name).write_bytes(make_png())
        for name in ('boot.js', 'boot.css'):
            (self.root / 'src' / name).write_bytes((patch_app.ROOT / 'src' / name).read_bytes())
        (self.root / 'src/background.css').write_bytes(b'body { background-image: url("./codex-background.png"); }')
        self.enterContext(patch.object(patch_app, 'ROOT', self.root))
        self.enterContext(patch.object(patch_app.animation_config, 'LOCAL', self.root / '.local'))
        self.enterContext(patch.object(patch_app.background, 'ROOT', self.root))

    def prepare_background_archive(self, missing_asset=None):
        seed, original, target = (self.root / name for name in ('seed.asar', 'source.asar', 'target.asar'))
        make_archive(seed)
        Asar(seed).write_changes(original, {
            'package.json': json.dumps({'name': 'openai-codex-electron', 'version': patch_app.VERSION}).encode(),
            patch_app.MAIN: b'main placeholder', 'webview/index.html': b'<head></head><body></body>',
            **{f'webview/assets/{name}': b'preload fixture' for name in patch_app.STARTUP_PRELOADS
               if name != missing_asset},
        })
        video = self.root / 'video.webm'
        video.write_bytes(b'video fixture')
        self.enterContext(patch.object(patch_app, 'load_settings', return_value={'video': 'default'}))
        self.enterContext(patch.object(patch_app, 'video_info', return_value={'duration': 4}))
        self.enterContext(patch.object(patch_app, 'video_path', return_value=video))
        self.enterContext(patch.object(patch_app, 'patch_main', return_value='patched main'))
        return original, target

    def test_roundtrip_preserves_source_and_unmodified_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            original, patched = Path(folder) / 'source.asar', Path(folder) / 'patched.asar'
            make_archive(original)
            before = original.read_bytes()
            source = Asar(original)
            changes = {'a.txt': b'replacement', 'webview/assets/boot.webm': b'new video'}
            source.write_changes(patched, changes)
            result = Asar(patched)
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual(result.entry('native.node'), source.entry('native.node'))
            for name, data in changes.items():
                self.assertEqual(result.read(name), data)
                self.assertEqual(result.entry(name)['integrity']['hash'], hashlib.sha256(data).hexdigest())
            with self.assertRaises(ValueError):
                source.write_changes(original, changes)
            with self.assertRaises(FileExistsError):
                source.write_changes(patched, changes)

    def test_mismatch_and_double_patch_fail_closed(self):
        for content in ['', 'marker marker']:
            with self.assertRaises(ValueError):
                replace_once(content, 'marker', 'new')
        with self.assertRaises(ValueError):
            patch_main('unexpected app build')
        patched = patch_html('<head></head><body></body>')
        self.assertIn('src="./assets/codex-boot.js"', patched)
        self.assertNotIn('codex-background.css', patched)
        self.assertNotIn('unsafe-inline', patched)
        with self.assertRaises(ValueError):
            patch_html(patched)

    def test_main_starts_animation_without_overriding_window_geometry(self):
        geometry = ('minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);'
                    'k&&R.once(`ready-to-show`,()=>{R.isDestroyed()||R.maximize()});'
                    'let i=Cje(t);if((0,W.default)(this.primaryWindowMode,t)){};')
        original = (geometry + 'await R.loadURL(t.o(f,{mcpAppSandboxLocalDevelopment:ee}));'
                    'B.createPrimaryWindow({title:m.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n})')
        result = patch_main(original)
        self.assertTrue(result.startswith(geometry.split(';', 1)[0] + ';'))
        self.assertIn('k&&R.once(`ready-to-show`,()=>{R.isDestroyed()||R.maximize()});', result)
        self.assertIn('e.codexflareStartup&&w&&(R.codexflareWindowMode=`restore`)', result)
        self.assertNotIn('setFullScreen', result)
        self.assertNotIn('fullscreen:', result)
        self.assertNotIn('autoplayPolicy', result)
        self.assertNotIn('codex-boot-play', result)
        self.assertIn('n&&!r&&d&&e.searchParams.set(`codexBootAnimation`,`1`)', result)
        self.assertIn('show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`?e:!0', result)
        with self.assertRaises(ValueError):
            patch_main(result)

    def test_html_preloads_startup_dependencies_without_executing_or_applying_them(self):
        csp = '<meta http-equiv="Content-Security-Policy" content="script-src self; style-src self">'
        script = '<script type="module" src="./assets/entry.js"></script>'
        existing_module, existing_style = patch_app.STARTUP_PRELOADS[0], patch_app.STARTUP_PRELOADS[-1]
        existing_links = (f'<link rel="modulepreload" href="./assets/{existing_module}">'
                          f"<link href='./assets/{existing_style}' rel='stylesheet'>")
        original = f'<head>{csp}{script}{existing_links}</head><body></body>'
        result = patch_html(original)
        self.assertIn(csp + script + existing_links, result)
        self.assertEqual(result.count('<script'), 2)
        for name in patch_app.STARTUP_PRELOADS:
            self.assertEqual(result.count(f'./assets/{name}'), 1)
            if name in (existing_module, existing_style):
                continue
            attributes = 'rel="preload" as="style"' if name.endswith('.css') else 'rel="modulepreload"'
            self.assertIn(f'<link {attributes} crossorigin href="./assets/{name}">', result)

    def test_missing_startup_dependency_fails_before_writing_archive(self):
        missing = patch_app.STARTUP_PRELOADS[-1]
        original, target = self.prepare_background_archive(missing_asset=missing)
        before = original.read_bytes()
        with self.assertRaisesRegex(ValueError, '启动预载资源缺失'):
            patch_archive(original, target)
        self.assertFalse(target.exists())
        self.assertEqual(original.read_bytes(), before)

    def test_startup_window_modes(self):
        result = subprocess.run(['node', '--test', str(Path(__file__).with_name('test_window_mode.cjs'))],
                                capture_output=True, text=True, env={**os.environ, 'PYTHON': sys.executable})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with self.assertRaises(ValueError):
            patch_main('unexpected app build', 'invalid')
        for muted in (None, 0, 1, 'false', [], {}):
            with self.subTest(muted=muted), self.assertRaisesRegex(ValueError, '静音'):
                patch_main('unexpected app build', muted=muted)

    def test_invalid_header(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.asar'
            path.write_bytes(struct.pack('<4I', 5, 10, 6, 2) + b'{}')
            with self.assertRaises(ValueError):
                Asar(path)

    def test_archive_embeds_selected_video_and_validated_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed, original, target = root / 'seed.asar', root / 'source.asar', root / 'target.asar'
            video = root / 'custom.webm'
            video.write_bytes(b'selected video')
            make_archive(seed)
            Asar(seed).write_changes(original, {
                'package.json': json.dumps({'name': 'openai-codex-electron', 'version': patch_app.VERSION}).encode(),
                patch_app.MAIN: b'main placeholder', 'webview/index.html': b'<head></head><body></body>',
                **{f'webview/assets/{name}': b'preload fixture' for name in patch_app.STARTUP_PRELOADS},
            })
            settings = {'video': 'a' * 64, 'speed': 0.5, 'brightness': 1.25,
                        'contrast': 0.75, 'saturation': 0, 'fit': 'contain', 'windowMode': 'centered',
                        'muted': False, 'background': {'enabled': False}}
            with patch.object(patch_app, 'load_settings', return_value=settings), \
                 patch.object(patch_app, 'video_info', return_value={'duration': 12.25}) as info, \
                 patch.object(patch_app, 'video_path', return_value=video) as path, \
                 patch.object(patch_app, 'patch_main', return_value='patched main') as main:
                metadata = patch_archive(original, target)
            main.assert_called_once_with('main placeholder', 'centered', False)
            info.assert_called_once_with(settings['video'])
            path.assert_called_once_with(settings['video'])
            archive = Asar(target)
            self.assertEqual(archive.read('webview/assets/codex-boot.webm'), b'selected video')
            script = archive.read('webview/assets/codex-boot.js').decode()
            self.assertNotIn('CODEX_BOOT_SETTINGS', script)
            embedded = script.split('const settings = ', 1)[1].split(';', 1)[0]
            self.assertEqual(json.loads(embedded), settings | {'duration': 12.25})
            self.assertEqual(metadata['animation'], settings | {'duration': 12.25})
            self.assertEqual(metadata['source_sha256'], hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertIsNone(metadata['background'])
            self.assertNotIn(b'codex-background', archive.read('webview/index.html'))
            with self.assertRaises(KeyError):
                archive.read('webview/assets/codex-background.png')

    def test_archive_embeds_default_background_without_changing_source(self):
        original, target = self.prepare_background_archive()
        before = original.read_bytes()
        png = make_png()
        (self.root / '.local/background.png').write_bytes(b'unselected legacy')
        metadata = patch_archive(original, target)
        archive = Asar(target)
        self.assertEqual(archive.read('webview/assets/codex-background.png'), png)
        css = archive.read('webview/assets/codex-background.css')
        self.assertTrue(css.endswith((self.root / 'src/background.css').read_bytes()))
        self.assertIn(b'--codex-bg-opacity: 0.18', css)
        self.assertIn(b'--codex-bg-position: 80%', css)
        self.assertIn(b'--codex-bg-scale: 70%', css)
        self.assertIn(b'href="./assets/codex-background.css"', archive.read('webview/index.html'))
        self.assertIn(b'id="codex-background-preload" rel="preload" as="image"', archive.read('webview/index.html'))
        self.assertIn(b'fetchpriority="high"', archive.read('webview/index.html'))
        self.assertEqual(metadata['background'], {'width': 1, 'height': 1, 'size': len(png),
                                                  'sha256': hashlib.sha256(png).hexdigest()})
        self.assertEqual(original.read_bytes(), before)

    def test_archive_preserves_explicit_legacy_background(self):
        original, target = self.prepare_background_archive()
        png = make_png()
        (self.root / 'assets/default1.png').write_bytes(b'unselected default')
        (self.root / '.local/background.png').write_bytes(png)
        with patch.object(patch_app, 'load_settings', return_value={
            'video': 'default', 'background': {'image': 'legacy'},
        }):
            patch_archive(original, target)
        self.assertEqual(Asar(target).read('webview/assets/codex-background.png'), png)

    def test_archive_reads_user_data_outside_code_directory(self):
        original, target = self.prepare_background_archive()
        local = self.root / 'user-data'
        local.mkdir()
        png = make_png()
        (local / 'background.png').write_bytes(png)
        with patch.object(patch_app.animation_config, 'LOCAL', local), \
                patch.object(patch_app, 'load_settings', return_value={
                    'video': 'default', 'background': {'image': 'legacy'},
                }):
            patch_archive(original, target)
        self.assertEqual(Asar(target).read('webview/assets/codex-background.png'), png)

    def test_archive_embeds_prepared_background_and_reports_its_metadata(self):
        original, target = self.prepare_background_archive()
        png = make_png()
        prepared = make_png(width=2)
        metadata = patch_app.background.validate_png(prepared)
        with patch.object(patch_app.background, 'prepare_image', return_value=(prepared, metadata)) as prepare:
            result = patch_archive(original, target)
        prepare.assert_called_once_with(png, patch_app.background.validate_png(png))
        self.assertEqual(Asar(target).read('webview/assets/codex-background.png'), prepared)
        self.assertEqual(result['background'], metadata)
        self.assertEqual((self.root / 'assets/default1.png').read_bytes(), png)
        target.unlink()
        with patch.object(patch_app.background, 'prepare_image', side_effect=ValueError('背景预处理失败')):
            with self.assertRaisesRegex(ValueError, '背景预处理失败'):
                patch_archive(original, target)
        self.assertFalse(target.exists())

    def test_archive_embeds_second_builtin_background_when_selected(self):
        original, target = self.prepare_background_archive()
        (self.root / 'assets/default1.png').write_bytes(b'unselected default')
        (self.root / '.local/background.png').write_bytes(b'unselected legacy')
        with patch.object(patch_app, 'load_settings', return_value={
            'video': 'default', 'background': {'image': 'default2'},
        }):
            patch_archive(original, target)
        self.assertEqual(Asar(target).read('webview/assets/codex-background.png'), make_png())

    def test_selected_image_and_disabled_background_control_archive(self):
        original, target = self.prepare_background_archive()
        png = make_png()
        image_id = hashlib.sha256(png).hexdigest()
        folder = self.root / '.local/backgrounds'
        folder.mkdir()
        (folder / f'{image_id}.png').write_bytes(png)
        # The legacy image is invalid; only the selected image should be opened.
        (self.root / '.local/background.png').write_bytes(b'broken legacy')
        settings = {'video': 'default', 'background': {
            'enabled': True, 'image': image_id, 'opacity': 0.3, 'position': 90, 'scale': 120,
        }}
        with patch.object(patch_app, 'load_settings', return_value=settings):
            patch_archive(original, target)
        archive = Asar(target)
        self.assertEqual(archive.read('webview/assets/codex-background.png'), png)
        css = archive.read('webview/assets/codex-background.css')
        for variable in (b'--codex-bg-opacity: 0.3', b'--codex-bg-position: 90%', b'--codex-bg-scale: 120%'):
            self.assertIn(variable, css)
        target.unlink()
        settings['background']['enabled'] = False
        with patch.object(patch_app, 'load_settings', return_value=settings):
            metadata = patch_archive(original, target)
        self.assertIsNone(metadata['background'])
        self.assertNotIn(b'codex-background', Asar(target).read('webview/index.html'))
        with self.assertRaises(KeyError):
            Asar(target).read('webview/assets/codex-background.png')

    def test_invalid_background_fails_before_writing_archive(self):
        original, target = self.prepare_background_archive()
        before = original.read_bytes()
        png = make_png()
        damaged = bytearray(png)
        damaged[45] ^= 1
        cases = [b'not a PNG', png[:32], png[:-1], bytes(damaged), make_png(width=0),
                 make_png(width=8193), make_png(height=8193), make_png(width=8192, height=8192),
                 make_png(depth=3), make_png(color=7), png + b'extra',
                 b'\0' * (40 * 1024 * 1024 + 1)]
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                (self.root / 'assets/default1.png').write_bytes(data)
                with self.assertRaises(ValueError):
                    patch_archive(original, target)
                self.assertEqual(original.read_bytes(), before)
                self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
