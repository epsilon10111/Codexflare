#!/usr/bin/env python3
"""在 work 中验证 DEB 内容、只读资源及用户命名空间中的安装/删除。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile

from rpm_smoke import PROBE, run, snapshot

ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = {'usr/bin/codexflare', 'usr/bin/codexflare-manage'}


def inspect_archive(package, control=False):
    """在解包前拒绝链接、特殊文件、越界路径及维护脚本。"""
    entries = {}
    option = '--ctrl-tarfile' if control else '--fsys-tarfile'
    with subprocess.Popen(['dpkg-deb', option, str(package)], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as process:
        try:
            with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    assert not path.is_absolute() and '..' not in path.parts, member.name
                    assert member.isfile() or member.isdir(), f'包内不应有链接或特殊文件：{member.name}'
                    assert member.uid == member.gid == 0, member.name
                    name = str(path)
                    assert name not in entries, f'重复路径：{name}'
                    if name == '.':
                        assert member.isdir()
                        continue
                    if control:
                        assert name in ('control', 'md5sums') and member.isfile(), f'不允许的控制文件：{name}'
                        assert member.size < 1024 * 1024 and member.mode == 0o644, name
                        entries[name] = archive.extractfile(member).read().decode('utf-8')
                    else:
                        assert path.is_relative_to('usr'), name
                        assert not set(path.parts) & {'.local', 'work', 'profile', '__pycache__'}, name
                        assert path.name not in ('ChatGPT', 'app.asar', 'default.mp4', 'boot.webm'), name
                        if member.isfile():
                            assert (name in WRAPPERS or path.is_relative_to('usr/share/codexflare')
                                    or path.is_relative_to('usr/share/doc/codexflare')
                                    or name in ('usr/share/applications/codexflare.desktop',
                                                'usr/share/icons/hicolor/scalable/apps/codexflare.svg',
                                                'usr/share/man/man1/codexflare.1.gz',
                                                'usr/share/man/man1/codexflare-manage.1.gz')), name
                        expected_mode = 0o755 if member.isdir() or name in WRAPPERS else 0o644
                        assert member.mode == expected_mode, f'文件权限错误：{name}'
                        entries[name] = {'directory': member.isdir(), 'mode': oct(member.mode)}
            error = process.stderr.read().decode(errors='replace')
            assert process.wait(timeout=10) == 0, error
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('deb', type=Path)
    args = parser.parse_args()
    package = args.deb.resolve(strict=True)
    for command in ('dpkg', 'dpkg-deb', 'dpkg-query', 'desktop-file-validate'):
        if not shutil.which(command):
            parser.error(f'缺少验证工具：{command}')
    if os.getuid() == 0:
        parser.error('请以普通用户运行，以验证用户目录写入权限')
    (ROOT / 'work').mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='deb-smoke-', dir=ROOT / 'work'))
    result = {'passed': False, 'package': str(package), 'output': str(output)}
    print(f'验证输出：{output}', flush=True)
    try:
        fields = ('Package', 'Version', 'Architecture', 'Depends', 'Recommends')
        metadata = run(['dpkg-deb', '--show', '--showformat=' +
                        ''.join('${' + field + '}\n' for field in fields), str(package)]).splitlines()
        assert len(metadata) == len(fields), metadata
        result['metadata'] = dict(zip(fields, metadata))
        assert metadata[0] == 'codexflare' and metadata[2] == 'all', metadata
        dependencies = {value.strip() for value in metadata[3].split(',')}
        assert {'python3 (>= 3.11)', 'python3-gi', 'gir1.2-gtk-3.0', 'gir1.2-webkit2-4.1',
                'gstreamer1.0-plugins-base', 'gstreamer1.0-plugins-good', 'coreutils'} <= dependencies
        assert 'ffmpeg' in {value.strip() for value in metadata[4].split(',')}
        (output / 'control.txt').write_text(run(['dpkg-deb', '--field', str(package)]))
        control = inspect_archive(package, control=True)
        assert set(control) == {'control', 'md5sums'}, '控制信息或文件校验值缺失'
        entries = inspect_archive(package)
        (output / 'files.json').write_text(json.dumps(entries, indent=2) + '\n')
        files = {name for name, info in entries.items() if not info['directory']}
        parents = {str(parent) for name in files for parent in PurePosixPath(name).parents}
        assert all(name in parents for name, info in entries.items() if info['directory']), '包中存在无关目录'
        assert WRAPPERS | {'usr/share/codexflare/.packaged',
                           'usr/share/applications/codexflare.desktop'} <= files
        hashes = {}
        for line in control['md5sums'].splitlines():
            digest, name = line.split('  ', 1)
            assert name in files and name not in hashes, name
            hashes[name] = digest
        assert set(hashes) == files, 'md5sums 未覆盖全部文件'
        extracted = output / 'extracted'
        run(['dpkg-deb', '--extract', str(package), str(extracted)])
        for name, digest in hashes.items():
            with (extracted / name).open('rb') as stream:
                assert hashlib.file_digest(stream, 'md5').hexdigest() == digest, name
        licenses = extracted / 'usr/share/doc/codexflare'
        assert 'MIT License' in (licenses / 'LICENSE').read_text()
        assert 'Codexflare Bundled Media License' in (licenses / 'MEDIA-LICENSE').read_text()
        assert (licenses / 'THIRD_PARTY_NOTICES.md').is_file()
        copyright_text = (licenses / 'copyright').read_text()
        assert 'MIT' in copyright_text and 'Codexflare-Media' in copyright_text
        run(['desktop-file-validate', str(extracted / 'usr/share/applications/codexflare.desktop')])
        tree = extracted / 'usr/share/codexflare'
        before = snapshot(tree)
        for path in [*tree.rglob('*'), tree]:
            path.chmod(path.stat().st_mode & ~0o222)
        home = output / 'home'
        home.mkdir()
        env = {**os.environ, 'HOME': str(home), 'XDG_DATA_HOME': str(home / 'data'),
               'XDG_CONFIG_HOME': str(home / 'config'), 'XDG_CACHE_HOME': str(home / 'cache')}
        result['runtime'] = json.loads(run([sys.executable, '-I', '-B', '-c', PROBE, str(tree)],
                                           env=env, cwd=output))
        assert snapshot(tree) == before, '用户操作改写了包内资源'
        user_data = snapshot(home)

        available = shutil.which('unshare') and subprocess.run(
            ['unshare', '--user', '--map-root-user', 'true'], capture_output=True, timeout=10).returncode == 0
        if available:
            dpkg_root = output / 'dpkg-root'
            dpkg_root.mkdir()
            command = ['unshare', '--user', '--map-root-user', 'dpkg', '--root=' + str(dpkg_root),
                       '--log=' + str(output / 'dpkg.log'), '--force-depends', '--no-triggers']
            run([*command, '--install', str(package)], env=env)
            installed = run(['dpkg-query', '--admindir=' + str(dpkg_root / 'var/lib/dpkg'),
                             '--show', '--showformat=${Status}\n${Version}\n', 'codexflare']).splitlines()
            assert installed == ['install ok installed', metadata[1]], installed
            assert snapshot(dpkg_root / 'usr/share/codexflare') == before
            run([*command, '--remove', 'codexflare'], env=env)
            assert not (dpkg_root / 'usr/bin/codexflare').exists()
            assert not (dpkg_root / 'usr/share/codexflare').exists()
            assert snapshot(home) == user_data, '卸载不应改变用户配置'
            result['transaction'] = 'user-namespace install and remove passed; dependencies not resolved'
        else:
            result['transaction'] = 'unpacked only; user namespaces unavailable; installation not tested'
        result['passed'] = True
    except Exception as error:
        result['error'] = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            result['stderr'] = error.stderr
        raise
    finally:
        (output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
