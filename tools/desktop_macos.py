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
                    NSAppearanceNameDarkAqua, NSTerminateCancel)
from WebKit import (WKWebView, WKWebViewConfiguration, WKWebsiteDataStore,
                    WKNavigationActionPolicyAllow, WKNavigationActionPolicyCancel)


def local_navigation(uri, origin):
    target, home = urlsplit(uri), urlsplit(origin)
    return (target.scheme == home.scheme and target.netloc == home.netloc
            and target.username is None and target.password is None)


# WKWebView can supply C++-generated blocks without introspection metadata. Invoke
# these four fixed callback types using Apple's documented Block ABI, rather than
# relying on removed private PyObjC signature-constructor symbols.
# https://clang.llvm.org/docs/Block-ABI-Apple.html
class _Block(ctypes.Structure):
    _fields_ = [('isa', ctypes.c_void_p), ('flags', ctypes.c_int),
                ('reserved', ctypes.c_int), ('invoke', ctypes.c_void_p)]


def call_block(handler, kind=None, value=None):
    if handler.__block_signature__ is not None:
        return handler() if kind is None else handler(value)
    address = objc.pyobjc_id(handler)
    invoke = _Block.from_address(address).invoke
    if kind is None:
        ctypes.CFUNCTYPE(None, ctypes.c_void_p)(invoke)(address)
    else:
        type_ = {'integer': ctypes.c_long, 'bool': ctypes.c_bool, 'object': ctypes.c_void_p}[kind]
        argument = (None if value is None else objc.pyobjc_id(value)) if kind == 'object' else value
        ctypes.CFUNCTYPE(None, ctypes.c_void_p, type_)(invoke)(address, argument)


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
        uri = str(action.request().URL().absoluteString())
        allowed = action.targetFrame() is not None and local_navigation(uri, self.origin)
        call_block(handler, 'integer', WKNavigationActionPolicyAllow if allowed else WKNavigationActionPolicyCancel)

    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(self, view, config, action, features):
        return None

    def webView_runOpenPanelWithParameters_initiatedByFrame_completionHandler_(self, view, parameters, frame, handler):
        panel = NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(True)
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(parameters.allowsMultipleSelection())
        panel.beginSheetModalForWindow_completionHandler_(self.window,
            lambda result: call_block(handler, 'object', panel.URLs() if result == NSModalResponseOK else None))

    def webView_runJavaScriptAlertPanelWithMessage_initiatedByFrame_completionHandler_(self, view, message, frame, handler):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(message)
        alert.addButtonWithTitle_('确定')
        alert.runModal()
        call_block(handler)

    def webView_runJavaScriptConfirmPanelWithMessage_initiatedByFrame_completionHandler_(self, view, message, frame, handler):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(message)
        alert.addButtonWithTitle_('确定'); alert.addButtonWithTitle_('取消')
        call_block(handler, 'bool', alert.runModal() == NSAlertFirstButtonReturn)

    @objc.signature(b'B@:@')
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

    @objc.signature(b'Q@:@')
    def applicationShouldTerminate_(self, sender):
        self.window.performClose_(None)
        return NSTerminateCancel

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
    app.setDelegate_(delegate)
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
