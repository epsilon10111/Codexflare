from collections import deque
from contextlib import nullcontext
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools import animation, windows_inject as inject


def attached(url='', session='page-1', kind='page'):
    return {'method': 'Target.attachedToTarget', 'params': {'sessionId': session,
            'waitingForDebugger': True, 'targetInfo': {'targetId': 'target-' + session, 'type': kind, 'url': url}}}


class WindowsInjectionTests(unittest.TestCase):
    def test_auto_attach_never_pauses_original_app_startup(self):
        transport = Mock()
        inject.Injector(transport, 'guard', {}).start()
        transport.call.assert_called_once_with('Target.setAutoAttach', {
            'autoAttach': True, 'waitForDebuggerOnStart': False,
            'flatten': True, 'filter': [{'type': 'page'}, {'exclude': True}]})

    def test_only_root_primary_document_is_eligible(self):
        for url in ('app://-/index.html', 'app://-/index.html?initialRoute=%2F'):
            self.assertTrue(inject.main_url(url))
        for url in ('', 'about:blank', 'https://example.com/index.html', 'app://fs/index.html',
                    'app://-/detached-window.html', 'app://-/index.html?initialRoute=/avatar-overlay',
                    'app://-/index.html?initialRoute=/&initialRoute=/page/test'):
            self.assertFalse(inject.main_url(url), url)

    def test_prepare_script_uses_validated_data_without_changing_settings_or_csp(self):
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder)
            video = local / 'video.webm'
            video.write_bytes(b'fixture video')
            package = {'name': 'openai-codex-electron', 'version': '26.1021.31345',
                       'codexBuildNumber': '21828', 'codexWindowsPackageIdentity': 'OpenAI.Codex'}
            settings = animation.validate_settings({'background': {'enabled': False}})
            before = json.dumps(settings)
            with patch.object(inject, 'Asar') as archive, \
                    patch.object(animation, 'video_info', return_value={'duration': 1}), \
                    patch.object(animation, 'video_path', return_value=video):
                archive.return_value.read.return_value = json.dumps(package).encode()
                script = inject.prepare_script(local, settings, local)
            self.assertEqual(json.dumps(settings), before)
            self.assertIn('data:video/webm;base64,', script)
            self.assertIn('window !== window.top', script)
            self.assertIn("sessionStorage.getItem('codexflare:launch')", script)
            self.assertNotIn('document.currentScript', script)
            self.assertNotIn('Content-Security-Policy', script)
            self.assertNotIn('setBypassCSP', script)
            result = subprocess.run(['node', '--check'], input=script, capture_output=True,
                                    text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_background_blob_is_shared_by_css_and_preload_for_both_decoders(self):
        image = bytes(range(256))
        scripts = []
        with patch.object(inject, 'Asar') as archive, \
                patch.object(inject.patch_windows, 'select_build', return_value=SimpleNamespace(patch_background_css=None)), \
                patch.object(animation, 'video_info', return_value={'duration': 1}), \
                patch.object(animation, 'video_path', return_value=SimpleNamespace(read_bytes=lambda: b'video')), \
                patch.object(inject.background, 'load_selected') as selected, \
                patch.object(inject.background, 'prepare_image', return_value=(image, {})):
            archive.return_value.read.return_value = b'{}'
            for enabled in (True, False):
                selected.return_value = (image, {}) if enabled else (None, None)
                scripts.append(inject.prepare_script(Path('source'), {'background': {'enabled': enabled}}, Path('local')))
        harness = r'''
const assert = require('node:assert/strict'), vm = require('node:vm');
const scripts = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
(async () => {
  for (const fast of [true, false]) for (const [index, script] of scripts.entries()) {
    const enabled = index === 0, nodes = new Map(), blobs = [];
    let fastCalls = 0, fallbackCalls = 0;
    class Bytes extends Uint8Array {}
    Bytes.fromBase64 = fast ? value => { fastCalls++; return new Uint8Array(Buffer.from(value, 'base64')); } : undefined;
    class LocalURL extends URL {
      static createObjectURL(blob) { blobs.push(blob); return 'blob:app://-/regression'; }
    }
    const window = {}; window.top = window;
    vm.runInNewContext(script, {window, location: {href: 'app://-/index.html'}, URL: LocalURL, Blob,
      Uint8Array: Bytes, atob(value) { fallbackCalls++; return atob(value); },
      document: {documentElement: {append(node) { nodes.set(node.id, node); }},
        createElement: tag => ({tag}), getElementById: id => nodes.get(id) || null},
      performance: {now: () => 0}, setTimeout() {},
      sessionStorage: {getItem() { throw Error('Disable animation in this fixture'); }}}, {timeout: 1000});
    assert.equal(blobs.length, Number(enabled));
    assert.equal(fastCalls, Number(enabled && fast));
    assert.equal(fallbackCalls, Number(enabled && !fast));
    const css = nodes.get('codexflare-style').textContent;
    assert.equal(css.includes('blob:app://-/regression'), enabled);
    assert.equal(nodes.has('codex-background-preload'), enabled);
    if (enabled) {
      assert.equal(blobs[0].type, 'image/png'); assert.equal(blobs[0].size, 256);
      assert.deepEqual(Buffer.from(await blobs[0].arrayBuffer()), Buffer.from(Array.from({length: 256}, (_, i) => i)));
      assert.equal(nodes.get('codex-background-preload').href, 'blob:app://-/regression');
      assert.ok(css.includes('url("blob:app://-/regression")'));
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
'''
        result = subprocess.run(['node', '-e', harness], input=json.dumps(scripts), capture_output=True,
                                text=True, encoding='utf-8', timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_session_preserves_environment_unless_test_profile_is_explicit(self):
        with patch.dict(sys.modules, {'msvcrt': SimpleNamespace(get_osfhandle=lambda fd: fd)}), \
                patch.object(subprocess, 'STARTUPINFO', SimpleNamespace, create=True), \
                patch.object(subprocess, 'CREATE_NO_WINDOW', 0, create=True), \
                patch.object(subprocess, 'Popen') as start, \
                patch.object(inject.threading, 'Thread'), \
                patch.dict(os.environ, {'UNCHANGED': 'yes', 'CODEX_HOME': 'existing-home'}, clear=True):
            start.return_value.poll.return_value = 0
            ordinary = inject.Session(Path('official'), arguments=('codex://test',))
            try:
                command, = start.call_args.args
                self.assertEqual(start.call_args.kwargs['env'], {'UNCHANGED': 'yes', 'CODEX_HOME': 'existing-home'})
                self.assertFalse(any(arg.startswith('--user-data-dir') for arg in command))
                self.assertIn('codex://test', command)
                self.assertNotIn('--remote-debugging-port', ' '.join(command))
                self.assertEqual(len(start.call_args.kwargs['startupinfo'].lpAttributeList['handle_list']), 2)
            finally:
                ordinary.close()
            test = inject.Session(Path('official'), test_profile=Path('test-profile'))
            try:
                self.assertIn('test-profile', start.call_args.kwargs['env']['CODEX_HOME'])
                self.assertIn('CODEX_ELECTRON_USER_DATA_PATH', start.call_args.kwargs['env'])
            finally:
                test.close()
            for argument in ('--remote-debugging-port=9222', '-remote-debugging-port=9222',
                             '/remote-debugging-port=9222', '--REMOTE-DEBUGGING-PIPE'):
                with self.subTest(argument=argument), self.assertRaises(ValueError):
                    inject.Session(Path('official'), arguments=(argument,))

    def test_pipe_handles_partial_writes_and_interleaved_events(self):
        session = inject.Session.__new__(inject.Session)
        session.sequence, session.writer = 0, 99
        session.messages, session.events, session.paused = queue.Queue(), deque(), {'page-1'}
        written = bytearray()
        def short_write(_fd, data):
            count = min(3, len(data))
            written.extend(data[:count])
            return count
        with patch.object(os, 'write', side_effect=short_write):
            session.send('Test.method', {'text': '中文'})
        self.assertEqual(json.loads(written[:-1])['params']['text'], '中文')
        self.assertEqual(written[-1], 0)
        event = attached()
        session.messages.put(event)
        session.messages.put({'id': 2, 'result': {}})
        with patch.object(session, 'send', return_value=2):
            session.call('Runtime.runIfWaitingForDebugger', session='page-1')
        self.assertEqual(session.event(), event)
        self.assertFalse(session.paused)

    def test_unknown_target_is_guarded_and_failure_still_resumes_it(self):
        transport = Mock()
        transport.call.return_value = {}
        controller = inject.Injector(transport, 'guarded script', {'muted': True})
        controller.handle(attached())
        self.assertTrue(any(call.args[0] == 'Page.addScriptToEvaluateOnNewDocument' for call in transport.call.call_args_list))
        self.assertEqual(transport.call.call_args_list[0].args[0], 'Runtime.runIfWaitingForDebugger')
        for url, kind in (('https://example.com/', 'page'), ('app://-/index.html?initialRoute=/pet', 'page'), ('', 'worker')):
            transport.reset_mock()
            controller.handle(attached(url, kind=kind))
            transport.call.assert_called_once_with('Runtime.runIfWaitingForDebugger', session='page-1')
        def fail(method, *args, **kwargs):
            if method == 'Page.addScriptToEvaluateOnNewDocument':
                raise RuntimeError('injection failed')
            return {}
        transport.call.side_effect = fail
        transport.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'injection failed'):
            controller.handle(attached())
        self.assertEqual(transport.call.call_args_list[0].args[0], 'Runtime.runIfWaitingForDebugger')

    def test_already_loaded_main_gets_audio_and_centers_only_its_process(self):
        transport = Mock()
        transport.process.pid = 123
        def answer(method, params=None, **kwargs):
            if method == 'Runtime.evaluate' and params.get('expression') == 'document.readyState === "complete"':
                return {'result': {'value': True}}
            return {'windowId': 3}
        transport.call.side_effect = answer
        controller = inject.Injector(transport, 'guard', {'windowMode': 'centered', 'muted': False})
        with patch.object(inject, 'center_window') as center:
            controller.handle(attached('app://-/index.html'))
            center.assert_called_once_with(123)
            self.assertFalse(controller.configured)
            controller.handle({'method': 'Runtime.bindingCalled', 'sessionId': 'page-1',
                               'params': {'name': 'codexflareReady', 'payload': 'ready'}})
            self.assertEqual(center.call_count, 2)
        self.assertTrue(controller.configured)
        transport.call.assert_any_call('Runtime.evaluate', {'expression': 'document.dispatchEvent(new Event("codex-boot-play"))',
            'userGesture': True}, session='page-1')

    def test_centered_native_bounds_use_dpi_and_fit_work_area(self):
        api = Mock()
        api.GetDpiForWindow.return_value = 192
        def monitor(_handle, pointer):
            pointer._obj.rcWork = inject.wintypes.RECT(-3000, 20, 0, 1420)
            return True
        api.GetMonitorInfoW.side_effect = monitor
        with patch.object(inject, '_window', return_value=nullcontext((api, 45))):
            inject.center_window(123)
        api.ShowWindow.assert_called_once_with(45, 9)
        api.SetWindowPos.assert_called_once_with(45, None, -2600, 20, 2200, 1400, 0x14)

    def test_fullscreen_native_fit_only_writes_changed_monitor_bounds(self):
        api = Mock()
        rectangle = inject.wintypes.RECT(-2500, 200, -1000, 1300)
        def bounds(_handle, pointer):
            pointer._obj.left, pointer._obj.top = rectangle.left, rectangle.top
            pointer._obj.right, pointer._obj.bottom = rectangle.right, rectangle.bottom
            return True
        def monitor(_handle, pointer):
            pointer._obj.rcMonitor = inject.wintypes.RECT(-3840, 0, 0, 2160)
            return True
        api.GetWindowRect.side_effect = bounds
        api.GetMonitorInfoW.side_effect = monitor
        with patch.object(inject, '_window', side_effect=lambda pid: nullcontext((api, 45))) as window:
            inject.fit_fullscreen_window(123)
            api.SetWindowPos.assert_called_once_with(45, None, -3840, 0, 3840, 2160, 0x14)
            api.SetWindowPos.reset_mock()
            rectangle = inject.wintypes.RECT(-3840, 0, 0, 2160)
            inject.fit_fullscreen_window(123)
            api.SetWindowPos.assert_not_called()
            window.assert_called_with(123)
        api.ShowWindow.assert_not_called()

    @patch.object(inject, 'fit_fullscreen_window')
    def test_fullscreen_uses_browser_gesture_and_reports_denial(self, fit):
        transport = Mock()
        transport.process.pid = 123
        transport.call.return_value = {'result': {'value': True}}
        controller = inject.Injector(transport, 'guard', {'windowMode': 'fullscreen'})
        controller.main_session = 'main'
        controller.configure_window()
        method, params = transport.call.call_args.args
        self.assertEqual(method, 'Runtime.evaluate')
        self.assertIn('requestFullscreen', params['expression'])
        self.assertTrue(params['userGesture'])
        self.assertTrue(params['awaitPromise'])
        fit.assert_called_once_with(123)
        fit.reset_mock()
        transport.call.return_value = {'result': {'value': False}}
        controller.configure_window()
        fit.assert_not_called()
        transport.call.return_value = {'exceptionDetails': {'text': 'denied'}}
        with self.assertRaisesRegex(RuntimeError, '全屏'):
            controller.configure_window()

    @patch.object(inject, 'fit_fullscreen_window')
    def test_fullscreen_waits_for_workspace_and_respects_skip(self, _fit):
        transport = Mock()
        transport.call.return_value = {'result': {'value': True}}
        controller = inject.Injector(transport, 'guard', {'windowMode': 'fullscreen', 'muted': False})
        controller.main_session = 'main'
        controller.loaded('main')
        self.assertFalse(controller.configured)
        self.assertEqual(transport.call.call_count, 1)
        self.assertIn('codex-boot-play', transport.call.call_args.args[1]['expression'])
        transport.reset_mock()
        event = {'method': 'Runtime.bindingCalled', 'sessionId': 'main',
                 'params': {'name': 'codexflareReady', 'payload': 'ready'}}
        controller.handle(event)
        controller.handle(event)
        self.assertEqual(transport.call.call_count, 1)
        self.assertTrue(controller.configured)
        expression = transport.call.call_args.args[1]['expression']
        check = ('const assert=require("node:assert/strict");let calls=0;'
                 'global.document={documentElement:{dataset:{codexBoot:"skipped"},requestFullscreen(){calls++;}}};'
                 'assert.equal(eval(' + json.dumps(expression) + '),false);assert.equal(calls,0);')
        result = subprocess.run(['node'], input=check, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        transport.reset_mock()
        controller = inject.Injector(transport, 'guard', {'windowMode': 'fullscreen', 'muted': True})
        controller.main_session = 'main'
        controller.handle(event)
        transport.call.assert_not_called()
        controller.loaded('main')
        self.assertTrue(controller.configured)
        self.assertEqual(transport.call.call_count, 1)

    def test_frame_resize_maintains_only_active_main_html_fullscreen(self):
        transport = Mock()
        transport.process.pid = 123
        controller = inject.Injector(transport, 'guard', {'windowMode': 'fullscreen'})
        controller.main_session = 'main'
        controller.configured = True
        event = {'method': 'Page.frameResized', 'sessionId': 'main'}
        with patch.object(inject, 'fit_fullscreen_window') as fit:
            transport.call.return_value = {'result': {'value': True}}
            controller.handle(event)
            transport.call.assert_called_once_with('Runtime.evaluate',
                {'expression': '!!document.fullscreenElement', 'returnByValue': True}, session='main')
            fit.assert_called_once_with(123)
            fit.reset_mock()
            transport.call.return_value = {'result': {'value': False}}
            controller.handle(event)
            fit.assert_not_called()
            transport.reset_mock()
            controller.handle(event | {'sessionId': 'auxiliary'})
            controller.configured = False
            controller.handle(event)
            controller.configured = True
            controller.settings['windowMode'] = 'restore'
            controller.handle(event)
            transport.call.assert_not_called()
            fit.assert_not_called()

    def test_navigation_before_page_enable_is_identified_from_current_frame(self):
        transport = Mock()
        transport.call.side_effect = lambda method, *args, **kwargs: (
            {'frameTree': {'frame': {'url': 'app://-/index.html'}}} if method == 'Page.getFrameTree' else {})
        controller = inject.Injector(transport, 'guard', {'muted': True})
        controller.handle(attached(''))
        self.assertEqual(controller.main_session, 'page-1')
        self.assertTrue(controller.started)

    def test_reopened_main_keeps_background_without_replaying_animation(self):
        transport = Mock()
        transport.call.return_value = {}
        marker = "animate = sessionStorage.getItem('codexflare:launch') !== token;"
        controller = inject.Injector(transport, marker, {'muted': True})
        controller.handle(attached('app://-/index.html'))
        controller.handle({'method': 'Target.detachedFromTarget', 'params': {'sessionId': 'page-1'}})
        self.assertIsNone(controller.main_session)
        controller.handle(attached('app://-/index.html', session='page-2'))
        transport.call.assert_any_call('Page.addScriptToEvaluateOnNewDocument',
            {'source': 'animate = false;', 'runImmediately': True}, session='page-2')

    def test_failure_waits_for_original_exit_without_terminating_it(self):
        session = Mock()
        session.process.poll.return_value = None
        with patch.object(inject, 'prepare_script', return_value='script'), \
                patch.object(inject, 'Session', return_value=session), \
                patch.object(inject, 'Injector') as controller, patch.object(inject, 'print'):
            controller.return_value.start.side_effect = RuntimeError('failed')
            with self.assertRaisesRegex(RuntimeError, 'failed'):
                inject.run(Path('official'), {}, Path('local'))
        session.release.assert_called_once()
        session.process.wait.assert_called_once()
        session.process.terminate.assert_not_called()
        session.process.kill.assert_not_called()
        self.assertLess(session.mock_calls.index(unittest.mock.call.process.wait()),
                        session.mock_calls.index(unittest.mock.call.close()))

    def test_normal_eof_before_poll_updates_is_not_an_injection_error(self):
        session = Mock()
        session.process.poll.return_value = None
        session.process.wait.return_value = 0
        session.event.side_effect = inject.PipeClosed('closed')
        with patch.object(inject, 'prepare_script', return_value='script'), \
                patch.object(inject, 'Session', return_value=session), patch.object(inject, 'Injector'):
            self.assertEqual(inject.run(Path('official'), {}, Path('local')), 0)
        session.release.assert_not_called()
        session.close.assert_called_once()

    def test_tray_wait_after_first_main_has_no_startup_deadline(self):
        session = Mock()
        session.process.poll.side_effect = [None, 0]
        session.process.returncode = 0
        controller = Mock(started=True, main_session=None)
        with patch.object(inject, 'prepare_script', return_value='script'), \
                patch.object(inject, 'Session', return_value=session), \
                patch.object(inject, 'Injector', return_value=controller), \
                patch.object(inject.time, 'monotonic', side_effect=[0, 1000]):
            self.assertEqual(inject.run(Path('official'), {}, Path('local')), 0)
        session.release.assert_not_called()

    def test_release_resumes_all_targets_and_live_pipe_cannot_be_closed(self):
        session = inject.Session.__new__(inject.Session)
        session.paused = {'one', 'two'}
        session.process = Mock()
        session.process.poll.return_value = None
        with patch.object(session, 'send') as send:
            session.release()
            for target in ('one', 'two'):
                send.assert_any_call('Runtime.runIfWaitingForDebugger', session=target)
            send.assert_any_call('Target.setAutoAttach', {'autoAttach': False,
                                 'waitForDebuggerOnStart': False, 'flatten': True})
        with self.assertRaisesRegex(RuntimeError, '仍在运行'), patch.object(os, 'close') as close:
            session.close()
        close.assert_not_called()
