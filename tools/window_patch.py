"""Patch the reviewed window flow by semantic anchors and captured local bindings.

These are deliberately narrow structural matches, not a general JS rewriter.
Renamed minifier bindings are accepted; missing or ambiguous flows are rejected.
"""
import re
from string import Template

IDENT = r'[A-Za-z_$][\w$]*'


def one(pattern, text, role):
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError(f'不兼容的窗口结构: {role} 必须唯一 (找到 {len(matches)})')
    return matches[0]


def patch_main(text, window_mode='restore', muted=True, *, protocol=False):
    if window_mode not in ('restore', 'fullscreen', 'centered'):
        raise ValueError('无效的启动窗口方式')
    if type(muted) is not bool:
        raise ValueError('静音开关必须是布尔值')
    if 'codexflare' in text or 'codexBootAnimation' in text:
        raise ValueError('主进程已经包含 Codexflare 补丁')
    edits = []

    def render(template, **bindings):
        return Template(template).substitute(bindings)

    gate = one(r'let\s+(?P<primary>'+IDENT+r')=\((?P<options>'+IDENT+
               r')\.appearance\?\?[`\'"]primary[`\'"]\)===[`\'"]primary[`\'"],'
               r'(?P<page>'+IDENT+r')=(?P=primary)&&', text, 'primary/page classification')
    ctor = one(r'minWidth:(?P<minimum>'+IDENT+r')\?\.width,minHeight:(?P=minimum)\?\.height,'
               r'webPreferences:(?P<prefs>'+IDENT+r')\},(?P<window>'+IDENT+r')=new '
               r'(?P<electron>'+IDENT+r')\.BrowserWindow\((?P<config>'+IDENT+r')\);', text, 'BrowserWindow')
    load = one(r'await (?P<window>'+IDENT+r')\.loadURL\((?P<url>'+IDENT+r'\.'+IDENT+r'\('
               +IDENT+r',\{mcpAppSandboxLocalDevelopment:'+IDENT+r'\}\))\)', text, 'packaged loadURL')
    if not gate.end() < ctor.start() < load.start() or ctor['window'] != load['window']:
        raise ValueError('不兼容的主窗口创建/加载顺序')
    context = text[gate.end():ctor.start()]
    saved = one(r'(?P<maximized>'+IDENT+r')=(?P<saved>'+IDENT+r')\?\.isMaximized===(?:!0|true)',
                context, 'saved maximization')
    show = one(r'\bshow:(?P<show>'+IDENT+r')=(?:!0|true)', context, 'initial visibility')
    caller = one(r'(?P<manager>'+IDENT+r')\.createPrimaryWindow\(\{title:(?P<electron>'+IDENT+
                 r')\.app.getName\(\),show:(?P<show>'+IDENT+r'),initialRoute:(?P<route>'+IDENT+
                 r')===[`\'"]/[`\'"]\?void 0:(?P=route),opener:(?P<opener>'+IDENT+r')\}\)',
                 text, 'startup caller')
    # Newer builds explicitly distinguish background launches at this call site.
    backgrounds = list(re.finditer(r'\bbackground:('+IDENT+r')=(?:!1|false)',
                                   text[max(0, caller.start()-400):caller.start()]))
    if len(backgrounds) > 1:
        raise ValueError('后台启动标记不唯一')
    background = backgrounds[0][1] if backgrounds else None
    modern = background is not None
    bindings = gate.groupdict() | ctor.groupdict() | saved.groupdict() | show.groupdict()
    # The legacy flow only animates visible windows; modern callers carry an explicit startup flag.
    condition = render('$primary&&!$page&&', **gate.groupdict()) + (
        render('$options.codexflareStartup', **gate.groupdict()) if modern else show['show'])
    startup = condition if modern else condition + '&&' + gate['options'] + '.codexflareStartup'
    bindings['gate'] = startup

    audio = '' if muted else render(
        '$condition&&$window.webContents.once(`$event`,async()=>{try{'
        'await $window.webContents.executeJavaScript("document.dispatchEvent(new Event(`codex-boot-play`))",!0)'
        '}catch{}});', condition=condition, window=load['window'], event='did-finish-load' if modern else 'dom-ready')
    edits.append((load, render('await $window.loadURL((()=>{$audio'
        'let codexflareUrl=new URL($url);$condition&&codexflareUrl.searchParams.set(`codexBootAnimation`,`1`);'
        'return codexflareUrl.toString()})())', **load.groupdict(), audio=audio, condition=condition)))
    edits.append((caller, render('$manager.createPrimaryWindow({title:$electron.app.getName(),'
        'show:process.env.CODEX_ELECTRON_START_IN_BACKGROUND===`1`$background?$show:!0,'
        'initialRoute:$route===`/`?void 0:$route,opener:$opener,'
        'codexflareStartup:!$show$foreground&&!$manager.getPrimaryWindow()})', **caller.groupdict(),
        background='||'+background if modern else '', foreground='&&!'+background if modern else '')))
    if window_mode == 'restore':
        replacement = ctor[0] + render('if($gate&&$saved){$window.codexflareWindowMode=`restore`;', **bindings)
        if modern:
            replacement += render('if(!$saved.isMaximized){let restore=()=>{if($window.isDestroyed())return;'
                '$window.isMaximized()&&$window.unmaximize();'
                '$window.setBounds({x:$saved.x,y:$saved.y,width:$saved.width,height:$saved.height})};'
                'restore();$window.once(`ready-to-show`,restore)}', **bindings)
        replacement += '}'
    else:
        replacement = render('minWidth:$minimum?.width,minHeight:$minimum?.height,webPreferences:$prefs};'
            'let codexflareMode=$gate?`$mode`:null;if(codexflareMode){$maximized=!1;'
            'if(codexflareMode===`centered`){let a=(Number.isFinite($config.x)&&Number.isFinite($config.y)?'
            '$electron.screen.getDisplayMatching($config):$electron.screen.getPrimaryDisplay()).workArea,'
            'w=Math.min(1100,a.width),h=Math.min(760,a.height);'
            'Object.assign($config,{width:w,height:h,x:a.x+Math.round((a.width-w)/2),'
            'y:a.y+Math.round((a.height-h)/2),minWidth:Math.min($config.minWidth??w,w),'
            'minHeight:Math.min($config.minHeight??h,h)})}}'
            'let $window=new $electron.BrowserWindow($config);'
            'if(codexflareMode){$window.codexflareWindowMode=codexflareMode;', **bindings, mode=window_mode)
        if modern:
            replacement += render('if(codexflareMode===`centered`){let place=()=>{if($window.isDestroyed())return;'
                '$window.isMaximized()&&$window.unmaximize();'
                '$window.setBounds({x:$config.x,y:$config.y,width:$config.width,height:$config.height})};'
                'place();$window.once(`ready-to-show`,place)}', **bindings)
        replacement += render('if(codexflareMode===`fullscreen`){let enter=()=>{'
            '$window.isDestroyed()||$window.setFullScreen(!0)};'
            '$window.isVisible()?enter():$window.once(`show`,enter)}}', **bindings)
    edits.append((ctor, replacement))

    resize = one(r'let (?P<size>'+IDENT+r')=this.getPrimaryMinimumSize\(\);for\(let (?P<win>'+IDENT+
                 r') of (?P<windows>'+IDENT+r')\)\{if\((?P=win)\.setMinimumSize\((?P=size)\.width,(?P=size)\.height\)',
                 text, 'minimum size synchronization')
    if window_mode == 'centered':
        edits.append((resize, render('for(let $win of $windows){let $size=this.getPrimaryMinimumSize();'
            'if($win.codexflareWindowMode===`centered`){let a=$electron.screen.getDisplayMatching($win.getBounds()).workArea;'
            '$size={width:Math.min($size.width,a.width),height:Math.min($size.height,a.height)}}'
            'if($win.setMinimumSize($size.width,$size.height)', **resize.groupdict(), electron=ctor['electron'])))
    onboarding = one(r'let (?P<result>'+IDENT+r')=(?P<helper>'+IDENT+r')\((?P<mode>'+IDENT+r')\);'
                     r'if\(\(0,(?P<compare>'+IDENT+r')\.default\)\(this.primaryWindowMode,(?P=mode)\)\)',
                     text, 'onboarding window mode')
    prefix = text[max(0, onboarding.start()-1000):onboarding.start()]
    windows = list(re.finditer(r'('+IDENT+r')='+re.escape(ctor['electron'])+
                              r'\.BrowserWindow.fromWebContents\(', prefix))
    if windows:
        mode_window = windows[-1][1]
    else:
        # Unbundled equivalents can receive the window directly.
        mode_window = one(r'function '+IDENT+r'\(('+IDENT+r'),'+re.escape(onboarding['mode'])+r'\)\{\s*$',
                          prefix, 'window mode arguments')[1]
    edits.append((onboarding, render('let $result=$window.codexflareWindowMode?null:$helper($mode);'
        'if((0,$compare.default)(this.primaryWindowMode,$mode))', **onboarding.groupdict(), window=mode_window)))
    if protocol:
        registration = one(IDENT+r'\.deepLinks.registerProtocolClient\(\)', text, 'protocol registration')
        edits.append((registration, 'void 0'))
    for match, replacement in sorted(edits, key=lambda edit: edit[0].start(), reverse=True):
        text = text[:match.start()] + replacement + text[match.end():]
    return text
