"""Native Windows editor using the installed Edge WebView2 runtime."""
import threading
from urllib.parse import urlsplit

import webview


def local_navigation(uri, origin):
    target, home = urlsplit(uri), urlsplit(origin)
    return (target.scheme == home.scheme and target.netloc == home.netloc
            and target.username is None and target.password is None)


class CloseGuard:
    def __init__(self, window, server):
        self.window, self.server = window, server
        self.pending = self.approved = False

    def closing(self):
        if self.approved:
            return True
        if not self.pending:
            self.pending = True
            # The WinForms closing event runs on the UI thread; JS must run off-thread.
            threading.Thread(target=self.check, daemon=True).start()
        return False

    def check(self):
        locked = self.server.write_lock.acquire(blocking=False)
        try:
            if not locked:
                self.window.create_confirmation_dialog('Codexflare', '操作仍在进行，请完成后再关闭。')
                return
            try:
                dirty = self.window.run_js('Boolean(document.getElementById("save-state")?.classList.contains("dirty"))')
            except Exception:
                dirty = None
            self.approved = dirty is False or self.window.create_confirmation_dialog(
                'Codexflare', '放弃未保存的设置并关闭？')
            if self.approved:
                self.window.destroy()
        finally:
            if locked and not self.approved:
                self.server.write_lock.release()
            self.pending = False


def create_window(url, server):
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
    webview.settings['ALLOW_DOWNLOADS'] = False
    window = webview.create_window('Codexflare', url, width=1280, height=900,
                                  min_size=(800, 600), background_color='#101010')
    guard = CloseGuard(window, server)
    window.events.closing += guard.closing

    def before_show():
        def navigation(sender, args):
            args.Cancel = not local_navigation(str(args.Uri), url)
        # Native access is needed to cancel navigation before a remote page can load.
        window.native.webview.NavigationStarting += navigation

    window.events.before_show += before_show
    return window


def run(url, server):
    create_window(url, server)
    webview.start(gui='edgechromium', private_mode=True)
