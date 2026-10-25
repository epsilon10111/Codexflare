from pathlib import Path
import shlex
import struct
import tempfile
import unittest
from unittest.mock import patch

from tools import manage_macos as mac


class MacIconTests(unittest.TestCase):
    def test_bundle_icon_replaces_vendor_asset_catalog_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / 'Codexflare.app'
            info = {'CFBundleIconFile': 'electron.icns', 'CFBundleIconName': 'Icon',
                    'CodexAppIconBaseName': 'icon-chatgpt'}
            mac.install_icon(bundle, info)
            icon = bundle / 'Contents/Resources' / info['CFBundleIconFile']
            data = icon.read_bytes()
            self.assertEqual(data, (mac.ROOT / 'ui/mark.icns').read_bytes())
            self.assertEqual(struct.unpack('>4sI', data[:8]), (b'icns', len(data)))
            self.assertNotIn('CFBundleIconName', info)
            self.assertNotIn('CodexAppIconBaseName', info)

    def test_launcher_declares_its_bundled_icon(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / 'Codexflare.app'
            mac.make_launcher(bundle)
            icon = bundle / 'Contents/Resources' / mac.bundle_info(bundle)['CFBundleIconFile']
            self.assertEqual(icon.read_bytes(), (mac.ROOT / 'ui/mark.icns').read_bytes())

    def test_frozen_launcher_uses_the_application_dispatcher(self):
        executable = '/Applications/Codexflare Editor.app/Contents/MacOS/Codexflare'
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(mac.sys, 'frozen', True, create=True), \
                patch.object(mac.sys, 'executable', executable):
            bundle = Path(directory) / 'Codexflare.app'
            mac.make_launcher(bundle)
            self.assertEqual((bundle / 'Contents/MacOS/launch').read_text(),
                             '#!/bin/sh\nexec ' + shlex.quote(executable) + ' --manage launch "$@"\n')


if __name__ == '__main__':
    unittest.main()
