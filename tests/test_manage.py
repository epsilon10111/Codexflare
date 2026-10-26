import contextlib
import io
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import manage


class ManageCommandTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'win32', 'Windows windowless launcher')
    def test_pythonw_launch_error_is_visible(self):
        import ctypes
        with patch.object(sys, 'argv', ['manage.py', 'launch']), \
                patch.object(sys, 'stderr', None), \
                patch.object(manage, 'platform_manager') as manager, \
                patch.object(ctypes.windll.user32, 'MessageBoxW') as message:
            manager.return_value.launch.side_effect = RuntimeError('请正常退出原版')
            with self.assertRaises(SystemExit) as error:
                manage.main()
            self.assertEqual(error.exception.code, 1)
            message.assert_called_once_with(None, '请正常退出原版', 'Codexflare', 0x10)


@unittest.skipIf(sys.platform == 'win32', 'Linux desktop entries and POSIX permissions')
class ManageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'system'
        (self.source / 'resources').mkdir(parents=True)
        (self.source / 'resources/app.asar').write_bytes(b'original app')
        (self.source / 'ChatGPT').write_bytes(b'binary')
        self.desktop = self.root / 'applications/chatgpt.desktop'
        self.desktop.parent.mkdir()
        self.system_desktop = self.root / 'system.desktop'
        self.system_desktop.write_text('[Desktop Entry]\nName=ChatGPT\nExec=chatgpt %U\nIcon=chatgpt\n')
        self.local = self.root / '.local'
        values = {'SOURCE': self.source, 'SYSTEM_DESKTOP': self.system_desktop,
                  'DESKTOP': self.desktop, 'LOCAL': self.local,
                  'STATE': self.local / 'install.json', 'BACKUP': self.local / 'chatgpt.desktop.original',
                  'RUNTIME': self.local / 'runtime'}
        self.patches = contextlib.ExitStack()
        self.addCleanup(self.patches.close)
        for name, value in values.items():
            self.patches.enter_context(patch.object(manage, name, value))
        self.fingerprint = {'version': manage.VERSION, 'binary': [1], 'asar': [2]}
        self.patches.enter_context(patch.object(manage, 'fingerprint', side_effect=lambda: dict(self.fingerprint)))
        self.patches.enter_context(patch.object(manage, 'running_pids', return_value=[]))
        self.patches.enter_context(patch.object(manage.subprocess, 'run', side_effect=self.copy_runtime))
        self.patches.enter_context(patch.object(manage, 'patch_archive', side_effect=self.patch_archive))
        self.patches.enter_context(contextlib.redirect_stdout(io.StringIO()))

    def copy_runtime(self, command, check):
        self.assertEqual(command[:3], ['cp', '-a', '--reflink=auto'])
        self.assertTrue(check)
        shutil.copytree(self.source, command[-1], dirs_exist_ok=True)

    def patch_archive(self, source, destination):
        self.assertEqual(source, self.source / 'resources/app.asar')
        destination.write_bytes(b'patched app')
        return {'version': manage.VERSION, 'source_sha256': manage.digest(source.read_bytes())}

    def test_repeat_install_preserves_original_and_restore_mode(self):
        original = b'[Desktop Entry]\nExec=custom-codex %U\n'
        self.desktop.write_bytes(original)
        self.desktop.chmod(0o640)
        manage.install()
        manage.install()
        self.assertEqual(manage.BACKUP.read_bytes(), original)
        self.assertEqual((manage.RUNTIME / 'resources/app.asar').read_bytes(), b'patched app')
        self.assertEqual((self.source / 'resources/app.asar').read_bytes(), b'original app')
        manage.uninstall()
        self.assertEqual(self.desktop.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.desktop.stat().st_mode), 0o640)
        self.assertTrue(manage.RUNTIME.exists())

    def test_uninstall_removes_only_our_new_entry(self):
        manage.install()
        manage.uninstall()
        self.assertFalse(self.desktop.exists())
        self.assertFalse(manage.read_state()['active'])

    def test_desktop_uses_persistent_launcher_with_uninstall_fallback(self):
        manager = self.root / 'installed/tools/manage.py'
        manager.parent.mkdir(parents=True)
        manager.touch()
        with patch.object(manage, '__file__', str(manager)):
            manage.install()
        launcher = self.local / 'launch.py'
        self.assertTrue(launcher.is_file())
        self.assertIn(f'{manage.desktop_quote(launcher)} %U', self.desktop.read_text())
        arguments = ['codex://threads/123', 'argument with spaces', '--example']
        for installed in (True, False):
            if not installed:
                manager.unlink()
            with self.subTest(installed=installed), patch.object(manage.os, 'execv') as execute, \
                    patch.object(sys, 'argv', [str(launcher), *arguments]):
                exec(compile(launcher.read_bytes(), str(launcher), 'exec'), {})
                command = [sys.executable, str(manager.resolve()), 'launch'] if installed else [str(manage.SYSTEM_LAUNCHER)]
                execute.assert_called_once_with(command[0], [*command, *arguments])
        manage.uninstall()
        self.assertTrue(launcher.is_file())
        self.assertFalse(self.desktop.exists())

    def test_user_modification_is_never_overwritten(self):
        manage.install()
        self.desktop.write_text('user edited')
        with self.assertRaisesRegex(ValueError, '拒绝'):
            manage.uninstall()
        with self.assertRaisesRegex(ValueError, '拒绝'):
            manage.install()
        self.assertEqual(self.desktop.read_text(), 'user edited')

    def test_stale_source_falls_back_and_arguments_survive(self):
        manage.install()
        with patch.object(manage.os, 'execv') as execute:
            manage.launch(['codex://threads/123', '--example'])
            execute.assert_called_once_with(str(manage.RUNTIME / 'ChatGPT'),
                                            [str(manage.RUNTIME / 'ChatGPT'), 'codex://threads/123', '--example'])
        self.fingerprint['asar'] = [3]
        with patch.object(manage.os, 'execv') as execute, contextlib.redirect_stderr(io.StringIO()) as warnings:
            manage.launch(['codex://threads/123'])
            execute.assert_called_once_with(str(manage.SYSTEM_LAUNCHER),
                                            [str(manage.SYSTEM_LAUNCHER), 'codex://threads/123'])
            self.assertIn('已更新', warnings.getvalue())

    def test_missing_patched_archive_falls_back(self):
        manage.install()
        (manage.RUNTIME / 'resources/app.asar').unlink()
        with patch.object(manage.os, 'execv') as execute, contextlib.redirect_stderr(io.StringIO()):
            manage.launch([])
            execute.assert_called_once_with(str(manage.SYSTEM_LAUNCHER), [str(manage.SYSTEM_LAUNCHER)])

    def test_running_runtime_and_unsupported_version_refuse_install(self):
        with patch.object(manage, 'running_pids', return_value=[123]):
            with self.assertRaisesRegex(ValueError, '仍在运行'):
                manage.install()
        self.fingerprint['version'] = 'future'
        with self.assertRaisesRegex(ValueError, '仅支持'):
            manage.install()
        self.assertFalse(manage.RUNTIME.exists())

    def test_source_change_during_copy_never_enables_override(self):
        def changing_copy(command, check):
            self.copy_runtime(command, check)
            self.fingerprint['asar'] = [99]
        with patch.object(manage.subprocess, 'run', side_effect=changing_copy):
            with self.assertRaisesRegex(ValueError, '发生变化'):
                manage.install()
        self.assertFalse(self.desktop.exists())

    def test_desktop_quoting_escapes_both_layers(self):
        self.assertEqual(manage.desktop_quote('/a path/python'), '"/a path/python"')
        self.assertEqual(manage.desktop_quote('/a%/x'), '"/a%%/x"')
        self.assertEqual(manage.desktop_quote('$`"\\'), '"\\\\$\\\\`\\\\"\\\\\\\\"')
        with self.assertRaises(ValueError):
            manage.desktop_quote('bad\npath')

    def test_desktop_symlink_refused(self):
        self.desktop.symlink_to(self.system_desktop)
        with self.assertRaisesRegex(ValueError, '符号链接'):
            manage.install()


if __name__ == '__main__':
    unittest.main()
