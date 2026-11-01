from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from tools import animation, background, configure, editor, manage

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
                    '0000000b49444154789c63f80f040009fb03fdfb5e6b2b0000000049454e44ae426082')


class ConfigureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patches = ExitStack()
        self.addCleanup(patches.close)
        for name, value in {
            'ROOT': self.root, 'LOCAL': self.root / '.local',
            'SETTINGS': self.root / '.local/animation.json', 'MEDIA': self.root / '.local/media',
        }.items():
            patches.enter_context(patch.object(animation, name, value))
        patches.enter_context(patch.object(background, 'ROOT', self.root))
        (self.root / 'assets').mkdir()
        (self.root / 'assets/default.webm').write_bytes(b'video')
        for name in ('default1.png', 'default2.png'):
            (self.root / 'assets' / name).write_bytes(PNG)

    def test_preview_does_not_create_configuration_directory(self):
        result = configure.update_settings({'background': {'opacity': 0.12}})
        self.assertEqual(result['changes'], {'background.opacity': {'before': 0.18, 'after': 0.12}})
        self.assertFalse(result['saved'])
        self.assertFalse(result['applied'])
        self.assertFalse(animation.LOCAL.exists())

    def test_partial_save_preserves_other_settings_without_installing(self):
        animation.save_settings({'speed': 0.75, 'background': {'image': 'default2', 'scale': 90}})
        with patch.object(editor.manage, 'install') as install:
            result = configure.update_settings({'background': {'opacity': 0.1}}, save=True)
        install.assert_not_called()
        self.assertEqual(result['settings'], animation.load_settings())
        self.assertEqual(result['settings']['speed'], 0.75)
        self.assertEqual(result['settings']['background']['image'], 'default2')
        self.assertEqual(result['settings']['background']['scale'], 90)
        self.assertEqual(list(result['changes']), ['background.opacity'])
        self.assertTrue(result['saved'])
        self.assertFalse(result['applied'])

    def test_invalid_patch_and_missing_media_leave_settings_intact(self):
        animation.save_settings({'speed': 0.75})
        before = animation.SETTINGS.read_bytes()
        for change in ([], {'unknown': 1}, {'speed': True}, {'speed': float('nan')},
                       {'background': {'opacity': 1}}, {'video': 'a' * 64},
                       {'background': {'image': 'b' * 64}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                configure.update_settings(change, save=True)
            self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_corrupted_settings_are_not_replaced(self):
        animation.LOCAL.mkdir()
        animation.SETTINGS.write_bytes(b'{broken')
        with self.assertRaises(ValueError):
            configure.update_settings({'speed': 1}, save=True)
        self.assertEqual(animation.SETTINGS.read_bytes(), b'{broken')

    def test_editor_blocks_writes_and_another_editor_until_closed(self):
        with editor.EditorServer():
            self.assertFalse(configure.update_settings({'speed': 0.5})['saved'])
            with self.assertRaisesRegex(ValueError, '关闭编辑器'):
                configure.update_settings({'speed': 0.5}, save=True)
            with self.assertRaises(ValueError):
                editor.EditorServer()
            with self.assertRaises(ValueError):
                configure.import_media('background', self.root / 'assets/default1.png')
        self.assertTrue(configure.update_settings({'speed': 0.5}, save=True)['saved'])

    def test_bind_failure_releases_editor_lock(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            with self.assertRaises(OSError):
                editor.EditorServer(occupied.getsockname())
        self.assertTrue(configure.update_settings({}, save=True)['saved'])

    def test_import_background_does_not_select_or_apply_it(self):
        result = configure.import_media('background', self.root / 'assets/default1.png')
        self.assertNotIn('url', result['media'])
        self.assertEqual(background.image_path(result['media']['id'], animation.LOCAL).read_bytes(), PNG)
        self.assertFalse(result['selected'])
        self.assertFalse(result['applied'])
        self.assertFalse(animation.SETTINGS.exists())

    def test_import_rejects_invalid_empty_and_oversized_files(self):
        source = self.root / 'bad.png'
        for content in (b'', b'invalid'):
            source.write_bytes(content)
            with self.assertRaises(ValueError):
                configure.import_media('background', source)
        source.write_bytes(PNG)
        with patch.object(background, 'MAX_UPLOAD', 1), self.assertRaises(ValueError):
            configure.import_media('background', source)
        self.assertFalse((animation.LOCAL / 'backgrounds').exists())

    def run_cli(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = configure.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_errors_are_json_and_do_not_save(self):
        source = self.root / 'patch.json'
        for content in (b'{' , b'\xff', b'[]', b' ' * 4097):
            source.write_bytes(content)
            code, stdout, stderr = self.run_cli(['set', str(source), '--save'])
            self.assertEqual(code, 1)
            self.assertEqual(stdout, '')
            self.assertIn('error', json.loads(stderr))
        self.assertFalse(animation.SETTINGS.exists())

    def test_check_exit_code_and_manage_routing(self):
        with patch.object(editor, 'installation_status', return_value={'available': False}):
            code, stdout, stderr = self.run_cli(['check'])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(stdout)['installation']['available'])
        self.assertEqual(stderr, '')
        with patch('sys.argv', ['manage.py', 'configure', 'check']), \
                patch.object(configure, 'main', return_value=2) as command:
            self.assertEqual(manage.main(), 2)
        command.assert_called_once_with(['check'])


if __name__ == '__main__':
    unittest.main()
