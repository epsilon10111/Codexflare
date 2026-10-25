from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import animation


class AnimationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        for name, value in {
            'ROOT': self.root, 'LOCAL': self.root / '.local',
            'SETTINGS': self.root / '.local/animation.json', 'MEDIA': self.root / '.local/media',
        }.items():
            self.patches.enter_context(patch.object(animation, name, value))
        (self.root / 'assets').mkdir()
        (self.root / 'assets/boot.webm').write_bytes(b'default video')

    def add_video(self, **changes):
        video_id = 'a' * 64
        animation.MEDIA.mkdir(parents=True, exist_ok=True)
        (animation.MEDIA / f'{video_id}.webm').write_bytes(b'imported video')
        info = {'id': video_id, 'name': '我的视频.webm', 'duration': 12.5, 'width': 1280, 'height': 720}
        info.update(changes)
        (animation.MEDIA / f'{video_id}.json').write_text(json.dumps(info))
        return video_id, info

    def test_default_and_partial_settings_do_not_mutate_defaults(self):
        self.assertEqual(animation.load_settings(), animation.DEFAULT_SETTINGS)
        settings = animation.validate_settings({'speed': 0.5, 'saturation': 0, 'fit': 'contain'})
        self.assertEqual(settings['brightness'], 1)
        self.assertEqual(settings['speed'], 0.5)
        settings['speed'] = 2
        self.assertEqual(animation.DEFAULT_SETTINGS['speed'], 1)
        self.assertEqual(animation.video_info('default')['duration'], 4)

    def test_rejects_invalid_settings(self):
        for value in [None, [], 'settings', {'unknown': 1}, {'video': '../outside'},
                      {'video': 'A' * 64}, {'video': True}, {'fit': 'stretch'}, {'fit': []}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                animation.validate_settings(value)
        for field, minimum, maximum in [('speed', 0.5, 2), ('brightness', 0.25, 2),
                                         ('contrast', 0.5, 2), ('saturation', 0, 2)]:
            for value in [True, False, None, '1', float('nan'), float('inf'),
                          -float('inf'), minimum - 0.01, maximum + 0.01, 10 ** 1000]:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    animation.validate_settings({field: value})
            for value in (minimum, maximum):
                self.assertEqual(animation.validate_settings({field: value})[field], value)

    def test_custom_video_roundtrip_and_missing_file_preserves_settings(self):
        video_id, info = self.add_video()
        settings = animation.save_settings({'video': video_id, 'speed': 0.75, 'brightness': 1.25})
        self.assertEqual(animation.load_settings(), settings)
        self.assertEqual(animation.video_info(video_id), info)
        self.assertEqual(animation.SETTINGS.stat().st_mode & 0o777, 0o600)
        self.assertEqual(animation.SETTINGS.parent.stat().st_mode & 0o777, 0o700)
        before = animation.SETTINGS.read_bytes()
        animation.video_path(video_id).unlink()
        with self.assertRaises(ValueError):
            animation.save_settings({'video': video_id})
        self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_atomic_write_failure_preserves_previous_file(self):
        animation.save_settings({})
        before = animation.SETTINGS.read_bytes()
        with patch.object(animation.os, 'replace', side_effect=OSError('模拟写入失败')):
            with self.assertRaises(OSError):
                animation.save_settings({'speed': 2})
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        self.assertEqual(list(animation.SETTINGS.parent.glob('.animation.*')), [])

    def test_corrupt_settings_fail_without_overwriting(self):
        animation.SETTINGS.parent.mkdir()
        for content in ('{broken', '[]', '{"speed": NaN}', '{"extra": 1}'):
            animation.SETTINGS.write_text(content)
            with self.subTest(content=content), self.assertRaises(ValueError):
                animation.load_settings()
            self.assertEqual(animation.SETTINGS.read_text(), content)

    def test_rejects_invalid_video_metadata(self):
        for changes in [ {'id': 'b' * 64}, {'name': None}, {'duration': True},
                         {'duration': 0}, {'duration': 30.01}, {'duration': float('nan')},
                         {'duration': float('inf')}, {'duration': 10 ** 1000},
                         {'width': False}, {'width': 0}, {'height': 720.5}]:
            video_id, _ = self.add_video(**changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                animation.video_info(video_id)
        video_id, _ = self.add_video()
        metadata = animation.MEDIA / f'{video_id}.json'
        metadata.write_text('{broken')
        with self.assertRaises(ValueError):
            animation.video_info(video_id)
        metadata.unlink()
        with self.assertRaises(ValueError):
            animation.video_info(video_id)


if __name__ == '__main__':
    unittest.main()
