import json
from pathlib import Path
import re
import tempfile
import unittest

from tools.patch_app import Asar, check_archive
from test_patch import make_archive, style_fixture


class CompatibilityTests(unittest.TestCase):
    def build(self, root, platform, *, broken=False):
        suffix = '_macos' if platform == 'darwin' else ''
        fixture = Path(__file__).with_name('test_window_mode'+suffix+'.cjs').read_text(encoding='utf-8')
        main = re.search(r'let fixture = `([\s\S]*?)\n`;', fixture)[1].replace('\\`', '`')
        if platform == 'win32':
            main += ';AnotherName.deepLinks.registerProtocolClient()'
        if broken:
            main = main.replace('mcpAppSandboxLocalDevelopment', 'changedLoadingContract')
        seed, archive = root/'seed.asar', root/'app.asar'
        make_archive(seed)
        assets = {f'webview/assets/{role}-future.{ext}': style_fixture() if ext == 'css' else b'asset'
                  for role, ext in (('rpc','js'), ('app-main','js'), ('app-initial','js'),
                                    ('app-primary','js'), ('app-initial','css'), ('app-primary','css'))}
        Asar(seed).write_changes(archive, assets | {
            'package.json': json.dumps({'name':'openai-codex-electron','version':'99.1.1',
                'codexBuildNumber':'99999','codexWindowsPackageIdentity':'OpenAI.Codex'}).encode(),
            '.vite/build/main-future.js': main.encode(),
            'webview/assets/app-shared-future.css': b'shared',
            'webview/index.html': b'<head></head><body></body>',
        })
        return archive

    def test_unknown_version_with_compatible_structure_passes_on_all_platforms(self):
        for platform in ('linux','darwin','win32'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as folder:
                archive = self.build(Path(folder), platform)
                before = archive.read_bytes()
                for mode in ('restore','centered','fullscreen'):
                    result = check_archive(archive, platform, {'windowMode':mode, 'muted':False})
                    self.assertEqual(result['version'], '99.1.1')
                    self.assertEqual(result['main'], '.vite/build/main-future.js')
                self.assertEqual(archive.read_bytes(), before)
                self.assertEqual(len(list(Path(folder).iterdir())), 2)

    def test_changed_structure_fails_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = self.build(Path(folder), 'darwin', broken=True)
            before = archive.read_bytes()
            with self.assertRaisesRegex(ValueError, 'packaged loadURL'):
                check_archive(archive, 'darwin')
            self.assertEqual(archive.read_bytes(), before)
