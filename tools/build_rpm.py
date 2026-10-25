#!/usr/bin/env python3
"""从指定 Git 提交构建 RPM、源包和校验文件；不安装软件。"""
import argparse
import gzip
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD', help='构建已提交的 Git ref，默认 HEAD')
    args = parser.parse_args()
    if not shutil.which('rpmbuild'):
        parser.error('需要 rpm-build 和 desktop-file-utils')
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', args.ref + '^{commit}'], cwd=ROOT, text=True).strip()
    version = subprocess.check_output(['git', 'show', f'{commit}:VERSION'], cwd=ROOT, text=True).strip()
    if re.fullmatch(r'\d+\.\d+\.\d+', version) is None:
        parser.error('VERSION 必须是三段数字版本')
    spec = subprocess.check_output(['git', 'show', f'{commit}:packaging/codexflare.spec'], cwd=ROOT)
    if not re.search(rb'^Version:\s+' + version.encode() + rb'\s*$', spec, re.MULTILINE):
        parser.error('VERSION 与 spec 版本不一致')
    output = ROOT / 'dist'
    output.mkdir(exist_ok=True)
    work = ROOT / 'work'
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rpmbuild-', dir=work) as folder:
        top = Path(folder)
        for name in ('BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS'):
            (top / name).mkdir()
        tar = top / 'source.tar'
        subprocess.run(['git', 'archive', '--format=tar', f'--prefix=codexflare-{version}/',
                        '-o', str(tar), commit], cwd=ROOT, check=True)
        source = top / 'SOURCES' / f'codexflare-{version}.tar.gz'
        with tar.open('rb') as raw, source.open('wb') as target:
            with gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as compressed:
                shutil.copyfileobj(raw, compressed)
        spec_path = top / 'SPECS/codexflare.spec'
        spec_path.write_bytes(spec)
        subprocess.run(['rpmbuild', '-ba', '--define', f'_topdir {top}', str(spec_path)], check=True)
        artifacts = [source, *sorted((top / 'RPMS').rglob('*.rpm')), *sorted((top / 'SRPMS').glob('*.rpm'))]
        if len(artifacts) != 3:
            raise RuntimeError('预期一个源码归档、一个 RPM 和一个 SRPM')
        checksums = []
        for artifact in artifacts:
            destination = output / artifact.name
            shutil.copyfile(artifact, destination)
            with destination.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            checksums.append(f'{digest}  {destination.name}\n')
        (output / 'SHA256SUMS').write_text(''.join(checksums))
    print(f'构建提交：{commit}\n发布产物：{output}')


if __name__ == '__main__':
    main()
