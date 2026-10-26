import contextlib
import hashlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import manage_macos as mac, patch_macos, patch_app
from tools.background_layout import BackgroundLayout
from test_patch import style_fixture


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


def mac_main_fixture(version=patch_macos.VERSION):
    fixture = Path(__file__).with_name('test_window_mode_macos.cjs').read_text(encoding='utf-8')
    text = re.search(r'let fixture = `([\s\S]*?)\n`;', fixture)[1].replace('\\`', '`')
    build = patch_macos.select_build(version)
    names = {'O':build['electron'], 'S':build['saved_bounds'], 'A5e':build['onboarding'],
             'q':build['equal'], 'We':build['protocol'].split('.')[0]}
    return re.sub(r'\b[A-Za-z_$][\w$]*\b', lambda m:names.get(m[0],m[0]), text)


def mac_style_archive(version):
    build = patch_macos.select_build(version)
    css = ''.join('.'+name+'{}' for name in build['background_classes'].values())
    css += '._background_106nk_2{}._fade_106nk_2{}._surface_106nk_2{}'
    class Archive:
        def __init__(self):
            self.data = {name:css for name in build['background_styles']}
        def entry(self, name):
            return {'files':{name:{} for name in self.data}}
        def read(self,name):
            return self.data[name.removeprefix('webview/assets/')].encode()
    return Archive()


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
            'CrProductDirName':'Codex', 'CFBundleDisplayName':'Codex',
            'CFBundleIconFile':'electron.icns', 'CFBundleIconName':'Icon',
            'CodexAppIconBaseName':'icon-chatgpt',
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
        self.source_entitlements = {}
        self.signed_entitlements = []
        self.enterContext(patch.object(mac.subprocess, 'run', side_effect=self.run_command))
        self.enterContext(patch.object(mac, 'patch_archive', side_effect=self.patch_archive))
        # Cross-platform unit tests use a rename implementation; native swap is tested separately.
        self.enterContext(patch.object(mac, 'swap_directory', side_effect=self.swap))

    def run_command(self, command, **kw):
        if command[0] == '/usr/bin/ditto':
            shutil.copytree(command[1], command[2])
        elif command[0] == '/usr/bin/codesign' and '--display' in command:
            return mac.subprocess.CompletedProcess(command, 0, plistlib.dumps(self.source_entitlements), b'')
        elif command[0] == '/usr/bin/codesign' and '--force' in command:
            self.signed_entitlements.append(plistlib.loads(Path(command[command.index('--entitlements') + 1]).read_bytes()))

    def patch_archive(self, source, target, **kw):
        self.assertEqual(kw.keys(), {'platform', 'preserve_identity'})
        self.assertEqual(kw['platform'], 'darwin')
        self.assertIs(type(kw['preserve_identity']), bool)
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

    def test_unowned_launcher_refused(self):
        mac.DESKTOP.mkdir(parents=True)
        with self.assertRaises(ValueError):
            mac.install()

    def test_runtime_symlink_refused(self):
        self.local.mkdir()
        try:
            mac.RUNTIME.symlink_to(mac.SOURCE, target_is_directory=True)
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314:
                self.skipTest('Windows symlink privilege unavailable')
            raise
        with self.assertRaises(ValueError):
            mac.install()

    def test_new_build_metadata_allowed_but_architecture_rejected(self):
        info = mac.fingerprint(); info['build'] = '99999'
        mac.require_supported(info)
        with patch.object(mac.subprocess, 'check_output', return_value='x86_64'):
            with self.assertRaises(ValueError): mac.require_supported(mac.fingerprint())

    def test_source_metadata_is_required_without_version_allowlist(self):
        for version, build in (('26.1013.31256', '20586'), ('26.1021.31345', '21828')):
            source = mac.fingerprint() | {'version': version, 'build': build}
            with self.subTest(version=version):
                self.assertTrue(mac.supported_source(source))
                mac.require_supported(source)
                for bad in ({'build': ''}, {'build': None}, {'version': None}):
                    self.assertFalse(mac.supported_source(source | bad))
                    with self.assertRaises(ValueError):
                        mac.require_supported(source | bad)
        self.assertTrue(mac.supported_source({'version': '26.1013.31256', 'build': '21828'}))
        self.assertTrue(mac.supported_source({'version': '99.1.1', 'build': '99999'}))
        self.assertFalse(mac.supported_source({}))

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

    def test_original_identity_keeps_metadata_and_only_local_resource_entitlements(self):
        target = self.root/'OriginalEntry.app'
        shutil.copytree(mac.SOURCE, target)
        before = mac.bundle_info(target)
        allowed = {'com.apple.security.device.audio-input': True,
                   'com.apple.security.device.camera': True,
                   'com.apple.security.automation.apple-events': True,
                   'com.apple.security.files.user-selected.read-write': True,
                   'com.apple.security.network.client': True,
                   'com.apple.security.personal-information.calendars': True,
                   'com.apple.security.app-sandbox': False}
        self.source_entitlements = allowed | {
            'com.apple.application-identifier': 'TEAM.com.openai.codex',
            'com.apple.developer.team-identifier': 'TEAM',
            'com.apple.security.application-groups': ['TEAM.group'],
            'keychain-access-groups': ['TEAM.*'],
            'com.apple.developer.aps-environment': 'production',
            'com.apple.developer.usernotifications.communication': True,
            'com.apple.security.cs.allow-dyld-environment-variables': True,
        }
        mac.seal_bundle(target, preserve_identity=True)
        after = mac.bundle_info(target)
        self.assertEqual({k:v for k,v in after.items() if k != 'ElectronAsarIntegrity'},
                         {k:v for k,v in before.items() if k != 'ElectronAsarIntegrity'})
        self.assertFalse((target/'Contents/Resources/codexflare.icns').exists())
        self.assertEqual(self.signed_entitlements, [allowed | {
            'com.apple.security.cs.allow-jit': True,
            'com.apple.security.cs.allow-unsigned-executable-memory': True,
            'com.apple.security.cs.disable-library-validation': True}])

    def test_invalid_original_entitlement_refuses_before_writing_bundle(self):
        target = self.root/'OriginalEntry.app'
        shutil.copytree(mac.SOURCE, target)
        before = (target/mac.PLIST).read_bytes()
        self.source_entitlements = {'com.apple.security.device.camera': 'yes'}
        with self.assertRaisesRegex(ValueError, '签名权限值'):
            mac.seal_bundle(target, preserve_identity=True)
        self.assertEqual((target/mac.PLIST).read_bytes(), before)
        self.assertFalse(self.signed_entitlements)

    def test_build_from_backup_does_not_depend_on_global_source(self):
        backup = self.root/'Backup.app'
        mac.SOURCE.rename(backup)
        before = mac.fingerprint(backup)
        target = self.root/'OriginalEntry.app'
        with patch.object(mac, 'patch_archive', side_effect=self.patch_archive) as patcher, \
                patch.object(mac.subprocess, 'check_output', return_value='arm64') as arch:
            source, metadata = mac.build_runtime(target, source=backup, preserve_identity=True)
        self.assertEqual(source, before)
        self.assertEqual(mac.fingerprint(backup), before)
        self.assertFalse(mac.SOURCE.exists())
        self.assertEqual(metadata['version'], patch_macos.VERSION)
        patcher.assert_called_once_with(backup/mac.ASAR, target/'Contents/Resources/app.patched.asar',
                                       platform='darwin', preserve_identity=True)
        arch.assert_called_once_with(['/usr/bin/lipo', '-archs', str(mac.executable(backup))], text=True)
        self.assertEqual(mac.bundle_info(target)['CFBundleIdentifier'], 'com.openai.codex')

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

    def test_original_identity_archive_keeps_protocol_registration(self):
        main = mac_main_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed, source = root/'seed.asar', root/'source.asar'
            asar(seed, {'package.json':json.dumps({
                'name':'openai-codex-electron', 'version':patch_macos.VERSION}).encode()})
            patch_app.Asar(seed).write_changes(source, {
                patch_macos.MAIN:main.encode(), 'webview/index.html':b'<head></head><body></body>',
                **{'webview/assets/'+name:(style_fixture() if name.endswith('.css') else b'preload fixture') for name in patch_macos.STARTUP_PRELOADS},
            })
            before = source.read_bytes()
            video = root/'video.webm'
            video.write_bytes(b'video fixture')
            with patch.object(patch_app, 'load_settings', return_value={
                    'video':'default', 'background':{'enabled':False}}), \
                    patch.object(patch_app, 'video_info', return_value={'duration':4}), \
                    patch.object(patch_app, 'video_path', return_value=video):
                for preserve in (False, True):
                    with self.subTest(preserve_identity=preserve):
                        target = root/f'target-{preserve}.asar'
                        patch_app.patch_archive(source, target, platform='darwin', preserve_identity=preserve)
                        patched = patch_app.Asar(target).read(patch_macos.MAIN).decode()
                        self.assertEqual('Ke.deepLinks.registerProtocolClient()' in patched, preserve)
                        self.assertIn('codexBootAnimation',patched)
            self.assertEqual(source.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, '唯一'):
            patch_macos.patch_main(main+'Ke.deepLinks.registerProtocolClient();', preserve_identity=True)

    def test_both_macos_builds_preserve_identity_without_version_gating(self):
        for version, build_number, main_path, electron, onboarding, equal, protocol in (
            ('26.1013.31256', '20586', '.vite/build/main-CLu1A25j.js', 'D', 'YPe', 'Fe', 'Ke'),
            ('26.1021.31345', '21828', '.vite/build/main-0FVbxCQU.js', 'O', 'A5e', 'q', 'We'),
        ):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                build = patch_macos.select_build(version, build_number)
                self.assertEqual(build['main'], main_path)
                main = mac_main_fixture(version)
                root = Path(directory)
                seed, source = root/'seed.asar', root/'source.asar'
                asar(seed, {'package.json': json.dumps({'name': 'openai-codex-electron',
                    'version': version, 'codexBuildNumber': build_number}).encode()})
                patch_app.Asar(seed).write_changes(source, {
                    main_path: main.encode(), 'webview/index.html': b'<head></head><body></body>',
                    **{'webview/assets/'+name: (style_fixture() if name.endswith('.css') else b'preload fixture') for name in build['preloads']},
                })
                video = root/'video.webm'
                video.write_bytes(b'video fixture')
                with patch.object(patch_app, 'load_settings', return_value={
                        'video': 'default', 'background': {'enabled': False}}), \
                        patch.object(patch_app, 'video_info', return_value={'duration': 4}), \
                        patch.object(patch_app, 'video_path', return_value=video):
                    for preserve in (False, True):
                        target = root/f'target-{preserve}.asar'
                        metadata = patch_app.patch_archive(source, target, platform='darwin', preserve_identity=preserve)
                        self.assertEqual(metadata['version'], version)
                        patched = patch_app.Asar(target).read(main_path).decode()
                        self.assertEqual(f'{protocol}.deepLinks.registerProtocolClient()' in patched, preserve)
                        self.assertIn('codexBootAnimation', patched)
                        html = patch_app.Asar(target).read('webview/index.html').decode()
                        for name in build['preloads']:
                            self.assertIn(name, html)
                other = '26.1021.31345' if version == '26.1013.31256' else '26.1013.31256'
                self.assertIn('codexBootAnimation', patch_macos.patch_main(main, version=other))
                with self.assertRaisesRegex(ValueError, '唯一'):
                    patch_macos.patch_main(main + f'{protocol}.deepLinks.registerProtocolClient();',
                                           version=version, preserve_identity=True)

    def test_both_builds_use_their_own_background_resources(self):
        style = (patch_app.ROOT/'src/background.css').read_text()
        fixture = (patch_app.ROOT/'tests/background_fixture.html').read_text()
        for version, workspace, composer in (('26.1013.31256','etoz9','5est5'), ('26.1021.31345','azz1c','1q7o3')):
            with self.subTest(version=version):
                archive = mac_style_archive(version)
                layout = BackgroundLayout(archive)
                patched = layout.adapt(style)
                self.assertIn(f'._WorkspaceContent_{workspace}_2::before', patched)
                self.assertIn(f'._ComposerLayoutRoot_{composer}_2', patched)
                self.assertIn('._background_106nk_2._fade_106nk_2.from-surface', patched)
                adapted = layout.fixture(fixture)
                self.assertIn(f'class="_MainContentSurface_{workspace}_2"', adapted)
                self.assertEqual(adapted.count(f'composer _ComposerLayoutRoot_{composer}_2'), 2)
                self.assertEqual(adapted.count('_background_106nk_2 _fade_106nk_2'), 2)
                self.assertEqual(adapted.count('_background_106nk_2 _surface_106nk_2'), 2)
                with self.assertRaisesRegex(ValueError, 'Unexpected footer fixture'):
                    layout.fixture(fixture.replace('bg-gradient-to-t','changed-footer',1))
                archive.data = {name:css.replace(f'._ComposerLayoutRoot_{composer}_2','.changed')
                                for name,css in archive.data.items()}
                with self.assertRaisesRegex(ValueError, 'ComposerLayoutRoot'):
                    BackgroundLayout(archive)

    @unittest.skipUnless(sys.platform=='darwin','Darwin renamex_np')
    def test_native_directory_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a',Path(directory)/'b'
            a.mkdir(); b.mkdir(); (a/'a').touch(); (b/'b').touch()
            mac.swap_directory(a,b)
            self.assertTrue((a/'b').exists()); self.assertTrue((b/'a').exists())


if __name__=='__main__': unittest.main()
