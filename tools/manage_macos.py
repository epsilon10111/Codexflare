"""Reversible macOS application copy; never changes /Applications or vendor profiles."""
import ctypes
import hashlib
import json
import mmap
import os
from pathlib import Path
import plistlib
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import shlex

if __package__:
    from .patch_app import Asar, patch_archive
    from .patch_macos import VERSION, BUILD, SUPPORTED, select_build
    from .paths import ROOT, LOCAL, command_for
    from .manage import atomic_write, digest
else:
    from patch_app import Asar, patch_archive
    from patch_macos import VERSION, BUILD, SUPPORTED, select_build
    from paths import ROOT, LOCAL, command_for
    from manage import atomic_write, digest


def find_source():
    override = os.environ.get('CODEXFLARE_SOURCE_APP')
    if override:
        return Path(override).expanduser().absolute()
    for path in (Path('/Applications/Codex.app'), Path('/Applications/ChatGPT.app')):
        if (path / 'Contents/Resources/app.asar').is_file():
            return path
    return Path('/Applications/Codex.app')


SOURCE = find_source()
RUNTIME = LOCAL / 'Codexflare Runtime.app'
STATE = LOCAL / 'install-macos.json'
DESKTOP = Path.home() / 'Applications/Codexflare Codex.app'
ASAR = Path('Contents/Resources/app.asar')
PLIST = Path('Contents/Info.plist')


def bundle_info(bundle):
    with (bundle / PLIST).open('rb') as stream:
        return plistlib.load(stream)


def executable(bundle):
    name = bundle_info(bundle)['CFBundleExecutable']
    if not isinstance(name, str) or Path(name).name != name or name in ('.', '..'):
        raise ValueError('无效的 CFBundleExecutable')
    return bundle / 'Contents/MacOS' / name


def fingerprint(bundle=None):
    bundle = SOURCE if bundle is None else Path(bundle)
    info = bundle_info(bundle)
    package = json.loads(Asar(bundle / ASAR).read('package.json'))
    if package.get('name') != 'openai-codex-electron':
        raise ValueError('来源不是 Codex Electron 应用')
    result = {'version': package['version'], 'build': str(info['CFBundleVersion']),
              'source': str(bundle.resolve())}
    for path in (bundle / ASAR, executable(bundle), bundle / PLIST):
        value = path.stat()
        result[str(path.relative_to(bundle))] = [value.st_dev, value.st_ino, value.st_size,
                                                value.st_mtime_ns, value.st_ctime_ns]
    return result


def supported_source(source):
    try:
        select_build(source['version'], source['build'])
        return source['build'] is not None
    except (KeyError, ValueError):
        return False


def require_supported(source, bundle=None):
    if not supported_source(source):
        raise ValueError(f'仅支持 macOS Codex {SUPPORTED}；当前 {source.get("version")} / {source.get("build")}')
    bundle = SOURCE if bundle is None else Path(bundle)
    arch = subprocess.check_output(['/usr/bin/lipo', '-archs', str(executable(bundle))], text=True).strip()
    if arch != 'arm64':
        raise ValueError(f'当前 macOS 补丁仅验证 Apple Silicon arm64；来源为 {arch}')


def read_state():
    if not STATE.exists():
        return None
    state = json.loads(STATE.read_text())
    if (not isinstance(state, dict) or state.get('schema') != 1 or state.get('platform') != 'darwin'
            or state.get('desktop') != str(DESKTOP)):
        raise ValueError('无效的 macOS 安装状态或启动器路径')
    return state


def save_state(state):
    atomic_write(STATE, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())


def desktop_snapshot():
    if DESKTOP.is_symlink():
        raise ValueError('启动器不能是符号链接')
    if not DESKTOP.exists():
        return None
    if not DESKTOP.is_dir():
        raise ValueError('启动器路径已被其他文件占用')
    entries = []
    for path in sorted(DESKTOP.rglob('*')):
        if path.is_symlink():
            raise ValueError('启动器含有不受支持的符号链接')
        if path.is_file():
            entries.append((str(path.relative_to(DESKTOP)), digest(path.read_bytes()),
                            stat.S_IMODE(path.stat().st_mode)))
    return {'sha256': digest(json.dumps(entries).encode())}


def running_pids():
    # ps comm is the executable path on Darwin; avoid matching a shell's arguments.
    result = subprocess.run(['/bin/ps', '-axo', 'pid=,comm='], capture_output=True, text=True, check=True)
    prefix = str(RUNTIME.resolve()) + '/'
    pids = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].startswith(prefix):
            # Crash reporting helpers can outlive a normally quit application.
            if (parts[1].startswith(prefix + 'Contents/Frameworks/')
                    and Path(parts[1]).name == 'browser_crashpad_handler'):
                continue
            pids.append(int(parts[0]))
    return pids


