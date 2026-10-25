from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import animation

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
                    '0000000b49444154789c63f80f040009fb03fdfb5e6b2b0000000049454e44ae426082')


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
        self.patches.enter_context(patch.object(animation.background, 'ROOT', self.root))
        (self.root / 'assets').mkdir()
        (self.root / 'assets/default.webm').write_bytes(b'default video')
        for name in ('default1.png', 'default2.png'):
            (self.root / 'assets' / name).write_bytes(PNG)

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
        settings['background']['opacity'] = 0.5
        self.assertEqual(animation.DEFAULT_SETTINGS['speed'], 1)
        self.assertEqual(animation.DEFAULT_SETTINGS['background']['opacity'], 0.18)
        self.assertEqual(animation.video_info('default')['duration'], 10.039)
        self.assertEqual(animation.video_path('default'), self.root / 'assets/default.webm')

    def test_default_background_and_legacy_images_remain_available(self):
        background = animation.background
        self.assertEqual(background.DEFAULT_SETTINGS['image'], 'default')
        for image_id, filename in (('default', 'default1.png'), ('default2', 'default2.png')):
            self.assertEqual(background.image_path(image_id, animation.LOCAL), self.root / 'assets' / filename)
            self.assertEqual(background.read_image(image_id, animation.LOCAL)[0], PNG)
            self.assertEqual(background.image_info(image_id, animation.LOCAL), {
                'id': image_id, 'name': filename, 'width': 1, 'height': 1,
            })
        self.assertEqual(background.load_selected({'image': 'legacy'}, animation.LOCAL), (None, None))
        animation.LOCAL.mkdir()
        (animation.LOCAL / 'background.png').write_bytes(PNG)
        saved = animation.save_settings({'background': {'image': 'legacy'}})
        self.assertEqual(saved['background']['image'], 'legacy')
        self.assertEqual(background.read_image('legacy', animation.LOCAL)[0], PNG)
        self.assertEqual(background.image_info('legacy', animation.LOCAL)['name'], '现有背景.png')
        saved = animation.save_settings({'background': {'image': 'default2'}})
        self.assertEqual(animation.load_settings(), saved)
        (self.root / 'assets/default1.png').unlink()
        with self.assertRaises(ValueError):
            background.load_selected({}, animation.LOCAL)
        self.assertEqual(background.load_selected({'image': 'default2'}, animation.LOCAL)[0], PNG)
        self.assertEqual(background.load_selected({'enabled': False}, animation.LOCAL), (None, None))

    def test_background_settings_are_strict_and_legacy_files_remain_compatible(self):
        animation.SETTINGS.parent.mkdir()
        animation.SETTINGS.write_text('{"speed": 0.75}')
        self.assertEqual(animation.load_settings()['background'], animation.background.DEFAULT_SETTINGS)
        for value in (None, [], True, {'unknown': 1}, {'enabled': 1}, {'image': '../private'},
                      {'image': 'A' * 64}, {'image': None}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                animation.validate_settings({'background': value})
        for field, minimum, maximum in (('opacity', 0, 0.5), ('position', 50, 100), ('scale', 40, 140)):
            for value in (True, None, '1', float('nan'), float('inf'), 10 ** 1000, minimum - 1, maximum + 1):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    animation.validate_settings({'background': {field: value}})
            for value in (minimum, maximum):
                self.assertEqual(animation.validate_settings({'background': {field: value}})['background'][field], value)
        saved = animation.save_settings({'background': {'enabled': False, 'image': 'a' * 64}})
        before = animation.SETTINGS.read_bytes()
        with self.assertRaises(ValueError):
            animation.save_settings({'background': {'image': 'a' * 64}})
        self.assertEqual(animation.SETTINGS.read_bytes(), before)
        self.assertEqual(animation.load_settings(), saved)

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

    def test_window_mode_defaults_and_roundtrip(self):
        self.assertEqual(animation.load_settings()['windowMode'], 'restore')
        for mode in ('restore', 'fullscreen', 'centered'):
            saved = animation.save_settings({'windowMode': mode, 'brightness': 1.25})
            self.assertEqual(animation.load_settings(), saved)
            self.assertEqual(saved['windowMode'], mode)
        before = animation.SETTINGS.read_bytes()
        for mode in (None, True, [], {}, 'maximized', 'FULLSCREEN'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                animation.save_settings({'windowMode': mode})
            self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_muted_defaults_and_roundtrip(self):
        self.assertTrue(animation.load_settings()['muted'])
        for muted in (False, True):
            saved = animation.save_settings({'muted': muted})
            self.assertEqual(animation.load_settings(), saved)
            self.assertEqual(saved['muted'], muted)
        before = animation.SETTINGS.read_bytes()
        for muted in (None, 0, 1, 'false', [], {}):
            with self.subTest(muted=muted), self.assertRaises(ValueError):
                animation.save_settings({'muted': muted})
            self.assertEqual(animation.SETTINGS.read_bytes(), before)

    def test_custom_video_roundtrip_and_missing_file_preserves_settings(self):
        video_id, info = self.add_video()
        settings = animation.save_settings({'video': video_id, 'speed': 0.75, 'brightness': 1.25})
        self.assertEqual(animation.load_settings(), settings)
        self.assertEqual(animation.video_info(video_id), info)
        if sys.platform != 'win32':
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
                         {'duration': 0}, {'duration': 30.06}, {'duration': float('nan')},
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
