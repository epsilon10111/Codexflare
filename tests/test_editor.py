import http.client
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from tools import animation, background, editor

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
                    '0000000b49444154789c63f80f040009fb03fdfb5e6b2b0000000049454e44ae426082')


class EditorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.local = Path(temporary.name)
        for key, value in {'LOCAL': self.local, 'MEDIA': self.local / 'media',
                           'SETTINGS': self.local / 'animation.json'}.items():
            mock = patch.object(animation, key, value)
            mock.start()
            self.addCleanup(mock.stop)
        (self.local / 'assets').mkdir()
        for name in ('default1.png', 'default2.png'):
            (self.local / 'assets' / name).write_bytes(PNG)
        image_root = patch.object(background, 'ROOT', self.local)
        image_root.start()
        self.addCleanup(image_root.stop)
        status = patch.object(editor, 'installation_status', return_value={
            'active': False, 'available': True, 'running': False, 'message': '尚未安装'})
        status.start()
        self.addCleanup(status.stop)
        self.server = editor.EditorServer()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, headers=None, token=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        self.addCleanup(connection.close)
        values = {'X-Editor-Token': self.server.token} if token else {}
        values.update(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body)
            values['Content-Type'] = 'application/json'
        connection.request(method, path, body=body, headers=values)
        response = connection.getresponse()
        data = response.read()
        if response.getheader('Content-Type', '').startswith('application/json'):
            data = json.loads(data)
        return response.status, data, response

    def test_state_and_settings_persist_without_applying(self):
        status, state, _ = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(state['token'], self.server.token)
        self.assertEqual(state['videos'][0]['url'], '/media/default')
        self.assertEqual([image['id'] for image in state['images']], ['default', 'default2'])
        self.assertEqual(self.request('GET', '/background/default')[1], PNG)
        self.assertEqual(self.request('GET', '/background/default2')[1], PNG)
        with patch.object(editor.manage, 'install') as install:
            status, data, _ = self.request('POST', '/api/settings', {
                'speed': 0.5, 'brightness': 1.25, 'windowMode': 'centered', 'muted': False,
                'background': {'image': 'default2'}})
            self.assertEqual(status, 200)
            self.assertEqual(data['settings'], animation.load_settings())
            install.assert_not_called()
        _, state, _ = self.request('GET', '/api/state')
        self.assertEqual(state['settings']['speed'], 0.5)
        self.assertEqual(state['settings']['windowMode'], 'centered')
        self.assertFalse(state['settings']['muted'])
        self.assertEqual(state['settings']['background']['image'], 'default2')

    def test_background_upload_preview_save_and_install(self):
        animation.save_settings({'speed': 0.75})
        before = animation.SETTINGS.read_bytes()
        status, result, _ = self.request('POST', '/api/background/upload', PNG,
                                         {'X-Filename': '%E8%83%8C%E6%99%AF.png'})
        self.assertEqual(status, 200, result)
        image_id = hashlib.sha256(PNG).hexdigest()
        expected = {'id': image_id, 'name': '背景.png', 'width': 1, 'height': 1,
                    'url': '/background/' + image_id}
        self.assertEqual(result['image'], expected)
        path = background.image_path(image_id, self.local)
        self.assertEqual(path.read_bytes(), PNG)
        if sys.platform != 'win32':
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.with_suffix('.json').stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        self.assertEqual(self.request('GET', expected['url'])[1], PNG)
        self.assertEqual(self.request('GET', '/api/state')[1]['images'][2:], [expected])
        settings = {'background': {'image': image_id, 'opacity': 0.25, 'position': 85, 'scale': 90}}
        self.assertEqual(self.request('POST', '/api/settings', settings)[0], 200)
        with patch.object(editor.manage, 'running_pids', return_value=[]), \
                patch.object(editor.manage, 'fingerprint', return_value={'version': editor.manage.VERSION, 'build': getattr(editor.manage, 'BUILD', None)}), \
                patch.object(editor.manage, 'install') as install:
            self.assertEqual(self.request('POST', '/api/install', settings)[0], 200)
            install.assert_called_once_with()
        self.assertEqual(animation.load_settings()['background'], background.DEFAULT_SETTINGS | settings['background'])

    def test_background_upload_validation_and_legacy_recovery(self):
        (self.local / 'background.png').write_bytes(PNG)
        _, state, _ = self.request('GET', '/api/state')
        self.assertEqual([image['id'] for image in state['images']], ['default', 'default2', 'legacy'])
        self.assertEqual(self.request('GET', '/background/legacy')[1], PNG)
        animation.save_settings({'background': {'image': 'legacy'}})
        before = animation.SETTINGS.read_bytes()
        self.assertEqual(self.request('POST', '/api/background/upload', PNG, token=False)[0], 403)
        for data in (b'not a png', PNG[:-1], PNG + b'extra'):
            self.assertEqual(self.request('POST', '/api/background/upload', data)[0], 400)
        self.assertEqual(self.request('POST', '/api/background/upload', b'',
                                      {'Content-Length': str(background.MAX_UPLOAD + 1)})[0], 413)
        self.assertEqual(self.request('GET', '/background/../../README.md')[0], 400)
        self.assertEqual(self.request('POST', '/api/settings', {'background': {'image': 'a' * 64}})[0], 400)
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        self.assertFalse((self.local / 'backgrounds').exists())
        (self.local / 'background.png').write_bytes(b'broken')
        _, state, _ = self.request('GET', '/api/state')
        self.assertTrue(state['warning'])
        self.assertFalse(state['settings']['background']['enabled'])
        self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_changed_imported_image_is_rejected_before_saving(self):
        image = editor.import_image(PNG, 'test.png')
        animation.save_settings({'background': {'image': image['id']}})
        before = animation.SETTINGS.read_bytes()
        background.image_path(image['id'], self.local).write_bytes(b'corrupt image')
        self.assertEqual(self.request('POST', '/api/settings', {'background': {'image': image['id']}})[0], 400)
        self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_local_origin_and_write_token_required(self):
        self.assertEqual(self.request('POST', '/api/settings', {}, token=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertFalse(animation.SETTINGS.exists())

    def test_invalid_requests_leave_saved_settings_intact(self):
        animation.save_settings({'brightness': 1.5})
        before = animation.SETTINGS.read_bytes()
        for body in ('[]', '{', '{"speed":NaN}', '{"speed":true}', '{"video":"../../etc/passwd"}',
                     '{"windowMode":"unknown"}', '{"muted":1}'):
            self.assertEqual(self.request('POST', '/api/settings', body)[0], 400)
        self.assertEqual(self.request('POST', '/api/upload', b'',
                                      {'Content-Length': str(editor.MAX_UPLOAD + 1)})[0], 413)
        self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_ranges_and_path_traversal(self):
        video = animation.video_path('default').read_bytes()
        status, data, response = self.request('GET', '/media/default', headers={'Range': 'bytes=2-15'})
        self.assertEqual((status, data), (206, video[2:16]))
        self.assertEqual(response.getheader('Content-Range'), f'bytes 2-15/{len(video)}')
        self.assertEqual(self.request('GET', '/media/default', headers={'Range': 'bytes=-8'})[1], video[-8:])
        for header in ('bytes=-0', 'bytes=20-10', 'bytes=0-1,2-3', 'bytes=999999999-'):
            self.assertEqual(self.request('GET', '/media/default', headers={'Range': header})[0], 416)
        self.assertEqual(self.request('GET', '/media/../../README.md')[0], 400)
        self.assertEqual(self.request('GET', '/tools/manage.py')[0], 404)

    def test_running_runtime_blocks_install_before_saving(self):
        with patch.object(editor.manage, 'running_pids', return_value=[123]), \
                patch.object(editor.manage, 'install') as install:
            self.assertEqual(self.request('POST', '/api/install', {'speed': 2})[0], 409)
            install.assert_not_called()
        self.assertFalse(animation.SETTINGS.exists())

    def test_install_and_uninstall_delegate_to_existing_manager(self):
        with patch.object(editor.manage, 'running_pids', return_value=[]), \
                patch.object(editor.manage, 'fingerprint', return_value={'version': editor.manage.VERSION, 'build': getattr(editor.manage, 'BUILD', None)}), \
                patch.object(editor.manage, 'install') as install, \
                patch.object(editor.manage, 'uninstall') as uninstall:
            self.assertEqual(self.request('POST', '/api/install', {'speed': 2})[0], 200)
            install.assert_called_once_with()
            self.assertEqual(animation.load_settings()['speed'], 2)
            self.assertEqual(self.request('POST', '/api/uninstall', {})[0], 200)
            uninstall.assert_called_once_with()

    def test_macos_install_accepts_both_builds_but_rejects_mismatched_build(self):
        from tools import manage_macos as mac
        with patch.object(editor, 'manage', mac), \
                patch.object(editor, 'original_manager', return_value=None), \
                patch.object(mac, 'running_pids', return_value=[]), \
                patch.object(mac, 'install') as install:
            for version, build in (('26.1013.31256', '20586'), ('26.1021.31345', '21828')):
                with self.subTest(build=build), patch.object(mac, 'fingerprint', return_value={'version': version, 'build': build}):
                    status, data, _ = self.request('POST', '/api/install', {'speed': 1})
                    self.assertEqual(status, 200, data)
            self.assertEqual(install.call_count, 2)
            with patch.object(mac, 'fingerprint', return_value={'version': '26.1021.31345', 'build': '20586'}):
                status, data, _ = self.request('POST', '/api/install', {'speed': 1})
                self.assertEqual(status, 400, data)
                self.assertIn('21828', data['error'])
            self.assertEqual(install.call_count, 2)

    def test_install_preserves_platform_launch_hint(self):
        with patch.object(editor.manage, 'running_pids', return_value=[]), \
                patch.object(editor.manage, 'fingerprint', return_value={'version': editor.manage.VERSION, 'build': getattr(editor.manage, 'BUILD', None)}), \
                patch.object(editor.manage, 'install'), \
                patch.object(editor.manage, 'LAUNCH_HINT', '从开始菜单打开 Codexflare Codex。', create=True):
            status, data, _ = self.request('POST', '/api/install', {'speed': 1})
        self.assertEqual(status, 200, data)
        self.assertIn('从开始菜单打开 Codexflare Codex。', data['message'])

    def test_original_mode_prepares_settings_while_chatgpt_is_running(self):
        original = MagicMock()
        original.status.return_value = {
            'mode': 'original', 'phase': 'queued', 'active': False, 'available': True,
            'running': True, 'pending': True, 'queued': True,
            'message': '已准备，退出 ChatGPT 后自动应用；下次从原图标启动生效。'}
        def prepare():
            self.assertEqual(animation.load_settings()['speed'], 1.6)
            self.assertEqual(animation.load_settings()['windowMode'], 'fullscreen')
        original.prepare.side_effect = prepare
        with patch.object(editor, 'original_manager', return_value=original), \
                patch.object(editor.manage, 'running_pids', return_value=[123]), \
                patch.object(editor.manage, 'install') as install:
            status, data, _ = self.request('POST', '/api/install', {'speed': 1.6, 'windowMode': 'fullscreen'})
        self.assertEqual(status, 200, data)
        self.assertEqual(data['settings']['speed'], 1.6)
        self.assertTrue(data['installation']['pending'])
        self.assertTrue(data['installation']['running'])
        self.assertIn('退出 ChatGPT 后自动应用', data['message'])
        original.prepare.assert_called_once_with()
        original.launch_worker.assert_called_once_with()
        original.activate_pending.assert_not_called()
        install.assert_not_called()

    def test_original_mode_restore_queues_without_changing_saved_settings(self):
        animation.save_settings({'speed': 1.6})
        before = animation.SETTINGS.read_bytes()
        original = MagicMock()
        original.status.return_value = {
            'mode': 'original', 'phase': 'queued', 'active': True, 'available': True,
            'running': True, 'pending': True, 'message': '已准备恢复原版，退出 ChatGPT 后自动应用。'}
        with patch.object(editor, 'original_manager', return_value=original), \
                patch.object(editor.manage, 'uninstall') as uninstall:
            status, data, _ = self.request('POST', '/api/uninstall', {})
        self.assertEqual(status, 200, data)
        self.assertTrue(data['installation']['pending'])
        self.assertIn('恢复原版', data['message'])
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        original.uninstall.assert_called_once_with()
        original.launch_worker.assert_called_once_with()
        original.activate_pending.assert_not_called()
        uninstall.assert_not_called()

    def test_failed_original_preparation_preserves_settings_without_starting_worker(self):
        original = MagicMock()
        original.prepare.side_effect = ValueError('来源改变')
        with patch.object(editor, 'original_manager', return_value=original):
            status, data, _ = self.request('POST', '/api/install', {'speed': 1.6})
        self.assertEqual(status, 400)
        self.assertIn('配置已保存，但尚未应用', data['error'])
        self.assertEqual(animation.load_settings()['speed'], 1.6)
        original.launch_worker.assert_not_called()

    def test_saving_original_mode_settings_does_not_prepare_or_activate(self):
        with patch.object(editor, 'original_manager') as route:
            status, data, _ = self.request('POST', '/api/settings', {'speed': 1.6})
        self.assertEqual(status, 200, data)
        self.assertEqual(animation.load_settings()['speed'], 1.6)
        route.assert_not_called()

    def test_busy_and_broken_settings_are_recoverable(self):
        with self.server.write_lock:
            self.assertEqual(self.request('POST', '/api/settings', {})[0], 409)
        animation.SETTINGS.write_text('broken')
        status, state, _ = self.request('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertTrue(state['warning'])
        self.assertEqual(state['settings'], animation.DEFAULT_SETTINGS)
        self.assertEqual(animation.SETTINGS.read_text(), 'broken')
        self.assertEqual(self.request('POST', '/api/settings', {})[0], 200)

    def test_failed_install_preserves_saved_settings_and_reports_failure(self):
        with patch.object(editor.manage, 'running_pids', return_value=[]), \
                patch.object(editor.manage, 'fingerprint', return_value={'version': editor.manage.VERSION, 'build': getattr(editor.manage, 'BUILD', None)}), \
                patch.object(editor.manage, 'install', side_effect=ValueError('来源改变')):
            status, data, _ = self.request('POST', '/api/install', {'speed': 0.5})
        self.assertEqual(status, 400)
        self.assertIn('配置已保存，但尚未应用', data['error'])
        self.assertEqual(animation.load_settings()['speed'], 0.5)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), '需要 FFmpeg')
    def test_real_upload_conversion_and_invalid_media(self):
        source = self.local / 'tiny.webm'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=64x48:r=10:d=0.5', '-c:v', 'libvpx-vp9', str(source)], check=True)
        status, data, _ = self.request('POST', '/api/upload', source.read_bytes(), {'X-Filename': 'tiny.webm'})
        self.assertEqual(status, 200, data)
        video = data['video']
        self.assertEqual((video['width'], video['height']), (64, 48))
        self.assertTrue(animation.video_path(video['id']).is_file())
        tracks = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                                 '-show_entries', 'stream=codec_name', '-of', 'json',
                                 str(animation.video_path(video['id']))],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(tracks.stdout)['streams'], [])
        if sys.platform != 'win32':
            self.assertEqual(stat.S_IMODE(animation.video_path(video['id']).stat().st_mode), 0o600)
        self.assertFalse(animation.SETTINGS.exists())
        self.assertEqual(self.request('POST', '/api/settings', {'video': video['id']})[0], 200)
        _, state, _ = self.request('GET', '/api/state')
        self.assertEqual(state['videos'][1]['id'], video['id'])
        self.assertEqual(self.request('POST', '/api/settings', {'video': 'default'})[0], 200)
        self.assertEqual(self.request('GET', '/api/state')[1]['videos'][1]['id'], video['id'])
        self.assertEqual(self.request('POST', '/api/settings', {'video': video['id']})[0], 200)
        before = animation.SETTINGS.read_bytes()
        self.assertEqual(self.request('POST', '/api/upload', b'not video', {'X-Filename': 'bad.webm'})[0], 400)
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        animation.video_path(video['id']).unlink()
        _, recovered, _ = self.request('GET', '/api/state')
        self.assertTrue(recovered['warning'])
        self.assertEqual(recovered['settings']['video'], 'default')
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        self.assertFalse(list(self.local.glob('upload-*')))
        self.assertFalse(list(animation.MEDIA.glob('convert-*')))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), '需要 FFmpeg')
    def test_audio_survives_import_at_duration_limit(self):
        source = self.local / 'audio.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=blue:s=64x48:r=10:d=30', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=30', '-c:v', 'mpeg4', '-c:a', 'aac',
                        '-t', '30', str(source)], check=True)
        status, result, _ = self.request('POST', '/api/upload', source.read_bytes(), {'X-Filename': 'audio.mp4'})
        self.assertEqual(status, 200, result)
        video = result['video']
        self.assertLessEqual(video['duration'], animation.MAX_ENCODED_DURATION)
        self.assertGreaterEqual(video['duration'], 30)
        output = animation.video_path(video['id'])
        tracks = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a',
                                 '-show_entries', 'stream=codec_name', '-of', 'json', str(output)],
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(tracks.stdout)['streams'], [{'codec_name': 'opus'}])
        self.assertEqual(self.request('POST', '/api/settings', {'video': video['id'], 'muted': False})[0], 200)
        self.assertFalse(animation.load_settings()['muted'])


