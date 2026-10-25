"""本地动画设置与已导入的视频索引。"""
import json
import math
import os
from pathlib import Path
import re
import tempfile

if __package__:
    from . import background
    from .paths import ROOT, LOCAL
else:
    import background
    from paths import ROOT, LOCAL

SETTINGS = LOCAL / 'animation.json'
MEDIA = LOCAL / 'media'
# WebM 的帧边界和 Opus 编码延迟可在 30 秒原片后增加少量封装时长。
MAX_ENCODED_DURATION = 30.05
DEFAULT_SETTINGS = {
    'video': 'default', 'speed': 1.0, 'brightness': 1.0,
    'contrast': 1.0, 'saturation': 1.0, 'fit': 'cover',
    'windowMode': 'restore', 'muted': True,
    'background': background.DEFAULT_SETTINGS.copy(),
}


def video_path(video_id):
    if video_id == 'default':
        return ROOT / 'assets/default.webm'
    if not isinstance(video_id, str) or re.fullmatch('[0-9a-f]{64}', video_id) is None:
        raise ValueError('视频标识无效')
    return MEDIA / f'{video_id}.webm'


def validate_settings(data):
    if not isinstance(data, dict) or data.keys() - DEFAULT_SETTINGS.keys():
        raise ValueError('动画设置必须是对象，且不能包含未知字段')
    settings = DEFAULT_SETTINGS | data
    settings['background'] = background.validate_settings(settings['background'])
    video_path(settings['video'])
    for name, minimum, maximum in (
        ('speed', 0.5, 2), ('brightness', 0.25, 2),
        ('contrast', 0.5, 2), ('saturation', 0, 2),
    ):
        value = settings[name]
        if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
            raise ValueError(f'{name} 必须是 {minimum} 到 {maximum} 之间的有限数值')
    if settings['fit'] not in ('cover', 'contain'):
        raise ValueError('画面适配只能是 cover 或 contain')
    if settings['windowMode'] not in ('restore', 'fullscreen', 'centered'):
        raise ValueError('启动窗口只能是 restore、fullscreen 或 centered')
    if not isinstance(settings['muted'], bool):
        raise ValueError('静音设置必须是布尔值')
    return settings


def video_info(video_id):
    path = video_path(video_id)
    if not path.is_file():
        raise ValueError('找不到视频文件，请重新导入或选择默认视频')
    if video_id == 'default':
        return {'id': 'default', 'name': 'default', 'duration': 10.039, 'width': 1920, 'height': 1080}
    try:
        info = json.loads((MEDIA / f'{video_id}.json').read_text())
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError('视频信息缺失或损坏，请重新导入') from error
    if not isinstance(info, dict) or info.get('id') != video_id or not isinstance(info.get('name'), str):
        raise ValueError('视频信息无效')
    duration = info.get('duration')
    if type(duration) not in (int, float) or not 0 < duration <= MAX_ENCODED_DURATION or not math.isfinite(duration):
        raise ValueError('视频时长必须大于 0 且不超过 30 秒')
    if any(type(info.get(key)) is not int or info[key] <= 0 for key in ('width', 'height')):
        raise ValueError('视频尺寸必须是正整数')
    return {key: info[key] for key in ('id', 'name', 'duration', 'width', 'height')}


def load_settings():
    try:
        data = json.loads(SETTINGS.read_text())
    except FileNotFoundError:
        return validate_settings({})
    except json.JSONDecodeError as error:
        raise ValueError('动画设置损坏，请恢复默认设置') from error
    return validate_settings(data)


def save_settings(data):
    settings = validate_settings(data)
    video_info(settings['video'])
    background.load_selected(settings['background'], LOCAL)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix='.animation.', dir=SETTINGS.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            json.dump(settings, output, ensure_ascii=False, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, SETTINGS)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return settings
