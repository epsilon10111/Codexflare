import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from tools import windows_package as package


class WindowsPackageTests(unittest.TestCase):
    def setUp(self):
        self.source = Path('registered app').resolve()
        self.info = {'full_name': 'OpenAI.Codex_1.2.3.0_x64__test',
                     'family_name': 'OpenAI.Codex_test', 'app_id': 'App'}

    def test_matching_identity_needs_no_restart(self):
        with patch.object(package, 'registered_package', return_value=self.info), \
                patch.object(package, 'current_package_full_name', return_value=self.info['full_name']), \
                patch.object(package, 'powershell') as shell:
            self.assertFalse(package.launch_in_package(self.source, ['python.exe', 'manage.py', 'launch']))
        shell.assert_not_called()

    def test_restart_keeps_arguments_and_only_explicit_data_paths(self):
        command = ['python.exe', '脚本 with spaces.py', 'quote" and $(never) ` ; & end\\']
        env = {'CODEX_HOME': 'C:\\账户 数据', 'CODEX_ELECTRON_USER_DATA_PATH': 'C:\\原账户',
               'CODEXFLARE_SOURCE_APP': 'previous path', 'API_SECRET': 'never serialize this'}
        with patch.object(package, 'registered_package', return_value=self.info), \
                patch.object(package, 'current_package_full_name', return_value=None), \
                patch.object(package, 'powershell') as shell, \
                patch.object(package.subprocess, 'list2cmdline', wraps=subprocess.list2cmdline) as quote, \
                patch.dict(os.environ, env, clear=True):
            self.assertTrue(package.launch_in_package(self.source, command))
        payload = json.loads(base64.b64decode(quote.call_args.args[0][1]))
        self.assertEqual(payload['command'], command)
        self.assertEqual(payload['package'], self.info['full_name'])
        self.assertEqual(payload['environment'], {key: value for key, value in env.items() if key != 'API_SECRET'} |
                         {'CODEXFLARE_SOURCE_APP': str(self.source)})
        self.assertNotIn('never serialize this', str(shell.call_args))
        self.assertIn('-PreventBreakaway', shell.call_args.args[0])
        self.assertNotIn(command[-1], shell.call_args.args[0])

    def test_failed_reentry_cannot_restart_again_or_downgrade(self):
        with patch.object(package, 'registered_package', return_value=self.info), \
                patch.object(package, 'current_package_full_name', return_value=None), \
                patch.object(package, 'powershell') as shell, \
                patch.dict(os.environ, {package.RESTART_MARKER: self.info['full_name']}):
            with self.assertRaisesRegex(ValueError, '未能保留'):
                package.launch_in_package(self.source, ['python.exe', 'manage.py', 'launch'])
        shell.assert_not_called()

    def test_bootstrap_prefers_pythonw_without_changing_the_requested_command(self):
        command = [sys.executable, 'manage.py', 'launch']
        with patch.object(package, 'registered_package', return_value=self.info), \
                patch.object(package, 'current_package_full_name', return_value=None), \
                patch.object(package, 'powershell') as shell, \
                patch.object(package.subprocess, 'list2cmdline', wraps=subprocess.list2cmdline) as quote, \
                patch.dict(os.environ, {}, clear=True):
            for exists in (True, False):
                with self.subTest(pythonw_exists=exists), patch.object(Path, 'is_file', return_value=exists):
                    self.assertTrue(package.launch_in_package(self.source, command))
                expected = Path(sys.executable).with_name('pythonw.exe') if exists else Path(sys.executable)
                self.assertEqual(shell.call_args.kwargs['CODEXFLARE_PACKAGE_PYTHON'], expected)
                payload = json.loads(base64.b64decode(quote.call_args.args[0][1]))
                self.assertEqual(payload['command'], command)

    def test_unregistered_source_and_dispatch_errors_stop_launch(self):
        with patch.object(package, 'registered_package', side_effect=ValueError('not registered')), \
                patch.object(package, 'powershell') as shell:
            with self.assertRaisesRegex(ValueError, 'not registered'):
                package.launch_in_package(self.source, ['python.exe'])
        shell.assert_not_called()
        with patch.object(package, 'registered_package', return_value=self.info), \
                patch.object(package, 'current_package_full_name', return_value=None), \
                patch.dict(os.environ, {}, clear=True), \
                patch.object(package, 'powershell', side_effect=ValueError('activation denied')):
            with self.assertRaisesRegex(ValueError, 'activation denied'):
                package.launch_in_package(self.source, ['python.exe'])

    def test_registry_match_uses_path_data_and_validates_fields(self):
        with patch.object(package, 'powershell', return_value=json.dumps(self.info)) as shell:
            self.assertEqual(package.registered_package(self.source), self.info)
        self.assertEqual(shell.call_args.kwargs['CODEXFLARE_PACKAGE_SOURCE'], str(self.source))
        self.assertNotIn(str(self.source), shell.call_args.args[0])
        self.assertIn('Get-AppxPackageManifest', shell.call_args.args[0])
        for response in ('[]', '{}', '{"full_name":1}', 'null'):
            with self.subTest(response=response), patch.object(package, 'powershell', return_value=response):
                with self.assertRaises(ValueError):
                    package.registered_package(self.source)

    def test_bootstrap_checks_identity_and_sets_child_marker(self):
        payload = {'package': self.info['full_name'], 'command': ['python.exe', '脚本.py', 'argument'],
                   'environment': {'CODEX_HOME': 'C:\\original'}}
        with patch.object(package, 'current_package_full_name', return_value=self.info['full_name']), \
                patch.object(package.subprocess, 'call', return_value=4) as start, \
                patch.dict(os.environ, {'SYSTEMROOT': 'C:\\Windows'}, clear=True):
            self.assertEqual(package.run_command(payload), 4)
        self.assertEqual(start.call_args.args[0], payload['command'])
        self.assertEqual(start.call_args.kwargs['env'], {'SYSTEMROOT': 'C:\\Windows',
            'CODEX_HOME': 'C:\\original', package.RESTART_MARKER: self.info['full_name']})
        with patch.object(package, 'current_package_full_name', return_value=None), \
                patch.object(package.subprocess, 'call') as start:
            with self.assertRaisesRegex(ValueError, '未获得原版身份'):
                package.run_command(payload)
        start.assert_not_called()

    def test_bootstrap_rejects_unexpected_environment_and_invalid_arguments(self):
        payload = {'package': self.info['full_name'], 'command': ['python.exe'], 'environment': {}}
        cases = [payload | {'environment': {'API_SECRET': 'x'}}, payload | {'command': []},
                 payload | {'command': 'python.exe'}, payload | {'command': ['bad\0argument']}]
        with patch.object(package, 'current_package_full_name', return_value=self.info['full_name']), \
                patch.object(package.subprocess, 'call') as start:
            for invalid in cases:
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    package.run_command(invalid)
        start.assert_not_called()

    def test_native_identity_errors_do_not_mean_unpacked(self):
        api = Mock(return_value=5)
        library = Mock(GetCurrentPackageFullName=api)
        with patch.object(sys, 'platform', 'win32'), patch.object(package.ctypes, 'WinDLL', return_value=library, create=True):
            with self.assertRaises(OSError):
                package.current_package_full_name()
            api.return_value = 15700
            self.assertIsNone(package.current_package_full_name())


if __name__ == '__main__':
    unittest.main()
