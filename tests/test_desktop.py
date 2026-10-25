from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

try:
    from tools import desktop
    from tools.desktop import local_navigation
except (ImportError, ValueError):
    desktop = None
    local_navigation = None


class DesktopSmokeCLITests(unittest.TestCase):
    def test_help_and_missing_app_root_do_not_require_gtk(self):
        script = Path(__file__).resolve().parents[1] / 'tools/desktop_smoke.py'
        result = subprocess.run([sys.executable, str(script), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--app-root', result.stdout)
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, str(script), '--app-root', folder],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('--app-root 必须包含 Codexflare 的 tools 目录', result.stderr)


@unittest.skipIf(local_navigation is None, '需要系统 Python 的 GTK/WebKit 运行时')
class DesktopTests(unittest.TestCase):
    def test_navigation_stays_inside_editor_origin(self):
        origin = 'http://127.0.0.1:12345'
        for uri in [origin, origin + '/', origin + '/?video=default#preview']:
            with self.subTest(uri=uri):
                self.assertTrue(local_navigation(uri, origin))
        for uri in ['https://example.com', 'http://127.0.0.1:12346/',
                    'http://127.0.0.1:12345.evil.example/', 'http://127.0.0.1:12345@evil.example/',
                    'http://evil.example@127.0.0.1:12345/', 'https://127.0.0.1:12345/',
                    'file:///etc/passwd', 'javascript:alert(1)', 'about:blank',
                    'data:text/html,test', 'codex://threads/test', '//127.0.0.1:12345/']:
            with self.subTest(uri=uri):
                self.assertFalse(local_navigation(uri, origin))

    def test_native_styles_parse(self):
        from gi.repository import Gtk
        style = Gtk.CssProvider()
        style.load_from_path(str(Path(desktop.__file__).resolve().parents[1] / 'ui/desktop.css'))

    def test_titlebar_close_preserves_unsaved_and_busy_protection(self):
        from gi import repository
        from gi.repository import Gdk, GdkPixbuf, Gtk, WebKit2
        gtk, gdk, pixbuf, webkit = (MagicMock() for _ in range(4))
        window = gtk.Window.return_value
        view = webkit.WebView.new_with_context.return_value
        window_signals, view_signals = {}, {}
        window.connect.side_effect = lambda name, callback: window_signals.update({name: callback})
        view.connect.side_effect = lambda name, callback: view_signals.update({name: callback})
        server = SimpleNamespace(write_lock=threading.Lock())
        with patch.multiple(repository, Gtk=gtk, Gdk=gdk, GdkPixbuf=pixbuf, WebKit2=webkit):
            self.assertEqual(desktop.create_window('http://127.0.0.1:12345/', server), (window, view))
        gtk.HeaderBar.assert_called_once_with(title='Codexflare', show_close_button=True)
        window.set_titlebar.assert_called_once_with(gtk.HeaderBar.return_value)
        window.set_decorated.assert_not_called()

        self.assertTrue(window_signals['delete-event'](window, None))
        view.try_close.assert_called_once_with()
        window.destroy.assert_not_called()
        with server.write_lock:
            self.assertTrue(window_signals['delete-event'](window, None))
            view_signals['close'](view)
            view.try_close.assert_called_once_with()
            window.destroy.assert_not_called()
        view_signals['close'](view)
        window.destroy.assert_called_once_with()
        self.assertTrue(server.write_lock.locked())
        server.write_lock.release()


if __name__ == '__main__':
    unittest.main()
