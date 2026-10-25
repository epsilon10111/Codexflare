"""Exact anchors reviewed against the macOS arm64 26.1016.61520 / 21421 build."""
VERSION = '26.1016.61520'
BUILD = '21421'
MAIN = '.vite/build/main-JI9qDiXp.js'
STARTUP_PRELOADS = (
    'rpc-e7720454018f.js', 'app-main-192108c1edfe.js',
    'app-initial-c95ddb62696e.js', 'app-primary-58a09006cc0c.js',
    'app-initial-9d42883ac737.css', 'app-primary-4d86db640757.css',
)


def patch_main(text, window_mode='restore', muted=True):
    if __package__:
        from .patch_app import replace_once
    else:
        from patch_app import replace_once
    if window_mode not in ('restore', 'fullscreen', 'centered') or type(muted) is not bool:
        raise ValueError('无效的启动窗口或静音设置')
    gate = 'n&&!r&&e.codexflareStartup'
    sound = ('' if muted else gate + '&&R.webContents.once(`dom-ready`,async()=>{try{'
             'await R.webContents.executeJavaScript("document.dispatchEvent(new Event(`codex-boot-play`))",!0)'
             '}catch{}});')
    text = replace_once(text,
        'await R.loadURL(t.o(p,{mcpAppSandboxLocalDevelopment:P}))',
        'await R.loadURL((()=>{' + sound +
        'let u=new URL(t.o(p,{mcpAppSandboxLocalDevelopment:P}));'
        + gate + '&&u.searchParams.set(`codexBootAnimation`,`1`);return u.toString()})())')
    text = replace_once(text,
        'B.createPrimaryWindow({title:O.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n})',
        'B.createPrimaryWindow({title:O.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`||r?e:!0,'
        'initialRoute:t===`/`?void 0:t,opener:n,codexflareStartup:!e&&!r&&!B.getPrimaryWindow()})')
    anchor = 'minWidth:A?.width,minHeight:A?.height,webPreferences:F},R=new O.BrowserWindow(L);'
    if window_mode == 'restore':
        replacement = anchor + gate + '&&S&&(R.codexflareWindowMode=`restore`);'
    else:
        replacement = ('minWidth:A?.width,minHeight:A?.height,webPreferences:F};'
            f'let codexflareMode={gate}?`{window_mode}`:null;'
            'if(codexflareMode){k=!1;if(codexflareMode===`centered`){'
            'let a=(Number.isFinite(L.x)&&Number.isFinite(L.y)?'
            'O.screen.getDisplayMatching(L):O.screen.getPrimaryDisplay()).workArea,'
            'w=Math.min(1100,a.width),h=Math.min(760,a.height);'
            'Object.assign(L,{width:w,height:h,x:a.x+Math.round((a.width-w)/2),'
            'y:a.y+Math.round((a.height-h)/2),minWidth:Math.min(L.minWidth??w,w),'
            'minHeight:Math.min(L.minHeight??h,h)})}}'
            'let R=new O.BrowserWindow(L);if(codexflareMode){R.codexflareWindowMode=codexflareMode;'
            'if(codexflareMode===`fullscreen`){let enter=()=>{R.isDestroyed()||R.setFullScreen(!0)};'
            'R.isVisible()?enter():R.once(`show`,enter)}}')
        if window_mode == 'centered':
            text = replace_once(text,
                'let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height)',
                'for(let n of e){let t=this.getPrimaryMinimumSize();'
                'if(n.codexflareWindowMode===`centered`){let a=O.screen.getDisplayMatching(n.getBounds()).workArea;'
                't={width:Math.min(t.width,a.width),height:Math.min(t.height,a.height)}}'
                'if(n.setMinimumSize(t.width,t.height)')
    text = replace_once(text, anchor, replacement)
    text = replace_once(text, 'let i=gFe(t);if((0,G.default)(this.primaryWindowMode,t))',
        'let i=n.codexflareWindowMode?null:gFe(t);if((0,G.default)(this.primaryWindowMode,t))')
    # A local customization must not take over the vendor's URL scheme registration.
    return replace_once(text, 'Ke.deepLinks.registerProtocolClient()', 'void 0')
