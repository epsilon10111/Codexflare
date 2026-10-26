import contextlib
import io
import json
import os
import shutil
from pathlib import Path
import struct
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import manage, manage_windows as windows, patch_app, patch_windows


def fixture_archive(path):
    package = {'name': 'openai-codex-electron', 'version': patch_windows.VERSION,
               'codexBuildNumber': patch_windows.BUILD, 'codexWindowsPackageIdentity': 'OpenAI.Codex'}
    data = json.dumps(package).encode()
    header = json.dumps({'files': {'package.json': {'offset': '0', 'size': len(data)}}}).encode()
    padding = b'\0' * (-len(header) % 4)
    size = 4 + len(header) + len(padding)
    path.write_bytes(struct.pack('<4I', 4, size + 4, size, len(header)) + header + padding + data)


class WindowsManagerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / 'official'
        (self.source / 'resources').mkdir(parents=True)
        fixture_archive(self.source / windows.ASAR)
        record = json.dumps([{'file': 'resources\\app.asar', 'alg': 'SHA256',
                              'value': windows.header_hash(self.source / windows.ASAR)}], separators=(',', ':')).encode()
        (self.source / windows.BINARY).write_bytes(b'PE fixture\0' + record + b'\0end')
        (self.source / 'Codex.exe').write_bytes(b'launcher')
        (self.source / 'chrome.dll').write_bytes(b'runtime')
        (self.source / 'owl-shell-runtime.json').write_text(json.dumps({'platform': 'win32', 'arch': 'x64'}))
        self.local = self.root / 'local'
        self.desktop = self.root / 'menu/Codex (Codexflare).lnk'
        self.enterContext(patch.multiple(windows, SOURCE=self.source, LOCAL=self.local,
            RUNTIME=self.local / 'runtime-windows', STATE=self.local / 'install-windows.json', DESKTOP=self.desktop))
        self.enterContext(patch.object(windows, 'running_pids', return_value=[]))
        self.enterContext(patch.object(windows, 'source_running_pids', return_value=[]))
        self.package_launch = self.enterContext(patch.object(windows.windows_package, 'launch_in_package', return_value=False))
        self.registered_package = self.enterContext(patch.object(windows.windows_package, 'registered_package', return_value={
            'full_name': 'OpenAI.Codex_fixture_x64__test', 'family_name': 'OpenAI.Codex_test', 'app_id': 'App'}))
        self.enterContext(patch.object(windows, 'find_source', return_value=self.source))
        self.enterContext(patch.object(windows, 'make_launcher', side_effect=lambda path: path.write_bytes(b'shortcut')))
        self.enterContext(patch.object(windows, 'patch_archive', side_effect=self.patch_archive))
        self.settings = windows.animation.validate_settings({'brightness': 1.25})
        self.enterContext(patch.object(windows.animation, 'load_settings', return_value=self.settings))
        self.inject = SimpleNamespace(prepare_script=Mock(return_value='validated script'), run=Mock())
        self.enterContext(patch.dict(sys.modules, {'tools.windows_inject': self.inject, 'windows_inject': self.inject}))
        self.enterContext(patch.object(sys.modules['tools'], 'windows_inject', self.inject, create=True))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def patch_archive(self, source, destination, *, platform):
        self.assertEqual(platform, 'win32')
        patch_app.Asar(source).write_changes(destination, {'patch.txt': b'patched'})
        return {'version': patch_windows.VERSION}

    def test_reinstall_uninstall_preserves_source_and_data(self):
        original = {str(path.relative_to(self.source)): path.read_bytes()
                    for path in self.source.rglob('*') if path.is_file()}
        with patch.object(windows, 'build_runtime', side_effect=AssertionError('Must not build a copy')), \
                patch.object(windows.shutil, 'copytree', side_effect=AssertionError('Must not copy the app')):
            windows.install()
            windows.install()
        self.assertIsNone(windows.runtime_problem(windows.read_state()))
        self.assertEqual(windows.read_state()['mode'], 'original')
        self.assertEqual(windows.read_state()['settings'], self.settings)
        self.inject.prepare_script.assert_called_with(self.source, self.settings, self.local)
        windows.uninstall()
        windows.uninstall()
        self.assertFalse(self.desktop.exists())
        self.assertFalse(windows.read_state()['active'])
        for name in ('runtime-windows', 'profile-windows', 'codex-home-windows'):
            self.assertFalse((self.local / name).exists())
        self.assertEqual({str(path.relative_to(self.source)): path.read_bytes()
                          for path in self.source.rglob('*') if path.is_file()}, original)

    def test_foreign_or_edited_shortcut_is_preserved(self):
        self.desktop.parent.mkdir()
        self.desktop.write_bytes(b'foreign')
        with self.assertRaisesRegex(ValueError, '拒绝'):
            windows.install()
        self.desktop.unlink()
        windows.install()
        self.desktop.write_bytes(b'edited')
        for action in (windows.install, windows.uninstall):
            with self.assertRaisesRegex(ValueError, '拒绝'):
                action()
        self.assertEqual(self.desktop.read_bytes(), b'edited')

    def test_running_and_unsupported_sources_refused(self):
        with patch.object(windows, 'running_pids', return_value=[123]):
            with self.assertRaisesRegex(ValueError, '仍在运行'):
                windows.install()
        (self.source / 'owl-shell-runtime.json').write_text('{"platform":"win32","arch":"arm64"}')
        with self.assertRaisesRegex(ValueError, 'x64'):
            windows.install()
        self.assertFalse(self.desktop.exists())

    def test_source_change_during_prepare_never_enables_launcher(self):
        before = windows.fingerprint()
        with patch.object(windows, 'fingerprint', side_effect=[before, before | {'build': 'future'}]):
            with self.assertRaisesRegex(ValueError, '发生变化'):
                windows.install()
        self.assertFalse(self.desktop.exists())

    def test_invalid_assets_never_enable_launcher(self):
        self.inject.prepare_script.side_effect = ValueError('invalid video')
        with self.assertRaisesRegex(ValueError, 'invalid video'):
            windows.install()
        self.assertFalse(self.desktop.exists())
        self.assertIsNone(windows.read_state())

    def test_unregistered_source_never_enables_launcher(self):
        self.registered_package.side_effect = ValueError('来源不是已注册的标准版 Windows 包')
        with self.assertRaisesRegex(ValueError, '已注册'):
            windows.install()
        self.registered_package.assert_called_once_with(self.source)
        self.assertFalse(self.desktop.exists())
        self.assertIsNone(windows.read_state())
        self.assertFalse(self.local.exists())
        self.inject.prepare_script.assert_not_called()

    def test_first_install_commit_failure_leaves_no_active_install(self):
        original = windows.atomic_write
        for target in (self.desktop, windows.STATE):
            with self.subTest(target=target):
                def fail(path, data):
                    if path == target:
                        raise PermissionError('commit failed')
                    return original(path, data)
                with patch.object(windows, 'atomic_write', side_effect=fail):
                    with self.assertRaisesRegex(PermissionError, 'commit failed'):
                        windows.install()
                self.assertIsNone(windows.read_state())
                self.assertFalse(self.desktop.exists())
                self.assertFalse(windows.RUNTIME.exists())

    def test_reinstall_commit_failure_restores_shortcut_and_state(self):
        windows.install()
        state = windows.STATE.read_bytes()
        shortcut = self.desktop.read_bytes()
        original = windows.atomic_write
        for target in (self.desktop, windows.STATE):
            with self.subTest(target=target):
                def fail(path, data):
                    if path == target:
                        raise PermissionError('commit failed')
                    return original(path, data)
                with patch.object(windows, 'atomic_write', side_effect=fail), \
                        patch.object(windows, 'make_launcher', side_effect=lambda path: path.write_bytes(b'new shortcut')):
                    with self.assertRaisesRegex(PermissionError, 'commit failed'):
                        windows.install()
                self.assertEqual(windows.STATE.read_bytes(), state)
                self.assertEqual(self.desktop.read_bytes(), shortcut)
                self.assertIsNone(windows.runtime_problem(windows.read_state()))

    def test_changed_source_is_rejected_and_launch_falls_back(self):
        for relative in windows.RUNTIME_FILES:
            with self.subTest(file=relative):
                windows.install()
                path = self.source / relative
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                self.assertIsNotNone(windows.runtime_problem(windows.read_state()))
                with patch.object(windows.subprocess, 'Popen') as start, contextlib.redirect_stderr(io.StringIO()):
                    windows.launch(['with spaces'])
                    self.assertEqual(start.call_args.args[0], [str(self.source / 'Codex.exe'), 'with spaces'])
                    self.assertNotIn('env', start.call_args.kwargs)
                path.write_bytes(original)
        self.inject.run.assert_not_called()

    def test_failed_rollback_keeps_the_previous_shortcut_for_recovery(self):
        windows.install()
        shortcut = self.desktop.read_bytes()
        state = windows.STATE.read_bytes()
        original = windows.atomic_write

        def fail_rollback(path, data):
            if path == self.desktop and data == shortcut:
                raise PermissionError('rollback failed')
            return original(path, data)

        with patch.object(windows, 'save_state', side_effect=PermissionError('commit failed')), \
                patch.object(windows, 'atomic_write', side_effect=fail_rollback), \
                patch.object(windows, 'make_launcher', side_effect=lambda path: path.write_bytes(b'new shortcut')):
            with self.assertRaisesRegex(PermissionError, 'rollback failed') as raised:
                windows.install()
        recovery = list(self.local.glob('windows-launcher-*/previous.lnk'))
        self.assertEqual(len(recovery), 1)
        self.assertEqual(recovery[0].read_bytes(), shortcut)
        self.assertEqual(windows.STATE.read_bytes(), state)
        self.assertTrue(any('安装恢复目录' in note for note in raised.exception.__notes__))

    def test_missing_or_modified_shortcut_is_reported(self):
        windows.install()
        self.desktop.unlink()
        self.assertIn('启动器', windows.runtime_problem(windows.read_state()))
        self.desktop.write_bytes(b'foreign edit')
        self.assertIn('启动器', windows.runtime_problem(windows.read_state()))
        self.assertEqual(self.desktop.read_bytes(), b'foreign edit')

    def test_custom_source_survives_a_new_launcher_environment(self):
        with patch.dict(os.environ, {'CODEXFLARE_SOURCE_APP': str(self.source)}):
            windows.install()
        self.assertTrue(windows.read_state()['custom_source'])
        with patch.dict(os.environ):
            os.environ.pop('CODEXFLARE_SOURCE_APP', None)
            with patch.object(windows, 'powershell', side_effect=AssertionError('Should use saved custom source')):
                self.assertEqual(REAL_FIND_SOURCE(), self.source.resolve())
            windows.install()
        self.assertTrue(windows.read_state()['custom_source'])

    def test_default_source_is_rediscovered_after_store_update(self):
        with patch.dict(os.environ):
            os.environ.pop('CODEXFLARE_SOURCE_APP', None)
            windows.install()
            self.assertFalse(windows.read_state()['custom_source'])
            updated = self.root / 'new-store-package'
            with patch.object(sys, 'platform', 'win32'), patch.object(windows, 'powershell', return_value=str(updated)):
                self.assertEqual(REAL_FIND_SOURCE(), updated / 'app')

    def test_launch_uses_original_and_applied_settings_without_a_new_profile(self):
        windows.install()
        arguments = ['codex://threads/123', 'with spaces']
        applied = windows.read_state()['settings']
        self.settings['brightness'] = 1.75
        self.inject.prepare_script.reset_mock()
        with patch.object(windows.subprocess, 'Popen', side_effect=AssertionError('The injector launches the original')):
            windows.launch(arguments)
        self.inject.prepare_script.assert_called_once_with(self.source, applied, self.local)
        self.inject.run.assert_called_once_with(self.source, applied, self.local,
                                                arguments=arguments, prepared_script='validated script')
        for name in ('runtime-windows', 'profile-windows', 'codex-home-windows'):
            self.assertFalse((self.local / name).exists())

    def test_original_can_be_running_during_install_but_must_exit_before_launch(self):
        with patch.object(windows, 'source_running_pids', return_value=[4321]):
            windows.install()
            with self.assertRaisesRegex(ValueError, '请正常退出'):
                windows.launch([])
        self.inject.run.assert_not_called()
        self.package_launch.assert_not_called()

    def test_launch_restarts_only_the_launcher_in_the_original_package(self):
        windows.install()
        self.package_launch.return_value = True
        arguments = ['codex://threads/123', 'with spaces']
        with patch.object(windows.subprocess, 'Popen') as start:
            windows.launch(arguments)
        self.package_launch.assert_called_once_with(self.source,
            [sys.executable, str(Path(windows.__file__).with_name('manage.py').resolve()), 'launch', *arguments])
        self.inject.run.assert_not_called()
        start.assert_not_called()

    def test_package_identity_failure_never_runs_without_identity(self):
        windows.install()
        self.package_launch.side_effect = ValueError('包身份检查失败')
        with patch.object(windows.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(ValueError, '包身份'):
                windows.launch([])
        self.inject.run.assert_not_called()
        start.assert_not_called()

    def test_missing_or_invalid_applied_assets_fall_back_before_injection(self):
        windows.install()
        state = windows.STATE.read_bytes()
        for error in (FileNotFoundError('missing video'), ValueError('invalid PNG')):
            with self.subTest(error=error), \
                    patch.object(self.inject, 'prepare_script', side_effect=error), \
                    patch.object(windows.subprocess, 'Popen') as start, \
                    contextlib.redirect_stderr(io.StringIO()) as warnings:
                windows.launch(['with spaces'])
                start.assert_called_once_with([str(self.source / 'Codex.exe'), 'with spaces'], cwd=self.source)
                self.assertIn('无法准备已应用的动画或背景', warnings.getvalue())
                self.inject.run.assert_not_called()
                self.package_launch.assert_not_called()
                self.assertEqual(windows.STATE.read_bytes(), state)

    def test_injection_failure_never_launches_a_second_process(self):
        windows.install()
        for error in (RuntimeError('active session failed'), OSError('pipe failed')):
            with self.subTest(error=error), patch.object(self.inject, 'run', side_effect=error), \
                    patch.object(windows.subprocess, 'Popen') as start:
                with self.assertRaises(type(error)):
                    windows.launch([])
                start.assert_not_called()

    def test_launch_without_installation_falls_back_to_original(self):
        with patch.object(windows.subprocess, 'Popen') as start, contextlib.redirect_stderr(io.StringIO()):
            windows.launch(['with spaces'])
            self.assertEqual(start.call_args.args[0], [str(self.source / 'Codex.exe'), 'with spaces'])
            self.assertNotIn('env', start.call_args.kwargs)
        self.inject.run.assert_not_called()
        self.assertFalse(self.local.exists())

    def test_legacy_state_requires_reapply_and_never_launches_the_old_copy(self):
        windows.install()
        state = windows.read_state()
        del state['mode']
        windows.save_state(state)
        windows.RUNTIME.mkdir()
        (windows.RUNTIME / windows.BINARY).write_bytes(b'legacy copy')
        self.assertIn('重新应用', windows.runtime_problem(state))
        with patch.object(windows.subprocess, 'Popen') as start, contextlib.redirect_stderr(io.StringIO()):
            windows.launch([])
            self.assertEqual(start.call_args.args[0], [str(self.source / 'Codex.exe')])
            self.assertNotIn('env', start.call_args.kwargs)
        self.inject.run.assert_not_called()
        windows.install()
        self.assertIsNone(windows.runtime_problem(windows.read_state()))
        self.assertEqual((windows.RUNTIME / windows.BINARY).read_bytes(), b'legacy copy')

    def test_qa_build_preserves_original_and_updates_copy_integrity(self):
        original = (self.source / windows.ASAR).read_bytes()
        binary = (self.source / windows.BINARY).read_bytes()
        destination = self.root / 'qa-copy'
        windows.build_runtime(destination)
        self.assertEqual(patch_app.Asar(destination / windows.ASAR).read('patch.txt'), b'patched')
        self.assertNotEqual((destination / windows.BINARY).read_bytes(), binary)
        self.assertEqual((self.source / windows.ASAR).read_bytes(), original)
        self.assertEqual((self.source / windows.BINARY).read_bytes(), binary)

    def test_integrity_mismatch_and_duplicate_fail_closed(self):
        binary = self.source / windows.BINARY
        original = binary.read_bytes()
        with self.assertRaisesRegex(ValueError, '唯一'):
            windows.update_integrity(binary, '0' * 64, '1' * 64)
        self.assertEqual(binary.read_bytes(), original)
        binary.write_bytes(original * 2)
        with self.assertRaisesRegex(ValueError, '唯一'):
            windows.update_integrity(binary, windows.header_hash(self.source / windows.ASAR), '1' * 64)
        self.assertEqual(binary.read_bytes(), original * 2)

    def test_platform_dispatch_and_build_guard(self):
        with patch.object(sys, 'platform', 'win32'):
            self.assertIs(manage.platform_manager(), windows)
        package = json.loads(patch_app.Asar(self.source / windows.ASAR).read('package.json'))
        patch_windows.require_supported(package)
        for key in ('version', 'codexBuildNumber', 'codexWindowsPackageIdentity'):
            with self.assertRaises(ValueError):
                patch_windows.require_supported(package | {key: 'future'})
        with self.assertRaises(ValueError):
            windows.build_runtime(self.source / 'nested')

    def test_windows_patch_keeps_exact_anchors_and_disables_protocol_registration(self):
        original = ('minWidth:A?.width,minHeight:A?.height,webPreferences:P},R=new m.BrowserWindow(L);'
                    'await R.loadURL(t.o(f,{mcpAppSandboxLocalDevelopment:ee}));'
                    'B.createPrimaryWindow({title:m.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n});'
                    'let i=Cje(t);if((0,W.default)(this.primaryWindowMode,t)){};'
                    'Ge.deepLinks.registerProtocolClient()')
        result = patch_windows.patch_main(original)
        self.assertIn('codexBootAnimation', result)
        self.assertNotIn('registerProtocolClient()', result)
        for text in (result, original * 2, original.replace('Ge.deepLinks', 'changed.deepLinks')):
            with self.assertRaises(ValueError):
                patch_windows.patch_main(text)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows Shell COM integration')
    def test_real_shortcut_quotes_unicode_and_spaces(self):
        shortcut = self.root / '测试目录/测试 launcher.lnk'
        shortcut.parent.mkdir()
        # Call the real implementation while preserving the install-test substitute.
        original = REAL_MAKE_LAUNCHER
        original(shortcut)
        self.assertTrue(shortcut.is_file())
        # The legacy scripting reader also requires an ANSI-compatible filename.
        readable = self.root / 'inspect.lnk'
        shutil.copyfile(shortcut, readable)
        info = json.loads(windows.powershell(
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:CODEXFLARE_LINK); "
            "@{target=$s.TargetPath;arguments=$s.Arguments;icon=$s.IconLocation}|ConvertTo-Json -Compress", CODEXFLARE_LINK=readable))
        self.assertTrue(info['target'].endswith('pythonw.exe'))
        self.assertIn('manage.py', info['arguments'])
        self.assertTrue(info['arguments'].endswith(' launch'))
        self.assertEqual(Path(info['icon'].rsplit(',', 1)[0]).resolve(), (self.source / windows.BINARY).resolve())


