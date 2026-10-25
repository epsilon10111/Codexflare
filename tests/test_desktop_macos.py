import ctypes
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock, call
try:
    from tools import desktop_macos as desktop
except ImportError:
    desktop = None


@unittest.skipIf(desktop is None, 'Requires macOS and PyObjC')
class MacDesktopTests(unittest.TestCase):
    def test_only_editor_origin_can_navigate(self):
        origin = 'http://127.0.0.1:12345/'
        self.assertTrue(desktop.local_navigation(origin+'?x=1', origin))
        for uri in ('https://example.org', 'file:///etc/passwd', 'javascript:alert(1)',
                    'http://evil@127.0.0.1:12345/', 'http://127.0.0.1:12346/'):
            self.assertFalse(desktop.local_navigation(uri, origin))

    def test_signatureless_native_callbacks_use_correct_argument_types(self):
        for kind, ctype, value in [('integer',ctypes.c_long,1),('bool',ctypes.c_bool,True),
                                   ('object',ctypes.c_void_p,None)]:
            with self.subTest(kind=kind):
                received=[]
                callback=ctypes.CFUNCTYPE(None,ctypes.c_void_p,ctype)(lambda block,arg:received.append(arg))
                block=desktop._Block(0,0,0,ctypes.cast(callback,ctypes.c_void_p).value)
                handler=SimpleNamespace(__block_signature__=None)
                with patch.object(desktop.objc,'pyobjc_id',return_value=ctypes.addressof(block)):
                    desktop.call_block(handler,kind,value)
                self.assertEqual(received,[value])

    def test_signatureless_void_callback(self):
        received=[]
        callback=ctypes.CFUNCTYPE(None,ctypes.c_void_p)(lambda block:received.append(True))
        block=desktop._Block(0,0,0,ctypes.cast(callback,ctypes.c_void_p).value)
        with patch.object(desktop.objc,'pyobjc_id',return_value=ctypes.addressof(block)):
            desktop.call_block(SimpleNamespace(__block_signature__=None))
        self.assertEqual(received,[True])

    def test_close_protects_busy_and_unsaved_changes(self):
        server=SimpleNamespace(write_lock=threading.Lock())
        window,view=MagicMock(),MagicMock()
        delegate=desktop.EditorDelegate.alloc().init()
        delegate.configure('http://127.0.0.1:12345',server,window,view)
        with patch.object(desktop,'NSAlert') as alert:
            alert.alloc.return_value.init.return_value.runModal.return_value=desktop.NSAlertFirstButtonReturn
            with server.write_lock:
                self.assertFalse(delegate.windowShouldClose_(None))
            view.evaluateJavaScript_completionHandler_.assert_not_called()
            self.assertFalse(delegate.windowShouldClose_(None))
            callback=view.evaluateJavaScript_completionHandler_.call_args.args[1]
            callback(True,None)
            self.assertFalse(server.write_lock.locked())
            window.close.assert_not_called()
            self.assertFalse(delegate.windowShouldClose_(None))
            view.evaluateJavaScript_completionHandler_.call_args.args[1](False,None)
            window.close.assert_called_once()
            self.assertTrue(server.write_lock.locked())
            server.write_lock.release()
            self.assertTrue(delegate.windowShouldClose_(None))

    def test_closed_window_stops_and_wakes_the_event_loop(self):
        delegate = desktop.EditorDelegate.alloc().init()
        with patch.object(desktop, 'NSApplication') as application, patch.object(desktop, 'NSEvent') as events:
            app = application.sharedApplication.return_value
            factory = events.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_
            delegate.windowWillClose_(None)
            factory.assert_called_once_with(
                desktop.NSEventTypeApplicationDefined, (0, 0), 0, 0, 0, None, 0, 0, 0)
            self.assertEqual(app.mock_calls, [call.stop_(None), call.postEvent_atStart_(factory.return_value, True)])

    def test_native_file_panel_returns_only_selected_urls(self):
        delegate=desktop.EditorDelegate.alloc().init()
        window=MagicMock()
        delegate.configure('http://127.0.0.1:12345',SimpleNamespace(),window,MagicMock())
        with patch.object(desktop,'NSOpenPanel') as panels, patch.object(desktop,'call_block') as call:
            panel=panels.openPanel.return_value
            callback=object()
            delegate.webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_(
                None,SimpleNamespace(allowsMultipleSelection=lambda:False),None,callback)
            complete=panel.beginSheetModalForWindow_completionHandler_.call_args.args[1]
            complete(desktop.NSModalResponseOK)
            call.assert_called_with(callback,'object',panel.URLs.return_value)
            complete(0)
            call.assert_called_with(callback,'object',None)


if __name__=='__main__': unittest.main()
