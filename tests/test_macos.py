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

    def test_mismatched_build_and_architecture_rejected(self):
        info = mac.fingerprint(); info['build'] = '99999'
        with self.assertRaises(ValueError): mac.require_supported(info)
        with patch.object(mac.subprocess, 'check_output', return_value='x86_64'):
            with self.assertRaises(ValueError): mac.require_supported(mac.fingerprint())

    def test_supported_versions_require_their_exact_build_numbers(self):
        for version, build in (('26.1013.31256', '20586'), ('26.1021.31345', '21828')):
            source = mac.fingerprint() | {'version': version, 'build': build}
            with self.subTest(version=version):
                self.assertTrue(mac.supported_source(source))
                mac.require_supported(source)
                for bad in ({'build': '99999'}, {'build': None}, {'version': '26.9999.99999'}):
                    self.assertFalse(mac.supported_source(source | bad))
                    with self.assertRaises(ValueError):
                        mac.require_supported(source | bad)
        self.assertFalse(mac.supported_source({'version': '26.1013.31256', 'build': '21828'}))
        self.assertFalse(mac.supported_source({'version': '26.1021.31345', 'build': '20586'}))
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
        main = ('await z.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}));'
                'V.createPrimaryWindow({title:D.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n});'
                'minWidth:A?.width,minHeight:A?.height,webPreferences:F},z=new D.BrowserWindow(R);'
                'let i=YPe(t);if((0,Fe.default)(this.primaryWindowMode,t)){};'
                'Ke.deepLinks.registerProtocolClient();')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed, source = root/'seed.asar', root/'source.asar'
            asar(seed, {'package.json':json.dumps({
                'name':'openai-codex-electron', 'version':patch_macos.VERSION}).encode()})
            patch_app.Asar(seed).write_changes(source, {
                patch_macos.MAIN:main.encode(), 'webview/index.html':b'<head></head><body></body>',
                **{'webview/assets/'+name:b'preload fixture' for name in patch_macos.STARTUP_PRELOADS},
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

    def test_background_targets_current_workspace_and_composer_classes(self):
        style = (patch_app.ROOT/'src/background.css').read_text(encoding='utf-8')
        class Archive:
            def read(self, name):
                return {
                    'webview/assets/app-shared-ae384120d279.css': b':root {}',
                    'webview/assets/app-initial-e7c27dd40beb.css': (
                        b'._WorkspaceContent_etoz9_2{}._MainContentSurface_etoz9_2{}'
                        b'._MainContentViewport_etoz9_2{}._ComposerLayoutRoot_5est5_2{}'
                        b'._background_106nk_2{}._fade_106nk_2{}._surface_106nk_2{}'),
                    'webview/assets/thread-scroll-layout-24b9bd243051.css': b'._compactScrollMask_121j8_2{}',
                }[name]
        patched=patch_macos.patch_background_css(style,Archive())
        self.assertIn('._WorkspaceContent_etoz9_2::before',patched)
        self.assertIn('._ComposerLayoutRoot_5est5_2',patched)
        self.assertIn('._background_106nk_2._fade_106nk_2.from-surface',patched)
        self.assertNotIn('_WorkspaceContent_yl8z4_2',patched)
        self.assertNotIn('_ComposerLayoutRoot_15oep_2',patched)
        self.assertIn('mix-blend-mode: screen',patched)
        self.assertIn('pointer-events: none',patched)

    def test_background_fixture_uses_reviewed_macos_footer_and_workspace(self):
        fixture = (patch_app.ROOT/'tests/background_fixture.html').read_text()
        patched = patch_macos.adapt_background_fixture(fixture)
        self.assertIn('class="_MainContentSurface_etoz9_2"',patched)
        self.assertIn('class="_MainContentViewport_etoz9_2"',patched)
        self.assertEqual(patched.count('composer _ComposerLayoutRoot_5est5_2'),2)
        self.assertEqual(patched.count('_background_106nk_2 _fade_106nk_2'),2)
        self.assertEqual(patched.count('_background_106nk_2 _surface_106nk_2'),2)
        self.assertNotIn('bg-gradient-to-t from-surface',patched)
        with self.assertRaisesRegex(ValueError,'Unexpected footer fixture structure'):
            patch_macos.adapt_background_fixture(fixture.replace('bg-gradient-to-t','changed-footer',1))

    def test_background_rejects_unreviewed_css_modules(self):
        class Archive:
            def read(self,name): return b'.new-module {}'
        with self.assertRaisesRegex(ValueError,'Background selector missing'):
            patch_macos.patch_background_css('body {}',Archive())

    def test_archive_selects_exact_macos_build_and_rejects_mixed_anchors(self):
        for version, build_number, main_path, electron, onboarding, equal, protocol in (
            ('26.1013.31256', '20586', '.vite/build/main-CLu1A25j.js', 'D', 'YPe', 'Fe', 'Ke'),
            ('26.1021.31345', '21828', '.vite/build/main-0FVbxCQU.js', 'O', 'A5e', 'q', 'We'),
        ):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                build = patch_macos.select_build(version, build_number)
                self.assertEqual(build['main'], main_path)
                main = ('await z.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}));'
                        f'V.createPrimaryWindow({{title:{electron}.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n}});'
                        f'minWidth:A?.width,minHeight:A?.height,webPreferences:F}},z=new {electron}.BrowserWindow(R);'
                        f'let i={onboarding}(t);if((0,{equal}.default)(this.primaryWindowMode,t)){{}};'
                        f'{protocol}.deepLinks.registerProtocolClient();')
                root = Path(directory)
                seed, source = root/'seed.asar', root/'source.asar'
                asar(seed, {'package.json': json.dumps({'name': 'openai-codex-electron',
                    'version': version, 'codexBuildNumber': build_number}).encode()})
                patch_app.Asar(seed).write_changes(source, {
                    main_path: main.encode(), 'webview/index.html': b'<head></head><body></body>',
                    **{'webview/assets/'+name: b'preload fixture' for name in build['preloads']},
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
                with self.assertRaises(ValueError):
                    patch_macos.patch_main(main, version=other)
                with self.assertRaisesRegex(ValueError, '唯一'):
                    patch_macos.patch_main(main + f'{protocol}.deepLinks.registerProtocolClient();',
                                           version=version, preserve_identity=True)

    def test_both_builds_use_their_own_background_resources(self):
        style = (patch_app.ROOT/'src/background.css').read_text()
        fixture = (patch_app.ROOT/'tests/background_fixture.html').read_text()
        for version, workspace, composer, mask in (
            ('26.1013.31256', 'etoz9', '5est5', '121j8'),
            ('26.1021.31345', 'azz1c', '1q7o3', 'mpt93'),
        ):
            with self.subTest(version=version):
                build = patch_macos.select_build(version)
                css = (f'._WorkspaceContent_{workspace}_2{{}}._MainContentSurface_{workspace}_2{{}}'
                       f'._MainContentViewport_{workspace}_2{{}}._ComposerLayoutRoot_{composer}_2{{}}'
                       f'._compactScrollMask_{mask}_2{{}}._background_106nk_2{{}}._fade_106nk_2{{}}._surface_106nk_2{{}}')
                files = {'webview/assets/'+name: css.encode() for name in build['background_styles']}
                class Archive:
                    def read(self, name):
                        return files[name]
                patched = patch_macos.patch_background_css(style, Archive(), version=version)
                self.assertIn(f'._WorkspaceContent_{workspace}_2::before', patched)
                self.assertIn(f'._ComposerLayoutRoot_{composer}_2', patched)
                adapted = patch_macos.adapt_background_fixture(fixture, version=version)
                self.assertIn(f'class="_MainContentSurface_{workspace}_2"', adapted)
                self.assertEqual(adapted.count(f'composer _ComposerLayoutRoot_{composer}_2'), 2)
                files = {name: data.replace(f'._ComposerLayoutRoot_{composer}_2'.encode(), b'.changed')
                         for name, data in files.items()}
                with self.assertRaisesRegex(ValueError, 'Background selector missing'):
                    patch_macos.patch_background_css(style, Archive(), version=version)

    @unittest.skipUnless(sys.platform=='darwin','Darwin renamex_np')
    def test_native_directory_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            a,b=Path(directory)/'a',Path(directory)/'b'
            a.mkdir(); b.mkdir(); (a/'a').touch(); (b/'b').touch()
            mac.swap_directory(a,b)
            self.assertTrue((a/'b').exists()); self.assertTrue((b/'a').exists())


if __name__=='__main__': unittest.main()
