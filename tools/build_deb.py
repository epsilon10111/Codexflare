#!/usr/bin/env python3
"""用当前打包模板和指定 Git 提交的资源构建 DEB；不安装软件。"""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = ('animation', 'background', 'desktop', 'editor', 'manage', 'patch_app', 'paths')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD', help='资源来源 Git ref，默认已提交的 HEAD')
    args = parser.parse_args()
    for command in ('dpkg-deb', 'desktop-file-validate'):
        if not shutil.which(command):
            parser.error(f'缺少构建工具：{command}')
    commit = subprocess.check_output(
        ['git', 'rev-parse', '--verify', '--end-of-options', args.ref + '^{commit}'],
        cwd=ROOT, text=True).strip()
    version = subprocess.check_output(['git', 'show', f'{commit}:VERSION'], cwd=ROOT, text=True).strip()
    if re.fullmatch(r'\d+\.\d+\.\d+', version) is None:
        parser.error('VERSION 必须是三段数字版本')
    epoch = int(subprocess.check_output(['git', 'show', '-s', '--format=%ct', commit], cwd=ROOT))
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='debbuild-', dir=work) as folder:
        folder = Path(folder)
        archive = folder / 'source.tar'
        subprocess.run(['git', 'archive', '--format=tar', '-o', str(archive), commit], cwd=ROOT, check=True)
        source = folder / 'source'
        source.mkdir()
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts or not (member.isdir() or member.isfile()):
                    raise ValueError(f'源码归档包含不支持的路径或类型：{member.name}')
            tar.extractall(source, filter='data')
        package = folder / 'package'

        def install(relative, destination, executable=False):
            target = package / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
            target.chmod(0o755 if executable else 0o644)
            return target

        app = 'usr/share/codexflare'
        for module in MODULES:
            target = install(f'tools/{module}.py', f'{app}/tools/{module}.py')
            text = target.read_text()
            if text.startswith('#!'):
                target.write_text(text.partition('\n')[2])
        for directory in ('src', 'ui'):
            for path in sorted((source / directory).iterdir()):
                if not path.is_file():
                    raise ValueError(f'需要更新打包规则以包含子目录：{path.relative_to(source)}')
                install(str(path.relative_to(source)), f'{app}/{directory}/{path.name}')
        for name in ('default.webm', 'default1.png', 'default2.png'):
            install(f'assets/{name}', f'{app}/assets/{name}')
        install('VERSION', f'{app}/VERSION')
        (package / app / '.packaged').write_text(f'codexflare {version}\n')
        for name in ('codexflare', 'codexflare-manage'):
            install(f'packaging/{name}', f'usr/bin/{name}', executable=True)
            target = package / f'usr/share/man/man1/{name}.1.gz'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.compress((source / f'packaging/{name}.1').read_bytes(), mtime=0))
        desktop = install('packaging/codexflare.desktop', 'usr/share/applications/codexflare.desktop')
        install('ui/mark.svg', 'usr/share/icons/hicolor/scalable/apps/codexflare.svg')
        for relative, name in (('README.md', 'README.md'), ('LICENSE', 'LICENSE'),
                               ('assets/LICENSE', 'MEDIA-LICENSE'),
                               ('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')):
            install(relative, f'usr/share/doc/codexflare/{name}')
        # Use current packaging templates so the original v0.1.0 tag remains immutable.
        (package / 'usr/share/doc/codexflare/copyright').write_bytes(
            (ROOT / 'packaging/debian/copyright').read_bytes())
        size = sum((path.stat().st_size + 1023) // 1024 for path in package.rglob('*') if path.is_file())
        control = package / 'DEBIAN'
        control.mkdir()
        template = (ROOT / 'packaging/debian/control').read_text()
        (control / 'control').write_text(template.replace('@VERSION@', version).replace('@SIZE@', str(size)).replace('@COMMIT@', commit))
        sums = []
        for path in sorted((package / 'usr').rglob('*')):
            if path.is_file():
                sums.append(f'{hashlib.md5(path.read_bytes()).hexdigest()}  {path.relative_to(package)}\n')
        (control / 'md5sums').write_text(''.join(sums))
        for path in [*package.rglob('*'), package]:
            if path.is_dir():
                path.chmod(0o755)
            elif path.parent != package / 'usr/bin':
                path.chmod(0o644)
            os.utime(path, (epoch, epoch))
        subprocess.run(['desktop-file-validate', str(desktop)], check=True)
        built = folder / f'codexflare_{version}-1_all.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '-z6', '--threads-max=2',
                        '--build', str(package), str(built)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': str(epoch)})
        destination = output / built.name
        shutil.copyfile(built, destination)
        with destination.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        destination.with_suffix('.deb.sha256').write_text(f'{digest}  {destination.name}\n')
    print(f'资源提交：{commit}\n发布产物：{destination}')


if __name__ == '__main__':
    main()
