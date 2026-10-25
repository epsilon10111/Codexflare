"""源码资源与用户可写数据的位置。"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def command_for(script, *arguments):
    """Invoke a tool through Python or the packaged application's CLI dispatcher."""
    if getattr(sys, 'frozen', False):
        option = {'original_macos': '--original', 'manage': '--manage'}[script]
        return [sys.executable, option, *arguments]
    return [sys.executable, str(ROOT / 'tools' / (script + '.py')), *arguments]


def data_home():
    path = Path(os.environ.get('XDG_DATA_HOME', ''))
    return path if path.is_absolute() else Path.home() / '.local/share'


def local_dir(root):
    if root == Path('/usr/share/codexflare') or (root / '.packaged').is_file():
        return data_home() / 'codexflare'
    return root / '.local'


LOCAL = local_dir(ROOT)
