#!/usr/bin/env python3
"""Build a Windows source distribution from committed HEAD; Python is not bundled."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=ROOT):
        raise ValueError('正式发布必须从干净、已提交的 HEAD 构建')
    version = (ROOT / 'VERSION').read_text().strip()
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    name = f'Codexflare-{version}-Windows-x64-source'
    target = output / (name + '.zip')
    subprocess.run(['git', 'archive', '--format=zip', f'--prefix={name}/',
                    f'--output={target}', commit], cwd=ROOT, check=True)
    with zipfile.ZipFile(target, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / 'packaging/windows/Codexflare.cmd', name + '/Codexflare.cmd')
        archive.writestr(name + '/build-info.json', json.dumps({
            'version': version, 'source_commit': commit, 'platform': 'Windows x64',
            'python_bundled': False, 'python_required': '3.13',
        }, indent=2) + '\n')
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for relative in ('Codexflare.cmd', 'tools/editor.py', 'tools/windows_inject.py',
                         'src/background.css', 'requirements-windows.txt', 'assets/LICENSE'):
            assert name + '/' + relative in archive.namelist()
        assert not any('/.local/' in item or '/work/' in item for item in archive.namelist())
    with target.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n')
    print(json.dumps({'source_commit': commit, 'zip': str(target), 'sha256': digest}))


if __name__ == '__main__':
    main()
