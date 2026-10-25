"""用系统 GTK/WebKit 承载独立编辑窗口，不打开浏览器。"""
import os
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('WebKit2', '4.1')


def local_navigation(uri, origin):
    target, home = urlsplit(uri), urlsplit(origin)
    return target.scheme == home.scheme and target.netloc == home.netloc


def desktop_environment():
    if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
        return
    runtime = f'/run/user/{os.getuid()}'
    session = {**os.environ, 'XDG_RUNTIME_DIR': runtime,
               'DBUS_SESSION_BUS_ADDRESS': f'unix:path={runtime}/bus'}
    result = subprocess.run(['systemctl', '--user', 'show-environment'], env=session,
                            capture_output=True, text=True, timeout=5, check=True)
    keys = {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
            'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP'}
    os.environ.update(dict(line.split('=', 1) for line in result.stdout.splitlines()
                           if line.partition('=')[0] in keys))


def create_window(url, server):
    from gi.repository import Gdk, GdkPixbuf, Gtk, WebKit2
    context = WebKit2.WebContext.new_ephemeral()
    context.connect('download-started', lambda _context, download: download.cancel())
    view = WebKit2.WebView.new_with_context(context)
    view.set_background_color(Gdk.RGBA(0.015, 0.015, 0.015, 1))
    window = Gtk.Window(title='Codexflare')
    window.set_name('codex-animation-window')
    window.set_wmclass('codex-animation-studio', 'CodexAnimationStudio')
    window.set_default_size(1280, 900)
    window.set_size_request(1000, 720)
    window.set_position(Gtk.WindowPosition.CENTER)
    titlebar = Gtk.HeaderBar(title='Codexflare', show_close_button=True)
    titlebar.set_name('codex-animation-titlebar')
    titlebar.set_has_subtitle(False)
    titlebar.set_decoration_layout(':minimize,maximize,close')
    window.set_titlebar(titlebar)
    ui = Path(__file__).resolve().parents[1] / 'ui'
    style = Gtk.CssProvider()
    style.load_from_path(str(ui / 'desktop.css'))
    Gtk.StyleContext.add_provider_for_screen(window.get_screen(), style,
                                            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    icon = ui / 'mark.svg'
    if icon.is_file():
        window.set_icon(GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon), 64, 64))
    window.add(view)

    def decide_policy(_view, decision, kind):
        if kind in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                    WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            uri = decision.get_navigation_action().get_request().get_uri()
            if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION or not local_navigation(uri, url):
                decision.ignore()
                return True
        return False

    def operation_pending():
        if not server.write_lock.locked():
            return False
        dialog = Gtk.MessageDialog(transient_for=window, modal=True,
                                   message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK,
                                   text='操作仍在进行，请完成后再关闭')
        dialog.format_secondary_text('素材导入或设置应用尚未结束，窗口会保留当前进度。')
        dialog.run()
        dialog.destroy()
        return True

    def request_close(_window, _event):
        if not operation_pending():
            view.try_close()
        return True

    def close(_view):
        if not server.write_lock.acquire(blocking=False):
            operation_pending()
            return
        # 关停期间持续拒绝新写入，避免退出时截断安装或转码。
        window.destroy()

    def deny_permission(_view, request):
        request.deny()
        return True

    view.connect('decide-policy', decide_policy)
    view.connect('permission-request', deny_permission)
    view.connect('close', close)
    window.connect('delete-event', request_close)
    window.connect('destroy', lambda _window: Gtk.main_quit())
    view.load_uri(url)
    return window, view


def init_desktop():
    desktop_environment()
    # 本机 WebKit 的 DMA-BUF 路径无法分配 GBM 缓冲，仅为此进程启用兼容渲染。
    os.environ.setdefault('WEBKIT_DISABLE_DMABUF_RENDERER', '1')
    if os.environ.get('DISPLAY'):
        # 当前 KDE/驱动组合的 WebKit Wayland 窗口报协议错误，使用现有 XWayland。
        os.environ.setdefault('GDK_BACKEND', 'x11')
    from gi.repository import Gtk
    if not Gtk.init_check()[0]:
        raise RuntimeError('无法连接图形桌面，请在当前桌面会话中启动编辑器')
    Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
    return Gtk


def run(url, server):
    Gtk = init_desktop()
    window, _view = create_window(url, server)
    window.show_all()
    Gtk.main()