def require_stopped():
    pids = running_pids()
    if pids:
        raise ValueError(f'定制副本仍在运行（PID {pids}）；请先正常退出')


def swap_directory(staged, destination):
    if not destination.exists():
        os.replace(staged, destination)
        return
    rename = ctypes.CDLL(None, use_errno=True).renamex_np
    rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(os.fsencode(staged), os.fsencode(destination), 2) != 0:  # RENAME_SWAP
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def integrity_digest(integrity):
    content = ''.join(key + value['algorithm'] + value['hash'] for key, value in sorted(integrity.items()))
    return hashlib.sha256(content.encode()).digest()


def update_framework_integrity(bundle, previous, current):
    # Electron 41+ embeds a second digest of the Info.plist integrity dictionary.
    # Format: electron/electron shell/common/asar/integrity_digest.mm (v1).
    framework = bundle / 'Contents/Frameworks/Codex Framework.framework/Codex Framework'
    sentinel = b'AGbevlPCksUGKNL8TSn7wGmJEuJsXb2A'
    with framework.open('r+b') as file, mmap.mmap(file.fileno(), 0) as data:
        start = data.find(sentinel)
        if start < 0 or data.find(sentinel, start + 1) >= 0:
            raise ValueError('arm64 framework integrity marker must occur exactly once')
        start += len(sentinel)
        if data[start:start + 34] != b'\x01\x01' + integrity_digest(previous):
            raise ValueError('Unexpected or mismatched framework integrity digest; refusing to patch')
        data[start:start + 34] = b'\x01\x01' + integrity_digest(current)
        data.flush()


def seal_bundle(bundle, preserve_identity=False):
    """Update Electron's ASAR header integrity, then ad-hoc sign this copy only."""
    if type(preserve_identity) is not bool:
        raise ValueError('保留应用身份必须是布尔值')
    entitlements = {'com.apple.security.cs.allow-jit': True,
                    'com.apple.security.cs.allow-unsigned-executable-memory': True,
                    'com.apple.security.cs.disable-library-validation': True}
    if preserve_identity:
        result = subprocess.run(['/usr/bin/codesign', '--display', '--entitlements', '-', '--xml', str(bundle)],
                                check=True, capture_output=True)
        original = plistlib.loads(result.stdout)
        if not isinstance(original, dict):
            raise ValueError('无效的原应用签名权限')
        # Only reviewed local resource rights; Team, app groups, Keychain and APNs are excluded.
        for name in ('app-sandbox', 'automation.apple-events', 'device.audio-input', 'device.camera',
                     'files.user-selected.read-write', 'network.client', 'personal-information.calendars'):
            key = 'com.apple.security.' + name
            if key in original:
                if type(original[key]) is not bool:
                    raise ValueError(f'无效的原应用签名权限值: {key}')
                entitlements[key] = original[key]
    archive = bundle / ASAR
    with archive.open('rb') as stream:
        size, header_size, payload_size, string_size = struct.unpack('<4I', stream.read(16))
        if size != 4 or header_size != payload_size + 4 or not 0 < string_size <= payload_size - 4:
            raise ValueError('无效的 ASAR 头')
        header = stream.read(string_size)
    info = bundle_info(bundle)
    previous_integrity = info['ElectronAsarIntegrity']
    info['ElectronAsarIntegrity'] = {'Resources/app.asar': {
        'algorithm': 'SHA256', 'hash': hashlib.sha256(header).hexdigest()}}
    update_framework_integrity(bundle, previous_integrity, info['ElectronAsarIntegrity'])
    if not preserve_identity:
        # A distinct identity prevents standalone copies from sharing vendor account caches.
        info['CFBundleIdentifier'] = 'org.codexflare.runtime'
        info['CrProductDirName'] = 'org.codexflare.runtime'
        info.pop('CFBundleURLTypes', None)
        info['CFBundleDisplayName'] = 'Codex (Codexflare)'
        install_icon(bundle, info)
    (bundle / PLIST).write_bytes(plistlib.dumps(info))
    with tempfile.NamedTemporaryFile(suffix='.plist') as file:
        file.write(plistlib.dumps(entitlements)); file.flush()
        subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', '--options', 'runtime',
                        '--entitlements', file.name, str(bundle)], check=True, capture_output=True)
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(bundle)],
                   check=True, capture_output=True)


def build_runtime(destination, source=None, preserve_identity=False):
    """Used by installation and isolated smoke tests; no launcher or profile changes."""
    source = SOURCE if source is None else Path(source)
    destination = Path(destination)
    before = fingerprint(source)
    require_supported(before, bundle=source)
    if destination.exists():
        raise ValueError('构建目标已经存在')
    subprocess.run(['/usr/bin/ditto', str(source), str(destination)], check=True)
    patched = destination / 'Contents/Resources/app.patched.asar'
    metadata = patch_archive(source / ASAR, patched, platform='darwin', preserve_identity=preserve_identity)
    os.replace(patched, destination / ASAR)
    seal_bundle(destination, preserve_identity=preserve_identity)
    if fingerprint(source) != before:
        raise ValueError('构建期间原版应用发生变化，未启用副本')
    return before, metadata


