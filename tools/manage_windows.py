"""Launch the installed Windows app with in-memory visuals; never copy or edit it."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

if __package__:
    from . import animation, windows_package
    from .manage import atomic_write, digest
    from .patch_app import Asar, patch_archive
    from .patch_windows import VERSION, BUILD, SUPPORTED_BUILDS, require_supported
    from .paths import LOCAL
else:
    import animation, windows_package
    from manage import atomic_write, digest
    from patch_app import Asar, patch_archive
    from patch_windows import VERSION, BUILD, SUPPORTED_BUILDS, require_supported
    from paths import LOCAL


powershell = windows_package.powershell


def find_source():
    override = os.environ.get('CODEXFLARE_SOURCE_APP')
    if not override:
        try:
            state = read_state()
            if state and state.get('custom_source') is True:
                saved = state['source']['source']
                if isinstance(saved, str) and Path(saved).is_absolute():
                    override = saved
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if override:
        path = Path(override).expanduser().absolute()
        return path / 'app' if (path / 'app/resources/app.asar').is_file() else path
    if sys.platform == 'win32':
        location = powershell("Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | "
                              "Select-Object -First 1 -ExpandProperty InstallLocation")
        if location:
            return Path(location) / 'app'
    return Path.home() / 'AppData/Local/Programs/Codex'


RUNTIME = LOCAL / 'runtime-windows'
STATE = LOCAL / 'install-windows.json'
DESKTOP = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'Microsoft/Windows/Start Menu/Programs/Codex (Codexflare).lnk'
ASAR = Path('resources/app.asar')
BINARY = 'ChatGPT.exe'
RUNTIME_FILES = (ASAR, Path(BINARY), Path('chrome.dll'), Path('owl-shell-runtime.json'))
SUPPORTED_VERSIONS = tuple(version for version, _build in SUPPORTED_BUILDS)
LAUNCH_HINT = '正常退出原版后，从开始菜单 Codex (Codexflare) 启动同一原版应用；原 Store 图标保持不变。'


def fingerprint():
    package = json.loads(Asar(SOURCE / ASAR).read('package.json'))
    if package.get('name') != 'openai-codex-electron':
        raise ValueError('来源不是 Codex 应用')
    require_supported(package)
    runtime = json.loads((SOURCE / 'owl-shell-runtime.json').read_text(encoding='utf-8'))
    if runtime.get('platform') != 'win32' or runtime.get('arch') != 'x64':
        raise ValueError('仅支持 Windows x64 Owl 运行时')
    result = {'version': package['version'], 'build': package.get('codexBuildNumber'),
              'source': str(SOURCE.resolve())}
    for relative in RUNTIME_FILES:
        info = (SOURCE / relative).stat()
        result[str(relative)] = [info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    return result


def read_state():
    if not STATE.exists():
        return None
    state = json.loads(STATE.read_text(encoding='utf-8'))
    if (not isinstance(state, dict) or state.get('schema') != 1 or state.get('platform') != 'win32'
            or state.get('desktop') != str(DESKTOP)):
        raise ValueError('无效的 Windows 安装状态或启动器路径')
    return state


SOURCE = find_source()


def save_state(state):
    atomic_write(STATE, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())


def desktop_snapshot():
    if DESKTOP.is_symlink():
        raise ValueError('启动器不能是符号链接')
    if not DESKTOP.exists():
        return None
    if not DESKTOP.is_file():
        raise ValueError('启动器路径已被占用')
    return {'sha256': digest(DESKTOP.read_bytes())}


def running_pids():
    output = powershell(
        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and "
        "$_.ExecutablePath.StartsWith($env:CODEXFLARE_RUNTIME_PREFIX, [StringComparison]::OrdinalIgnoreCase) } | "
        "Select-Object -ExpandProperty ProcessId", CODEXFLARE_RUNTIME_PREFIX=str(RUNTIME.resolve()) + os.sep)
    return [int(line) for line in output.splitlines() if line.strip()]


def require_stopped():
    pids = running_pids()
    if pids:
        raise ValueError(f'定制副本仍在运行（PID {pids}）；请先正常退出')


def source_running_pids():
    output = powershell(
        "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and "
        "[String]::Equals($_.ExecutablePath, $env:CODEXFLARE_SOURCE_EXE, [StringComparison]::OrdinalIgnoreCase) } | "
        "Select-Object -ExpandProperty ProcessId", CODEXFLARE_SOURCE_EXE=str((SOURCE / BINARY).resolve()))
    return [int(line) for line in output.splitlines() if line.strip()]


def build_runtime(destination):
    destination = Path(destination)
    if destination.exists() or SOURCE.resolve() in destination.resolve().parents:
        raise ValueError('构建目标已存在或位于原版应用内')
    before = fingerprint()
    shutil.copytree(SOURCE, destination)
    patched = destination / 'resources/app.patched.asar'
    metadata = patch_archive(SOURCE / ASAR, patched, platform='win32')
    os.replace(patched, destination / ASAR)
    update_integrity(destination / BINARY, header_hash(SOURCE / ASAR), header_hash(destination / ASAR))
    if fingerprint() != before:
        raise ValueError('构建期间原版应用发生变化，未启用副本')
    return before, metadata


def header_hash(archive):
    Asar(archive)  # Validate the pickle header before hashing its JSON bytes.
    with Path(archive).open('rb') as stream:
        size = struct.unpack('<4I', stream.read(16))[3]
        return hashlib.sha256(stream.read(size)).hexdigest()


def update_integrity(binary, previous, current):
    # Exact, same-size ElectronAsar resource edit in this build's copied executable.
    # This invalidates the copy's vendor signature; no integrity fuse is disabled.
    record = json.dumps([{'file': 'resources\\app.asar', 'alg': 'SHA256', 'value': previous}],
                        separators=(',', ':')).encode()
    data = Path(binary).read_bytes()
    if data.count(record) != 1:
        raise ValueError('Windows ASAR integrity 记录不是唯一匹配，拒绝修改')
    replacement = record.replace(previous.encode(), current.encode())
    if len(replacement) != len(record):
        raise ValueError('Windows ASAR integrity 长度不匹配')
    Path(binary).write_bytes(data.replace(record, replacement, 1))


def make_launcher(path):
    import ctypes
    from uuid import UUID

    python = Path(sys.executable)
    if python.with_name('pythonw.exe').is_file():
        python = python.with_name('pythonw.exe')
    arguments = subprocess.list2cmdline([str(Path(__file__).with_name('manage.py').resolve()), 'launch'])
    # WScript.Shell.Save uses the ANSI code page; IShellLinkW/IPersistFile preserve Unicode paths.
    ole = ctypes.OleDLL('ole32')
    ole.CoInitialize.argtypes = [ctypes.c_void_p]
    ole.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                                    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    link, persist = ctypes.c_void_p(), ctypes.c_void_p()

    def guid(value):
        return ctypes.create_string_buffer(UUID(value).bytes_le)

    def method(pointer, index, result, *types):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(result, ctypes.c_void_p, *types)(table[index])

    ole.CoInitialize(None)
    try:
        ole.CoCreateInstance(guid('00021401-0000-0000-c000-000000000046'), None, 1,
                             guid('000214f9-0000-0000-c000-000000000046'), ctypes.byref(link))
        # IShellLinkW vtable slots: SetPath, SetArguments, SetWorkingDirectory, SetDescription.
        for index, value in ((20, str(python)), (11, arguments), (9, str(LOCAL.parent)),
                             (7, 'Codex with Codexflare')):
            method(link, index, ctypes.HRESULT, ctypes.c_wchar_p)(link, value)
        method(link, 17, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)(link, str(SOURCE / BINARY), 0)
        method(link, 0, ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            link, guid('0000010b-0000-0000-c000-000000000046'), ctypes.byref(persist))
        method(persist, 6, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)(persist, str(path), 1)
    finally:
        for pointer in (persist, link):
            if pointer.value:
                method(pointer, 2, ctypes.c_ulong)(pointer)
        ole.CoUninitialize()


def install():
    if __package__:
        from . import windows_inject
    else:
        import windows_inject

    state, current = read_state(), desktop_snapshot()
    if current is not None and (not state or not state.get('active') or current != state.get('installed_desktop')):
        raise ValueError('启动器已存在或已被其他操作修改；拒绝覆盖')
    require_stopped()
    before = fingerprint()
    windows_package.registered_package(SOURCE)
    settings = animation.load_settings()
    windows_inject.prepare_script(SOURCE, settings, LOCAL)
    LOCAL.mkdir(parents=True, exist_ok=True)
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='windows-launcher-', dir=LOCAL))
    cleanup = True
    try:
        launcher = directory / 'launcher.lnk'
        make_launcher(launcher)
        content = launcher.read_bytes()
        require_stopped()
        if fingerprint() != before:
            raise ValueError('准备期间原版应用发生变化，未启用启动器')
        if desktop_snapshot() != current:
            raise ValueError('准备期间启动器发生变化，拒绝覆盖')
        previous_desktop = DESKTOP.read_bytes() if current is not None else None
        if previous_desktop is not None:
            (directory / 'previous.lnk').write_bytes(previous_desktop)
        installed_desktop = {'sha256': digest(content)}
        cleanup = False  # Keep the prior shortcut if rollback fails or the process is interrupted.
        try:
            atomic_write(DESKTOP, content)
            save_state({'schema': 1, 'platform': 'win32', 'desktop': str(DESKTOP), 'active': True,
                        'mode': 'original', 'settings': settings,
                        'source': before, 'custom_source': bool(os.environ.get('CODEXFLARE_SOURCE_APP')
                            or (state and state.get('custom_source'))),
                        'installed_desktop': installed_desktop})
        except Exception:
            try:
                if desktop_snapshot() == installed_desktop:
                    if previous_desktop is None:
                        DESKTOP.unlink()
                    elif previous_desktop != content:
                        atomic_write(DESKTOP, previous_desktop)
            except Exception as error:
                error.add_note(f'安装恢复目录：{directory}')
                raise
            cleanup = True
            raise
        cleanup = True
    finally:
        if cleanup:
            shutil.rmtree(directory)
    print(f'已启用原版应用启动器：{DESKTOP}\n未创建应用副本或独立账户目录。\n{LAUNCH_HINT}')


def uninstall():
    state = read_state()
    if not state or not state.get('active'):
        print('尚未启用 Windows 定制启动器。')
        return
    current = desktop_snapshot()
    if current is not None:
        if current != state['installed_desktop']:
            raise ValueError('启动器已被其他操作修改；拒绝删除')
        DESKTOP.unlink()
    state['active'] = False
    save_state(state)
    print('已移除 Codexflare 启动器；保留配置和素材，未修改原版或停止任何进程。')


def runtime_problem(state):
    if not state or not state.get('active'):
        return '尚未安装或已回退'
    if state.get('mode') != 'original':
        return '旧版副本安装状态；请重新应用以启用原版应用模式'
    try:
        if not state.get('installed_desktop') or desktop_snapshot() != state['installed_desktop']:
            return '启动器缺失或已被修改'
        animation.validate_settings(state['settings'])
    except (OSError, ValueError, KeyError) as error:
        return f'无法验证启动器或已应用设置：{error}'
    try:
        if fingerprint() != state['source']:
            return '原版 Codex 已更新；请重新应用以验证动画和背景'
    except (OSError, ValueError, KeyError, struct.error) as error:
        return f'无法验证原版应用：{error}'
    return None


def launch(arguments):
    try:
        state = read_state()
        problem = runtime_problem(state)
    except (OSError, ValueError, KeyError) as error:
        problem = f'安装状态无法读取：{error}'
    if not problem:
        pids = source_running_pids()
        if pids:
            raise ValueError(f'原版应用仍在运行（PID {pids}）；请正常退出后再使用 Codexflare 启动器，不会自动终止会话')
        if __package__:
            from . import windows_inject
        else:
            import windows_inject
        try:
            script = windows_inject.prepare_script(SOURCE, state['settings'], LOCAL)
        except (OSError, ValueError, KeyError, struct.error) as error:
            problem = f'无法准备已应用的动画或背景：{error}'
    if problem:
        source = find_source()
        executable = source / BINARY
        if not executable.is_file():
            raise ValueError(f'{problem}；找不到原版 Codex，请从开始菜单打开原版')
        if sys.stderr:
            print(f'{problem}；打开原版应用。', file=sys.stderr, flush=True)
        command = [str(executable), *arguments]
        if windows_package.launch_in_package(source, command):
            return
        return subprocess.Popen(command, cwd=source)
    command = [sys.executable, str(Path(__file__).with_name('manage.py').resolve()), 'launch', *arguments]
    if windows_package.launch_in_package(SOURCE, command):
        return
    return windows_inject.run(SOURCE, state['settings'], LOCAL, arguments=arguments, prepared_script=script)


def status():
    print(f'状态：{runtime_problem(read_state()) or "原版应用增强启动器可用"}')
    versions = '、'.join(f'{version} / build {build}' for version, build in SUPPORTED_BUILDS)
    print(f'目标：Windows x64 Codex {versions}\n原版：{SOURCE}\n启动器：{DESKTOP}\n不创建第二份应用或独立账户目录。')
