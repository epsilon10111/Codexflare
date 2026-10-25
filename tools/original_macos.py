"""Prepare reversible customizations for the original macOS application path."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time

if __package__:
    from . import manage_macos as mac
    from .paths import command_for
else:
    import manage_macos as mac
    from paths import command_for

SOURCE = mac.SOURCE
LOCAL = mac.LOCAL
STATE = LOCAL / 'original-install.json'
BACKUP = LOCAL / 'Original ChatGPT.app'
LOCK = LOCAL / 'original-install.lock'
WORKER_LOCK = LOCAL / 'original-worker.lock'
LOG = LOCAL / 'original-worker.log'
OFFICIAL_REQUIREMENT = ('identifier "com.openai.codex" and anchor apple generic '
                        'and certificate leaf[subject.OU] = "2DC432GLL2"')


class BusyError(ValueError):
    pass


def _local():
    if LOCAL.is_symlink():
        raise ValueError('原路径安装目录不能是符号链接')
    LOCAL.mkdir(parents=True, exist_ok=True)


@contextmanager
def _lock(path):
    import fcntl
    _local()
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise BusyError('原路径安装操作仍在进行') from error
        yield
    finally:
        os.close(descriptor)


def _bundle(path):
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f'应用必须是普通目录：{path}')


def bundle_digest(bundle):
    """Content identity survives directory exchanges and checks framework symlinks."""
    _bundle(bundle)
    root = bundle.resolve()
    result = hashlib.sha256()
    for path in sorted(bundle.rglob('*')):
        relative = path.relative_to(bundle).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            if not path.resolve().is_relative_to(root):
                raise ValueError(f'应用含越界符号链接：{relative}')
            value = 'link:' + os.readlink(path)
        elif stat.S_ISDIR(mode):
            value = 'directory'
        elif stat.S_ISREG(mode):
            value = 'file'
        else:
            raise ValueError(f'应用含不支持的文件：{relative}')
        result.update(f'{relative}\0{stat.S_IMODE(mode)}\0{value}\0'.encode())
        if value == 'file':
            with path.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    result.update(chunk)
    return result.hexdigest()


def _verify(bundle, official=False):
    _bundle(bundle)
    command = ['/usr/bin/codesign', '--verify', '--deep', '--strict']
    if official:
        command += ['--test-requirement', '=' + OFFICIAL_REQUIREMENT]
    subprocess.run([*command, str(bundle)], check=True, capture_output=True)


def _candidate_path(path):
    path = Path(path)
    if (path.name != SOURCE.name or path.parent.parent != SOURCE.parent
            or not path.parent.name.startswith('.codexflare-original-')
            or path.parent.is_symlink() or path.is_symlink()):
        raise ValueError('无效的待安装应用路径')
    return path


def read_state():
    if STATE.is_symlink():
        raise ValueError('原路径安装状态不能是符号链接')
    if not STATE.exists():
        return None
    state = json.loads(STATE.read_text())
    if (not isinstance(state, dict) or state.get('schema') != 1
            or state.get('target') != str(SOURCE) or state.get('backup') != str(BACKUP)
            or not isinstance(state.get('original_sha256'), str)):
        raise ValueError('原路径安装状态无效')
    pending = state.get('pending')
    if pending:
        if (not isinstance(pending, dict) or pending.get('action') not in ('install', 'restore')
                or not isinstance(pending.get('sha256'), str)
                or not isinstance(pending.get('expected_sha256'), str)):
            raise ValueError('原路径待安装状态无效')
        _candidate_path(pending['path'])
    return state


def _save(state):
    mac.atomic_write(STATE, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())


def running_pids():
    result = subprocess.run(['/bin/ps', '-axo', 'pid=,comm='], capture_output=True, text=True, check=True)
    prefix = str(SOURCE.resolve()) + '/Contents/'
    pids = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        path = parts[1]
        if path.startswith(prefix + 'MacOS/') or path.startswith(prefix + 'Frameworks/'):
            if path.startswith(prefix + 'Frameworks/') and Path(path).name == 'browser_crashpad_handler':
                continue
            pids.append(int(parts[0]))
    return pids


def _check_backup(state):
    if bundle_digest(BACKUP) != state['original_sha256']:
        raise ValueError('官方备份发生变化；未覆盖当前应用')
    _verify(BACKUP, official=True)


def _remove_candidate(path):
    path = _candidate_path(path)
    shutil.rmtree(path.parent)


def _finish(state):
    pending = state['pending']
    state['active'] = pending['action'] == 'install'
    state['installed_sha256'] = pending['sha256'] if state['active'] else None
    state['target_fingerprint'] = mac.fingerprint(SOURCE)
    state['pending'] = None
    state.pop('exchanging', None)
    state.pop('error', None)
    _save(state)
    # Only discard the exchanged old copy after the recovery state is durable.
    try:
        _remove_candidate(pending['path'])
    except OSError:
        pass  # A leftover previous bundle is safer than undoing a completed installation.


def _recover(state):
    if not state or not state.get('exchanging'):
        return state
    _check_backup(state)
    pending = state['pending']
    candidate = _candidate_path(pending['path'])
    target_hash, candidate_hash = bundle_digest(SOURCE), bundle_digest(candidate)
    if target_hash == pending['sha256'] and candidate_hash == pending['expected_sha256']:
        _verify_exchanged(state)
        _finish(state)
    elif target_hash == pending['expected_sha256'] and candidate_hash == pending['sha256']:
        state.pop('exchanging', None)
        _save(state)
    else:
        raise ValueError('上次换包中断后应用发生变化；保留全部副本，拒绝覆盖')
    return state


def _verify_exchanged(state):
    pending = state['pending']
    try:
        _verify(SOURCE, official=pending['action'] == 'restore')
    except Exception as error:
        candidate = _candidate_path(pending['path'])
        if (not running_pids() and bundle_digest(SOURCE) == pending['sha256']
                and bundle_digest(candidate) == pending['expected_sha256']):
            mac.swap_directory(candidate, SOURCE)
            state.pop('exchanging', None)
            state['target_fingerprint'] = mac.fingerprint(SOURCE)
        state['error'] = str(error)
        _save(state)
        raise


def _initial_state():
    _bundle(SOURCE)
    if BACKUP.is_symlink():
        raise ValueError('官方备份不能是符号链接')
    before = bundle_digest(SOURCE)
    _verify(SOURCE, official=True)
    mac.require_supported(mac.fingerprint(SOURCE), bundle=SOURCE)
    mac.check_compatibility(bundle=SOURCE, preserve_identity=True)
    if not BACKUP.exists():
        with tempfile.TemporaryDirectory(prefix='original-backup-', dir=LOCAL) as directory:
            staged = Path(directory) / SOURCE.name
            subprocess.run(['/usr/bin/ditto', str(SOURCE), str(staged)], check=True)
            if bundle_digest(staged) != before or bundle_digest(SOURCE) != before:
                raise ValueError('备份期间原版应用发生变化；未安装')
            _verify(staged, official=True)
            os.replace(staged, BACKUP)
    if bundle_digest(BACKUP) != before:
        raise ValueError('已有官方备份不属于当前原版；拒绝覆盖备份')
    state = {'schema': 1, 'mode': 'original', 'target': str(SOURCE), 'backup': str(BACKUP),
             'original_sha256': before, 'active': False, 'installed_sha256': None,
             'target_fingerprint': mac.fingerprint(SOURCE), 'pending': None}
    _save(state)
    return state


def _prepare(action):
    with _lock(LOCK):
        state = _recover(read_state()) or _initial_state()
        _check_backup(state)
        expected = state['installed_sha256'] if state['active'] else state['original_sha256']
        if bundle_digest(SOURCE) != expected:
            raise ValueError('原应用已更新或被其他操作修改；未覆盖，也不会还原旧版本')
        directory = Path(tempfile.mkdtemp(prefix='.codexflare-original-', dir=SOURCE.parent))
        candidate = directory / SOURCE.name
        try:
            if action == 'install':
                mac.build_runtime(candidate, source=BACKUP, preserve_identity=True)
            else:
                subprocess.run(['/usr/bin/ditto', str(BACKUP), str(candidate)], check=True)
            _verify(candidate, official=action == 'restore')
            if bundle_digest(SOURCE) != expected:
                raise ValueError('构建期间原应用发生变化；未覆盖')
            candidate_hash = bundle_digest(candidate)
            old_pending = state.get('pending')
            state['pending'] = {'action': action, 'path': str(candidate),
                                'sha256': candidate_hash, 'expected_sha256': expected}
            state.pop('error', None)
            state.pop('failed_candidate', None)
            _save(state)
            if old_pending:
                _remove_candidate(old_pending['path'])
        except Exception as error:
            # Keep a failed candidate for diagnosis; the original and its backup remain intact.
            state['error'] = str(error)
            state['failed_candidate'] = str(candidate)
            _save(state)
            raise
    return status()


def prepare():
    """Build and queue only; never replace or stop the running original application."""
    return _prepare('install')


def uninstall():
    """Queue an exact official restore using the same exit/transaction protections."""
    return _prepare('restore')


def activate_pending():
    """Return False while the original is running; otherwise apply the pending exchange."""
    with _lock(LOCK):
        state = read_state()
        recovering = bool(state and state.get('exchanging'))
        state = _recover(state)
        if not state or not state.get('pending'):
            return recovering
        if running_pids():
            return False
        try:
            pending = state['pending']
            candidate = _candidate_path(pending['path'])
            _check_backup(state)
            if bundle_digest(SOURCE) != pending['expected_sha256']:
                raise ValueError('等待期间原应用已更新或被修改；未覆盖')
            if bundle_digest(candidate) != pending['sha256']:
                raise ValueError('待安装应用发生变化；未覆盖原版')
            _verify(candidate, official=pending['action'] == 'restore')
            if running_pids():
                return False
            state['exchanging'] = True
            _save(state)
            mac.swap_directory(candidate, SOURCE)
            _verify_exchanged(state)
            _finish(state)
            return True
        except Exception as error:
            state['error'] = str(error)
            _save(state)
            raise


def _worker_running():
    try:
        with _lock(WORKER_LOCK):
            return False
    except BusyError:
        return True


def status():
    state = None
    try:
        state = read_state()
        fingerprint = mac.fingerprint(SOURCE)
        available = mac.supported_source(fingerprint)
        running = bool(running_pids())
        pending = bool(state and state.get('pending'))
        active = bool(state and state.get('active'))
        changed = state and not state.get('exchanging') and fingerprint != state['target_fingerprint']
        if available:
            mac.check_compatibility(bundle=BACKUP if active and not changed else SOURCE, preserve_identity=True)
        error = state and state.get('error')
        if changed:
            active = False
            error = '原应用已更新或被其他操作修改；未覆盖'
        worker = _worker_running()
        phase = 'failed' if error else 'queued' if pending and running else 'pending' if pending else 'active' if active else 'ready'
        restoring = pending and state['pending']['action'] == 'restore'
        message = (str(error) if error else
                   '恢复原版已准备；退出原应用后自动恢复' if restoring and worker else
                   '恢复原版已准备，等待执行' if restoring else
                   '定制版已准备；退出原应用后自动应用，下次仍从原入口启动' if pending and worker else
                   '定制版已准备，等待执行；原应用仍保持当前版本' if pending else
                   '动画与背景已应用到原来的应用入口' if active else
                   '将应用到原来的应用入口；保留官方备份以便恢复')
        return {'mode': 'original', 'phase': phase, 'active': active, 'available': available,
                'running': running, 'pending': pending, 'queued': pending and running,
                'worker_running': worker, 'message': message}
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        return {'mode': 'original', 'phase': 'failed', 'active': False, 'available': False,
                'running': False, 'pending': bool(state and state.get('pending')),
                'queued': False, 'worker_running': False, 'message': str(error)}


def launch_worker(relaunch=False):
    """Explicitly dispatch one exit-waiter; callers must finish candidate validation first."""
    state = read_state()
    if not state or not state.get('pending') or state.get('error') or _worker_running():
        return False
    descriptor = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'ab') as log:
        command = command_for('original_macos', 'wait-activate')
        if relaunch:
            command.append('--relaunch')
        env = os.environ.copy()
        if getattr(sys, 'frozen', False):
            env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         start_new_session=True, close_fds=True, env=env)
    return True


def wait_activate(relaunch=False):
    try:
        with _lock(WORKER_LOCK):
            print(f'等待 {SOURCE} 正常退出；不会结束任何进程。', flush=True)
            while True:
                state = read_state()
                if not state or not state.get('pending'):
                    return
                if state.get('error'):
                    print(f'未执行：{state["error"]}', flush=True)
                    return
                action = state['pending']['action']
                try:
                    if activate_pending():
                        print(f'{action} 完成：{SOURCE}；已通过签名校验。', flush=True)
                        if relaunch:
                            env = {key: value for key, value in os.environ.items()
                                   if key not in ('CODEX_HOME', 'CODEX_ELECTRON_USER_DATA_PATH',
                                                  'CODEX_ELECTRON_START_IN_BACKGROUND')}
                            subprocess.run(['/usr/bin/open', str(SOURCE)], check=True, env=env)
                        return
                except BusyError:
                    pass
                time.sleep(2)
    except BusyError:
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'activate', 'uninstall', 'status', 'wait-activate'))
    parser.add_argument('--relaunch', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'wait-activate':
            wait_activate(args.relaunch)
        else:
            result = {'prepare': prepare, 'activate': activate_pending,
                      'uninstall': uninstall, 'status': status}[args.command]()
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'错误：{error}\n')


if __name__ == '__main__':
    main()
