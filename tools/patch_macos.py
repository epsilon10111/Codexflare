"""Exact anchors reviewed for the supported macOS arm64 builds."""
BUILDS = {
    '26.1013.31256': {
        'version': '26.1013.31256', 'build': '20586',
        'main': '.vite/build/main-CLu1A25j.js',
        'preloads': (
            'rpc-44f82a48298e.js', 'app-main-aa050bc301e8.js',
            'app-initial-3ccf4886957f.js', 'app-primary-a33cb51a1875.js',
            'app-initial-e7c27dd40beb.css', 'app-primary-71492d0e9e92.css',
        ),
        'electron': 'D', 'saved_bounds': 'C', 'onboarding': 'YPe', 'equal': 'Fe',
        'protocol': 'Ke.deepLinks.registerProtocolClient()',
        'background_classes': {
            '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_etoz9_2',
            '_MainContentSurface_yl8z4_2': '_MainContentSurface_etoz9_2',
            '_MainContentViewport_yl8z4_2': '_MainContentViewport_etoz9_2',
            '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_5est5_2',
            '_compactScrollMask_121j8_2': '_compactScrollMask_121j8_2',
        },
        'background_styles': ('app-shared-ae384120d279.css', 'app-initial-e7c27dd40beb.css',
                              'thread-scroll-layout-24b9bd243051.css'),
    },
    '26.1021.31345': {
        'version': '26.1021.31345', 'build': '21828',
        'main': '.vite/build/main-0FVbxCQU.js',
        'preloads': (
            'rpc-f4d8744cf30b.js', 'app-main-a7fcc565935a.js',
            'app-initial-feb30b196d11.js', 'app-primary-7d7313419f84.js',
            'app-initial-56db6e0bcb8b.css', 'app-primary-5fa64a4ee99d.css',
        ),
        'electron': 'O', 'saved_bounds': 'S', 'onboarding': 'A5e', 'equal': 'q',
        'protocol': 'We.deepLinks.registerProtocolClient()',
        'background_classes': {
            '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_azz1c_2',
            '_MainContentSurface_yl8z4_2': '_MainContentSurface_azz1c_2',
            '_MainContentViewport_yl8z4_2': '_MainContentViewport_azz1c_2',
            '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_1q7o3_2',
            '_compactScrollMask_121j8_2': '_compactScrollMask_mpt93_2',
        },
        'background_styles': ('app-shared-bd3e4e649b69.css', 'app-initial-56db6e0bcb8b.css',
                              'app-primary-5fa64a4ee99d.css'),
    },
}
# Legacy callers retain the original release default; installation selects from its source.
VERSION = '26.1013.31256'
BUILD = BUILDS[VERSION]['build']
MAIN = BUILDS[VERSION]['main']
STARTUP_PRELOADS = BUILDS[VERSION]['preloads']
BACKGROUND_CLASSES = BUILDS[VERSION]['background_classes']
BACKGROUND_STYLES = BUILDS[VERSION]['background_styles']
SUPPORTED = '、'.join(f"{item['version']} / build {item['build']}" for item in BUILDS.values())


def select_build(version, build=None):
    selected = BUILDS.get(version) if isinstance(version, str) else None
    if selected is None or (build is not None and str(build) != selected['build']):
        raise ValueError(f'仅支持 macOS Codex {SUPPORTED}；当前 {version} / {build}')
    return selected


