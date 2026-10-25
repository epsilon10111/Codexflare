"""源码资源与用户可写数据的位置。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def data_home():
    path = Path(os.environ.get('XDG_DATA_HOME', ''))
    return path if path.is_absolute() else Path.home() / '.local/share'


def local_dir(root):
    if root == Path('/usr/share/codexflare') or (root / '.packaged').is_file():
        return data_home() / 'codexflare'
    return root / '.local'


LOCAL = local_dir(ROOT)
