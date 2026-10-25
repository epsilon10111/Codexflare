from pathlib import Path
import os
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import original_macos as original
from tests.test_macos import asar

verify_bundle = original._verify


@unittest.skipIf(os.name == 'nt', 'Requires POSIX locks, file modes, and symlinks')
class OriginalMacTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        self.source = root / 'Applications/ChatGPT.app'
        self.local = root / 'local'
        self.local.mkdir()
        (self.source / 'Contents/MacOS').mkdir(parents=True)
        (self.source / 'Contents/Resources').mkdir()
        (self.source / 'Contents/MacOS/ChatGPT').write_bytes(b'official binary')
        (self.source / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'com.openai.codex', 'CFBundleExecutable': 'ChatGPT',
            'CFBundleName': 'ChatGPT', 'CrProductDirName': 'com.openai.codex',
            'CFBundleVersion': original.mac.BUILD,
            'CFBundleURLTypes': [{'CFBundleURLSchemes': ['codex']}]}))
        asar(self.source / original.mac.ASAR, {'package.json':
             ('{"name":"openai-codex-electron","version":"' + original.mac.VERSION + '"}').encode()})
        for name, value in {'SOURCE': self.source, 'LOCAL': self.local,
                            'STATE': self.local / 'original-install.json',
                            'BACKUP': self.local / 'Original ChatGPT.app',
                            'LOCK': self.local / 'install.lock',
                            'WORKER_LOCK': self.local / 'worker.lock',
                            'LOG': self.local / 'worker.log'}.items():
            self.enterContext(patch.object(original, name, value))
        self.verify = self.enterContext(patch.object(original, '_verify'))
        self.enterContext(patch.object(original.mac, 'require_supported'))
        self.build = self.enterContext(patch.object(original.mac, 'build_runtime', side_effect=self.build_runtime))
        self.enterContext(patch.object(original.mac, 'swap_directory', side_effect=self.swap))
        self.run = self.enterContext(patch.object(original.subprocess, 'run', side_effect=self.run_command))
        self.enterContext(patch.object(original.mac, 'check_compatibility', return_value={'version': '99.1.1'}))
        self.pids = []
        self.sequence = 0
        self.before = original.bundle_digest(self.source)

    def test_active_status_checks_official_backup_not_patched_target(self):
        original.prepare()
        self.assertTrue(original.activate_pending())
        with patch.object(original.mac, 'check_compatibility', return_value={}) as check:
            self.assertTrue(original.status()['active'])
            check.assert_called_once_with(bundle=original.BACKUP, preserve_identity=True)

    def test_incompatible_structure_stops_before_backup_or_replacement(self):
        with patch.object(original.mac, 'check_compatibility', side_effect=ValueError('incompatible structure')):
            with self.assertRaisesRegex(ValueError, 'incompatible structure'):
                original.prepare()
        self.assertFalse(original.BACKUP.exists())
        self.assertFalse(original.STATE.exists())
        self.assertEqual(original.bundle_digest(self.source), self.before)

    def build_runtime(self, destination, source=None, preserve_identity=False):
        self.assertEqual(source, original.BACKUP)
        self.assertTrue(preserve_identity)
        shutil.copytree(source, destination, symlinks=True)
        self.sequence += 1
        (destination / 'Contents/MacOS/ChatGPT').write_bytes(f'patched {self.sequence}'.encode())

    def run_command(self, command, **kwargs):
        if command[0] == '/usr/bin/ditto':
            shutil.copytree(command[1], command[2], symlinks=True)
        elif command[0] == '/bin/ps':
            return subprocess.CompletedProcess(command, 0, stdout='\n'.join(self.pids))
        return subprocess.CompletedProcess(command, 0)

    @staticmethod
    def swap(source, destination):
        temporary = source.with_suffix('.old')
        destination.rename(temporary)
        source.rename(destination)
        temporary.rename(source)

    def test_prepare_only_then_wait_for_main_and_renderers_before_exchange(self):
        self.pids = [f'10 {self.source}/Contents/MacOS/ChatGPT']
        result = original.prepare()
        self.assertTrue(result['pending'])
        self.assertEqual(original.bundle_digest(self.source), self.before)
        self.assertEqual(original.bundle_digest(original.BACKUP), self.before)
        self.assertFalse(original.activate_pending())
        self.pids = [f'11 {self.source}/Contents/Frameworks/Helper.app/Contents/MacOS/Helper']
        self.assertFalse(original.activate_pending())
        self.pids = [f'12 {self.source}/Contents/Resources/codex',
                     f'13 {self.source}/Contents/Frameworks/Codex.framework/Helpers/browser_crashpad_handler']
        self.assertTrue(original.activate_pending())
        self.assertNotEqual(original.bundle_digest(self.source), self.before)
        self.assertEqual(original.bundle_digest(original.BACKUP), self.before)
        self.assertEqual(original.status()['phase'], 'active')
        self.assertIsNone(original.read_state()['pending'])

    def test_restore_and_repeated_apply_always_use_immutable_official_backup(self):
        original.prepare()
        original.activate_pending()
        original.prepare()
        original.activate_pending()
        self.assertEqual(self.build.call_count, 2)
        self.assertEqual(original.bundle_digest(original.BACKUP), self.before)
        self.pids = [f'10 {self.source}/Contents/MacOS/ChatGPT']
        original.uninstall()
        self.assertFalse(original.activate_pending())
        self.pids = []
        self.assertTrue(original.activate_pending())
        self.assertEqual(original.bundle_digest(self.source), self.before)
        self.assertFalse(original.status()['active'])

    def test_external_update_is_not_overwritten_and_candidate_is_retained(self):
        original.prepare()
        candidate = Path(original.read_state()['pending']['path'])
        (self.source / 'Contents/MacOS/ChatGPT').write_bytes(b'official update')
        changed = original.bundle_digest(self.source)
        with self.assertRaisesRegex(ValueError, '已更新'):
            original.activate_pending()
        self.assertEqual(original.bundle_digest(self.source), changed)
        self.assertTrue(candidate.exists())
        self.assertEqual(original.status()['phase'], 'failed')
        self.assertTrue(original.status()['available'])

    def test_modified_candidate_and_backup_are_refused(self):
        original.prepare()
        candidate = Path(original.read_state()['pending']['path'])
        (candidate / 'unexpected').touch()
        with self.assertRaisesRegex(ValueError, '待安装应用'):
            original.activate_pending()
        self.assertEqual(original.bundle_digest(self.source), self.before)
        (original.BACKUP / 'unexpected').touch()
        with self.assertRaisesRegex(ValueError, '官方备份'):
            original.prepare()
        self.assertTrue(candidate.exists())

    def test_failed_build_keeps_original_backup_and_existing_pending(self):
        original.prepare()
        previous = original.read_state()['pending']
        with patch.object(original.mac, 'build_runtime', side_effect=ValueError('build failure')):
            with self.assertRaisesRegex(ValueError, 'build failure'):
                original.prepare()
        self.assertEqual(original.read_state()['pending'], previous)
        self.assertEqual(original.bundle_digest(self.source), self.before)
        self.assertTrue(Path(previous['path']).exists())
        self.assertEqual(original.status()['phase'], 'failed')

    def test_interrupted_exchange_is_recovered_without_losing_official_backup(self):
        original.prepare()
        with patch.object(original, '_finish', side_effect=OSError('interrupted')):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                original.activate_pending()
        self.assertTrue(original.read_state()['exchanging'])
        self.assertNotEqual(original.bundle_digest(self.source), self.before)
        self.assertTrue(original.activate_pending())
        self.assertTrue(original.read_state()['active'])
        self.assertIsNone(original.read_state()['pending'])
        self.assertEqual(original.bundle_digest(original.BACKUP), self.before)
        self.assertFalse(original.activate_pending())

    def test_worker_relaunches_after_finishing_an_interrupted_exchange(self):
        original.prepare()
        state = original.read_state()
        state['exchanging'] = True
        original._save(state)
        self.swap(Path(state['pending']['path']), self.source)
        original.wait_activate(relaunch=True)
        self.assertTrue(original.read_state()['active'])
        self.assertIsNone(original.read_state()['pending'])
        self.assertEqual(self.run.call_args.args[0], ['/usr/bin/open', str(self.source)])

    def test_post_exchange_signature_failure_rolls_back_and_keeps_candidate(self):
        original.prepare()
        pending = original.read_state()['pending']

        def verify(bundle, official=False):
            if bundle == self.source:
                raise subprocess.CalledProcessError(1, ['codesign', '--verify'])

        with patch.object(original, '_verify', side_effect=verify):
            with self.assertRaises(subprocess.CalledProcessError):
                original.activate_pending()
        self.assertEqual(original.bundle_digest(self.source), self.before)
        self.assertEqual(original.bundle_digest(Path(pending['path'])), pending['sha256'])
        self.assertNotIn('exchanging', original.read_state())
        self.assertEqual(original.status()['phase'], 'failed')

    def test_official_verification_uses_an_inline_apple_signing_requirement(self):
        verify_bundle(self.source, official=True)
        self.run.assert_called_with([
            '/usr/bin/codesign', '--verify', '--deep', '--strict', '--test-requirement',
            '=' + original.OFFICIAL_REQUIREMENT, str(self.source)], check=True, capture_output=True)

    def test_bundle_symlinks_are_internal_and_top_level_symlinks_are_rejected(self):
        resources = self.source / 'Contents/Resources'
        (resources / 'inside').symlink_to('app.asar')
        original.bundle_digest(self.source)
        (resources / 'outside').symlink_to(self.local)
        with self.assertRaisesRegex(ValueError, '越界'):
            original.bundle_digest(self.source)
        link = self.source.parent / 'Link.app'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, '普通目录'):
            original.bundle_digest(link)

    def test_broken_backup_and_state_symlinks_are_not_overwritten(self):
        original.BACKUP.symlink_to(self.local / 'missing-backup')
        with self.assertRaisesRegex(ValueError, '备份不能是符号链接'):
            original.prepare()
        self.assertTrue(original.BACKUP.is_symlink())
        original.BACKUP.unlink()
        original.STATE.symlink_to(self.local / 'missing-state')
        with self.assertRaisesRegex(ValueError, '状态不能是符号链接'):
            original.prepare()
        self.assertTrue(original.STATE.is_symlink())

    def test_transaction_lock_and_worker_lock_prevent_concurrent_operations(self):
        with original._lock(original.LOCK):
            with self.assertRaises(original.BusyError):
                original.prepare()
        original.prepare()
        with original._lock(original.WORKER_LOCK), patch.object(original.subprocess, 'Popen') as spawn:
            self.assertFalse(original.launch_worker())
            original.wait_activate()
            spawn.assert_not_called()

    def test_worker_launch_is_explicit_and_relaunch_uses_original_path(self):
        with patch.object(original.subprocess, 'Popen') as spawn:
            original.prepare()
            spawn.assert_not_called()
            self.assertTrue(original.launch_worker(relaunch=True))
            self.assertIn('--relaunch', spawn.call_args.args[0])
        original.wait_activate(relaunch=True)
        command = self.run.call_args
        self.assertEqual(command.args[0], ['/usr/bin/open', str(self.source)])
        self.assertNotIn('CODEX_HOME', command.kwargs['env'])
        self.assertNotIn('CODEX_ELECTRON_USER_DATA_PATH', command.kwargs['env'])
        self.assertTrue(original.read_state()['active'])

    def test_frozen_worker_starts_an_independent_application_process(self):
        original.prepare()
        executable = '/Applications/Codexflare.app/Contents/MacOS/Codexflare'
        with patch.object(original.sys, 'frozen', True, create=True), \
                patch.object(original.sys, 'executable', executable), \
                patch.dict(os.environ, {'PYINSTALLER_RESET_ENVIRONMENT': '0'}), \
                patch.object(original.subprocess, 'Popen') as spawn:
            self.assertTrue(original.launch_worker(relaunch=True))
            self.assertEqual(spawn.call_args.args[0],
                             [executable, '--original', 'wait-activate', '--relaunch'])
            self.assertEqual(spawn.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertEqual(os.environ['PYINSTALLER_RESET_ENVIRONMENT'], '0')
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
            self.assertTrue(spawn.call_args.kwargs['close_fds'])

    def test_pending_cannot_redirect_the_swap_to_another_path(self):
        original.prepare()
        state = original.read_state()
        state['pending']['path'] = str(self.local / 'unrelated.app')
        original._save(state)
        with self.assertRaisesRegex(ValueError, '待安装应用路径'):
            original.activate_pending()
        self.assertEqual(original.bundle_digest(self.source), self.before)


if __name__ == '__main__':
    unittest.main()
