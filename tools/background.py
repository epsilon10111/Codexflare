"""本地 PNG 背景的设置、文件索引与边界验证。"""
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
MAX_UPLOAD = 40 * 1024 * 1024
DEFAULT_SETTINGS = {'enabled': True, 'image': 'default', 'opacity': 0.18, 'position': 80, 'scale': 70}


def image_path(image_id, local):
    if image_id in ('default', 'default2'):
        return ROOT / 'assets' / ('default1.png' if image_id == 'default' else 'default2.png')
    if image_id == 'legacy':
        return local / 'background.png'
    if not isinstance(image_id, str) or re.fullmatch('[0-9a-f]{64}', image_id) is None:
        raise ValueError('背景图片标识无效')
    return local / 'backgrounds' / f'{image_id}.png'


def validate_settings(data):
    if not isinstance(data, dict) or data.keys() - DEFAULT_SETTINGS.keys():
        raise ValueError('背景设置必须是对象，且不能包含未知字段')
    settings = DEFAULT_SETTINGS | data
    if type(settings['enabled']) is not bool:
        raise ValueError('背景开关必须是布尔值')
    image_path(settings['image'], Path('.'))
    for name, minimum, maximum in (('opacity', 0, 0.5), ('position', 50, 100), ('scale', 40, 140)):
        value = settings[name]
        if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
            raise ValueError(f'{name} 必须是 {minimum} 到 {maximum} 之间的有限数值')
    return settings


def validate_png(data):
    if len(data) > MAX_UPLOAD:
        raise ValueError('背景 PNG 不能超过 40 MiB')
    if len(data) < 33 or data[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
        raise ValueError('背景必须是有效的 PNG 图片')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data[16:29])
    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= 64_000_000):
        raise ValueError('背景 PNG 每边不能超过 8192 像素，总计不能超过 6400 万像素')
    if depth not in depths.get(color, ()) or compression or filtering or interlace not in (0, 1):
        raise ValueError('背景 PNG 的 IHDR 无效')
    offset, has_data = 8, False
    while offset + 12 <= len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        end = offset + 12 + size
        kind = data[offset + 4:offset + 8]
        if end > len(data) or zlib.crc32(memoryview(data)[offset + 4:end - 4]) != struct.unpack_from('>I', data, end - 4)[0]:
            raise ValueError('背景 PNG 数据损坏或被截断')
        if kind == b'IHDR' and offset != 8:
            raise ValueError('背景 PNG 包含重复 IHDR')
        has_data |= kind == b'IDAT' and size > 0
        if kind == b'IEND':
            if size or not has_data or end != len(data):
                raise ValueError('背景 PNG 结尾无效')
            return {'width': width, 'height': height, 'size': len(data),
                    'sha256': hashlib.sha256(data).hexdigest()}
        offset = end
    raise ValueError('背景 PNG 缺少完整 IEND')


def read_image(image_id, local):
    path = image_path(image_id, local)
    with path.open('rb') as source:
        data = source.read(MAX_UPLOAD + 1)
    info = validate_png(data)
    if image_id not in ('default', 'default2', 'legacy') and info['sha256'] != image_id:
        raise ValueError('背景图片内容与标识不一致，请重新导入')
    return data, info


def prepare_image(data, info):
    """缩小运行副本中的大图，保留素材原件与透明度。"""
    width, height = info['width'], info['height']
    if width <= 3840 and height <= 2160:
        return data, info
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        # 仅 Python 的安装环境仍能使用原图。
        return data, info
    ratio = min(3840 / width, 2160 / height)
    width, height = max(1, round(width * ratio)), max(1, round(height * ratio))
    try:
        result = subprocess.run([
            ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-xerror',
            '-protocol_whitelist', 'pipe', '-f', 'image2pipe', '-c:v', 'png',
            '-threads', '2', '-i', 'pipe:0', '-map', '0:v:0', '-frames:v', '1',
            '-an', '-sn', '-dn', '-map_metadata', '-1',
            '-vf', f'scale={width}:{height}:flags=lanczos',
            '-c:v', 'png', '-pix_fmt', 'rgba64be' if data[24] == 16 else 'rgba',
            '-threads', '2', '-f', 'image2pipe', 'pipe:1',
        ], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30)
    except subprocess.TimeoutExpired as error:
        raise ValueError('背景预处理超时，请重试') from error
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError('背景预处理失败，请检查 FFmpeg 或重新选择图片') from error
    prepared = validate_png(result.stdout)
    if (prepared['width'], prepared['height']) != (width, height):
        raise ValueError('背景预处理输出尺寸不符')
    return result.stdout, prepared


def load_selected(settings, local):
    settings = validate_settings(settings)
    if not settings['enabled']:
        return None, None
    if settings['image'] == 'legacy' and not image_path('legacy', local).exists():
        return None, None
    try:
        return read_image(settings['image'], local)
    except FileNotFoundError as error:
        raise ValueError('找不到背景图片，请重新导入或关闭背景') from error


def image_info(image_id, local):
    path = image_path(image_id, local)
    if not path.is_file():
        raise ValueError('找不到背景图片，请重新导入')
    if image_id in ('default', 'default2', 'legacy'):
        _, metadata = read_image(image_id, local)
        info = {'id': image_id, 'name': '现有背景.png' if image_id == 'legacy' else path.name, **metadata}
    else:
        try:
            info = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise ValueError('背景图片信息缺失或损坏，请重新导入') from error
        if not isinstance(info, dict) or info.get('id') != image_id or not isinstance(info.get('name'), str):
            raise ValueError('背景图片信息无效')
        if any(type(info.get(key)) is not int or not 0 < info[key] <= 8192 for key in ('width', 'height')):
            raise ValueError('背景图片尺寸无效')
        if info['width'] * info['height'] > 64_000_000:
            raise ValueError('背景图片尺寸过大')
    return {key: info[key] for key in ('id', 'name', 'width', 'height')}
