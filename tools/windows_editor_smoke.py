#!/usr/bin/env python3
"""Exercise the real WebView2 editor with temporary settings and an isolated server."""
import base64
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

if __package__:
    from . import animation, editor
    from .desktop_windows import create_window
else:
    import animation
    import editor
    from desktop_windows import create_window
import webview


def main():
    work = editor.ROOT / 'work'
    work.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='windows-editor-', dir=work))
    failures = []
    with ExitStack() as stack:
        for name, value in {'LOCAL': output, 'MEDIA': output / 'media',
                            'SETTINGS': output / 'animation.json'}.items():
            stack.enter_context(patch.object(animation, name, value))
        server = stack.enter_context(editor.EditorServer())
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        window = create_window(f'http://127.0.0.1:{server.server_port}/', server)

        def wait_for(script):
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                result = window.run_js(script)
                if result:
                    return result
                time.sleep(.1)
            raise AssertionError(f'Timed out: {script}')

        def check():
            try:
                assert window.events.loaded.wait(25), 'WebView2 did not load'
                wait_for('document.querySelector("#preview")?.readyState >= 2 && !document.querySelector("#speed").disabled')
                window.run_js('document.querySelector("#toggle-play").click()')
                wait_for('document.querySelector("#preview").currentTime > 1 && !document.querySelector("#preview").paused')
                window.run_js('document.querySelector("#speed").value="1.5"; document.querySelector("#speed").dispatchEvent(new Event("input"))')
                wait_for('document.querySelector("#save-state").classList.contains("dirty")')
                window.run_js('document.querySelector("#save").click()')
                wait_for('!document.querySelector("#save-state").classList.contains("dirty")')
                assert animation.load_settings()['speed'] == 1.5
                png = base64.b64encode((editor.ROOT / 'assets/default2.png').read_bytes()).decode()
                window.run_js('''(() => {
                    const transfer = new DataTransfer();
                    const bytes = Uint8Array.from(atob(''' + json.dumps(png) + '''), c => c.charCodeAt(0));
                    transfer.items.add(new File([bytes], '背景 smoke.png', {type:'image/png'}));
                    const input = document.querySelector('#background-file');
                    input.files = transfer.files; input.dispatchEvent(new Event('change'));
                })()''')
                wait_for('Array.from(document.querySelector("#background-source").options).some(o => o.textContent.includes("背景 smoke"))')
                window.run_js('document.querySelector("#background-tab").click()')
                wait_for('document.querySelector("#background-image").naturalWidth > 0')
                window.run_js('document.querySelector("#save").click()')
                wait_for('!document.querySelector("#save-state").classList.contains("dirty")')
                assert animation.load_settings()['background']['image'] not in ('default', 'default2')

                from System import Func, Object
                from System.IO import FileStream, FileMode
                from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
                stream = FileStream(str(output / 'editor.png'), FileMode.Create)
                try:
                    task = window.native.Invoke(Func[Object](lambda: window.native.webview.CoreWebView2.CapturePreviewAsync(
                        CoreWebView2CapturePreviewImageFormat.Png, stream)))
                    assert task.Wait(10000), 'Screenshot timed out'
                finally:
                    stream.Dispose()
                window.run_js('''(() => {
                    const transfer = new DataTransfer();
                    transfer.items.add(new File(['bad PNG'], 'invalid.png', {type:'image/png'}));
                    const input = document.querySelector('#background-file');
                    input.files = transfer.files; input.dispatchEvent(new Event('change'));
                })()''')
                wait_for('!document.querySelector("#error-banner").hidden')
                assert animation.load_settings()['speed'] == 1.5
                window.run_js('location.href="https://example.invalid/"')
                time.sleep(.3)
                assert window.get_current_url() == f'http://127.0.0.1:{server.server_port}/'
                result = {'passed': True, 'playback': True, 'png_upload': True, 'saved': True,
                          'invalid_png_rejected': True, 'navigation_blocked': True, 'output': str(output)}
                (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
                print(json.dumps(result), flush=True)
            except Exception as error:
                failures.append(error)
            finally:
                # The test already verified persistence; bypass interactive close dialogs on failure.
                if failures:
                    window.events.closing._items.clear()
                window.destroy()

        try:
            webview.start(check, gui='edgechromium', private_mode=True)
            if not failures:
                assert server.write_lock.locked(), 'Close guard did not hold the write lock'
        finally:
            server.shutdown()
            worker.join()
    if failures:
        raise failures[0]


if __name__ == '__main__':
    main()
