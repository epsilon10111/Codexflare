import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

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


class PatchTests(unittest.TestCase):
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
        self.assertNotIn('unsafe-inline', patched)
        with self.assertRaises(ValueError):
            patch_html(patched)

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
            })
            settings = {'video': 'a' * 64, 'speed': 0.5, 'brightness': 1.25,
                        'contrast': 0.75, 'saturation': 0, 'fit': 'contain'}
            with patch.object(patch_app, 'load_settings', return_value=settings), \
                 patch.object(patch_app, 'video_info', return_value={'duration': 12.25}) as info, \
                 patch.object(patch_app, 'video_path', return_value=video) as path, \
                 patch.object(patch_app, 'patch_main', return_value='patched main'):
                metadata = patch_archive(original, target)
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


if __name__ == '__main__':
    unittest.main()
