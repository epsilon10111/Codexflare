#!/usr/bin/env python3
"""安装可回退的用户级 Codex 启动副本，不修改系统包或用户 profile。"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

if __package__:
    from .patch_app import Asar, VERSION, patch_archive
    from .paths import ROOT, LOCAL, data_home
else:
    from patch_app import Asar, VERSION, patch_archive
    from paths import ROOT, LOCAL, data_home

RUNTIME = LOCAL / 'runtime'
STATE = LOCAL / 'install.json'
BACKUP = LOCAL / 'chatgpt.desktop.original'
SOURCE = Path('/usr/lib/chatgpt')
SYSTEM_LAUNCHER = Path('/usr/bin/chatgpt')
SYSTEM_DESKTOP = Path('/usr/share/applications/chatgpt.desktop')
DESKTOP = data_home() / 'applications/chatgpt.desktop'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint():
    package = json.loads(Asar(SOURCE / 'resources/app.asar').read('package.json'))
    if package.get('name') != 'openai-codex-electron':
        raise ValueError('来源不是 Codex Electron 应用')
    result = {'version': package['version']}
    for relative in ('resources/app.asar', 'ChatGPT'):
        info = (SOURCE / relative).stat()
        result[relative] = [info.st_dev, info.st_ino, info.st_size,
                            info.st_mtime_ns, info.st_ctime_ns]
    return result


def read_state():
    if not STATE.exists():
        return None
    state = json.loads(STATE.read_text())
    if not isinstance(state, dict) or state.get('schema') != 1 or state.get('desktop') != str(DESKTOP):
        raise ValueError('安装状态无效或属于另一个 desktop 路径')
    return state


def atomic_write(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            if os.name != 'nt':
                os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_state(state):
    atomic_write(STATE, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())


def desktop_snapshot():
    if DESKTOP.is_symlink():
        raise ValueError('用户 desktop 是符号链接；为避免覆盖链接目标，停止')
    if not DESKTOP.exists():
        return None
    if not DESKTOP.is_file():
        raise ValueError('用户 desktop 不是普通文件')
    return {'sha256': digest(DESKTOP.read_bytes()),
            'mode': stat.S_IMODE(DESKTOP.stat().st_mode)}


def desktop_quote(value):
    value = str(value)
    if any(char in value for char in '\n\r\0'):
        raise ValueError('desktop 启动路径不能包含换行或 NUL')
    # Desktop Entry 字符串先反转义，再解析 Exec；两层都必须保留转义。
    value = value.replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return '"' + value.replace('\\', '\\\\') + '"'


def launcher_content():
    # RPM 卸载后保留用户启动器，原有菜单仍可回到系统 Codex。
    return f'''import os
from pathlib import Path
import sys

manager = Path({str(Path(__file__).resolve())!r})
command = [sys.executable, str(manager), 'launch'] if manager.is_file() else [{str(SYSTEM_LAUNCHER)!r}]
os.execv(command[0], [*command, *sys.argv[1:]])
'''.encode()


def desktop_content():
    command = f'{desktop_quote(sys.executable)} {desktop_quote(LOCAL / "launch.py")} %U'
    lines = SYSTEM_DESKTOP.read_text().splitlines(keepends=True)
    section = None
    replaced = 0
    for index, line in enumerate(lines):
        if line.strip().startswith('['):
            section = line.strip()
        if section == '[Desktop Entry]' and line.startswith('Exec='):
            lines[index] = f'Exec={command}\n'
            replaced += 1
    if replaced != 1:
        raise ValueError('系统 desktop 主入口 Exec 不是唯一一处，停止')
    return ''.join(lines).encode()


def running_pids():
    prefix = str(RUNTIME.resolve()) + os.sep
    result = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            executable = os.readlink(entry / 'exe')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if executable.startswith(prefix):
            result.append(int(entry.name))
    return result


def require_stopped():
    pids = running_pids()
    if pids:
        raise ValueError(f'定制副本仍在运行（PID {pids}）；请先退出，再重新安装')


def swap_runtime(staged):
    if not RUNTIME.exists():
        os.replace(staged, RUNTIME)
        return
    # Linux 原子交换两个目录，避免更新时留下缺失或半复制的 runtime。
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(staged), -100, os.fsencode(RUNTIME), 2) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def install():
    state = read_state()
    current_desktop = desktop_snapshot()
    if state:
        expected = state['installed_desktop'] if state['active'] else state['original_desktop']
        # 上次若在保存状态后、替换 desktop 前中断，原入口仍可安全重试。
        if current_desktop not in (expected, state['original_desktop']):
            raise ValueError('用户 desktop 已被其他操作修改；拒绝覆盖')
    before = fingerprint()
    if before['version'] != VERSION:
        raise ValueError(f'仅支持 Codex {VERSION}；当前 {before["version"]}')
    require_stopped()
    LOCAL.mkdir(parents=True, exist_ok=True)
    LOCAL.chmod(0o700)
    if RUNTIME.is_symlink():
        raise ValueError('runtime 不能是符号链接')
    staged = Path(tempfile.mkdtemp(prefix='runtime.build-', dir=LOCAL))
    try:
        subprocess.run(['cp', '-a', '--reflink=auto', str(SOURCE) + '/.', str(staged)], check=True)
        patched = staged / 'resources/app.patched.asar'
        metadata = patch_archive(SOURCE / 'resources/app.asar', patched)
        if metadata['version'] != VERSION or fingerprint() != before:
            raise ValueError('生成副本期间系统应用发生变化，未启用本次副本')
        os.chmod(patched, stat.S_IMODE((SOURCE / 'resources/app.asar').stat().st_mode))
        os.replace(patched, staged / 'resources/app.asar')
        content = desktop_content()
        if desktop_snapshot() != current_desktop:
            raise ValueError('构建期间用户 desktop 发生变化，拒绝覆盖')
        if state is None:
            if BACKUP.exists():
                raise ValueError('发现无对应安装状态的原始备份，拒绝覆盖备份')
            if current_desktop:
                with BACKUP.open('xb') as output:
                    output.write(DESKTOP.read_bytes())
                os.chmod(BACKUP, current_desktop['mode'])
            state = {'schema': 1, 'desktop': str(DESKTOP),
                     'original_desktop': current_desktop, 'active': False,
                     'source': before, 'patch': metadata, 'installed_desktop': None}
            save_state(state)
        require_stopped()
        swap_runtime(staged)
        atomic_write(LOCAL / 'launch.py', launcher_content())
        state.update(active=True, source=before, patch=metadata,
                     installed_desktop={'sha256': digest(content), 'mode': 0o644})
        save_state(state)
        atomic_write(DESKTOP, content, 0o644)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    print(f'已安装 Codex {VERSION} 定制副本：{RUNTIME}')
    print('应用菜单入口已启用；当前已运行的系统应用需要正常退出后重新打开。')


def uninstall():
    state = read_state()
    if not state or not state['active']:
        print('未启用本工具的 desktop 覆盖，无需恢复。')
        return
    current = desktop_snapshot()
    original = state['original_desktop']
    if current == original:
        print('原始 desktop 已恢复。')
    elif current != state['installed_desktop']:
        raise ValueError('用户 desktop 已被其他操作修改；拒绝覆盖或删除')
    elif original:
        content = BACKUP.read_bytes()
        if digest(content) != original['sha256']:
            raise ValueError('原始 desktop 备份校验失败，未修改入口')
        atomic_write(DESKTOP, content, original['mode'])
        print('已恢复安装前的用户 desktop 文件与权限。')
    else:
        DESKTOP.unlink()
        print('已移除本工具新增的 desktop 覆盖，恢复系统入口。')
    state['active'] = False
    save_state(state)
    print(f'未删除用户数据；保留副本和备份：{LOCAL}。未停止任何进程。')


def runtime_problem(state):
    if not state or not state.get('active'):
        return '尚未安装或已回退'
    if not all((RUNTIME / path).is_file() for path in ('ChatGPT', 'resources/app.asar')):
        return '定制运行副本缺失'
    try:
        if fingerprint() != state['source']:
            return '系统 Codex 已更新，旧补丁尚未重新验证'
    except (OSError, ValueError, KeyError, struct.error) as error:
        return f'无法验证系统版本：{error}'
    return None


def launch(arguments):
    try:
        problem = runtime_problem(read_state())
    except (OSError, ValueError, KeyError) as error:
        problem = f'安装状态无法读取：{error}'
    executable = SYSTEM_LAUNCHER if problem else RUNTIME / 'ChatGPT'
    if problem:
        print(f'警告：{problem}；本次启动原版 Codex。', file=sys.stderr, flush=True)
    os.execv(str(executable), [str(executable), *arguments])


def status():
    state = read_state()
    problem = runtime_problem(state)
    print(f'状态：{problem or "定制副本可用"}')
    if state:
        print(f'补丁版本：{state["patch"]["version"]}')
        print(f'desktop 仍由本工具持有：{desktop_snapshot() == state.get("installed_desktop") and state["active"]}')
    print(f'副本路径：{RUNTIME}')


def platform_manager():
    if sys.platform == 'win32':
        if __package__:
            from . import manage_windows
        else:
            import manage_windows
        return manage_windows
    return sys.modules[__name__]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('install', 'launch', 'uninstall', 'status'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if args.command == 'launch':
            platform_manager().launch(args.arguments)
        elif args.arguments:
            parser.error('只有 launch 接受应用参数')
        else:
            getattr(platform_manager(), args.command)()
    except (OSError, ValueError, KeyError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, f'错误：{error}\n')


if __name__ == '__main__':
    main()
