"""Discover reviewed bundle roles without depending on generated filename hashes."""
import json
from pathlib import PurePosixPath
import re


def files(archive, directory):
    try:
        entries = archive.entry(directory)['files']
    except KeyError as error:
        raise ValueError(f'缺少应用资源目录: {directory}') from error
    return [name for name, entry in entries.items()
            if 'files' not in entry and not entry.get('unpacked') and 'link' not in entry]


def unique_asset(archive, directory, role, extension):
    matches = [name for name in files(archive, directory)
               if re.fullmatch(re.escape(role) + r'-[\w-]+\.' + extension, name)]
    if len(matches) != 1:
        raise ValueError(f'应用资源角色必须唯一: {role}.{extension} (找到 {len(matches)})')
    name = matches[0]
    if not archive.read(f'{directory}/{name}'):
        raise ValueError(f'应用资源为空: {name}')
    return name


def discover_layout(archive):
    main = '.vite/build/' + unique_asset(archive, '.vite/build', 'main', 'js')
    preloads = tuple(unique_asset(archive, 'webview/assets', role, extension)
                     for role, extension in (('rpc', 'js'), ('app-main', 'js'),
                         ('app-initial', 'js'), ('app-primary', 'js'),
                         ('app-initial', 'css'), ('app-primary', 'css')))
    return main, preloads


def entrypoint(archive):
    package = json.loads(archive.read('package.json'))
    name = package.get('main')
    if not isinstance(name, str) or not name:
        raise ValueError('应用缺少 main 入口')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not archive.read(str(path)):
        raise ValueError('无效的应用入口')
    return str(path)
