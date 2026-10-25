#!/usr/bin/env python3
"""以独立登录/后端目录运行原生测试，保留截图与数据，退出后清理测试运行时。"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

if __package__:
    from .animation import DEFAULT_SETTINGS, validate_settings
    from .editor import probe_video
    from .patch_app import Asar, MAIN, ROOT, replace_once
else:
    from animation import DEFAULT_SETTINGS, validate_settings
    from editor import probe_video
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
        paused: video.paused, error: video.error?.code ?? null, rate: video.playbackRate,
        filter: getComputedStyle(video).filter, fit: getComputedStyle(video).objectFit } : null,
      rootChildren: document.getElementById('root')?.childElementCount ?? 0
    }));
    if (++count >= CODEX_PROBE_SAMPLES) clearInterval(timer);
  }, CODEX_PROBE_INTERVAL);
}
'''


def archived_settings(script):
    match = re.search(r'^\s*const settings = (.+);$', script, re.MULTILINE)
    if not match or match[1] == '/* CODEX_BOOT_SETTINGS */ null':
        return DEFAULT_SETTINGS.copy()
    data = json.loads(match[1])
    if not isinstance(data, dict):
        raise ValueError('归档中的动画设置无效')
    return validate_settings({key: value for key, value in data.items() if key != 'duration'})


def probe_timing(animation):
    duration = animation['duration'] / animation['speed']
    interval = min(250, max(16, int(duration * 1000 / 8)))
    timeout = (max(8, math.ceil(duration + 4)) + 3) * 1000
    return {'interval': interval, 'samples': math.ceil(timeout / interval), 'timeout': timeout}


def validate_samples(samples, animation):
    playing = [s for s in samples if s['video'] and s['video']['time'] > 0
               and not s['video']['paused'] and not s['video']['error']
               and s['video']['width'] == animation['width']
               and s['video']['height'] == animation['height']]
    ended = [s for s in samples if s['state'] == 'ended' and not s['layer']]
    assert playing, '没有采集到目标分辨率的视频正常解码播放'
    assert ended, '动画未正常结束并释放遮罩'
    for sample in playing:
        video = sample['video']
        assert math.isclose(video['rate'], animation['speed'], abs_tol=1e-6), '播放速度未生效'
        assert video['fit'] == animation['fit'], '画面适配未生效'
        if video['filter'] == 'none':
            values = (1, 1, 1)
        else:
            match = re.fullmatch(r'brightness\(([^)]+)\) contrast\(([^)]+)\) saturate\(([^)]+)\)', video['filter'])
            assert match, '视频滤镜格式不符合预期'
            values = tuple(map(float, match.groups()))
        assert all(math.isclose(value, animation[key], abs_tol=1e-6)
                   for value, key in zip(values, ('brightness', 'contrast', 'saturation'))), '视频滤镜未生效'
    assert all(s['native']['fullscreen'] and s['native']['visible'] for s in playing + ended)
    assert all(s['native']['bounds'] == s['native']['display'] for s in playing + ended)
    # 分数缩放下 DOMRect 保留小数，而 innerWidth/innerHeight 为整数。
    assert all(s['rect']['x'] == 0 and s['rect']['y'] == 0 and
               abs(s['rect']['width'] - s['viewport']['width']) < 1 and
               abs(s['rect']['height'] - s['viewport']['height']) < 1 for s in playing)
    assert all(s['rootChildren'] > 0 for s in ended), '退出动画后应用未挂载'
    return playing, ended


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / '.local/runtime',
                        help='待测预构建副本目录；只在 work 内的复制品中注入探针')
    args = parser.parse_args()
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='native-smoke-', dir=work))
    runtime = output / 'runtime'
    source = args.runtime.resolve()
    subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(runtime)], check=True)
    try:
        archive_path = runtime / 'resources/app.asar'
        archive = Asar(archive_path)
        script = archive.read('webview/assets/codex-boot.js').decode()
        video = output / 'video.webm'
        video.write_bytes(archive.read('webview/assets/codex-boot.webm'))
        animation = archived_settings(script) | probe_video(video)
        timing = probe_timing(animation)
        page_probe = PAGE_PROBE.replace('CODEX_PROBE_SAMPLES', str(timing['samples']))
        page_probe = page_probe.replace('CODEX_PROBE_INTERVAL', str(timing['interval']))
        (output / 'animation.json').write_text(json.dumps(animation, ensure_ascii=False, indent=2))
        early = '.vite/build/early-bootstrap.js'
        changes = {
            early: b'require("./codex-boot-probe.cjs");\n' + archive.read(early),
            '.vite/build/codex-boot-probe.cjs': (ROOT / 'tests/native_probe.cjs').read_bytes(),
            MAIN: replace_once(archive.read(MAIN).decode(),
                'Ge.deepLinks.registerProtocolClient()', 'void 0').encode(),
            'webview/assets/codex-boot.js': (script + page_probe).encode(),
        }
        temporary = archive_path.with_suffix('.qa.asar')
        archive.write_changes(temporary, changes)
        temporary.replace(archive_path)
        env = {**os.environ, 'CODEX_HOME': str(output / 'codex-home'),
               'CODEX_ELECTRON_USER_DATA_PATH': str(output / 'ui-profile'),
               'CODEX_BOOT_PROBE_OUTPUT': str(output),
               'CODEX_BOOT_PROBE_TIMEOUT_MS': str(timing['timeout'])}
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
                returncode = process.wait(timeout=timing['timeout'] / 1000 + 35)
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
        assert returncode == 0, returncode
        playing, ended = validate_samples(samples, animation)
        print(json.dumps({'passed': True, 'samples': len(samples), 'playing_samples': len(playing),
                          'ended_samples': len(ended), 'animation': animation,
                          'output': str(output)}, ensure_ascii=False))
    finally:
        # 只清理本次测试生成的运行时，不碰安装副本和用户配置。
        shutil.rmtree(runtime)


if __name__ == '__main__':
    main()
