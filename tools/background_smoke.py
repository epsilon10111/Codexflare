#!/usr/bin/env python3
"""在隔离 Electron 窗口验证背景层；使用真实样式和模拟会话，不运行应用后端。"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile

if __package__:
    from .patch_app import Asar, ROOT, replace_once
    from .native_smoke import probe_timing
    from .background_layout import BackgroundLayout
else:
    from patch_app import Asar, ROOT, replace_once
    from native_smoke import probe_timing
    from background_layout import BackgroundLayout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / ('.local/Codexflare Runtime.app' if sys.platform == 'darwin' else '.local/runtime'))
    parser.add_argument('--startup', action='store_true', help='验证真实动画到模拟工作区的首帧衔接')
    args = parser.parse_args()
    (ROOT / 'work').mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='background-smoke-', dir=ROOT / 'work'))
    macos = sys.platform == 'darwin'
    runtime = output / ('Runtime.app' if macos else 'runtime')
    if macos:
        if __package__:
            from . import manage_macos, patch_macos
        else:
            import manage_macos, patch_macos
        subprocess.run(['/usr/bin/ditto', str(args.runtime.resolve()), str(runtime)], check=True)
    else:
        subprocess.run(['cp', '-a', '--reflink=auto', str(args.runtime.resolve()), str(runtime)], check=True)
    try:
        archive_path = runtime / ('Contents/Resources/app.asar' if macos else 'resources/app.asar')
        archive = Asar(archive_path)
        # 使用候选归档的播放图片，避免把已经缩放的资源换回原始大图。
        archive.read('webview/assets/codex-background.png')
        system = Asar(manage_macos.SOURCE / manage_macos.ASAR if macos else '/usr/lib/chatgpt/resources/app.asar')
        fixture = (ROOT / 'tests/background_fixture.html').read_text()
        probe = 'startup_probe.cjs' if args.startup else 'background_probe.cjs'
        timeout_ms = 45000
        changes = {
            '.vite/build/early-bootstrap.js': b'require("./background-probe.cjs");\n',
            '.vite/build/background-probe.cjs': (ROOT / 'tests' / probe).read_bytes(),
        }
        if args.startup:
            fixture = replace_once(fixture, "font-src 'self'", "font-src 'self'; script-src 'self'; media-src 'self'")
            fixture = replace_once(fixture, '</head>',
                '<link id="codex-background-preload" rel="preload" as="image" href="./assets/codex-background.png">\n'
                '<link rel="stylesheet" href="./assets/codex-boot.css">\n'
                '<script src="./assets/codex-boot.js"></script>\n</head>')
            head, body = fixture.split('<body>', 1)
            workspace, tail = body.split('</body>', 1)
            fixture = (head + '<body><div id="root"><div class="startup-loader"></div></div>'
                       '<template id="workspace-template">' + workspace + '</template>'
                       '<script src="./assets/startup-page-probe.js"></script></body>' + tail)
            script = archive.read('webview/assets/codex-boot.js').decode()
            match = re.search(r'^\s*const settings = (.+);$', script, re.MULTILINE)
            if not match:
                raise ValueError('候选归档缺少开屏设置')
            settings = json.loads(match[1])
            settings['muted'] = True  # 隔离测量画面，不播放用户的音频。
            timeout_ms = 2 * probe_timing(settings)['timeout'] + 5000
            changes['webview/assets/codex-boot.js'] = replace_once(script, match[1], json.dumps(settings)).encode()
        else:
            # 普通背景回归固定摆放参数；首帧回归保留候选归档的实际设置。
            changes['webview/assets/codex-background.css'] = (ROOT / 'src/background.css').read_bytes()
        layout = BackgroundLayout(system)
        fixture = layout.fixture(fixture)
        if macos:
            fixture = fixture.replace('<html ', '<html data-codex-os="darwin" ', 1)
        probe_path = '.vite/build/background-probe.cjs'
        changes[probe_path] = replace_once(layout.adapt(changes[probe_path].decode()),
            '/* CODEX_BACKGROUND_STYLES */ []', json.dumps(layout.styles)).encode()
        if not args.startup:
            changes['webview/assets/codex-background.css'] = layout.adapt(
                (ROOT / 'src/background.css').read_text()).encode()
        fixture = re.sub(r'<link rel="stylesheet" href="./assets/(?:app-shared|app-initial|thread-scroll-layout)-[^\"]+">', '', fixture)
        fixture = fixture.replace('<link rel="stylesheet" href="./assets/codex-background.css">',
            ''.join(f'<link rel="stylesheet" href="./assets/{name}">\n' for name in layout.styles)
            + '<link rel="stylesheet" href="./assets/codex-background.css">', 1)
        for name in layout.styles:
            changes['webview/assets/' + name] = system.read('webview/assets/' + name)
        changes['webview/background-fixture.html'] = fixture.encode()
        temporary = archive_path.with_suffix('.qa.asar')
        archive.write_changes(temporary, changes)
        temporary.replace(archive_path)
        if macos:
            manage_macos.seal_bundle(runtime)
        env = {**os.environ, 'CODEX_BACKGROUND_PROBE_OUTPUT': str(output)}
        if args.startup:
            env['CODEX_STARTUP_PROBE_TIMEOUT_MS'] = str(timeout_ms)
        if not macos and not env.get('DISPLAY'):
            session = {**env, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}',
                       'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{os.getuid()}/bus'}
            result = subprocess.run(['systemctl', '--user', 'show-environment'], env=session,
                                    capture_output=True, text=True, check=True)
            keys = {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                    'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP',
                    'KDE_FULL_SESSION', 'KDE_SESSION_VERSION'}
            env.update(dict(line.split('=', 1) for line in result.stdout.splitlines()
                            if line.partition('=')[0] in keys))
        with (output / 'app.log').open('wb') as log:
            process = subprocess.Popen([str(manage_macos.executable(runtime) if macos else runtime / 'ChatGPT'),
                '--user-data-dir=' + str(output / 'profile'), *(['--use-mock-keychain'] if macos else [])], env=env,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                returncode = process.wait(timeout=timeout_ms / 1000 + (10 if args.startup else 0))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=5)
        result_path = output / 'result.json'
        if not result_path.exists():
            raise RuntimeError(f'未收到结果，退出码 {returncode}；查看 {output / "app.log"}')
        result = json.loads(result_path.read_text())
        assert returncode == 0 and result['passed'], result
        print(json.dumps({'passed': True, 'output': str(output), 'checks': result}, ensure_ascii=False))
    finally:
        shutil.rmtree(runtime)


if __name__ == '__main__':
    main()