def patch_main(text, window_mode='restore', muted=True, *, preserve_identity=False, version=VERSION):
    if __package__:
        from .patch_app import replace_once
    else:
        from patch_app import replace_once
    build = select_build(version)
    electron, saved = build['electron'], build['saved_bounds']
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
        f'V.createPrimaryWindow({{title:{electron}.app.getName(),show:e,initialRoute:t===`/`?void 0:t,opener:n}})',
        f'V.createPrimaryWindow({{title:{electron}.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`||r?e:!0,'
        'initialRoute:t===`/`?void 0:t,opener:n,codexflareStartup:!e&&!r&&!V.getPrimaryWindow()})')
    anchor = f'minWidth:A?.width,minHeight:A?.height,webPreferences:F}},z=new {electron}.BrowserWindow(R);'
    if window_mode == 'restore':
        replacement = (anchor + 'if(' + gate + f'&&{saved}){{z.codexflareWindowMode=`restore`;'
            f'if(!{saved}.isMaximized){{let restore=()=>{{if(z.isDestroyed())return;'
            f'z.isMaximized()&&z.unmaximize();z.setBounds({{x:{saved}.x,y:{saved}.y,width:{saved}.width,height:{saved}.height}})}};'
            'restore();z.once(`ready-to-show`,restore)}}')
    else:
        replacement = ('minWidth:A?.width,minHeight:A?.height,webPreferences:F};'
            f'let codexflareMode={gate}?`{window_mode}`:null;'
            'if(codexflareMode){k=!1;if(codexflareMode===`centered`){'
            'let a=(Number.isFinite(R.x)&&Number.isFinite(R.y)?'
            f'{electron}.screen.getDisplayMatching(R):{electron}.screen.getPrimaryDisplay()).workArea,'
            'w=Math.min(1100,a.width),h=Math.min(760,a.height);'
            'Object.assign(R,{width:w,height:h,x:a.x+Math.round((a.width-w)/2),'
            'y:a.y+Math.round((a.height-h)/2),minWidth:Math.min(R.minWidth??w,w),'
            'minHeight:Math.min(R.minHeight??h,h)})}}'
            f'let z=new {electron}.BrowserWindow(R);if(codexflareMode){{z.codexflareWindowMode=codexflareMode;'
            'if(codexflareMode===`centered`){let place=()=>{if(z.isDestroyed())return;'
            'z.isMaximized()&&z.unmaximize();z.setBounds({x:R.x,y:R.y,width:R.width,height:R.height})};'
            'place();z.once(`ready-to-show`,place)}'
            'if(codexflareMode===`fullscreen`){let enter=()=>{z.isDestroyed()||z.setFullScreen(!0)};'
            'z.isVisible()?enter():z.once(`show`,enter)}}')
        if window_mode == 'centered':
            text = replace_once(text,
                'let t=this.getPrimaryMinimumSize();for(let n of e){if(n.setMinimumSize(t.width,t.height)',
                'for(let n of e){let t=this.getPrimaryMinimumSize();'
                f'if(n.codexflareWindowMode===`centered`){{let a={electron}.screen.getDisplayMatching(n.getBounds()).workArea;'
                't={width:Math.min(t.width,a.width),height:Math.min(t.height,a.height)}}'
                'if(n.setMinimumSize(t.width,t.height)')
    text = replace_once(text, anchor, replacement)
    onboarding = f"{build['onboarding']}(t);if((0,{build['equal']}.default)(this.primaryWindowMode,t))"
    text = replace_once(text, 'let i=' + onboarding, 'let i=n.codexflareWindowMode?null:' + onboarding)
    # Standalone copies do not claim the vendor scheme; an original-entry build keeps it.
    protocol = build['protocol']
    return replace_once(text, protocol, protocol if preserve_identity else 'void 0')


def adapt_background_classes(text, *, version=VERSION):
    for old, new in select_build(version)['background_classes'].items():
        text = text.replace(old, new)
    return text.replace('.bg-gradient-to-t.from-surface',
                        '._background_106nk_2._fade_106nk_2.from-surface')


def patch_background_css(text, archive, *, version=VERSION):
    build = select_build(version)
    styles = '\n'.join(archive.read('webview/assets/' + name).decode() for name in build['background_styles'])
    for current in (*build['background_classes'].values(), '_background_106nk_2', '_fade_106nk_2', '_surface_106nk_2'):
        if '.' + current not in styles:
            raise ValueError(f'Background selector missing from the supported macOS build: {current}')
    return adapt_background_classes(text, version=version)


def adapt_background_fixture(text, *, version=VERSION):
    text = adapt_background_classes(text, version=version)
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