class EditorRoutingTests(unittest.TestCase):
    def test_original_mode_requires_macos_and_explicit_marker(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(animation, 'LOCAL', Path(directory)):
            with patch.object(editor.sys, 'platform', 'darwin'):
                self.assertIsNone(editor.original_manager())
            (animation.LOCAL / 'original-install.json').touch()
            with patch.object(editor.sys, 'platform', 'linux'):
                self.assertIsNone(editor.original_manager())

    def test_frozen_macos_uses_original_mode_before_the_first_install(self):
        from tools import original_macos
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(animation, 'LOCAL', Path(directory)), \
                patch.object(editor.sys, 'frozen', True, create=True):
            with patch.object(editor.sys, 'platform', 'darwin'):
                self.assertIs(editor.original_manager(), original_macos)
            with patch.object(editor.sys, 'platform', 'linux'):
                self.assertIsNone(editor.original_manager())

    def test_original_status_preserves_pending_and_running_independently(self):
        original = MagicMock()
        original.status.return_value = {'mode': 'original', 'active': True, 'available': True,
                                        'pending': True, 'running': True, 'message': '等待 ChatGPT 退出'}
        with patch.object(editor, 'original_manager', return_value=original), \
                patch.object(editor.manage, 'read_state') as read_state:
            self.assertEqual(editor.installation_status(), original.status.return_value)
        original.status.assert_called_once_with()
        read_state.assert_not_called()


if __name__ == '__main__':
    unittest.main()
