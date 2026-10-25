#!/usr/bin/env python3
"""Build and test an isolated Windows app copy; no launcher or real profile changes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

if __package__:
    from . import animation, manage_windows, patch_app
    from .native_smoke import PAGE_PROBE, probe_timing, validate_samples
else:
    import animation
    import manage_windows
    import patch_app
    from native_smoke import PAGE_PROBE, probe_timing, validate_samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-mode', choices=('restore', 'centered', 'fullscreen'), default='centered')
    parser.add_argument('--sound', action='store_true')
    parser.add_argument('--seed-bounds', nargs=4, type=int, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'))
    args = parser.parse_args()
    work = patch_app.ROOT / 'work'
    work.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='windows-smoke-', dir=work))
    runtime = output / 'runtime'
    settings = animation.validate_settings({'windowMode': args.window_mode, 'muted': not args.sound})
    with patch.object(patch_app, 'load_settings', return_value=settings):
        before, metadata = manage_windows.build_runtime(runtime)
    values = metadata['animation'] | animation.video_info('default')
    timing = probe_timing(values)
    archive_path = runtime / manage_windows.ASAR
    archive = patch_app.Asar(archive_path)
    previous = manage_windows.header_hash(archive_path)
    if __package__:
        from .build_layout import entrypoint
    else:
        from build_layout import entrypoint
    early = entrypoint(archive)
    script = archive.read('webview/assets/codex-boot.js').decode()
    page_probe = PAGE_PROBE.replace('CODEX_PROBE_SAMPLES', str(timing['samples']))
    page_probe = page_probe.replace('CODEX_PROBE_INTERVAL', str(timing['interval']))
    temporary = archive_path.with_suffix('.qa.asar')
    archive.write_changes(temporary, {
        early: b'require("./codex-boot-probe.cjs");\n' + archive.read(early),
        str(Path(early).parent / 'codex-boot-probe.cjs').replace('\\', '/'):
            (patch_app.ROOT / 'tests/native_probe.cjs').read_bytes(),
        'webview/assets/codex-boot.js': (script + page_probe).encode(),
    })
    temporary.replace(archive_path)
    manage_windows.update_integrity(runtime / manage_windows.BINARY, previous,
                                    manage_windows.header_hash(archive_path))
    env = {**os.environ, 'CODEX_HOME': str(output / 'codex-home'),
           'CODEX_ELECTRON_USER_DATA_PATH': str(output / 'ui-profile'),
           'CODEX_BOOT_PROBE_OUTPUT': str(output), 'CODEX_BOOT_PROBE_TIMEOUT_MS': str(timing['timeout'])}
    env.pop('CODEX_ELECTRON_START_IN_BACKGROUND', None)
    expected = dict(zip(('x', 'y', 'width', 'height'), args.seed_bounds)) if args.seed_bounds else None
    if expected:
        profile = output / 'codex-home'
        profile.mkdir()
        (profile / '.codex-global-state.json').write_text(json.dumps({
            'electron-main-window-bounds': expected | {'isMaximized': False}}), encoding='utf-8')
    print(f'Testing isolated copy: {output}', flush=True)
    with (output / 'app.log').open('wb') as log:
        # Exercise playback even on test desktops whose OS animation setting is off.
        process = subprocess.Popen([str(runtime / manage_windows.BINARY), '--force-prefers-no-reduced-motion',
            '--user-data-dir=' + env['CODEX_ELECTRON_USER_DATA_PATH']], cwd=runtime, env=env,
            stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = process.wait(timeout=timing['timeout'] / 1000 + 35)
        except subprocess.TimeoutExpired:
            # Only the process tree created by this smoke test may be stopped.
            subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            raise
    samples = json.loads((output / 'samples.json').read_text(encoding='utf-8'))
    assert code == 0, f'App exited {code}; see {output / "app.log"}'
    playing, ended = validate_samples(samples, values, expected)
    assert manage_windows.fingerprint() == before, 'Official installation changed'
    result = {'passed': True, 'playing_samples': len(playing), 'ended_samples': len(ended),
              'animation': values, 'output': str(output)}
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
