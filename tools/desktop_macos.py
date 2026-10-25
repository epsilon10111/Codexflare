"""Cocoa/WKWebView host for the loopback editor; no account/browser data is loaded."""
from urllib.parse import urlsplit

import objc
import ctypes
from Foundation import NSObject, NSURL, NSURLRequest, NSMakeRect, NSMakeSize
from AppKit import (NSApplication, NSApplicationActivationPolicyRegular, NSWindow,
                    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
                    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskResizable,
                    NSBackingStoreBuffered, NSAlert, NSAlertFirstButtonReturn,
                    NSOpenPanel, NSModalResponseOK, NSMenu, NSMenuItem, NSAppearance,
                    NSAppearanceNameDarkAqua)
from WebKit import (WKWebView, WKWebViewConfiguration, WKWebsiteDataStore,
                    WKNavigationActionPolicyAllow, WKNavigationActionPolicyCancel)


def local_navigation(uri, origin):
    target, home = urlsplit(uri), urlsplit(origin)
    return (target.scheme == home.scheme and target.netloc == home.netloc
            and target.username is None and target.password is None)


def signed_block(handler, signature):
    # WebKit callbacks can arrive without a block signature on current macOS/PyObjC.
    # Same narrowly scoped compatibility technique used by pywebview's Cocoa host.
    if not handler.__block_signature__:
        library = ctypes.PyDLL(objc._objc.__file__)
        factory = library.PyObjCMethodSignature_WithMetaData
        factory.restype = ctypes.py_object
        factory.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_bool]
        handler.__block_signature__ = factory(signature, None, False)
    return handler


class EditorWindow(NSWindow):
    pass


class EditorDelegate(NSObject, protocols=[objc.protocolNamed('WKNavigationDelegate'),
                                         objc.protocolNamed('WKUIDelegate'),
                                         objc.protocolNamed('NSWindowDelegate')]):

    @objc.python_method
    def configure(self, origin, server, window, view):
        self.origin, self.server, self.window, self.view = origin, server, window, view
        self.close_approved = False
        self.close_pending = False

    def webView_decidePolicyForNavigationAction_decisionHandler_(self, view, action, handler):
        handler = signed_block(handler, b'v@q')
        uri = str(action.request().URL().absoluteString())
        allowed = action.targetFrame() is not None and local_navigation(uri, self.origin)
        handler(WKNavigationActionPolicyAllow if allowed else WKNavigationActionPolicyCancel)

    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(self, *args):
        return None

    def webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_(self, view, parameters, frame, handler):
        handler = signed_block(handler, b'v@@')
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(parameters.allowsMultipleSelection())
        panel.beginSheetModalForWindow_completionHandler_(self.window,
            lambda result: handler(panel.URLs() if result == NSModalResponseOK else None))

    def webView_runJavaScriptAlertPanelWithMessage_initiatedByFrame_completionHandler_(self, view, message, frame, handler):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(message)
        alert.addButtonWithTitle_('确定')
        alert.runModal()
        signed_block(handler, b'v@')()

    def webView_runJavaScriptConfirmPanelWithMessage_initiatedByFrame_completionHandler_(self, view, message, frame, handler):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(message)
        alert.addButtonWithTitle_('确定'); alert.addButtonWithTitle_('取消')
        signed_block(handler, b'v@B')(alert.runModal() == NSAlertFirstButtonReturn)

    def windowShouldClose_(self, sender):
        if self.close_approved:
            return True
        if self.close_pending:
            return False
        if not self.server.write_lock.acquire(blocking=False):
            alert = NSAlert.alloc().init()
            alert.setMessageText_('操作仍在进行，请完成后再关闭')
            alert.runModal()
            return False
        self.close_pending = True

        def checked(dirty, error):
            approved = error is None and not dirty
            if not approved:
                alert = NSAlert.alloc().init()
                alert.setMessageText_('放弃未保存的设置并关闭？')
                alert.addButtonWithTitle_('取消'); alert.addButtonWithTitle_('放弃并关闭')
                approved = alert.runModal() != NSAlertFirstButtonReturn
            self.close_pending = False
            if approved:
                self.close_approved = True
                self.window.close()
            else:
                self.server.write_lock.release()
        self.view.evaluateJavaScript_completionHandler_(
            'Boolean(document.getElementById("save-state")?.classList.contains("dirty"))', checked)
        return False

    def windowWillClose_(self, notification):
        NSApplication.sharedApplication().stop_(None)

    def quit_(self, sender):
        self.window.performClose_(None)


def create_window(url, server):
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    config = WKWebViewConfiguration.alloc().init()
    config.setWebsiteDataStore_(WKWebsiteDataStore.nonPersistentDataStore())
    config.setMediaTypesRequiringUserActionForPlayback_(0)
    view = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, 1280, 900), config)
    mask = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
            NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable)
    window = EditorWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 1280, 900), mask, NSBackingStoreBuffered, False)
    window.setReleasedWhenClosed_(False)
    window.setTitle_('Codexflare')
    window.setMinSize_(NSMakeSize(800, 600))
    window.setAppearance_(NSAppearance.appearanceNamed_(NSAppearanceNameDarkAqua))
    window.setContentView_(view)
    window.center()
    delegate = EditorDelegate.alloc().init()
    delegate.configure(url, server, window, view)
    window.setDelegate_(delegate)
    view.setNavigationDelegate_(delegate)
    view.setUIDelegate_(delegate)
    # Keep the delegate alive: Cocoa's delegate properties are weak.
    window.codexflare_delegate = delegate
    menu = NSMenu.alloc().init()
    app_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Codexflare', None, '')
    submenu = NSMenu.alloc().initWithTitle_('Codexflare')
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Quit Codexflare', 'quit:', 'q')
    quit_item.setTarget_(delegate)
    submenu.addItem_(quit_item); app_item.setSubmenu_(submenu); menu.addItem_(app_item)
    edit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Edit', None, '')
    edit_menu = NSMenu.alloc().initWithTitle_('Edit')
    for title, action, key in (('Undo', 'undo:', 'z'), ('Cut', 'cut:', 'x'),
                               ('Copy', 'copy:', 'c'), ('Paste', 'paste:', 'v'), ('Select All', 'selectAll:', 'a')):
        edit_menu.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key))
    edit_item.setSubmenu_(edit_menu); menu.addItem_(edit_item)
    app.setMainMenu_(menu)
    view.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))
    return window, view


def run(url, server):
    app = NSApplication.sharedApplication()
    window, view = create_window(url, server)
    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()
