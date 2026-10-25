#!/usr/bin/env python3
"""Exercise the actual Cocoa editor, WebM playback and settings in an isolated directory."""
import argparse
import base64
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
        phase = [-1]

        def finish(error=None):
            if error: failures.append(str(error))
            (output/'result.json').write_text(json.dumps({'passed':not failures,'errors':failures,'samples':samples},indent=2))
            app.stop_(None)

        def upload(data, filename):
            encoded=base64.b64encode(data).decode()
            script=('let bytes=Uint8Array.from(atob('+json.dumps(encoded)+'),c=>c.charCodeAt(0));'
                    'let transfer=new DataTransfer();transfer.items.add(new File([bytes],'+json.dumps(filename)+',{type:"image/png"}));'
                    'let input=document.getElementById("background-file");input.files=transfer.files;'
                    'input.dispatchEvent(new Event("change",{bubbles:true}));')
            view.evaluateJavaScript_completionHandler_('(()=>{'+script+'})()',lambda *_:None)

        def snapshot_done(image, error):
            if error: finish(error); return
            bitmap = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
            data = bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
            data.writeToFile_atomically_(str(output/'editor.png'),True)
            png=bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
                              '0000000b49444154789c63f80f040009fb03fdfb5e6b2b0000000049454e44ae426082')
            upload(png,'mac-smoke.png')
            AppHelper.callLater(0.5,poll)

        def received(value, error):
            if error: finish(error); return
            state=json.loads(value); samples.append(state)
            (output/'progress.json').write_text(json.dumps({'phase':phase[0],'state':state},indent=2))
            if time.monotonic()>deadline: finish('Native editor timed out'); return
            if phase[0]==-1 and state.get('width')==1920 and state.get('canPlay'):
                phase[0]=0
                view.evaluateJavaScript_completionHandler_('document.getElementById("toggle-play").click();',lambda *_:None)
            elif phase[0]==0 and state.get('time',0)>0 and not state.get('paused') and state.get('width')==1920 and state.get('canPlay'):
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
            elif phase[0]==3 and state.get('imageName')=='mac-smoke.png':
                phase[0]=4
                view.evaluateJavaScript_completionHandler_('document.getElementById("save").click();',lambda *_:None)
            elif phase[0]==4 and animation.load_settings()['background']['image'] not in ('default','default2'):
                phase[0]=5
                upload(b'broken PNG','broken.png')
            elif phase[0]==5 and state.get('uploadError'):
                phase[0]=6
                # Wait for the failed request and UI save cycle to finish before testing close.
                AppHelper.callLater(0.5, window.performClose_, None)
                return
            AppHelper.callLater(0.5, poll)

        def poll():
            view.evaluateJavaScript_completionHandler_(
                'JSON.stringify((()=>{let v=document.querySelector("video"),i=document.querySelector("#background-preview img");'
                'return {canPlay:!document.getElementById("toggle-play")?.disabled,readyState:v?.readyState,networkState:v?.networkState,time:v?.currentTime,width:v?.videoWidth,paused:v?.paused,error:v?.error?.code??null,'
                'imageName:document.getElementById("background-name")?.textContent,uploadError:!document.getElementById("error-banner")?.hidden,'
                'backgroundLoaded:!!i&&i.complete&&i.naturalWidth>0}})())',received)
        AppHelper.callLater(0.5,poll)
        def deadline_check():
            if time.monotonic() > deadline:
                finish('Native editor timed out while closing')
                AppHelper.stopEventLoop()
            else:
                AppHelper.callLater(1, deadline_check)
        AppHelper.callLater(1, deadline_check)
        try:
            AppHelper.runEventLoop()
            if phase[0]!=6 and not failures:
                failures.append('Window closed before verification completed')
        finally:
            server.shutdown(); worker.join(); server.server_close()
            (output/'result.json').write_text(json.dumps({'passed':not failures,'errors':failures,'samples':samples},indent=2))
    if failures: raise RuntimeError('; '.join(failures))
    print(json.dumps({'passed':True,'output':str(output),'samples':len(samples)}))


if __name__=='__main__': main()
