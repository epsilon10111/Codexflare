import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from patch_app import Asar, patch_html, patch_main, replace_once


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


if __name__ == '__main__':
    unittest.main()
