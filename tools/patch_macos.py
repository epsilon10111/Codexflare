"""Exact anchors reviewed against the macOS arm64 26.1021.31345 / 21828 build."""
VERSION = '26.1021.31345'
BUILD = '21828'
MAIN = '.vite/build/main-0FVbxCQU.js'
STARTUP_PRELOADS = (
    'rpc-f4d8744cf30b.js', 'app-main-a7fcc565935a.js',
    'app-initial-feb30b196d11.js', 'app-primary-7d7313419f84.js',
    'app-initial-56db6e0bcb8b.css', 'app-primary-5fa64a4ee99d.css',
)


def patch_main(text, window_mode='restore', muted=True):
    if __package__:
        from .patch_app import replace_once
    else:
        from patch_app import replace_once
    if window_mode not in ('restore', 'fullscreen', 'centered') or type(muted) is not bool:
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
        'V.createPrimaryWindow({title:O.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n})',
        'V.createPrimaryWindow({title:O.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`||r?e:!0,'
        'initialRoute:t===`/`?void 0:t,opener:n,codexflareStartup:!e&&!r&&!V.getPrimaryWindow()})')
    anchor = 'minWidth:A?.width,minHeight:A?.height,webPreferences:F},z=new O.BrowserWindow(R);'
    if window_mode == 'restore':
        replacement = (anchor + 'if(' + gate + '&&S){z.codexflareWindowMode=`restore`;'
            'if(!S.isMaximized){let restore=()=>{if(z.isDestroyed())return;'
            'z.isMaximized()&&z.unmaximize();z.setBounds({x:S.x,y:S.y,width:S.width,height:S.height})};'
            'restore();z.once(`ready-to-show`,restore)}}')
    else:
        replacement = ('minWidth:A?.width,minHeight:A?.height,webPreferences:F};'
            f'let codexflareMode={gate}?`{window_mode}`:null;'
            'if(codexflareMode){k=!1;if(codexflareMode===`centered`){'
            'let a=(Number.isFinite(R.x)&&Number.isFinite(R.y)?'
            'O.screen.getDisplayMatching(R):O.screen.getPrimaryDisplay()).workArea,'
            'w=Math.min(1100,a.width),h=Math.min(760,a.height);'
            'Object.assign(R,{width:w,height:h,x:a.x+Math.round((a.width-w)/2),'
            'y:a.y+Math.round((a.height-h)/2),minWidth:Math.min(R.minWidth??w,w),'
            'minHeight:Math.min(R.minHeight??h,h)})}}'
            'let z=new O.BrowserWindow(R);if(codexflareMode){z.codexflareWindowMode=codexflareMode;'
            'if(codexflareMode===`centered`){let place=()=>{if(z.isDestroyed())return;'
            'z.isMaximized()&&z.unmaximize();z.setBounds({x:R.x,y:R.y,width:R.width,height:R.height})};'
            'place();z.once(`ready-to-show`,place)}'
            'if(codexflareMode===`fullscreen`){let enter=()=>{z.isDestroyed()||z.setFullScreen(!0)};'
            'z.isVisible()?enter():z.once(`show`,enter)}}')
        if window_mode == 'centered':
            text = replace_once(text,
                'let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height)',
                'for(let n of e){let t=this.getPrimaryMinimumSize();'
                'if(n.codexflareWindowMode===`centered`){let a=O.screen.getDisplayMatching(n.getBounds()).workArea;'
                't={width:Math.min(t.width,a.width),height:Math.min(t.height,a.height)}}'
                'if(n.setMinimumSize(t.width,t.height)')
    text = replace_once(text, anchor, replacement)
    text = replace_once(text, 'let i=A5e(t);if((0,q.default)(this.primaryWindowMode,t))',
        'let i=n.codexflareWindowMode?null:A5e(t);if((0,q.default)(this.primaryWindowMode,t))')
    # A local customization must not take over the vendor's URL scheme registration.
    return replace_once(text, 'We.deepLinks.registerProtocolClient()', 'void 0')

# CSS-module names are build-specific just like the main-process anchors.
BACKGROUND_CLASSES = {
    '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_azz1c_2',
    '_MainContentSurface_yl8z4_2': '_MainContentSurface_azz1c_2',
    '_MainContentViewport_yl8z4_2': '_MainContentViewport_azz1c_2',
    '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_1q7o3_2',
    '_compactScrollMask_121j8_2': '_compactScrollMask_mpt93_2',
}
BACKGROUND_STYLES = ('app-shared-bd3e4e649b69.css', 'app-initial-56db6e0bcb8b.css',
                     'app-primary-5fa64a4ee99d.css')


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
