import contextlib
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import manage_macos as mac, patch_macos, patch_app


def asar(path, files):
    entries, payload = {}, b''
    for name, data in files.items():
        entries[name] = {'size': len(data), 'offset': str(len(payload))}
        payload += data
    raw = json.dumps({'files': entries}).encode()
    padding = b'\0' * (-len(raw) % 4)
    size = len(raw) + len(padding) + 4
    path.write_bytes(struct.pack('<4I', 4, size + 4, size, len(raw)) + raw + padding + payload)
    return raw


class MacManagerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        source = self.root / 'ChatGPT.app'
        (source / 'Contents/Resources').mkdir(parents=True)
        (source / 'Contents/MacOS').mkdir()
        (source / 'Contents/MacOS/ChatGPT').write_bytes(b'binary fixture')
        (source / mac.PLIST).write_bytes(plistlib.dumps({'CFBundleExecutable':'ChatGPT',
            'CFBundleVersion':patch_macos.BUILD, 'CFBundleIdentifier':'com.openai.codex',
            'CFBundleURLTypes':[{'CFBundleURLSchemes':['codex']}]}))
        raw = asar(source / mac.ASAR, {'package.json':json.dumps({
            'name':'openai-codex-electron', 'version':patch_macos.VERSION}).encode()})
        info = mac.bundle_info(source)
        integrity = {'Resources/app.asar': {'algorithm':'SHA256', 'hash':hashlib.sha256(raw).hexdigest()}}
        info['ElectronAsarIntegrity'] = integrity
        (source/mac.PLIST).write_bytes(plistlib.dumps(info))
        framework=source/'Contents/Frameworks/Codex Framework.framework/Codex Framework'
        framework.parent.mkdir(parents=True)
        framework.write_bytes(b'fake-macho-prefix' + b'AGbevlPCksUGKNL8TSn7wGmJEuJsXb2A' + b'\x01\x01' + mac.integrity_digest(integrity))
        self.local = self.root / '.local'
        for name, value in {'SOURCE':source, 'LOCAL':self.local, 'RUNTIME':self.local/'Runtime.app',
            'STATE':self.local/'install.json', 'DESKTOP':self.root/'Applications/Launch.app'}.items():
            self.enterContext(patch.object(mac, name, value))
        self.enterContext(patch.object(mac, 'running_pids', return_value=[]))
        self.enterContext(patch.object(mac.subprocess, 'check_output', return_value='arm64'))
        self.enterContext(patch.object(mac.subprocess, 'run', side_effect=self.run_command))
        self.enterContext(patch.object(mac, 'patch_archive', side_effect=self.patch_archive))
        # Cross-platform unit tests use a rename implementation; native swap is tested separately.
        self.enterContext(patch.object(mac, 'swap_directory', side_effect=self.swap))

    def run_command(self, command, **kw):
        if command[0] == '/usr/bin/ditto':
            shutil.copytree(command[1], command[2])

    def patch_archive(self, source, target, **kw):
        self.assertEqual(kw, {'platform':'darwin'})
        patch_app.Asar(source).write_changes(target, {'custom.txt':b'patched'})
        return {'version':patch_macos.VERSION}

    def swap(self, source, target):
        if target.exists():
            old = target.with_suffix('.old')
            target.rename(old); source.rename(target); old.rename(source)
        else:
            source.rename(target)

    def test_install_replace_uninstall_preserves_original_and_profiles(self):
        before = mac.fingerprint()
        mac.install(); mac.install()
        state = mac.read_state()
        self.assertIsNone(mac.runtime_problem(state))
        self.assertEqual(before, mac.fingerprint())
        self.assertTrue(mac.DESKTOP.exists())
        self.assertNotIn('CFBundleURLTypes', mac.bundle_info(mac.RUNTIME))
        self.assertEqual(mac.bundle_info(mac.RUNTIME)['CFBundleIdentifier'],'org.codexflare.runtime')
        mac.uninstall()
        self.assertFalse(mac.DESKTOP.exists())
        self.assertTrue(mac.RUNTIME.exists())
        self.assertFalse(mac.read_state()['active'])
        self.assertFalse((self.local/'profile').exists())

    def test_changed_launcher_is_never_overwritten_or_removed(self):
        mac.install()
        marker = mac.DESKTOP/'user-file'
        marker.write_text('keep')
        with self.assertRaisesRegex(ValueError, '修改'):
            mac.install()
        with self.assertRaisesRegex(ValueError, '修改'):
            mac.uninstall()
        self.assertEqual(marker.read_text(), 'keep')

    def test_unowned_launcher_and_runtime_symlink_refused(self):
        mac.DESKTOP.mkdir(parents=True)
        with self.assertRaises(ValueError):
            mac.install()
        mac.DESKTOP.rmdir()
        self.local.mkdir()
        mac.RUNTIME.symlink_to(mac.SOURCE, target_is_directory=True)
        with self.assertRaises(ValueError):
            mac.install()

    def test_mismatched_build_and_architecture_rejected(self):
        info = mac.fingerprint(); info['build'] = '99999'
        with self.assertRaises(ValueError): mac.require_supported(info)
        with patch.object(mac.subprocess, 'check_output', return_value='x86_64'):
            with self.assertRaises(ValueError): mac.require_supported(mac.fingerprint())

    def test_busy_copy_not_overwritten(self):
        with patch.object(mac, 'running_pids', return_value=[123]):
            with self.assertRaisesRegex(ValueError, '123'): mac.install()
        self.assertFalse(mac.RUNTIME.exists())

    def test_integrity_hash_matches_raw_header_and_signing_is_verified(self):
        target = self.root/'Test.app'
        shutil.copytree(mac.SOURCE, target)
        with patch.object(mac.subprocess, 'run') as run:
            mac.seal_bundle(target)
        with (target/mac.ASAR).open('rb') as f:
            _,_,_,length=struct.unpack('<4I',f.read(16)); raw=f.read(length)
        info=mac.bundle_info(target)
        self.assertEqual(info['ElectronAsarIntegrity']['Resources/app.asar']['hash'],hashlib.sha256(raw).hexdigest())
        self.assertIn('--verify',run.call_args_list[-1].args[0])

    def test_framework_digest_mismatch_refuses_to_write(self):
        framework=mac.SOURCE/'Contents/Frameworks/Codex Framework.framework/Codex Framework'
        before=framework.read_bytes()
        with self.assertRaisesRegex(ValueError,'mismatched'):
            mac.update_framework_integrity(mac.SOURCE,{},mac.bundle_info(mac.SOURCE)['ElectronAsarIntegrity'])
        self.assertEqual(framework.read_bytes(),before)

    def test_source_update_falls_back_without_profile_override(self):
        mac.install()
        (mac.SOURCE/'Contents/MacOS/ChatGPT').write_bytes(b'new version')
        with patch.object(mac.os,'execv') as run:
            mac.launch(['--test'])
        self.assertEqual(run.call_args.args[0],'/usr/bin/open')

    def test_launch_uses_separate_profile_and_codex_home(self):
        mac.install()
        with patch.object(mac.os,'execve') as run:
            mac.launch([])
        _, args, env = run.call_args.args
        self.assertIn('--user-data-dir='+str(self.local/'profile'),args)
        self.assertEqual(env['CODEX_HOME'],str(self.local/'codex-home'))


