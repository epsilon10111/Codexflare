#!/usr/bin/env python3
"""供 Agent 使用的本地配置接口；默认预览，--save 才保存，不应用补丁。"""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

if __package__:
    from . import animation, background, editor
else:
    import animation
    import background
    import editor


def update_settings(patch, save=False):
    animation.validate_settings(patch)
    with animation.edit_lock() if save else nullcontext():
        before = animation.load_settings()
        settings = before | patch
        settings['background'] = before['background'] | patch.get('background', {})
        settings = animation.validate_settings(settings)
        animation.video_info(settings['video'])
        background.load_selected(settings['background'], animation.LOCAL)
        changes = {}
        for key, value in settings.items():
            if key == 'background':
                for field, item in value.items():
                    if before[key][field] != item:
                        changes[f'background.{field}'] = {'before': before[key][field], 'after': item}
            elif before[key] != value:
                changes[key] = {'before': before[key], 'after': value}
        if save:
            animation.save_settings(settings)
        return {'saved': save, 'applied': False, 'changes': changes, 'settings': settings}


def import_media(kind, source):
    source = source.expanduser().resolve(strict=True)
    limit = background.MAX_UPLOAD if kind == 'background' else editor.MAX_UPLOAD
    if not source.is_file() or not 0 < source.stat().st_size <= limit:
        raise ValueError(f'素材必须是非空普通文件，大小不超过 {limit // (1024 * 1024)} MiB')
    with animation.edit_lock():
        if kind == 'background':
            with source.open('rb') as stream:
                media = editor.import_image(stream.read(limit + 1), source.name)
        else:
            media = editor.import_video(source, source.name)
    # HTTP 预览地址只在编辑器服务内有效。
    return {'media': {key: value for key, value in media.items() if key != 'url'},
            'selected': False, 'applied': False}


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('show', help='读取当前设置，不修改文件')
    commands.add_parser('check', help='检查依赖和可应用状态；不可应用时返回 2')
    change = commands.add_parser('set', help='预览 JSON 文件里的局部修改')
    change.add_argument('patch', type=Path, help='UTF-8 JSON 文件；只填写要修改的字段')
    change.add_argument('--save', action='store_true', help='保存修改；仍需单独应用到 Codex')
    for name in ('video', 'background'):
        command = commands.add_parser(f'import-{name}', help=f'导入本地 {name}，不自动选中')
        command.add_argument('path', type=Path)
    args = parser.parse_args(arguments)
    status = 0
    try:
        if args.command == 'show':
            result = {'settings': animation.load_settings(), 'settings_file': str(animation.SETTINGS)}
        elif args.command == 'check':
            installation = editor.installation_status()
            result = {'platform': sys.platform, 'python': sys.version.split()[0],
                      'reference_codex_version': editor.manage.VERSION,
                      'compatibility_policy': 'structural',
                      'installation': installation,
                      'ffmpeg': bool(shutil.which('ffmpeg')), 'ffprobe': bool(shutil.which('ffprobe')),
                      'settings_file': str(animation.SETTINGS)}
            status = 0 if installation['available'] else 2
        elif args.command == 'set':
            with args.patch.open('rb') as stream:
                raw = stream.read(4097)
            if len(raw) > 4096:
                raise ValueError('配置修改文件不能超过 4 KiB')
            result = update_settings(json.loads(raw.decode('utf-8')), args.save)
        else:
            result = import_media(args.command.removeprefix('import-'), args.path)
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return status


if __name__ == '__main__':
    sys.exit(main())
