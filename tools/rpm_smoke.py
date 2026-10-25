#!/usr/bin/env python3
"""在 work 中验证 RPM 内容、只读代码的用户数据写入及隔离安装/卸载。"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROBE = r'''
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import threading

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from tools import animation, background, editor, manage, paths

expected = Path(os.environ['XDG_DATA_HOME']) / 'codexflare'
assert paths.LOCAL == animation.LOCAL == manage.LOCAL == expected
assert not os.access(root, os.W_OK), '测试代码树仍可写'
settings = animation.load_settings()
assert settings == animation.validate_settings({})
assert animation.video_path('default').read_bytes()[:4] == bytes.fromhex('1a45dfa3')
for image_id in ('default', 'default2'):
    data, info = background.read_image(image_id, expected)
    assert info['width'] > 0 and info['height'] > 0 and data
animation.save_settings(settings)
assert animation.load_settings() == settings
assert animation.SETTINGS.parent == expected
assert expected.stat().st_mode & 0o777 == 0o700
assert animation.SETTINGS.stat().st_mode & 0o777 == 0o600
with contextlib.redirect_stdout(io.StringIO()) as status:
    manage.status()
assert str(expected / 'runtime') in status.getvalue()
assert not manage.DESKTOP.exists()

with editor.EditorServer() as server:
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    def request(method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=15)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()
    try:
        code, body = request('GET', '/api/state')
        assert code == 200
        state = json.loads(body)
        assert [image['id'] for image in state['images']] == ['default', 'default2']
        assert request('POST', '/api/settings', '{}')[0] == 403
        settings['speed'] = 1.25
        settings['background']['image'] = 'default2'
        code, body = request('POST', '/api/settings', json.dumps(settings),
                             {'Content-Type': 'application/json', 'X-Editor-Token': state['token']})
        assert code == 200 and json.loads(body)['settings'] == settings
        assert animation.load_settings() == settings
        for route in ('/', '/editor.js', '/editor.css', '/media/default',
                      '/background/default', '/background/default2'):
            assert request('HEAD', route)[0] == 200, route
    finally:
        server.shutdown()
        worker.join(timeout=5)
assert not manage.DESKTOP.exists() and not manage.RUNTIME.exists()
assert not (root / '.local').exists()
print(json.dumps({'passed': True, 'data_directory': str(expected),
                  'http_save': True, 'read_only_code': True, 'builtin_assets': True}))
'''


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, check=True,
                          timeout=60, **kwargs).stdout


def snapshot(folder):
    return {str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob('*') if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rpm', type=Path)
    args = parser.parse_args()
    package = args.rpm.resolve(strict=True)
    for command in ('rpm', 'rpm2cpio', 'cpio', 'desktop-file-validate'):
        if not shutil.which(command):
            parser.error(f'缺少验证工具：{command}')
    if os.getuid() == 0:
        parser.error('请以普通用户运行，以验证用户目录写入权限')
    (ROOT / 'work').mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='rpm-smoke-', dir=ROOT / 'work'))
    result = {'passed': False, 'package': str(package), 'output': str(output)}
    print(f'验证输出：{output}', flush=True)
    try:
        metadata = run(['rpm', '-qp', '--qf', '%{NAME}\n%{VERSION}-%{RELEASE}\n%{ARCH}\n%{LICENSE}\n', str(package)]).splitlines()
        assert metadata[0] == 'codexflare' and metadata[2] == 'noarch', metadata
        assert 'MIT' in metadata[3] and 'LicenseRef-Codexflare-Media' in metadata[3]
        result['metadata'] = dict(zip(('name', 'version', 'arch', 'license'), metadata))
        scripts = run(['rpm', '-qp', '--scripts', '--triggers', '--filetriggers', str(package)])
        assert not scripts.strip(), 'RPM 不应有安装、卸载或触发脚本'
        dependencies = run(['rpm', '-qp', '--requires', str(package)])
        (output / 'requires.txt').write_text(dependencies)
        names = {line.split()[0] for line in dependencies.splitlines()}
        assert {'python3', 'python3-gobject', 'gtk3', 'webkit2gtk4.1',
                'gstreamer1-plugins-base', 'gstreamer1-plugins-good', 'coreutils'} <= names
        listing = run(['rpm', '-qp', '--qf', '[%{FILENAMES}\t%{FILEMODES:perms}\t%{FILELINKTOS}\n]', str(package)])
        (output / 'files.txt').write_text(listing)
        files = []
        for line in listing.splitlines():
            name, mode, link = line.split('\t')
            path = PurePosixPath(name)
            assert path.is_relative_to('/usr') and '..' not in path.parts, name
            assert mode[0] in ('-', 'd') and not link, f'包内不应有链接或特殊文件：{name}'
            assert not set(path.parts) & {'.local', 'work', 'profile', '__pycache__'}, name
            assert path.name not in ('ChatGPT', 'app.asar', 'default.mp4', 'boot.webm'), name
            files.append(name)
        assert {'/usr/bin/codexflare', '/usr/bin/codexflare-manage',
                '/usr/share/codexflare/.packaged',
                '/usr/share/applications/codexflare.desktop'} <= set(files)
        extracted = output / 'extracted'
        extracted.mkdir()
        with subprocess.Popen(['rpm2cpio', str(package)], stdout=subprocess.PIPE, stderr=subprocess.PIPE) as archive:
            unpacked = subprocess.run(['cpio', '-idm', '--quiet', '--no-absolute-filenames'],
                                      stdin=archive.stdout, capture_output=True, cwd=extracted, timeout=60)
            archive.stdout.close()
            error = archive.stderr.read().decode(errors='replace')
            assert archive.wait(timeout=10) == 0, error
            assert unpacked.returncode == 0, unpacked.stderr.decode(errors='replace')
        licenses = '\n'.join(path.read_text() for path in (extracted / 'usr/share/licenses').rglob('*') if path.is_file())
        assert 'MIT License' in licenses and 'Codexflare Bundled Media License' in licenses, '代码或素材许可证缺失'
        run(['desktop-file-validate', str(extracted / 'usr/share/applications/codexflare.desktop')])
        tree = extracted / 'usr/share/codexflare'
        before = snapshot(tree)
        for path in [*tree.rglob('*'), tree]:
            path.chmod(path.stat().st_mode & ~0o222)
        home = output / 'home'
        home.mkdir()
        env = {**os.environ, 'HOME': str(home), 'XDG_DATA_HOME': str(home / 'data'),
               'XDG_CONFIG_HOME': str(home / 'config'), 'XDG_CACHE_HOME': str(home / 'cache')}
        result['runtime'] = json.loads(run([sys.executable, '-I', '-B', '-c', PROBE, str(tree)], env=env, cwd=output))
        assert snapshot(tree) == before, '用户操作改写了包内资源'

        rpm_root = output / 'rpm-root'
        rpm_root.mkdir()
        rpm_command = ['rpm', '--root', str(rpm_root), '--dbpath', '/var/lib/rpm']
        available = shutil.which('unshare') and subprocess.run(
            ['unshare', '--user', '--map-root-user', 'true'], capture_output=True, timeout=10).returncode == 0
        if available:
            namespace = ['unshare', '--user', '--map-root-user']
            run([*namespace, *rpm_command, '-i', '--nodeps', '--noscripts', '--notriggers', str(package)])
            installed = run([*rpm_command, '-q', 'codexflare']).strip()
            assert installed == 'codexflare-' + metadata[1] + '.noarch', installed
            assert (rpm_root / 'usr/share/codexflare/.packaged').is_file()
            run([*namespace, *rpm_command, '-e', '--nodeps', '--noscripts', '--notriggers', 'codexflare'])
            assert not (rpm_root / 'usr/bin/codexflare').exists()
            assert not (rpm_root / 'usr/share/codexflare').exists()
            result['transaction'] = 'user-namespace install and uninstall passed; dependencies not resolved'
        else:
            run([*rpm_command, '-i', '--test', '--nodeps', '--noscripts', '--notriggers', str(package)])
            result['transaction'] = 'unpacked and transaction test only; user namespaces unavailable'
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
