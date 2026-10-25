#!/usr/bin/env python3
"""以独立登录/后端目录运行原生测试，保留截图与数据，退出后清理测试运行时。"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from patch_app import Asar, MAIN, ROOT, replace_once

PAGE_PROBE = r'''
if (new URLSearchParams(location.search).get('codexBootAnimation') === '1') {
  let count = 0;
  const timer = setInterval(() => {
    const layer = document.getElementById('codex-boot');
    const video = layer?.querySelector('video');
    const rect = layer?.getBoundingClientRect();
    console.log('CODEX_BOOT_PROBE:' + JSON.stringify({
      state: document.documentElement.dataset.codexBoot, layer: !!layer,
      viewport: { width: innerWidth, height: innerHeight },
      rect: rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null,
      video: video ? { time: video.currentTime, width: video.videoWidth, height: video.videoHeight,
        paused: video.paused, error: video.error?.code ?? null } : null,
      rootChildren: document.getElementById('root')?.childElementCount ?? 0
    }));
    if (++count >= 28) clearInterval(timer);
  }, 250);
}
'''


def main():
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='native-smoke-', dir=work))
    runtime = output / 'runtime'
    source = ROOT / '.local/runtime'
    subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(runtime)], check=True)
    try:
        archive_path = runtime / 'resources/app.asar'
        archive = Asar(archive_path)
        early = '.vite/build/early-bootstrap.js'
        changes = {
            early: b'require("./codex-boot-probe.cjs");\n' + archive.read(early),
            '.vite/build/codex-boot-probe.cjs': (ROOT / 'tests/native_probe.cjs').read_bytes(),
            MAIN: replace_once(archive.read(MAIN).decode(),
                'Ge.deepLinks.registerProtocolClient()', 'void 0').encode(),
            'webview/assets/codex-boot.js': archive.read('webview/assets/codex-boot.js') + PAGE_PROBE.encode(),
        }
        temporary = archive_path.with_suffix('.qa.asar')
        archive.write_changes(temporary, changes)
        temporary.replace(archive_path)
        env = {**os.environ, 'CODEX_HOME': str(output / 'codex-home'),
               'CODEX_ELECTRON_USER_DATA_PATH': str(output / 'ui-profile'),
               'CODEX_BOOT_PROBE_OUTPUT': str(output)}
        if not env.get('DISPLAY'):
            session = {**env, 'XDG_RUNTIME_DIR': f'/run/user/{os.getuid()}',
                       'DBUS_SESSION_BUS_ADDRESS': f'unix:path=/run/user/{os.getuid()}/bus'}
            result = subprocess.run(['systemctl', '--user', 'show-environment'], env=session,
                                    capture_output=True, text=True, check=True)
            keys = {'DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                    'XDG_RUNTIME_DIR', 'XDG_SESSION_TYPE', 'XDG_CURRENT_DESKTOP',
                    'KDE_FULL_SESSION', 'KDE_SESSION_VERSION'}
            env.update(dict(line.split('=', 1) for line in result.stdout.splitlines()
                            if line.partition('=')[0] in keys))
        env.pop('CODEX_ELECTRON_START_IN_BACKGROUND', None)
        with (output / 'app.log').open('wb') as log:
            process = subprocess.Popen([str(runtime / 'ChatGPT'),
                '--user-data-dir=' + env['CODEX_ELECTRON_USER_DATA_PATH']], env=env,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                returncode = process.wait(timeout=40)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    time.sleep(0.3)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
        if not (output / 'samples.json').exists():
            raise RuntimeError(f'未收到测试样本，退出码 {returncode}；查看 {output / "app.log"}')
        samples = json.loads((output / 'samples.json').read_text())
        playing = [s for s in samples if s['video'] and s['video']['time'] > 0.5
                   and not s['video']['paused'] and s['video']['width'] == 1920]
        ended = [s for s in samples if s['state'] == 'ended' and not s['layer']]
        assert returncode == 0, returncode
        assert playing, '没有采集到视频正常解码播放'
        assert ended, '动画未正常结束并释放遮罩'
        assert all(s['native']['fullscreen'] and s['native']['visible'] for s in playing + ended)
        assert all(s['native']['bounds'] == s['native']['display'] for s in playing + ended)
        # 分数缩放下 DOMRect 保留小数，而 innerWidth/innerHeight 为整数。
        assert all(s['rect']['x'] == 0 and s['rect']['y'] == 0 and
                   abs(s['rect']['width'] - s['viewport']['width']) < 1 and
                   abs(s['rect']['height'] - s['viewport']['height']) < 1 for s in playing)
        assert all(s['rootChildren'] > 0 for s in ended), '退出动画后应用未挂载'
        print(json.dumps({'passed': True, 'samples': len(samples), 'playing_samples': len(playing),
                          'ended_samples': len(ended), 'output': str(output)}, ensure_ascii=False))
    finally:
        # 只清理本次测试生成的运行时，不碰安装副本和用户配置。
        shutil.rmtree(runtime)


if __name__ == '__main__':
    main()
