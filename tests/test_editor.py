import http.client
import json
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import animation, editor


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
        with patch.object(editor.manage, 'install') as install:
            status, data, _ = self.request('POST', '/api/settings', {'speed': 0.5, 'brightness': 1.25})
            self.assertEqual(status, 200)
            self.assertEqual(data['settings'], animation.load_settings())
            install.assert_not_called()
        _, state, _ = self.request('GET', '/api/state')
        self.assertEqual(state['settings']['speed'], 0.5)

    def test_local_origin_and_write_token_required(self):
        self.assertEqual(self.request('POST', '/api/settings', {}, token=False)[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/api/state', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertFalse(animation.SETTINGS.exists())

    def test_invalid_requests_leave_saved_settings_intact(self):
        animation.save_settings({'brightness': 1.5})
        before = animation.SETTINGS.read_bytes()
        for body in ('[]', '{', '{"speed":NaN}', '{"speed":true}', '{"video":"../../etc/passwd"}'):
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
                patch.object(editor.manage, 'fingerprint', return_value={'version': editor.manage.VERSION}), \
                patch.object(editor.manage, 'install') as install, \
                patch.object(editor.manage, 'uninstall') as uninstall:
            self.assertEqual(self.request('POST', '/api/install', {'speed': 2})[0], 200)
            install.assert_called_once_with()
            self.assertEqual(animation.load_settings()['speed'], 2)
            self.assertEqual(self.request('POST', '/api/uninstall', {})[0], 200)
            uninstall.assert_called_once_with()

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
                patch.object(editor.manage, 'fingerprint', return_value={'version': editor.manage.VERSION}), \
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


if __name__ == '__main__':
    unittest.main()
