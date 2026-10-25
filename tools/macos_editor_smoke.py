#!/usr/bin/env python3
"""Exercise the actual Cocoa editor, WebM playback and settings in an isolated directory."""
import argparse
import contextlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('work/macos-editor'))
    args = parser.parse_args()
    if sys.platform != 'darwin': parser.error('需要 macOS')
    if __package__:
        from . import animation, editor, desktop_macos
    else:
        import animation, editor, desktop_macos
    from AppKit import NSApplication, NSBitmapImageRep, NSBitmapImageFileTypePNG
    from WebKit import WKSnapshotConfiguration
    from PyObjCTools import AppHelper
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    samples, failures = [], []
    with tempfile.TemporaryDirectory(prefix='config-', dir=output) as directory, contextlib.ExitStack() as stack:
        local = Path(directory)
        stack.enter_context(patch.multiple(animation, LOCAL=local, MEDIA=local/'media', SETTINGS=local/'animation.json'))
        stack.enter_context(patch.object(editor, 'installation_status', return_value={
            'active':False, 'available':False, 'running':False, 'message':'macOS 原生隔离验证；不安装应用'}))
        server = editor.EditorServer()
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        app = NSApplication.sharedApplication()
        window, view = desktop_macos.create_window(f'http://127.0.0.1:{server.server_port}/', server)
        window.makeKeyAndOrderFront_(None); app.activateIgnoringOtherApps_(True)
        deadline = time.monotonic()+45
        phase = [0]

        def finish(error=None):
            if error: failures.append(str(error))
            (output/'result.json').write_text(json.dumps({'passed':not failures,'errors':failures,'samples':samples},indent=2))
            AppHelper.stopEventLoop()

        def snapshot_done(image, error):
            if error: finish(error); return
            bitmap = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
            data = bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
            data.writeToFile_atomically_(str(output/'editor.png'),True)
            # Clean native close must acquire the write lock and stop the window loop.
            window.performClose_(None)
            AppHelper.callLater(0.2, finish)

        def received(value, error):
            if error: finish(error); return
            state=json.loads(value); samples.append(state)
            if time.monotonic()>deadline: finish('Native editor timed out'); return
            if phase[0]==0 and state.get('time',0)>0 and not state.get('paused') and state.get('width')==1920:
                phase[0]=1
                view.evaluateJavaScript_completionHandler_(
                    'document.getElementById("brightness").value="0.75";'
                    'document.getElementById("brightness").dispatchEvent(new Event("input",{bubbles:true}));'
                    'document.getElementById("save").click();', lambda *_:None)
            elif phase[0]==1 and animation.SETTINGS.exists():
                if animation.load_settings()['brightness'] != 0.75: finish('Settings did not persist'); return
                phase[0]=2
                view.evaluateJavaScript_completionHandler_(
                    'document.getElementById("background-tab").click();',lambda *_:None)
            elif phase[0]==2 and state.get('backgroundLoaded'):
                phase[0]=3
                view.takeSnapshotWithConfiguration_completionHandler_(WKSnapshotConfiguration.alloc().init(),snapshot_done)
                return
            AppHelper.callLater(0.5, poll)

        def poll():
            view.evaluateJavaScript_completionHandler_(
                'JSON.stringify((()=>{let v=document.querySelector("video"),i=document.querySelector("#background-preview img");'
                'return {time:v?.currentTime,width:v?.videoWidth,paused:v?.paused,error:v?.error?.code??null,'
                'backgroundLoaded:!!i&&i.complete&&i.naturalWidth>0}})())',received)
        AppHelper.callLater(0.5,poll)
        try:
            AppHelper.runEventLoop()
        finally:
            server.shutdown(); worker.join(); server.server_close()
    if failures: raise RuntimeError('; '.join(failures))
    print(json.dumps({'passed':True,'output':str(output),'samples':len(samples)}))


if __name__=='__main__': main()
