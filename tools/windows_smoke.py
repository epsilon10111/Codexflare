#!/usr/bin/env python3
"""Verify the signed Windows app through private pipes and an isolated test profile."""
import argparse
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time

if __package__:
    from . import animation, manage_windows, windows_inject, windows_package
    from .background_layout import BackgroundLayout
    from .patch_app import Asar, ROOT
else:
    import animation, manage_windows, windows_inject, windows_package
    from background_layout import BackgroundLayout
    from patch_app import Asar, ROOT

PROBE = '''(() => {
 const layer = document.getElementById('codex-boot'), video = layer?.querySelector('video');
 return {state: document.documentElement.dataset.codexBoot,
  background: document.documentElement.dataset.codexBackground,
  preloadLength: document.getElementById('codex-background-preload')?.href.length,
  blobBackground: document.getElementById('codex-background-preload')?.href.startsWith('blob:'),
  layer: !!layer, styles: !!document.getElementById('codexflare-style'),
  video: video ? {time:video.currentTime,ready:video.readyState,paused:video.paused,muted:video.muted,
   speed:video.playbackRate,fit:video.style.objectFit} : null};
})()'''


def hashes(source):
    result = {}
    for name in ('ChatGPT.exe', 'resources/app.asar', 'chrome.dll'):
        with (source / name).open('rb') as stream:
            result[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-mode', choices=('restore', 'centered', 'fullscreen'), default='centered')
    parser.add_argument('--sound', action='store_true')
    parser.add_argument('--seed-bounds', nargs=4, type=int)
    parser.add_argument('--exit-path', choices=('ended', 'skipped', 'media-error', 'reduced-motion'), default='ended')
    args = parser.parse_args()
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='windows-original-smoke-', dir=work))
    source = manage_windows.SOURCE
    package = windows_package.registered_package(source)
    if windows_package.current_package_full_name() != package['full_name']:
        raise RuntimeError('请在已安装应用的 MSIX 包上下文内运行此测试，命令见 WINDOWS.md')
    before = hashes(source)
    settings = animation.validate_settings({'windowMode': args.window_mode, 'muted': not args.sound})
    if args.seed_bounds:
        home = output / 'codex-home'
        home.mkdir()
        (home / '.codex-global-state.json').write_text(json.dumps({'electron-main-window-bounds':
            dict(zip(('x','y','width','height'), args.seed_bounds)) | {'isMaximized': False}}), encoding='utf-8')
    script = windows_inject.prepare_script(source, settings, output)
    flags = [] if args.exit_path == 'reduced-motion' else ['--force-prefers-no-reduced-motion']
    if args.exit_path == 'reduced-motion':
        flags = ['--force-prefers-reduced-motion']
    session = windows_inject.Session(source, arguments=flags, test_profile=output)
    package_size = wintypes.UINT()
    package_api = ctypes.WinDLL('kernel32').GetPackageFullName
    package_api.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    package_api.restype = wintypes.LONG
    package_code = package_api(session.process._handle, ctypes.byref(package_size), None)
    package_name = ctypes.create_unicode_buffer(max(1, package_size.value))
    if package_code == 122:
        package_code = package_api(session.process._handle, ctypes.byref(package_size), package_name)
    injector = windows_inject.Injector(session, script, settings)
    samples, events, changed, foregrounded = [], [], False, False
    result = {'passed': False, 'copied_application': False, 'real_account_used': False,
              'mode': args.window_mode, 'muted': not args.sound, 'exit_path': args.exit_path, 'output': str(output),
              'package_identity': {'status': package_code, 'name': package_name.value}}

    def evaluate(expression, await_promise=False):
        response = session.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True,
                                'awaitPromise': await_promise}, session=injector.main_session)
        if response.get('exceptionDetails'):
            raise AssertionError(response['exceptionDetails'].get('text', 'JavaScript failed'))
        return response.get('result', {}).get('value')

    def capture(name):
        data = session.call('Page.captureScreenshot', {'format': 'png'}, session=injector.main_session)['data']
        (output / name).write_bytes(base64.b64decode(data))

    try:
        assert package_code == 0 and package_name.value == package['full_name'], result['package_identity']
        injector.start()
        deadline, next_sample = time.monotonic() + 70, 0
        while time.monotonic() < deadline and session.process.poll() is None:
            event = session.event(timeout=.1)
            if event:
                events.append(event)
            injector.handle(event)
            if injector.main_session is None or time.monotonic() < next_sample:
                continue
            if not foregrounded:
                # Keep only this test window visible while Codex continues running the test harness.
                with windows_inject._window(session.process.pid) as (api, handle):
                    assert api.SetWindowPos(handle, wintypes.HWND(-1), 0, 0, 0, 0, 0x13)
                session.call('Page.bringToFront', session=injector.main_session)
                foregrounded = True
                result['visible_test_window'] = True
            next_sample = time.monotonic() + .25
            sample = evaluate(PROBE)
            if not sample:
                continue
            samples.append(sample)
            video = sample.get('video')
            if video and video['time'] > .6 and not (output / 'playing.png').exists():
                capture('playing.png')
            if not changed and video and video['time'] > 1 and args.exit_path in ('skipped', 'media-error'):
                if args.exit_path == 'skipped':
                    for event in ('keyDown', 'keyUp'):
                        session.call('Input.dispatchKeyEvent', {'type': event, 'key': 'Escape', 'code': 'Escape',
                                     'windowsVirtualKeyCode': 27}, session=injector.main_session)
                else:
                    evaluate('document.querySelector("#codex-boot video").src="data:video/webm;base64,AAAA"')
                changed = True
            if sample.get('state') == args.exit_path and not sample['layer'] and injector.configured:
                break
        else:
            raise AssertionError('Animation did not finish: ' + repr(samples[-3:]))
        assert samples[-1]['styles'], 'No injected styles'
        assert samples[-1]['blobBackground'] and samples[-1]['preloadLength'] < 256, 'Oversized preload URL regressed'
        assert samples[-1]['state'] == args.exit_path, samples[-1]
        playing = [s for s in samples if s.get('video') and s['video']['time'] > 0]
        if args.exit_path != 'reduced-motion':
            assert playing and max(s['video']['time'] for s in playing) > 1, 'Video did not advance'
            assert all(s['video']['muted'] == settings['muted'] for s in playing), 'Mute setting lost'
        capture('after.png')
        package_size.value = 0
        running_package_code = package_api(session.process._handle, ctypes.byref(package_size), None)
        running_package_name = ctypes.create_unicode_buffer(max(1, package_size.value))
        if running_package_code == 122:
            running_package_code = package_api(session.process._handle, ctypes.byref(package_size), running_package_name)
        result['running_package_identity'] = {'status': running_package_code, 'name': running_package_name.value}
        assert running_package_code == 0 and running_package_name.value == package['full_name']
        window = windows_inject.window_bounds(session.process.pid)
        window['htmlFullscreen'] = evaluate('!!document.fullscreenElement')
        result['window'] = window
        bounds = window
        scale = window['dpi'] / 96
        archive = Asar(source / 'resources/app.asar')
        fixture = (ROOT / 'tests/background_fixture.html').read_text(encoding='utf-8')
        layout = BackgroundLayout(archive)
        fixture = layout.fixture(fixture)
        style = '\n'.join(archive.read('webview/assets/' + n).decode() for n in layout.styles)
        style += re.search(r'<style>([\s\S]*?)</style>', fixture).group(1)
        body = fixture.split('<body>', 1)[1].split('</body>', 1)[0]
        session.call('Page.bringToFront', session=injector.main_session)
        evaluate('''(() => {
          const style=document.createElement('style');style.textContent=''' + json.dumps(style) + ''';
          document.head.append(style);document.body.innerHTML=''' + json.dumps(body) + ''';
          document.documentElement.dataset.theme='dark';document.documentElement.dataset.codexWindowType='electron';
          document.querySelector('#send').onclick=()=>document.querySelector('#send').dataset.clicked='true';
        })()''')
        for selector in ('#prompt', '#send'):
            position = evaluate('''(() => {const r=document.querySelector(''' + json.dumps(selector) + ''').getBoundingClientRect();
              return {x:r.x+r.width/2,y:r.y+r.height/2};})()''')
            for event in ('mousePressed', 'mouseReleased'):
                session.call('Input.dispatchMouseEvent', {'type': event, 'button': 'left', 'clickCount': 1,
                             **position}, session=injector.main_session)
            if selector == '#prompt':
                session.call('Input.insertText', {'text': 'local test'}, session=injector.main_session)
        background_state = evaluate('''(() => {
          const style=getComputedStyle(document.querySelector('main'),'::before');
          return {opacity:style.opacity,pointerEvents:style.pointerEvents,
            hasImage:style.backgroundImage.includes('blob:'),clicked:document.querySelector('#send').dataset.clicked,
            input:document.querySelector('#prompt').value};
        })()''')
        assert background_state['hasImage'] and float(background_state['opacity']) > 0, background_state
        assert background_state['pointerEvents'] == 'none' and background_state['clicked'] == 'true', background_state
        assert background_state['input'] == 'local test', background_state
        capture('background-fixture.png')
        evaluate("document.querySelector('#right-panel').hidden=false")
        assert evaluate("getComputedStyle(document.querySelector('#pane-content')).backgroundColor") == 'rgba(0, 0, 0, 0)'
        evaluate("document.querySelector('#right-panel').hidden=true;document.querySelector('main').dataset.theme='light'")
        assert evaluate("getComputedStyle(document.querySelector('main'),'::before').mixBlendMode") == 'multiply'
        evaluate("document.querySelector('main').dataset.theme='dark'")
        for name, value in (('prefers-reduced-transparency', 'reduce'), ('prefers-contrast', 'more'), ('forced-colors', 'active')):
            session.call('Emulation.setEmulatedMedia', {'features': [{'name': name, 'value': value}]}, session=injector.main_session)
            assert evaluate("getComputedStyle(document.querySelector('main'),'::before').display") == 'none', name
        session.call('Emulation.setEmulatedMedia', {'features': []}, session=injector.main_session)
        result['background_checks'] = ['native input and click', 'right panel transparent', 'light theme',
                                       'reduced transparency', 'high contrast', 'forced colors']
        while pending := session.event(timeout=0):
            injector.handle(pending)
        session.call('Page.reload', session=injector.main_session)
        reload_deadline = time.monotonic() + 20
        while time.monotonic() < reload_deadline:
            event = session.event(timeout=.1)
            injector.handle(event)
            if event and event.get('method') == 'Page.loadEventFired' and event.get('sessionId') == injector.main_session:
                reloaded = evaluate(PROBE)
                assert reloaded['styles'] and not reloaded.get('state') and not reloaded['layer'], reloaded
                break
        else:
            raise AssertionError('Reload did not preserve styles')
        if args.window_mode == 'fullscreen':
            assert window['htmlFullscreen'], bounds
            assert all(abs(bounds[k] - window['monitor'][k]) <= 4 for k in ('left', 'top', 'width', 'height')), bounds
        elif args.window_mode == 'centered':
            assert abs(bounds['width'] - min(round(1100 * scale), window['workArea']['width'])) <= 4, bounds
            assert abs(bounds['height'] - min(round(760 * scale), window['workArea']['height'])) <= 4, bounds
            for edge, dimension in (('left', 'width'), ('top', 'height')):
                assert abs(bounds[edge] - (window['workArea'][edge] + (window['workArea'][dimension] - bounds[dimension]) / 2)) <= 4, bounds
        elif args.seed_bounds:
            assert all(abs(bounds[k] - v * scale) <= 4 * scale
                       for k, v in zip(('left', 'top', 'width', 'height'), args.seed_bounds)), bounds
        result.update(passed=True, playing_samples=len(playing), background_fixture=background_state,
                      preload_url_length=samples[-1]['preloadLength'],
                      reload_without_animation=True, original_unchanged=hashes(source) == before)
        assert result['original_unchanged']
    finally:
        (output / 'samples.json').write_text(json.dumps(samples, indent=2), encoding='utf-8')
        (output / 'events.json').write_text(json.dumps(events, indent=2), encoding='utf-8')
        (output / 'pending-events.json').write_text(json.dumps({'events': list(session.events),
            'paused_sessions': sorted(session.paused)}, indent=2), encoding='utf-8')
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        session.release()
        if session.process.poll() is None:
            try:
                session.send('Browser.close')
                session.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                subprocess.run(['taskkill.exe','/PID',str(session.process.pid),'/T','/F'],
                    capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, check=True)
                session.process.wait(timeout=5)
        session.close()
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


if __name__ == '__main__':
    main()
