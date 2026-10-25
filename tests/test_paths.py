import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import paths


class PathTests(unittest.TestCase):
    def test_source_checkout_keeps_local_configuration(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'XDG_DATA_HOME': '/other/data'}):
            root = Path(folder)
            self.assertEqual(paths.local_dir(root), root / '.local')

    def test_packaged_data_uses_only_absolute_xdg_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.packaged').touch()
            for value in ('', 'relative/data'):
                with self.subTest(value=value), patch.dict(os.environ, {'XDG_DATA_HOME': value}):
                    self.assertEqual(paths.local_dir(root), Path.home() / '.local/share/codexflare')
            data = root / 'custom/data'
            with patch.dict(os.environ, {'XDG_DATA_HOME': str(data)}):
                self.assertEqual(paths.local_dir(root), data / 'codexflare')
                self.assertEqual(paths.local_dir(Path('/usr/share/codexflare')), data / 'codexflare')

    def test_packaged_modules_share_data_path_and_save_outside_code(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            root, data = folder / 'installed', folder / 'data'
            (root / 'tools').mkdir(parents=True)
            (root / '.packaged').touch()
            for name in ('paths.py', 'animation.py', 'background.py', 'manage.py', 'patch_app.py'):
                shutil.copyfile(paths.ROOT / 'tools' / name, root / 'tools' / name)
            (root / 'assets').mkdir()
            (root / 'assets/default.webm').touch()
            result = subprocess.run([sys.executable, '-c', '''
import json
from tools import animation, manage, patch_app
animation.save_settings({'background': {'enabled': False}})
print(json.dumps([str(animation.LOCAL), str(manage.LOCAL),
                  str(patch_app.animation_config.LOCAL), str(manage.DESKTOP)]))
'''], cwd=root, env=os.environ | {'XDG_DATA_HOME': str(data)},
                check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), [str(data / 'codexflare')] * 3 +
                             [str(data / 'applications/chatgpt.desktop')])
            self.assertTrue((data / 'codexflare/animation.json').is_file())
            self.assertFalse((root / '.local').exists())


if __name__ == '__main__':
    unittest.main()
