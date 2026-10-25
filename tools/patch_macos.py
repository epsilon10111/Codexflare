"""Exact anchors reviewed against the macOS arm64 26.1013.31256 / 20586 build."""
VERSION = '26.1013.31256'
BUILD = '20586'
MAIN = '.vite/build/main-CLu1A25j.js'
STARTUP_PRELOADS = (
    'rpc-44f82a48298e.js', 'app-main-aa050bc301e8.js',
    'app-initial-3ccf4886957f.js', 'app-primary-a33cb51a1875.js',
    'app-initial-e7c27dd40beb.css', 'app-primary-71492d0e9e92.css',
)


def patch_main(text, window_mode='restore', muted=True, *, preserve_identity=False):
    if __package__:
        from .patch_app import replace_once
    else:
        from patch_app import replace_once
    if (window_mode not in ('restore', 'fullscreen', 'centered')
            or type(muted) is not bool or type(preserve_identity) is not bool):
        raise ValueError('无效的启动窗口或静音设置')
    gate = 'n&&!r&&e.codexflareStartup'
    sound = ('' if muted else gate + '&&z.webContents.once(`did-finish-load`,async()=>{try{'
             'await z.webContents.executeJavaScript("document.dispatchEvent(new Event(`codex-boot-play`))",!0)'
             '}catch{}});')
    text = replace_once(text,
        'await z.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}))',
        'await z.loadURL((()=>{' + sound +
        'let u=new URL(t.o(p,{mcpAppSandboxLocalDevelopment:P}));'
        + gate + '&&u.searchParams.set(`codexBootAnimation`,`1`);return u.toString()})())')
    text = replace_once(text,
        'V.createPrimaryWindow({title:D.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n})',
        'V.createPrimaryWindow({title:D.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`||r?e:!0,'
        'initialRoute:t===`/`?void 0:t,opener:n,codexflareStartup:!e&&!r&&!V.getPrimaryWindow()})')
    anchor = 'minWidth:A?.width,minHeight:A?.height,webPreferences:F},z=new D.BrowserWindow(R);'
    if window_mode == 'restore':
        replacement = (anchor + 'if(' + gate + '&&C){z.codexflareWindowMode=`restore`;'
            'if(!C.isMaximized){let restore=()=>{if(z.isDestroyed())return;'
            'z.isMaximized()&&z.unmaximize();z.setBounds({x:C.x,y:C.y,width:C.width,height:C.height})};'
            'restore();z.once(`ready-to-show`,restore)}}')
    else:
        replacement = ('minWidth:A?.width,minHeight:A?.height,webPreferences:F};'
            f'let codexflareMode={gate}?`{window_mode}`:null;'
            'if(codexflareMode){k=!1;if(codexflareMode===`centered`){'
            'let a=(Number.isFinite(R.x)&&Number.isFinite(R.y)?'
            'D.screen.getDisplayMatching(R):D.screen.getPrimaryDisplay()).workArea,'
            'w=Math.min(1100,a.width),h=Math.min(760,a.height);'
            'Object.assign(R,{width:w,height:h,x:a.x+Math.round((a.width-w)/2),'
            'y:a.y+Math.round((a.height-h)/2),minWidth:Math.min(R.minWidth??w,w),'
            'minHeight:Math.min(R.minHeight??h,h)})}}'
            'let z=new D.BrowserWindow(R);if(codexflareMode){z.codexflareWindowMode=codexflareMode;'
            'if(codexflareMode===`centered`){let place=()=>{if(z.isDestroyed())return;'
            'z.isMaximized()&&z.unmaximize();z.setBounds({x:R.x,y:R.y,width:R.width,height:R.height})};'
            'place();z.once(`ready-to-show`,place)}'
            'if(codexflareMode===`fullscreen`){let enter=()=>{z.isDestroyed()||z.setFullScreen(!0)};'
            'z.isVisible()?enter():z.once(`show`,enter)}}')
        if window_mode == 'centered':
            text = replace_once(text,
                'let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height)',
                'for(let n of e){let t=this.getPrimaryMinimumSize();'
                'if(n.codexflareWindowMode===`centered`){let a=D.screen.getDisplayMatching(n.getBounds()).workArea;'
                't={width:Math.min(t.width,a.width),height:Math.min(t.height,a.height)}}'
                'if(n.setMinimumSize(t.width,t.height)')
    text = replace_once(text, anchor, replacement)
    text = replace_once(text, 'let i=YPe(t);if((0,Fe.default)(this.primaryWindowMode,t))',
        'let i=n.codexflareWindowMode?null:YPe(t);if((0,Fe.default)(this.primaryWindowMode,t))')
    # Standalone copies do not claim the vendor scheme; an original-entry build keeps it.
    protocol = 'Ke.deepLinks.registerProtocolClient()'
    return replace_once(text, protocol, protocol if preserve_identity else 'void 0')

# CSS-module names are build-specific just like the main-process anchors.
BACKGROUND_CLASSES = {
    '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_etoz9_2',
    '_MainContentSurface_yl8z4_2': '_MainContentSurface_etoz9_2',
    '_MainContentViewport_yl8z4_2': '_MainContentViewport_etoz9_2',
    '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_5est5_2',
    '_compactScrollMask_121j8_2': '_compactScrollMask_121j8_2',
}
BACKGROUND_STYLES = ('app-shared-ae384120d279.css', 'app-initial-e7c27dd40beb.css',
                     'thread-scroll-layout-24b9bd243051.css')


def adapt_background_classes(text):
    for old, new in BACKGROUND_CLASSES.items():
        text = text.replace(old, new)
    return text.replace('.bg-gradient-to-t.from-surface',
                        '._background_106nk_2._fade_106nk_2.from-surface')


def patch_background_css(text, archive):
    styles = '\n'.join(archive.read('webview/assets/' + name).decode() for name in BACKGROUND_STYLES)
    for current in (*BACKGROUND_CLASSES.values(), '_background_106nk_2', '_fade_106nk_2', '_surface_106nk_2'):
        if '.' + current not in styles:
            raise ValueError(f'Background selector missing from the supported macOS build: {current}')
    return adapt_background_classes(text)


def adapt_background_fixture(text):
    text = adapt_background_classes(text)
    replacements = {
        'pointer-events-none absolute inset-x-0 -top-8 z-0 h-8 bg-gradient-to-t from-surface':
            '_background_106nk_2 _fade_106nk_2 pointer-events-none absolute inset-x-0 z-0 from-surface',
        'pointer-events-none absolute inset-x-0 -top-8 z-0 bottom-0 mt-8 bg-surface':
            '_background_106nk_2 _surface_106nk_2 pointer-events-none absolute inset-x-0 z-0 bottom-0 bg-surface',
    }
    for old, new in replacements.items():
        if text.count(old) != 2:
            raise ValueError('Unexpected footer fixture structure')
        text = text.replace(old, new)
    return text
