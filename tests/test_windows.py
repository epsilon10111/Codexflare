import contextlib
import io
import json
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
        self.enterContext(patch.object(windows, 'find_source', return_value=self.source))
        self.enterContext(patch.object(windows, 'make_launcher', side_effect=lambda path: path.write_bytes(b'shortcut')))
        self.enterContext(patch.object(windows, 'patch_archive', side_effect=self.patch_archive))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def patch_archive(self, source, destination, *, platform):
        self.assertEqual(platform, 'win32')
        patch_app.Asar(source).write_changes(destination, {'patch.txt': b'patched'})
        return {'version': patch_windows.VERSION}

    def test_reinstall_uninstall_preserves_source_and_data(self):
        original = (self.source / windows.ASAR).read_bytes()
        binary = (self.source / windows.BINARY).read_bytes()
        windows.install()
        windows.install()
        self.assertIsNone(windows.runtime_problem(windows.read_state()))
        self.assertEqual(patch_app.Asar(windows.RUNTIME / windows.ASAR).read('patch.txt'), b'patched')
        self.assertNotEqual((windows.RUNTIME / windows.BINARY).read_bytes(), binary)
        windows.uninstall()
        windows.uninstall()
        self.assertFalse(self.desktop.exists())
        self.assertFalse(windows.read_state()['active'])
        self.assertTrue(windows.RUNTIME.is_dir())
        self.assertEqual((self.source / windows.ASAR).read_bytes(), original)
        self.assertEqual((self.source / windows.BINARY).read_bytes(), binary)

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

    def test_source_change_during_build_never_enables_launcher(self):
        before = windows.fingerprint()
        with patch.object(windows, 'fingerprint', side_effect=[before, before | {'build': 'future'}]):
            with self.assertRaisesRegex(ValueError, '发生变化'):
                windows.install()
        self.assertFalse(self.desktop.exists())

    def test_swap_failure_restores_previous_runtime(self):
        windows.install()
        staged = self.local / 'build/runtime'
        staged.mkdir(parents=True)
        original_replace = windows.os.replace
        def fail(source, target):
            if source == staged:
                raise PermissionError('locked')
            return original_replace(source, target)
        with patch.object(windows.os, 'replace', side_effect=fail):
            with self.assertRaises(PermissionError):
                windows.swap_runtime(staged)
        self.assertIsNone(windows.runtime_problem(windows.read_state()))

    def test_launch_isolates_profile_and_stale_copy_falls_back(self):
        windows.install()
        arguments = ['codex://threads/123', 'with spaces']
        with patch.object(windows.subprocess, 'Popen') as start:
            windows.launch(arguments)
            command = start.call_args.args[0]
            self.assertEqual(command[0], str(windows.RUNTIME / windows.BINARY))
            self.assertEqual(command[-2:], arguments)
            env = start.call_args.kwargs['env']
            self.assertEqual(env['CODEX_HOME'], str(self.local / 'codex-home-windows'))
            self.assertEqual(env['CODEX_ELECTRON_USER_DATA_PATH'], str(self.local / 'profile-windows'))
        (self.source / 'chrome.dll').write_bytes(b'updated')
        with patch.object(windows.subprocess, 'Popen') as start, contextlib.redirect_stderr(io.StringIO()):
            windows.launch(arguments)
            self.assertEqual(start.call_args.args[0], [str(self.source / 'Codex.exe'), *arguments])
            self.assertNotIn('env', start.call_args.kwargs)

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
            "@{target=$s.TargetPath;arguments=$s.Arguments}|ConvertTo-Json -Compress", CODEXFLARE_LINK=readable))
        self.assertTrue(info['target'].endswith('pythonw.exe'))
        self.assertIn('manage.py', info['arguments'])
        self.assertTrue(info['arguments'].endswith(' launch'))


REAL_MAKE_LAUNCHER = windows.make_launcher

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
