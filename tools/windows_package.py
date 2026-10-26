"""Run the existing launcher with the identity of its registered Windows package."""
import base64
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys


RESTART_MARKER = 'CODEXFLARE_PACKAGE_RESTART'
PATH_ENVIRONMENT = ('CODEX_HOME', 'CODEX_ELECTRON_USER_DATA_PATH', 'CODEXFLARE_SOURCE_APP', 'XDG_DATA_HOME')


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


def current_package_full_name():
    if sys.platform != 'win32':
        raise ValueError('Windows 包上下文仅支持 Windows')
    api = ctypes.WinDLL('kernel32').GetCurrentPackageFullName
    api.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
    api.restype = ctypes.c_long
    length = ctypes.c_uint32()
    result = api(ctypes.byref(length), None)
    if result == 15700:  # APPMODEL_ERROR_NO_PACKAGE
        return None
    if result != 122:
        raise OSError(result, '无法读取当前 Windows 包身份')
    name = ctypes.create_unicode_buffer(length.value)
    result = api(ctypes.byref(length), name)
    if result:
        raise OSError(result, '无法读取当前 Windows 包身份')
    return name.value


def registered_package(source):
    data = powershell(
        "$exe=[IO.Path]::GetFullPath((Join-Path $env:CODEXFLARE_PACKAGE_SOURCE 'ChatGPT.exe')); "
        "$matches=@(Get-AppxPackage -Name OpenAI.Codex | ForEach-Object { "
        "$p=$_; $root=$p.InstallLocation; "
        "if ($root -and [String]::Equals([IO.Path]::GetFullPath((Join-Path $root 'app/ChatGPT.exe')), "
        "$exe,[StringComparison]::OrdinalIgnoreCase)) { "
        "$manifest=Get-AppxPackageManifest -Package $p.PackageFullName; "
        "@($manifest.Package.Applications.Application) | ForEach-Object { "
        "if ($_.Executable -and [String]::Equals([IO.Path]::GetFullPath((Join-Path $root $_.Executable)), "
        "$exe,[StringComparison]::OrdinalIgnoreCase)) { "
        "@{full_name=$p.PackageFullName;family_name=$p.PackageFamilyName;app_id=$_.Id} } } } }); "
        "if ($matches.Count -ne 1) { throw '来源不是唯一匹配的已注册标准版 Windows 包' }; "
        "$matches[0] | ConvertTo-Json -Compress",
        CODEXFLARE_PACKAGE_SOURCE=str(Path(source).resolve()))
    package = json.loads(data)
    if not isinstance(package, dict) or any(not isinstance(package.get(key), str) or not package[key]
                                          for key in ('full_name', 'family_name', 'app_id')):
        raise ValueError('无法验证来源的 Windows 包注册信息')
    return package


def launch_in_package(source, command):
    """Return True after dispatch, or False when already in the correct package."""
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or '\0' in arg for arg in command):
        raise ValueError('无效的 Windows 包启动命令')
    package = registered_package(source)
    if current_package_full_name() == package['full_name']:
        return False
    if os.environ.get(RESTART_MARKER):
        raise ValueError('启动器未能保留原版 Windows 包身份；已停止，未以无身份模式启动')
    # Package activation does not inherit custom environment variables. Pass only data paths.
    payload = {'package': package['full_name'], 'command': command,
               'environment': {key: os.environ[key] for key in PATH_ENVIRONMENT if key in os.environ}}
    payload['environment']['CODEXFLARE_SOURCE_APP'] = str(Path(source).resolve())
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode('ascii')
    arguments = subprocess.list2cmdline([str(Path(__file__).resolve()), encoded])
    python = Path(sys.executable)
    if python.with_name('pythonw.exe').is_file():
        python = python.with_name('pythonw.exe')
    powershell(
        "$p=$env:CODEXFLARE_PACKAGE_REQUEST | ConvertFrom-Json; "
        "Invoke-CommandInDesktopPackage -PackageFamilyName $p.family_name -AppId $p.app_id "
        "-Command $env:CODEXFLARE_PACKAGE_PYTHON -Args $env:CODEXFLARE_PACKAGE_ARGUMENTS -PreventBreakaway",
        CODEXFLARE_PACKAGE_REQUEST=json.dumps(package), CODEXFLARE_PACKAGE_PYTHON=python,
        CODEXFLARE_PACKAGE_ARGUMENTS=arguments)
    return True


def run_command(payload):
    expected = payload['package']
    if not isinstance(expected, str) or not expected or current_package_full_name() != expected:
        raise ValueError('包上下文启动未获得原版身份；已停止，未启动应用')
    command, environment = payload['command'], payload['environment']
    if (not isinstance(command, list) or not command or
            any(not isinstance(arg, str) or '\0' in arg for arg in command) or
            not isinstance(environment, dict) or
            any(key not in PATH_ENVIRONMENT or not isinstance(value, str) or '\0' in value
                for key, value in environment.items())):
        raise ValueError('无效的包上下文启动参数')
    return subprocess.call(command, env={**os.environ, **environment, RESTART_MARKER: expected},
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


if __name__ == '__main__':
    try:
        result = run_command(json.loads(base64.b64decode(sys.argv[1], validate=True)))
    except (OSError, ValueError, KeyError, IndexError, TypeError, subprocess.SubprocessError) as error:
        if sys.stderr is None:
            ctypes.windll.user32.MessageBoxW(None, str(error), 'Codexflare', 0x10)
        else:
            print(f'错误：{error}', file=sys.stderr)
        sys.exit(1)
    sys.exit(result)
