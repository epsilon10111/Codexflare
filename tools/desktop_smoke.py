#!/usr/bin/python3
"""在隔离配置下自检独立桌面窗口，保留截图，不安装或恢复 Codex。"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import struct
import sys
import zlib
import tempfile
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, help='从解包的应用目录加载代码与资源；输出仍保存在源码仓库 work 中')
    args = parser.parse_args()
    if args.app_root:
        args.app_root = args.app_root.resolve()
        if not all((args.app_root / 'tools' / name).is_file() for name in ('animation.py', 'desktop.py', 'editor.py')):
            parser.error('--app-root 必须包含 Codexflare 的 tools 目录')
        sys.path.insert(0, str(args.app_root / 'tools'))
    if __package__ and not args.app_root:
        from . import animation, desktop, editor
    else:
        import animation
        import desktop
        import editor
    if args.app_root:
        assert all(Path(module.__file__).resolve().parents[1] == args.app_root
                   for module in (animation, desktop, editor)), '未加载指定应用目录中的模块'
    Gtk = desktop.init_desktop()
    from gi.repository import Gdk, GLib, WebKit2
    work = Path(__file__).resolve().parents[1] / 'work'
    work.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='desktop-smoke-', dir=work))
    expected = animation.DEFAULT_SETTINGS | {
        'speed': 0.5, 'brightness': 1.25, 'contrast': 1.1, 'saturation': 0.8, 'fit': 'contain',
        'windowMode': 'centered',
    }
    state = {'phase': -3, 'logged': None, 'pending': False, 'closed': False, 'chooser': False,
             'error': None, 'try_close_calls': 0, 'native': {}, 'background_chooser': False, 'close_cancelled': False}
    with tempfile.TemporaryDirectory(prefix='codex-desktop-test-') as folder, ExitStack() as patches:
        local = Path(folder)
        for name, value in {'LOCAL': local, 'SETTINGS': local / 'animation.json', 'MEDIA': local / 'media'}.items():
            patches.enter_context(patch.object(animation, name, value))
        fixture = work / 'editor-qa/upload-test.mp4'
        if not fixture.is_file():
            fixture = local / 'upload-test.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=320x180:rate=24:duration=3', '-c:v', 'mpeg4', str(fixture)], check=True)
        def png_chunk(kind, payload):
            return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload))
        background_fixture = local / 'background-test.png'
        pixels = b''.join(b'\x00' + b''.join(bytes((x % 256, y % 256, 170)) for x in range(640)) for y in range(360))
        background_fixture.write_bytes(b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 640, 360, 8, 2, 0, 0, 0))
                                       + png_chunk(b'IDAT', zlib.compress(pixels)) + png_chunk(b'IEND', b''))
        broken_background = local / 'broken.png'
        broken_background.write_bytes(b'broken png')
        server = editor.EditorServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        window, view = desktop.create_window(f'http://127.0.0.1:{server.server_port}', server)
        titlebar = window.get_titlebar()
        assert window.get_title() == 'Codexflare' and titlebar.get_title() == 'Codexflare', '小程序名称未更新'
        window.set_title('Codexflare · 自动验证中')
        titlebar.set_title('Codexflare · 自动验证中，请勿操作')
        assert isinstance(titlebar, Gtk.HeaderBar), '未安装原生自绘标题栏'
        assert window.get_decorated() and window.get_resizable(), '窗口装饰或缩放被禁用'
        original_close = view.try_close
        def traced_close():
            state['try_close_calls'] += 1
            original_close()
        view.try_close = traced_close
        deadline = time.monotonic() + 120

        def title_buttons():
            buttons = {}
            def visit(widget):
                style = widget.get_style_context()
                for name in ('minimize', 'maximize', 'close'):
                    if style.has_class('titlebutton') and style.has_class(name):
                        buttons[name] = widget
                if isinstance(widget, Gtk.Container):
                    widget.forall(visit)
            visit(titlebar)
            assert set(buttons) == {'minimize', 'maximize', 'close'}, '标题栏按钮不完整'
            return buttons

        def motion(x, y):
            event = Gdk.Event.new(Gdk.EventType.MOTION_NOTIFY)
            event.window, event.x, event.y = view.get_window(), x, y
            event.time, event.send_event = Gdk.CURRENT_TIME, True
            event.set_device(Gdk.Display.get_default().get_default_seat().get_pointer())
            view.event(event)

        def button_evidence():
            evidence = {}
            for name, button in title_buttons().items():
                rect = button.get_allocation()
                icons = []
                def visit(widget):
                    if isinstance(widget, Gtk.Image):
                        color = widget.get_style_context().get_color(widget.get_state_flags())
                        translated = widget.translate_coordinates(window, 0, 0)
                        assert translated, '无法定位标题栏图标'
                        x, y = translated[-2:]
                        width, height = widget.get_allocated_width(), widget.get_allocated_height()
                        native = window.get_window()
                        assert x >= 0 and y >= 0 and x + width <= native.get_width() and y + height <= native.get_height()
                        pixels = Gdk.pixbuf_get_from_window(native, x, y, width, height)
                        assert pixels, '无法读取标题栏图标像素'
                        raw, stride, channels = pixels.get_pixels(), pixels.get_rowstride(), pixels.get_n_channels()
                        bright = sum(max(raw[row * stride + col * channels:row * stride + col * channels + 3]) > 100
                                     for row in range(height) for col in range(width))
                        icons.append({'name': widget.get_icon_name()[0], 'alpha': color.alpha,
                                      'bounds': [x, y, width, height], 'bright_pixels': bright})
                    if isinstance(widget, Gtk.Container):
                        widget.forall(visit)
                visit(button)
                evidence[name] = {'visible': button.get_visible(), 'mapped': button.get_mapped(),
                                  'allocation': [rect.x, rect.y, rect.width, rect.height], 'icons': icons}
                assert button.get_visible() and button.get_mapped() and rect.width >= 16 and rect.height >= 16, f'{name} 按钮未显示'
                assert any(icon['alpha'] > 0 and icon['bright_pixels'] >= 3 for icon in icons), f'{name} 图标像素不可见'
            return evidence

        def fail(error):
            state['error'] = str(error)
            native = window.get_window()
            if native:
                pixels = Gdk.pixbuf_get_from_window(native, 0, 0, native.get_width(), native.get_height())
                if pixels:
                    pixels.savev(str(output / 'failure.png'), 'png', [], [])
            (output / 'failure.json').write_text(json.dumps(state, ensure_ascii=False, indent=2))
            window.destroy()

        def evaluate(script, callback=lambda value: None):
            state['pending'] = True
            def done(webview, result, _data):
                state['pending'] = False
                try:
                    callback(json.loads(webview.evaluate_javascript_finish(result).to_string()))
                except Exception as error:
                    fail(error)
            view.evaluate_javascript(script, -1, None, None, None, done, None)

        def action(script):
            evaluate('(() => {' + script + ';return JSON.stringify(true);})()')

        def choose_file(_view, request):
            if state['phase'] >= 11:
                state['background_chooser'] = True
                chosen = broken_background if state['phase'] == 15 else background_fixture
            else:
                state['chooser'] = True
                chosen = fixture
            request.select_files([str(chosen)])
            return True

        def snapshot(webview, result, filename):
            try:
                webview.get_snapshot_finish(result).write_to_png(str(output / filename.replace('.png', '-view.png')))
                native = window.get_window()
                pixels = Gdk.pixbuf_get_from_window(native, 0, 0, native.get_width(), native.get_height())
                assert pixels, '未能捕获包含标题栏的应用窗口'
                pixels.savev(str(output / filename), 'png', [], [])
                if filename == 'default.png':
                    state['native']['button_evidence'] = button_evidence()
                    state['phase'], state['resized_at'] = 7, time.monotonic()
                    window.resize(1000, 720)
                    return
                if filename == 'minimum.png':
                    state['phase'], state['scroll_index'], state['minimum_scroll'] = 10, 0, {}
                    action("document.getElementById('save').scrollIntoView({block:'center',behavior:'instant'})")
                    return
                if filename == 'background.png':
                    state['phase'] = 13
                    action("document.getElementById('background-enabled').click()")
                    return
                state['phase'] = 5
                action("const source=document.getElementById('video-source');source.value='default';"
                       "source.dispatchEvent(new Event('change'));document.getElementById('reset').click();"
                       "document.getElementById('save').click()")
            except Exception as error:
                fail(error)

        def check(data):
            state['last'] = data
            assert not data.get('error') or state['phase'] == 15, data.get('error')
            if not data.get('ready'):
                return
            phase = state['phase']
            if phase in (0, 1, 3, 7) and (phase != 7 or time.monotonic() - state['resized_at'] > 0.5):
                for name in ('save', 'install', 'video-source', 'upload-button', 'reset', 'window-mode', 'toggle-mute'):
                    rect = data['controls'][name]
                    assert (rect['width'] > 0 and rect['height'] > 0 and rect['left'] >= 0 and rect['top'] >= 0
                            and rect['right'] <= data['viewport']['width']
                            and (phase == 7 or rect['bottom'] <= data['viewport']['height'])), \
                        f'{name} 未在首屏完整显示：{rect}，视口{data["viewport"]}'
                assert data['page_width'] <= data['viewport']['width'] + 1, '页面出现横向溢出'
                for name, minimum in [('body', 16), ('h1', 28), ('h2', 18), ('.control-label', 15),
                                      ('#save', 15), ('#upload-button', 15), ('.field-hint', 13)]:
                    assert float(data['fonts'][name][:-2]) + 0.01 >= minimum, f'{name} 字号过小：{data["fonts"][name]}'
            if phase == 0:
                assert (data['width'], data['height']) == (1920, 1080), '默认视频未正常解码'
                assert data['window_mode'] == 'restore', '默认启动方式未恢复上次窗口'
                assert data['muted'] and data['mute_pressed'] == 'true', '默认静音状态不一致'
                assert data['background']['source'] == 'default', '未选择内置默认背景'
                state['hover_before'], state['hover_at'], state['phase'] = data['hover'], time.monotonic(), 8
                rect = data['controls']['upload-button']
                motion((rect['left'] + rect['width'] / 2) * view.get_allocated_width() / data['viewport']['width'],
                       (rect['top'] + rect['height'] / 2) * view.get_allocated_height() / data['viewport']['height'])
            elif phase == 8 and time.monotonic() - state['hover_at'] > 0.5:
                assert data['hover']['matched'], '原生指针事件未触发 WebKit 悬停'
                assert any(data['hover'][key] != state['hover_before'][key]
                           for key in ('background', 'border', 'transform')), '按钮悬停无可见样式响应'
                state['hover_after'], state['motion'] = data['hover'], data['motion']
                if data['motion']['reduced']:
                    assert all(item['animation'] == 'none' for item in data['motion']['elements'].values())
                else:
                    assert any(item['animation'] != 'none' for item in data['motion']['elements'].values()), '未检测到 CSS 动效'
                motion(2, 2)
                state['phase'] = 1
                action("for(const [id,value] of Object.entries({speed:.5,brightness:1.25,contrast:1.1,saturation:.8})){"
                       "const input=document.getElementById(id);input.value=value;input.dispatchEvent(new Event('input'));}"
                       "const mode=document.getElementById('window-mode');mode.value='centered';mode.dispatchEvent(new Event('change'));"
                       "const fit=document.querySelector('input[value=contain]');fit.checked=true;fit.dispatchEvent(new Event('change'));"
                       "document.getElementById('restart').click();document.getElementById('save').click()")
            elif phase == 1 and data['time'] > 1.4 and not data['paused'] and animation.load_settings() == expected:
                assert data['rate'] == 0.5 and data['fit'] == 'contain'
                assert data['window_mode'] == 'centered', '居中小窗口方式未保存'
                assert data['filter'] == 'brightness(1.25) contrast(1.1) saturate(0.8)'
                state['default_playback'] = data
                state['phase'] = 4
                view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, snapshot, 'default.png')
            elif phase == 7 and tuple(window.get_size()) == (1000, 720) and time.monotonic() - state['resized_at'] > 0.5:
                state['minimum'], state['phase'] = data, 4
                state['native']['minimum_size'] = list(window.get_size())
                view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, snapshot, 'minimum.png')
            elif phase == 9 and list(window.get_size()) == state['native']['default_size'] and time.monotonic() - state['resized_at'] > 0.5:
                state['phase'] = 2
                action("document.getElementById('upload-button').click()")
            elif phase == 10:
                names = ('save', 'install', 'video-source', 'upload-button', 'reset', 'window-mode', 'toggle-mute')
                name = names[state['scroll_index']]
                rect = data['controls'][name]
                assert rect['top'] >= -1 and rect['bottom'] <= data['viewport']['height'] + 1, f'最小窗口无法滚动到 {name}'
                state['minimum_scroll'][name] = rect
                state['scroll_index'] += 1
                if state['scroll_index'] < len(names):
                    action(f"document.getElementById('{names[state['scroll_index']]}').scrollIntoView({{block:'center',behavior:'instant'}})")
                else:
                    action("window.scrollTo(0,0);document.getElementById('adjustments').scrollTop=0")
                    state['phase'], state['resized_at'] = 9, time.monotonic()
                    window.resize(*state['native']['default_size'])
            elif phase == 2 and data['video'] != 'default':
                assert state['chooser'], '未经过原生文件选择器'
                assert (data['width'], data['height']) == (320, 180), '导入视频未正常解码'
                assert data['muted'] == expected['muted'], '更换视频不应改变静音偏好'
                assert data['rate'] == 0.5 and data['fit'] == 'contain'
                assert data['filter'] == 'brightness(1.25) contrast(1.1) saturate(0.8)'
                expected['video'] = data['video']
                assert animation.video_path(data['video']).is_file(), '未生成本地转码视频'
                state['phase'] = 3
                action("document.getElementById('restart').click();document.getElementById('save').click()")
            elif phase == 3 and data['time'] > 0.3 and not data['paused'] and animation.load_settings() == expected:
                state['imported_playback'] = data
                state['phase'] = 4
                view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, snapshot, 'desktop.png')
            elif phase == 5 and data['video'] == 'default' and data['saved'] and animation.load_settings() == animation.DEFAULT_SETTINGS | {'windowMode': 'centered'}:
                assert data['window_mode'] == 'centered', '重置动画参数不应重置启动方式'
                state['phase'] = 11
                action("document.getElementById('background-tab').click();document.getElementById('background-upload-button').click()")
            elif phase == 11 and data['background']['source'] != 'legacy' and data['background']['width'] == 640:
                assert state['background_chooser'], '图片未经过原生文件选择器'
                assert not data['background']['hidden'], '上传背景没有显示'
                state['phase'] = 12
                action("for(const [name,value] of Object.entries({opacity:.26,position:86,scale:92})){"
                       "const input=document.getElementById('background-'+name);input.value=value;input.dispatchEvent(new Event('input'));}"
                       "const mode=document.getElementById('window-mode');mode.value='fullscreen';mode.dispatchEvent(new Event('change'));"
                       "document.getElementById('save').click()")
            elif phase == 12 and data['saved']:
                background = animation.load_settings()['background']
                assert background == {'enabled': True, 'image': data['background']['source'], 'opacity': .26, 'position': 86, 'scale': 92}
                assert data['background']['opacity'] == '0.26' and data['background']['left'] == '40%'
                assert animation.load_settings()['windowMode'] == data['window_mode'] == 'fullscreen', '背景页未保存全屏方式'
                state['background'], state['phase'] = data['background'], 4
                view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, snapshot, 'background.png')
            elif phase == 13 and data['background']['hidden'] and not data['saved']:
                state['phase'] = 14
                title_buttons()['close'].clicked()
            elif phase == 14 and state['close_cancelled']:
                assert not state['closed'], '未保存背景的关闭取消未生效'
                state['phase'] = 15
                action("document.getElementById('background-upload-button').click()")
            elif phase == 15 and data.get('error'):
                assert 'PNG' in data['error'], '未显示图片格式错误'
                state['background_error'], state['phase'] = data['error'], 16
                action("document.getElementById('error-banner').hidden=true;document.getElementById('save').click()")
            elif phase == 16 and data['saved']:
                assert animation.load_settings()['background']['enabled'] is False
                assert animation.load_settings()['windowMode'] == 'fullscreen'
                state['phase'] = 17
                action("const mode=document.getElementById('window-mode');mode.value='restore';mode.dispatchEvent(new Event('change'));"
                       "document.getElementById('save').click()")
            elif phase == 17 and data['saved']:
                assert animation.load_settings()['windowMode'] == data['window_mode'] == 'restore', '恢复上次窗口方式未保存'
                state['window_modes'] = ['restore', 'centered', 'fullscreen', 'restore']
                assert data['paused'], '静音设置自检应在暂停状态进行'
                state['phase'] = 18
                action("document.getElementById('animation-tab').click();"
                       "document.getElementById('toggle-mute').click();document.getElementById('save').click()")
            elif phase == 18 and data['saved']:
                assert not data['muted'] and data['mute_pressed'] == 'false' and animation.load_settings()['muted'] is False
                state['phase'] = 19
                action("document.getElementById('refresh-state').click()")
            elif phase == 19 and data['saved']:
                assert not data['muted'] and data['mute_pressed'] == 'false', '刷新未保留声音偏好'
                state['mute_after_refresh'], state['phase'] = data['muted'], 20
                action("document.getElementById('toggle-mute').click();document.getElementById('save').click()")
            elif phase == 20 and data['saved']:
                assert data['muted'] and data['mute_pressed'] == 'true' and animation.load_settings()['muted'] is True
                state['phase'] = 21
                action("document.getElementById('background-tab').click();document.getElementById('background-enabled').click();"
                       "const image=document.getElementById('background-source');image.value='default2';image.dispatchEvent(new Event('change'));"
                       "document.getElementById('save').click()")
            elif phase == 21 and data['saved'] and data['background']['complete'] and data['background']['width'] > 0:
                assert animation.load_settings()['background']['image'] == data['background']['source'] == 'default2'
                assert data['background']['src'].endswith('/background/default2') and not data['background']['hidden']
                state['second_builtin'], state['phase'] = data['background'], 22
                action("const image=document.getElementById('background-source');image.value='default';image.dispatchEvent(new Event('change'));"
                       "document.getElementById('save').click()")
            elif phase == 22 and data['saved'] and data['background']['complete'] and data['background']['width'] > 0:
                assert animation.load_settings()['background']['image'] == data['background']['source'] == 'default'
                assert data['background']['src'].endswith('/background/default') and not data['background']['hidden']
                state['first_builtin'] = data['background']
                state['phase'] = 6
                title_buttons()['close'].clicked()

        def step():
            if state['logged'] != state['phase']:
                state['logged'] = state['phase']
                print(f"桌面自检阶段 {state['phase']}", flush=True)
            if time.monotonic() > deadline:
                fail(f"桌面自检超时，阶段 {state['phase']}：{state.get('last')}")
                return True
            native = window.get_window()
            if state['phase'] == -3 and native and window.get_mapped():
                state['native'] = {'decorated': window.get_decorated(), 'resizable': window.get_resizable(),
                                   'titlebar': titlebar.get_name(), 'titlebar_height': titlebar.get_allocated_height(),
                                   'default_size': list(window.get_size()), 'buttons': list(title_buttons())}
                assert 32 <= titlebar.get_allocated_height() <= 50, '标题栏高度不符合紧凑窗口要求'
                title_buttons()['maximize'].clicked()
                state['phase'] = -2
            elif state['phase'] == -2 and native.get_state() & Gdk.WindowState.MAXIMIZED:
                state['native']['maximized'] = True
                title_buttons()['maximize'].clicked()
                state['phase'] = -1
            elif state['phase'] == -1 and not native.get_state() & Gdk.WindowState.MAXIMIZED and list(window.get_size()) == state['native']['default_size']:
                state['native']['restored'], state['phase'] = True, 0
                motion(2, 2)
            if not state['pending'] and state['phase'] not in (4, 6):
                if state['phase'] == 8:
                    # 实际桌面指针移动会覆盖合成事件，在采样前保持测试悬停位置。
                    rect, viewport = state['last']['controls']['upload-button'], state['last']['viewport']
                    motion((rect['left'] + rect['width'] / 2) * view.get_allocated_width() / viewport['width'],
                           (rect['top'] + rect['height'] / 2) * view.get_allocated_height() / viewport['height'])
                evaluate("JSON.stringify((()=>{const v=document.getElementById('preview');"
                         "if(!v||document.readyState==='loading')return {ready:false};"
                         "if(!window.probeMedia){window.probeMedia=[];for(const type of ['volumechange','loadstart','loadedmetadata']){"
                         "v.addEventListener(type,()=>window.probeMedia.push({event:type,muted:v.muted,defaultMuted:v.defaultMuted,src:v.currentSrc}));}"
                         "document.addEventListener('click',e=>window.probeMedia.push({event:'click',id:e.target.closest('button')?.id,trusted:e.isTrusted}),true);}"
                         "const error=document.getElementById('error-banner');const hover=getComputedStyle(document.getElementById('upload-button'));return {"
                         "media_events:window.probeMedia,"
                         "ready:!!v&&v.readyState>=2&&!document.getElementById('adjustments').disabled&&!document.getElementById('restart').disabled,"
                         "error:error&&!error.hidden?document.getElementById('error-text').textContent:null,"
                         "background:{source:document.getElementById('background-source').value,"
                         "src:document.getElementById('background-image').currentSrc,complete:document.getElementById('background-image').complete,"
                         "width:document.getElementById('background-image').naturalWidth,hidden:document.getElementById('background-image').hidden,"
                         "opacity:getComputedStyle(document.getElementById('background-image')).opacity,left:document.getElementById('background-image').style.left},"
                         "video:document.getElementById('video-source')?.value,time:v?.currentTime,paused:v?.paused,"
                         "muted:v?.muted,mute_pressed:document.getElementById('toggle-mute').getAttribute('aria-pressed'),"
                         "window_mode:document.getElementById('window-mode').value,"
                         "width:v?.videoWidth,height:v?.videoHeight,rate:v?.playbackRate,"
                         "viewport:{width:innerWidth,height:innerHeight},page_width:document.documentElement.scrollWidth,"
                         "controls:Object.fromEntries(['save','install','video-source','upload-button','reset','window-mode','toggle-mute'].map(id=>"
                         "[id,document.getElementById(id)?.getBoundingClientRect()])),"
                         "fonts:Object.fromEntries(['body','h1','h2','.control-label','#save','#upload-button','.field-hint'].map(selector=>"
                         "[selector,getComputedStyle(document.querySelector(selector)).fontSize])),"
                         "hover:{matched:document.getElementById('upload-button').matches(':hover'),background:hover.backgroundColor,border:hover.borderColor,transform:hover.transform},"
                         "motion:{reduced:matchMedia('(prefers-reduced-motion: reduce)').matches,elements:Object.fromEntries("
                         "['.app-header','.preview-column','.settings-card','.depth-lines','body::after'].map(selector=>{"
                         "const style=selector==='body::after'?getComputedStyle(document.body,'::after'):getComputedStyle(document.querySelector(selector));"
                         "return [selector,{animation:style.animationName,duration:style.animationDuration,transition:style.transitionDuration}];}))},"
                         "filter:v?getComputedStyle(v).filter:null,fit:v?getComputedStyle(v).objectFit:null,"
                         "saved:document.getElementById('save-state')?.textContent==='设置已保存'};})())", check)
            return True

        def poll():
            try:
                return step()
            except Exception as error:
                fail(error)
                return True

        def script_dialog(_view, dialog):
            if dialog.get_dialog_type() == WebKit2.ScriptDialogType.BEFORE_UNLOAD_CONFIRM:
                dialog.confirm_set_confirmed(False)
                state['close_cancelled'] = True
                return True
            return False

        view.connect('script-dialog', script_dialog)
        view.connect('run-file-chooser', choose_file)
        window.connect('destroy', lambda _window: state.update(closed=True))
        timer = GLib.timeout_add(200, poll)
        window.show_all()
        window.present()
        try:
            Gtk.main()
        finally:
            GLib.source_remove(timer)
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        assert not thread.is_alive(), '编辑器服务未正常退出'
        assert not state['error'], state['error']
        assert state['phase'] == 6 and state['closed'], f"窗口未通过 try_close 正常关闭，阶段 {state['phase']}"
        assert state['try_close_calls'] == 2, '标题栏关闭未经过 try_close 或未保存保护未验证'
        assert all((output / name).stat().st_size > 0 for name in ('default.png', 'minimum.png', 'desktop.png', 'background.png')), '截图为空'
    report = {'passed': True, 'app_root': str(animation.ROOT),
              'chooser': state['chooser'], 'service_stopped': not thread.is_alive(),
              'native': state['native'], 'minimum': state['minimum'], 'minimum_scroll': state['minimum_scroll'], 'motion': state['motion'],
              'hover_before': state['hover_before'], 'hover_after': state['hover_after'],
              'try_close_calls': state['try_close_calls'], 'close_cancelled': state['close_cancelled'],
              'window_modes': state['window_modes'],
              'mute_after_refresh': state['mute_after_refresh'],
              'builtin_backgrounds': [state['first_builtin'], state['second_builtin']],
              'background': state['background'], 'background_error': state['background_error'], 'background_chooser': state['background_chooser'],
              'default_playback': state['default_playback'], 'imported_playback': state['imported_playback'],
              'output': str(output)}
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