def install_icon(bundle, info):
    resources = bundle / 'Contents/Resources'
    resources.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'ui/mark.icns', resources / 'codexflare.icns')
    info['CFBundleIconFile'] = 'codexflare.icns'
    # The vendor's asset-catalog name overrides CFBundleIconFile on macOS.
    info.pop('CFBundleIconName', None)
    info.pop('CodexAppIconBaseName', None)


def make_launcher(bundle):
    contents = bundle / 'Contents'
    (contents / 'MacOS').mkdir(parents=True)
    info = {'CFBundleIdentifier': 'org.codexflare.codex-launcher', 'CFBundleName': 'Codexflare Codex',
            'CFBundleExecutable': 'launch', 'CFBundlePackageType': 'APPL', 'CFBundleVersion': '1'}
    install_icon(bundle, info)
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    command = ' '.join(shlex.quote(str(value)) for value in
                       command_for('manage', 'launch'))
    script = contents / 'MacOS/launch'
    script.write_text('#!/bin/sh\nexec ' + command + ' "$@"\n')
    script.chmod(0o755)


def install():
    state = read_state()
    current = desktop_snapshot()
    if current is not None and (not state or not state.get('active') or current != state.get('installed_desktop')):
        raise ValueError('启动器已存在或已被其他操作修改；拒绝覆盖')
    require_stopped()
    LOCAL.mkdir(parents=True, exist_ok=True); LOCAL.chmod(0o700)
    if RUNTIME.is_symlink():
        raise ValueError('运行副本不能是符号链接')
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='mac-build-', dir=LOCAL) as directory:
        staged = Path(directory) / RUNTIME.name
        before, metadata = build_runtime(staged)
        require_stopped()
        if desktop_snapshot() != current:
            raise ValueError('构建期间启动器发生变化，拒绝覆盖')
        with tempfile.TemporaryDirectory(prefix='.codexflare-', dir=DESKTOP.parent) as launch_dir:
            launcher = Path(launch_dir) / DESKTOP.name
            make_launcher(launcher)
            # Runtime first: any interrupted transaction still leaves the official app intact.
            swap_directory(staged, RUNTIME)
            swap_directory(launcher, DESKTOP)
        save_state({'schema': 1, 'platform': 'darwin', 'desktop': str(DESKTOP), 'active': True,
                    'source': before, 'patch': metadata, 'installed_desktop': desktop_snapshot()})
    print(f'已安装定制副本：{RUNTIME}\n从 {DESKTOP} 启动；原版应用保持不变。')


def uninstall():
    state = read_state()
    if not state or not state.get('active'):
        print('尚未启用 macOS 定制启动器。'); return
    current = desktop_snapshot()
    if current is not None:
        if current != state['installed_desktop']:
            raise ValueError('启动器已被其他操作修改；拒绝删除')
        shutil.rmtree(DESKTOP)
    state['active'] = False
    save_state(state)
    print('已移除 Codexflare 启动器。原版应用、配置和副本保留；未停止任何进程。')


def runtime_problem(state):
    if not state or not state.get('active'):
        return '尚未安装或已回退'
    if not (RUNTIME / ASAR).is_file() or not (RUNTIME / PLIST).is_file():
        return '定制副本缺失'
    try:
        if not executable(RUNTIME).is_file():
            return '定制可执行文件缺失'
        if fingerprint() != state['source']:
            return '原版 Codex 已更新，旧补丁尚未重新验证'
    except (OSError, ValueError, KeyError, struct.error) as error:
        return f'无法验证原版应用：{error}'
    return None


def launch(arguments):
    try:
        problem = runtime_problem(read_state())
    except (OSError, ValueError, KeyError) as error:
        problem = f'安装状态无法读取：{error}'
    if problem:
        print(f'{problem}；打开原版应用。', file=sys.stderr, flush=True)
        return os.execv('/usr/bin/open', ['open', '-a', str(SOURCE), '--args', *arguments])
    # Ad-hoc copies cannot share vendor Keychain entitlements. Keep all state separate.
    env = {**os.environ, 'CODEX_HOME': str(LOCAL / 'codex-home'),
           'CODEX_ELECTRON_USER_DATA_PATH': str(LOCAL / 'profile')}
    binary = str(executable(RUNTIME))
    os.execve(binary, [binary, '--user-data-dir=' + env['CODEX_ELECTRON_USER_DATA_PATH'], *arguments], env)


def status():
    state = read_state()
    print(f'状态：{runtime_problem(state) or "定制副本可用"}')
    print(f'目标：macOS arm64 Codex {SUPPORTED}\n原版：{SOURCE}\n副本：{RUNTIME}\n启动器：{DESKTOP}')