class MacPatchTests(unittest.TestCase):
    def test_wrong_and_duplicate_anchors_fail(self):
        with self.assertRaises(ValueError): patch_macos.patch_main('unrecognized build')
        with self.assertRaises(ValueError): patch_macos.patch_main('', 'bad-mode')

    def test_macos_preloads_do_not_reference_linux_assets(self):
        result=patch_app.patch_html('<head></head>', preloads=patch_macos.STARTUP_PRELOADS)
        for name in patch_macos.STARTUP_PRELOADS: self.assertIn(name,result)
        for name in patch_app.STARTUP_PRELOADS: self.assertNotIn(name,result)

    def test_background_targets_current_workspace_and_composer_classes(self):
        style = (patch_app.ROOT/'src/background.css').read_text()
        class Archive:
            def read(self, name):
                return '\n'.join('.'+value+'{}' for value in (*patch_macos.BACKGROUND_CLASSES.values(), '_background_106nk_2', '_fade_106nk_2', '_surface_106nk_2')).encode()
        patched=patch_macos.patch_background_css(style,Archive())
        self.assertIn('._WorkspaceContent_azz1c_2::before',patched)
        self.assertIn('._ComposerLayoutRoot_1q7o3_2',patched)
        self.assertNotIn('_WorkspaceContent_yl8z4_2',patched)
        self.assertNotIn('_ComposerLayoutRoot_15oep_2',patched)
        self.assertIn('mix-blend-mode: screen',patched)
        self.assertIn('pointer-events: none',patched)

    def test_background_rejects_unreviewed_css_modules(self):
        class Archive:
            def read(self,name): return b'.new-module {}'
        with self.assertRaisesRegex(ValueError,'Background selector missing'):
            patch_macos.patch_background_css('body {}',Archive())

    @unittest.skipUnless(sys.platform=='darwin','Darwin renamex_np')
    def test_native_directory_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a',Path(directory)/'b'
            a.mkdir(); b.mkdir(); (a/'a').touch(); (b/'b').touch()
            mac.swap_directory(a,b)
            self.assertTrue((a/'b').exists()); self.assertTrue((b/'a').exists())


if __name__=='__main__': unittest.main()
