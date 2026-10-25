#!/usr/bin/env python3
"""Build a self-contained arm64 editor DMG from this checkout, without installing it."""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*command, **kwargs):
    return subprocess.run([str(arg) for arg in command], check=True, **kwargs)


def resources(destination):
    if __package__:
        from . import background
    else:
        import background
    for folder, files in {
        'ui': ('index.html', 'editor.js', 'editor.css', 'mark.svg', 'mark.icns'),
        'src': ('boot.js', 'boot.css', 'background.css'),
        'assets': ('default.webm', 'LICENSE'),
    }.items():
        (destination / folder).mkdir(parents=True)
        for name in files:
            shutil.copy2(ROOT / folder / name, destination / folder / name)
    if not shutil.which('ffmpeg'):
        raise RuntimeError('构建时需要 FFmpeg 预缩默认背景；不会把 FFmpeg 放进 DMG')
    for name in ('default1.png', 'default2.png'):
        data = (ROOT / 'assets' / name).read_bytes()
        prepared, info = background.prepare_image(data, background.validate_png(data))
        assert info['width'] <= 3840 and info['height'] <= 2160
        (destination / 'assets' / name).write_bytes(prepared)
    (destination / '.packaged').touch()
    licenses = destination / 'licenses'
    licenses.mkdir()
    shutil.copy2(ROOT / 'LICENSE', licenses / 'Codexflare-MIT.txt')
    python_license = Path(sys.base_prefix) / f'lib/python{sys.version_info.major}.{sys.version_info.minor}/LICENSE.txt'
    shutil.copy2(python_license, licenses / 'Python.txt')
    versions = {'python': sys.version.split()[0]}
    for name in ('pyinstaller', 'pyobjc-core', 'pyobjc-framework-Cocoa', 'pyobjc-framework-WebKit'):
        distribution = metadata.distribution(name)
        versions[name] = distribution.version
        files = [file for file in distribution.files or ()
                 if 'license' in file.name.lower() or 'copying' in file.name.lower()]
        if not files:
            raise RuntimeError(f'{name} 缺少可分发许可证')
        for index, file in enumerate(files):
            shutil.copy2(distribution.locate_file(file), licenses / f'{name}-{index}-{file.name}')
    (licenses / '说明.txt').write_text(
        'Codexflare 源码为 MIT，素材许可见 assets/LICENSE。\n'
        '本包 default1.png 和 default2.png 已用 Lanczos 等比例缩至 3840×2160 范围；其他素材未改动。\n'
        'Python: https://www.python.org/；PyObjC: https://github.com/ronaldoussoren/pyobjc；\n'
        'PyInstaller: https://pyinstaller.org/（含 bootloader 分发例外）。\n'
        'FFmpeg 不内嵌。包内不含 ChatGPT、Codex 官方应用或个人配置。\n'
        + json.dumps(versions, ensure_ascii=False, indent=2) + '\n')
    return versions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', action='store_true', help='require a clean committed source tree')
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('需要 Apple Silicon macOS 构建机')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT))
    if args.release and dirty:
        parser.error('正式发布必须从干净、已提交的 HEAD 构建')
    version = (ROOT / 'VERSION').read_text().strip()
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dmg-build-', dir=work) as folder:
        build = Path(folder)
        data = build / 'resources'
        data.mkdir()
        versions = resources(data)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                   '--windowed', '--onedir', '--noupx', '--target-arch', 'arm64',
                   '--name', 'Codexflare', '--osx-bundle-identifier', 'org.codexflare.editor',
                   '--icon', str(ROOT / 'ui/mark.icns'), '--paths', str(ROOT),
                   '--distpath', str(build / 'dist'), '--workpath', str(build / 'build'),
                   '--specpath', str(build), '--add-data', f'{data}:.', '--exclude-module', 'gi']
        for module in ('objc', 'Foundation', 'AppKit', 'Cocoa', 'WebKit', 'PyObjCTools'):
            command += ['--collect-all', module]
        command.append(str(ROOT / 'packaging/macos/launcher.py'))
        run(*command, cwd=ROOT)
        app = build / 'dist/Codexflare.app'
        plist = app / 'Contents/Info.plist'
        info = plistlib.loads(plist.read_bytes())
        info.update(CFBundleShortVersionString=version, CFBundleVersion=version,
                    LSMinimumSystemVersion='12.0', NSHighResolutionCapable=True,
                    NSAppBundlesUsageDescription='Codexflare 需要备份并修改 ChatGPT App，以应用开场动画和背景；也可恢复官方备份。')
        plist.write_bytes(plistlib.dumps(info))
        run('/usr/bin/codesign', '--force', '--deep', '--sign', '-', app)
        run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
        check = run(app / 'Contents/MacOS/Codexflare', '--self-check', capture_output=True, text=True)
        result = json.loads(check.stdout)
        assert result['passed'] and result['original_mode']
        stage = build / 'image'
        stage.mkdir()
        run('/usr/bin/ditto', app, stage / app.name)
        (stage / 'Applications').symlink_to('/Applications')
        shutil.copy2(ROOT / 'packaging/macos/安装说明.txt', stage / '安装说明.txt')
        source = stage / 'Codexflare-source.tar.gz'
        if args.release:
            current_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            if current_commit != commit or subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT):
                raise RuntimeError('构建期间源码发生变化，请重新提交后构建')
            run('git', 'archive', '--format=tar.gz', '--prefix=Codexflare/',
                f'--output={source}', commit, cwd=ROOT)
        else:
            with tarfile.open(source, 'w:gz') as archive:
                files = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
                def public_metadata(info):
                    info.uid = info.gid = 0
                    info.uname = info.gname = ''
                    return info
                for name in sorted(set(files) - {''}):
                    path = ROOT / name
                    if path.is_file():
                        archive.add(path, arcname='Codexflare/' + name, recursive=False, filter=public_metadata)
        manifest = {'version': version, 'arch': 'arm64', 'target_build': '20586',
                    'source_commit': commit, 'source_dirty': dirty,
                    'signing': 'ad-hoc, not notarized', 'dependencies': versions,
                    'ffmpeg_bundled': False, 'self_check': result}
        # Build-machine paths are not useful to recipients.
        for key in ('resources', 'data', 'ffmpeg'):
            manifest['self_check'].pop(key, None)
        (stage / '构建信息.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        name = f'Codexflare-{version}-macOS-arm64-build20586.dmg'
        temporary_dmg = build / name
        run('/usr/bin/hdiutil', 'create', '-volname', 'Codexflare', '-srcfolder', stage,
            '-format', 'UDZO', '-ov', temporary_dmg)
        run('/usr/bin/hdiutil', 'verify', temporary_dmg)
        destination = output / name
        os.replace(temporary_dmg, destination)
        with destination.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        (output / (name + '.sha256')).write_text(f'{digest}  {name}\n')
        (output / 'dmg-build.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'dmg': str(destination), 'sha256': digest, 'passed': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
