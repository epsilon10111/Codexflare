"""Customize the signed Windows app through inherited private CDP pipes."""
import base64
from collections import deque
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

if __package__:
    from . import animation, background
    from .background_layout import loading_class, patch_background_css
    from .patch_app import Asar, ROOT, check_archive, replace_once
else:
    import animation, background
    from background_layout import loading_class, patch_background_css
    from patch_app import Asar, ROOT, check_archive, replace_once


def main_url(url):
    parsed = urlsplit(url)
    # shortcut: only root-route cold starts; review auxiliary routes before allowing deep links.
    return (parsed.scheme, parsed.netloc, parsed.path) == ('app', '-', '/index.html') and all(
        route == '/' for route in parse_qs(parsed.query).get('initialRoute', []))


def prepare_script(source, settings, local):
    values = animation.validate_settings(settings)
    archive_path = Path(source) / 'resources/app.asar'
    check_archive(archive_path, 'win32', values)
    archive = Asar(archive_path)
    values = values | {'duration': animation.video_info(values['video'])['duration']}
    video = animation.video_path(values['video']).read_bytes()
    data_url = 'data:video/webm;base64,' + base64.b64encode(video).decode('ascii')
    boot = (ROOT / 'src/boot.js').read_text(encoding='utf-8')
    boot = replace_once(boot, "  if (new URLSearchParams(location.search).get('codexBootAnimation') !== '1') return;", '')
    boot = replace_once(boot, '/* CODEX_BOOT_SETTINGS */ null', json.dumps(values, allow_nan=False))
    boot = boot.replace('_delayedBlossom_ovcb0_16', loading_class(archive))
    boot = replace_once(boot, '  const scriptUrl = document.currentScript.src;', '')
    boot = replace_once(boot, "new URL('./codex-boot.webm', scriptUrl).href", json.dumps(data_url))
    start, end = '    const readySurface = () => {', '    const prepareWorkspace = () => {'
    if boot.count(start) != 1 or boot.count(end) != 1:
        raise ValueError('开屏就绪信号发生变化，需要重新核验')
    readiness = boot[boot.index(start):boot.index(end)]
    css = (ROOT / 'src/boot.css').read_text(encoding='utf-8')
    image, info = background.load_selected(values['background'], Path(local))
    image_data = None
    if image is not None:
        image, _ = background.prepare_image(image, info)
        image_data = base64.b64encode(image).decode('ascii')
        style = patch_background_css((ROOT / 'src/background.css').read_text(encoding='utf-8'), archive)
        style = replace_once(style, './codex-background.png', 'CODEXFLARE_BACKGROUND_IMAGE')
        selected = values['background']
        css += (f"\n:root {{ --codex-bg-opacity: {selected['opacity']}; "
                f"--codex-bg-position: {selected['position']}%; --codex-bg-scale: {selected['scale']}%; }}\n" + style)
    token = secrets.token_hex(16)
    return '''(() => {
  const url = new URL(location.href);
  if (window !== window.top || url.protocol !== 'app:' || url.host !== '-' || url.pathname !== '/index.html'
      || url.searchParams.getAll('initialRoute').some(route => route && route !== '/')) return;
  const install = () => {
    if (!document.documentElement) return false;
    if (document.getElementById('codexflare-style')) return true;
    const imageData = ''' + json.dumps(image_data) + ''';
    // The app's module preloader scans every link.href; keep the background URL short.
    const imageBytes = imageData ? (Uint8Array.fromBase64 ? Uint8Array.fromBase64(imageData)
      : Uint8Array.from(atob(imageData), value => value.charCodeAt(0))) : null;
    const image = imageBytes ? URL.createObjectURL(new Blob([imageBytes], {type: 'image/png'})) : null;
    const style = document.createElement('style');
    style.id = 'codexflare-style';
    style.textContent = (''' + json.dumps(css) + ''').replace('CODEXFLARE_BACKGROUND_IMAGE', image || '');
    document.documentElement.append(style);
    if (image) {
      const preload = document.createElement('link');
      preload.id = 'codex-background-preload'; preload.rel = 'preload'; preload.as = 'image'; preload.href = image;
      document.documentElement.append(preload);
    }
''' + readiness + '''
    const deadline = performance.now() + 60000;
    const reportReady = () => {
      const surface = readySurface();
      if (surface) {
        requestAnimationFrame(() => requestAnimationFrame(() => {
          if (readySurface() === surface) globalThis.codexflareReady?.('ready');
          else if (performance.now() < deadline) setTimeout(reportReady, 100);
        }));
      } else if (performance.now() < deadline) setTimeout(reportReady, 100);
    };
    reportReady();
    let animate = true;
    try {
      const token = ''' + json.dumps(token) + ''';
      animate = sessionStorage.getItem('codexflare:launch') !== token;
      sessionStorage.setItem('codexflare:launch', token);
    } catch { animate = false; }
    if (animate) {
''' + boot + '''
    }
    return true;
  };
  if (!install()) {
    const observer = new MutationObserver(() => { if (install()) observer.disconnect(); });
    observer.observe(document, {childList: true, subtree: true});
  }
})();'''


