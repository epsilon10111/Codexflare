"""Reversible Windows copy and separate Start Menu entry; never edits the MSIX app."""
import base64
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
    from .manage import atomic_write, digest
    from .patch_app import Asar, patch_archive
    from .patch_windows import VERSION, BUILD, require_supported
    from .paths import LOCAL
else:
    from manage import atomic_write, digest
    from patch_app import Asar, patch_archive
    from patch_windows import VERSION, BUILD, require_supported
    from paths import LOCAL


def powershell(script, **values):
    # Values travel as environment variables, never interpolated PowerShell source.
    script = ("$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new(); try { "
              + script + " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }")
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    try:
        return subprocess.check_output(
            ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
            env={**os.environ, **{key: str(value) for key, value in values.items()}},
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), stderr=subprocess.PIPE,
            encoding='utf-8', timeout=30).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError(f'Windows shell 操作失败：{error.stderr.strip()}') from error


def find_source():
    override = os.environ.get('CODEXFLARE_SOURCE_APP')
    if override:
        path = Path(override).expanduser().absolute()
        return path / 'app' if (path / 'app/resources/app.asar').is_file() else path
    if sys.platform == 'win32':
        location = powershell("Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | "
                              "Select-Object -First 1 -ExpandProperty InstallLocation")
        if location:
            return Path(location) / 'app'
    return Path.home() / 'AppData/Local/Programs/Codex'


SOURCE = find_source()
RUNTIME = LOCAL / 'runtime-windows'
STATE = LOCAL / 'install-windows.json'
DESKTOP = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming')) / 'Microsoft/Windows/Start Menu/Programs/Codex (Codexflare).lnk'
ASAR = Path('resources/app.asar')
BINARY = 'ChatGPT.exe'
LAUNCH_HINT = '请从开始菜单 Codex (Codexflare) 启动；原版 Codex 入口保持不变。'


def fingerprint():
    package = json.loads(Asar(SOURCE / ASAR).read('package.json'))
    if package.get('name') != 'openai-codex-electron':
        raise ValueError('来源不是 Codex 应用')
    require_supported(package)
    result = {'version': package['version'], 'build': package.get('codexBuildNumber'),
              'source': str(SOURCE.resolve())}
    for relative in (ASAR, Path(BINARY), Path('chrome.dll'), Path('owl-shell-runtime.json')):
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


def build_runtime(destination):
    destination = Path(destination)
    if destination.exists() or SOURCE.resolve() in destination.resolve().parents:
        raise ValueError('构建目标已存在或位于原版应用内')
    before = fingerprint()
    runtime = json.loads((SOURCE / 'owl-shell-runtime.json').read_text(encoding='utf-8'))
    if runtime.get('platform') != 'win32' or runtime.get('arch') != 'x64':
        raise ValueError('仅支持 Windows x64 Owl 运行时')
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


def swap_runtime(staged):
    if RUNTIME.is_symlink() or RUNTIME.is_junction():
        raise ValueError('运行副本不能是链接或目录联接')
    previous = staged.parent / 'previous'
    if RUNTIME.exists():
        os.replace(RUNTIME, previous)
    try:
        os.replace(staged, RUNTIME)
    except OSError:
        if previous.exists():
            os.replace(previous, RUNTIME)
        raise
    # shortcut: Windows cannot atomically exchange directories; interruption falls back to the official app.


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
        method(link, 17, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)(link, str(RUNTIME / BINARY), 0)
        method(link, 0, ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            link, guid('0000010b-0000-0000-c000-000000000046'), ctypes.byref(persist))
        method(persist, 6, ctypes.HRESULT, ctypes.c_wchar_p, ctypes.c_int)(persist, str(path), 1)
    finally:
        for pointer in (persist, link):
            if pointer.value:
                method(pointer, 2, ctypes.c_ulong)(pointer)
        ole.CoUninitialize()


def install():
    state, current = read_state(), desktop_snapshot()
    if current is not None and (not state or not state.get('active') or current != state.get('installed_desktop')):
        raise ValueError('启动器已存在或已被其他操作修改；拒绝覆盖')
    require_stopped()
    LOCAL.mkdir(parents=True, exist_ok=True)
    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='windows-build-', dir=LOCAL) as directory:
        staged = Path(directory) / 'runtime'
        before, metadata = build_runtime(staged)
        launcher = Path(directory) / 'launcher.lnk'
        make_launcher(launcher)
        content = launcher.read_bytes()
        require_stopped()
        if desktop_snapshot() != current:
            raise ValueError('构建期间启动器发生变化，拒绝覆盖')
        swap_runtime(staged)
        save_state({'schema': 1, 'platform': 'win32', 'desktop': str(DESKTOP), 'active': True,
                    'source': before, 'patch': metadata, 'installed_desktop': {'sha256': digest(content)}})
        atomic_write(DESKTOP, content)
    print(f'已安装定制副本：{RUNTIME}\n请从开始菜单 Codex (Codexflare) 启动。')


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
    print('已移除 Codexflare 启动器；保留配置、素材和副本，未停止任何进程。')


def runtime_problem(state):
    if not state or not state.get('active'):
        return '尚未安装或已回退'
    if not all((RUNTIME / path).is_file() for path in (ASAR, BINARY, 'chrome.dll')):
        return '定制副本缺失'
    try:
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
        source = find_source()
        executable = source / 'Codex.exe'
        if not executable.is_file():
            raise ValueError(f'{problem}；找不到原版 Codex，请从开始菜单打开原版')
        if sys.stderr:
            print(f'{problem}；打开原版应用。', file=sys.stderr, flush=True)
        return subprocess.Popen([str(executable), *arguments], cwd=source)
    # Keep the customized runtime and its backend separate from the official session.
    env = {**os.environ, 'CODEX_HOME': str(LOCAL / 'codex-home-windows'),
           'CODEX_ELECTRON_USER_DATA_PATH': str(LOCAL / 'profile-windows')}
    return subprocess.Popen([str(RUNTIME / BINARY),
                             '--user-data-dir=' + env['CODEX_ELECTRON_USER_DATA_PATH'], *arguments],
                            cwd=RUNTIME, env=env)


def status():
    print(f'状态：{runtime_problem(read_state()) or "定制副本可用"}')
    print(f'目标：Windows x64 Codex {VERSION} / build {BUILD}\n原版：{SOURCE}\n副本：{RUNTIME}\n启动器：{DESKTOP}')