REAL_MAKE_LAUNCHER = windows.make_launcher
REAL_FIND_SOURCE = windows.find_source

try:
    from tools.desktop_windows import CloseGuard, local_navigation
except ImportError:
    CloseGuard = None


@unittest.skipIf(CloseGuard is None, 'pywebview is required')
class WindowsEditorTests(unittest.TestCase):
    def test_navigation_is_same_origin(self):
        origin = 'http://127.0.0.1:12345/'
        self.assertTrue(local_navigation(origin + '?preview=1', origin))
        for url in ('https://example.com', 'file:///C:/Windows/win.ini', 'javascript:alert(1)',
                    'http://127.0.0.1:12346/', 'http://user@127.0.0.1:12345/'):
            self.assertFalse(local_navigation(url, origin))

    def test_close_guard_preserves_dirty_and_busy_edits(self):
        window = Mock()
        server = SimpleNamespace(write_lock=threading.Lock())
        guard = CloseGuard(window, server)
        window.run_js.return_value = True
        window.create_confirmation_dialog.return_value = False
        guard.check()
        window.destroy.assert_not_called()
        self.assertFalse(server.write_lock.locked())
        with server.write_lock:
            guard.check()
        self.assertEqual(window.run_js.call_count, 1)
        window.run_js.return_value = False
        guard.check()
        self.assertTrue(guard.approved)
        window.destroy.assert_called_once()
        self.assertTrue(server.write_lock.locked())
        server.write_lock.release()


if __name__ == '__main__':
    unittest.main()