class PipeClosed(RuntimeError):
    pass


class MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


@contextmanager
def _window(pid):
    api = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    signatures = {
        'EnumWindows': ([callback_type, wintypes.LPARAM], wintypes.BOOL),
        'GetWindowThreadProcessId': ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
        'GetWindowRect': ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
        'GetWindow': ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
        'IsWindowVisible': ([wintypes.HWND], wintypes.BOOL),
        'IsIconic': ([wintypes.HWND], wintypes.BOOL),
        'IsZoomed': ([wintypes.HWND], wintypes.BOOL),
        'GetDpiForWindow': ([wintypes.HWND], wintypes.UINT),
        'SetThreadDpiAwarenessContext': ([wintypes.HANDLE], wintypes.HANDLE),
        'MonitorFromWindow': ([wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
        'GetMonitorInfoW': ([wintypes.HANDLE, ctypes.POINTER(MonitorInfo)], wintypes.BOOL),
        'ShowWindow': ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
        'SetWindowPos': ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    previous = api.SetThreadDpiAwarenessContext(wintypes.HANDLE(-4))
    if not previous:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        windows = []
        def visit(handle, _):
            process = wintypes.DWORD()
            api.GetWindowThreadProcessId(handle, ctypes.byref(process))
            rectangle = wintypes.RECT()
            if (process.value == pid and not api.GetWindow(handle, 4)
                    and api.GetWindowRect(handle, ctypes.byref(rectangle))):
                area = (rectangle.right - rectangle.left) * (rectangle.bottom - rectangle.top)
                if area > 0:
                    windows.append((bool(api.IsWindowVisible(handle)), area, handle))
            return True
        if not api.EnumWindows(callback_type(visit), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        if not windows:
            raise RuntimeError('尚未找到本次启动进程的原版窗口')
        yield api, max(windows)[2]
    finally:
        api.SetThreadDpiAwarenessContext(previous)


def _rectangle(rectangle):
    return {'left': rectangle.left, 'top': rectangle.top,
            'width': rectangle.right - rectangle.left, 'height': rectangle.bottom - rectangle.top}


def window_bounds(pid):
    """Return physical screen pixels and DPI for a window owned by this process."""
    with _window(pid) as (api, handle):
        rectangle, monitor = wintypes.RECT(), MonitorInfo()
        monitor.cbSize = ctypes.sizeof(monitor)
        if (not api.GetWindowRect(handle, ctypes.byref(rectangle)) or
                not api.GetMonitorInfoW(api.MonitorFromWindow(handle, 2), ctypes.byref(monitor))):
            raise ctypes.WinError(ctypes.get_last_error())
        return _rectangle(rectangle) | {'dpi': api.GetDpiForWindow(handle),
            'windowState': 'minimized' if api.IsIconic(handle) else 'maximized' if api.IsZoomed(handle) else 'normal',
            'monitor': _rectangle(monitor.rcMonitor), 'workArea': _rectangle(monitor.rcWork)}


def center_window(pid):
    with _window(pid) as (api, handle):
        monitor = MonitorInfo()
        monitor.cbSize = ctypes.sizeof(monitor)
        if not api.GetMonitorInfoW(api.MonitorFromWindow(handle, 2), ctypes.byref(monitor)):
            raise ctypes.WinError(ctypes.get_last_error())
        area, scale = _rectangle(monitor.rcWork), api.GetDpiForWindow(handle) / 96
        width, height = min(round(1100 * scale), area['width']), min(round(760 * scale), area['height'])
        api.ShowWindow(handle, 9)
        if not api.SetWindowPos(handle, None, area['left'] + (area['width'] - width) // 2,
                area['top'] + (area['height'] - height) // 2, width, height, 0x14):
            raise ctypes.WinError(ctypes.get_last_error())


def fit_fullscreen_window(pid):
    with _window(pid) as (api, handle):
        rectangle, monitor = wintypes.RECT(), MonitorInfo()
        monitor.cbSize = ctypes.sizeof(monitor)
        if (not api.GetWindowRect(handle, ctypes.byref(rectangle)) or
                not api.GetMonitorInfoW(api.MonitorFromWindow(handle, 2), ctypes.byref(monitor))):
            raise ctypes.WinError(ctypes.get_last_error())
        area = _rectangle(monitor.rcMonitor)
        if _rectangle(rectangle) != area:
            if not api.SetWindowPos(handle, None, area['left'], area['top'],
                                    area['width'], area['height'], 0x14):
                raise ctypes.WinError(ctypes.get_last_error())


class Session:
    """One child process and its anonymous pipe; never opens a listening socket."""
    def __init__(self, source, arguments=(), test_profile=None):
        import msvcrt
        if any(str(arg).lstrip('-/').lower().startswith('remote-debugging-') for arg in arguments):
            raise ValueError('不能覆盖 Codexflare 的私有调试管道')
        self.messages, self.events, self.paused = queue.Queue(), deque(), set()
        self.sequence = 0
        self.closed = False
        child_read, self.writer = os.pipe()
        self.reader, child_write = os.pipe()
        handles = [msvcrt.get_osfhandle(fd) for fd in (child_read, child_write)]
        startup = subprocess.STARTUPINFO()
        startup.lpAttributeList = {'handle_list': handles}
        env = os.environ.copy()
        command = [str(Path(source) / 'ChatGPT.exe'), '--remote-debugging-pipe',
                   '--remote-debugging-io-pipes=' + ','.join(map(str, handles)), *arguments]
        if test_profile is not None:
            profile = Path(test_profile).resolve()
            env.update(CODEX_HOME=str(profile / 'codex-home'), CODEX_ELECTRON_USER_DATA_PATH=str(profile / 'profile'))
            command.append('--user-data-dir=' + env['CODEX_ELECTRON_USER_DATA_PATH'])
        try:
            for fd in (child_read, child_write):
                os.set_inheritable(fd, True)
            self.process = subprocess.Popen(command, cwd=source, env=env, startupinfo=startup,
                close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except BaseException:
            os.close(self.reader)
            os.close(self.writer)
            raise
        finally:
            os.close(child_read)
            os.close(child_write)
        threading.Thread(target=self._receive, daemon=True).start()

    def _receive(self):
        pending = bytearray()
        try:
            while chunk := os.read(self.reader, 65536):
                pending.extend(chunk)
                while b'\0' in pending:
                    raw, _, pending = pending.partition(b'\0')
                    message = json.loads(raw)
                    if message.get('method') == 'Target.attachedToTarget' and message['params'].get('waitingForDebugger'):
                        self.paused.add(message['params']['sessionId'])
                    self.messages.put(message)
        except (OSError, ValueError) as error:
            self.messages.put({'pipe_error': str(error)})
        finally:
            self.messages.put({'pipe_closed': True})

    def send(self, method, params=None, session=None):
        self.sequence += 1
        message = {'id': self.sequence, 'method': method, 'params': params or {}}
        if session is not None:
            message['sessionId'] = session
        payload = memoryview(json.dumps(message, ensure_ascii=False).encode('utf-8') + b'\0')
        while payload:
            written = os.write(self.writer, payload[:65536])
            if written <= 0:
                raise OSError('私有调试管道写入失败')
            payload = payload[written:]
        return self.sequence

    def call(self, method, params=None, session=None, timeout=15):
        identifier = self.send(method, params, session)
        deadline = time.monotonic() + timeout
        while True:
            try:
                message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as error:
                raise TimeoutError(f'私有调试管道超时：{method}') from error
            if 'pipe_error' in message:
                raise RuntimeError(message['pipe_error'])
            if message.get('pipe_closed'):
                raise PipeClosed('私有调试管道已关闭')
            if message.get('id') == identifier:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"].get("message", "失败")}')
                if method == 'Runtime.runIfWaitingForDebugger':
                    self.paused.discard(session)
                return message.get('result', {})
            if 'method' in message:
                self.events.append(message)

    def event(self, timeout=1):
        if self.events:
            return self.events.popleft()
        try:
            message = self.messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if 'pipe_error' in message:
            raise RuntimeError(message['pipe_error'])
        if message.get('pipe_closed'):
            raise PipeClosed('私有调试管道已关闭')
        return message if 'method' in message else None

    def release(self):
        for session in tuple(self.paused):
            try:
                self.send('Runtime.runIfWaitingForDebugger', session=session)
            except OSError:
                pass
        try:
            self.send('Target.setAutoAttach', {'autoAttach': False, 'waitForDebuggerOnStart': False, 'flatten': True})
        except OSError:
            pass

    def close(self):
        if self.process.poll() is None:
            raise RuntimeError('原版应用仍在运行，不能关闭其私有管道')
        if not self.closed:
            self.closed = True
            for fd in (self.reader, self.writer):
                os.close(fd)


class Injector:
    def __init__(self, session, script, settings):
        self.session, self.script, self.settings = session, script, settings
        self.targets = {}
        self.main_session = self.main_target = None
        self.configured = False
        self.load_seen = self.workspace_ready = False
        self.started = False

    def start(self):
        self.session.call('Target.setAutoAttach', {'autoAttach': True, 'waitForDebuggerOnStart': False,
                          'flatten': True, 'filter': [{'type': 'page'}, {'exclude': True}]})

    def handle(self, message):
        if not message:
            return
        method, params, session = message.get('method'), message.get('params', {}), message.get('sessionId')
        if method == 'Target.attachedToTarget':
            session, info = params['sessionId'], params['targetInfo']
            resumed = False
            try:
                # Electron's new page cannot answer Page.enable while startup is paused.
                self.session.call('Runtime.runIfWaitingForDebugger', session=session)
                resumed = True
                if (info.get('type') != 'page' or self.main_session is not None or
                        (info.get('url') not in ('', 'about:blank') and not main_url(info['url']))):
                    return
                self.targets[session] = info['targetId']
                self.session.call('Page.enable', session=session)
                self.session.call('Runtime.addBinding', {'name': 'codexflareReady'}, session=session)
                script = self.script if not self.started else replace_once(self.script,
                    "animate = sessionStorage.getItem('codexflare:launch') !== token;", 'animate = false;')
                self.session.call('Page.addScriptToEvaluateOnNewDocument',
                                  {'source': script, 'runImmediately': True}, session=session)
                frame = self.session.call('Page.getFrameTree', session=session)
                current_url = frame.get('frameTree', {}).get('frame', {}).get('url', info.get('url', ''))
                if main_url(current_url):
                    self.main_session, self.main_target = session, info['targetId']
                    self.started = True
                elif current_url not in ('', 'about:blank'):
                    self.session.call('Target.detachFromTarget', {'sessionId': session})
                    self.targets.pop(session, None)
            finally:
                if not resumed:
                    self.session.send('Runtime.runIfWaitingForDebugger', session=session)
            self.check_loaded(session)
        elif method == 'Page.frameNavigated' and session in self.targets and not params['frame'].get('parentId'):
            if main_url(params['frame']['url']) and self.main_session in (None, session):
                self.main_session, self.main_target = session, self.targets[session]
                self.started = True
                self.check_loaded(session)
            elif session != self.main_session:
                self.session.call('Target.detachFromTarget', {'sessionId': session})
                self.targets.pop(session, None)
        elif method == 'Target.detachedFromTarget':
            detached = params['sessionId']
            self.targets.pop(detached, None)
            if detached == self.main_session:
                self.main_session = self.main_target = None
                self.configured = False
                self.load_seen = self.workspace_ready = False
        elif method == 'Page.loadEventFired':
            self.loaded(session)
        elif (method == 'Page.frameResized' and session == self.main_session and self.configured
              and self.settings.get('windowMode') == 'fullscreen'):
            result = self.session.call('Runtime.evaluate', {'expression': '!!document.fullscreenElement',
                                       'returnByValue': True}, session=session)
            if result.get('result', {}).get('value') is True:
                fit_fullscreen_window(self.session.process.pid)
        elif (method == 'Runtime.bindingCalled' and session == self.main_session
              and params.get('name') == 'codexflareReady' and params.get('payload') == 'ready'
              and not self.workspace_ready):
            self.workspace_ready = True
            if self.load_seen and self.settings.get('windowMode') in ('centered', 'fullscreen'):
                self.configure_window()
            self.configured = self.load_seen

    def check_loaded(self, session):
        if session == self.main_session and not self.load_seen:
            result = self.session.call('Runtime.evaluate', {'expression': 'document.readyState === "complete"',
                                       'returnByValue': True}, session=session)
            if result.get('result', {}).get('value') is True:
                self.loaded(session)

    def loaded(self, session):
        if session == self.main_session and not self.load_seen:
            if not self.settings.get('muted', True):
                self.session.call('Runtime.evaluate', {'expression': 'document.dispatchEvent(new Event("codex-boot-play"))',
                                  'userGesture': True}, session=session)
            # The original login initialization exits fullscreen before the workspace is ready.
            if self.settings.get('windowMode') != 'fullscreen' or self.workspace_ready:
                self.configure_window()
            self.load_seen = True
            self.configured = self.settings.get('windowMode') not in ('centered', 'fullscreen') or self.workspace_ready

    def configure_window(self):
        mode = self.settings.get('windowMode', 'restore')
        if mode == 'restore':
            return
        if mode == 'fullscreen':
            expression = ('document.documentElement.dataset.codexBoot === "skipped" ? false : '
                          'document.documentElement.requestFullscreen({navigationUI:"hide"}).then(()=>true)')
            result = self.session.call('Runtime.evaluate', {'expression': expression,
                'userGesture': True, 'awaitPromise': True, 'returnByValue': True}, session=self.main_session)
            if 'exceptionDetails' in result:
                raise RuntimeError('原版应用拒绝全屏请求')
            if result.get('result', {}).get('value') is True:
                fit_fullscreen_window(self.session.process.pid)
        else:
            center_window(self.session.process.pid)


def run(source, settings, local, arguments=(), test_profile=None, *, prepared_script=None):
    script = prepare_script(source, settings, local) if prepared_script is None else prepared_script
    session = Session(source, arguments, test_profile)
    try:
        injector = Injector(session, script, settings)
        injector.start()
        deadline = time.monotonic() + 60
        while session.process.poll() is None:
            try:
                injector.handle(session.event())
            except PipeClosed:
                if session.process.wait(timeout=3) == 0:
                    return 0
                raise
            if not injector.started and time.monotonic() >= deadline:
                raise TimeoutError('未找到原版主窗口；请正常退出已运行的应用后再启动')
        return session.process.returncode
    except BaseException:
        session.release()
        if session.process.poll() is None:
            # Closing a live CDP pipe may exit Chromium; retain it until the user quits.
            print('Codexflare 注入失败；原版继续运行，退出后将报告错误。', file=sys.stderr, flush=True)
            session.process.wait()
        raise
    finally:
        session.close()
