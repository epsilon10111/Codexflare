import copy
import json
import unittest

from tools import native_smoke


class NativeSmokeTests(unittest.TestCase):
    def test_settings_come_from_archive_and_old_build_uses_defaults(self):
        self.assertEqual(native_smoke.archived_settings('(() => {})();'), native_smoke.DEFAULT_SETTINGS)
        self.assertEqual(native_smoke.archived_settings('const settings = /* CODEX_BOOT_SETTINGS */ null;'),
                         native_smoke.DEFAULT_SETTINGS)
        config = native_smoke.DEFAULT_SETTINGS | {'speed': 0.5, 'brightness': 1.25, 'duration': 30}
        settings = native_smoke.archived_settings('  const settings = ' + json.dumps(config) + ';\n')
        self.assertEqual(settings['speed'], 0.5)
        self.assertEqual(settings['brightness'], 1.25)
        self.assertNotIn('duration', settings)
        with self.assertRaises(ValueError):
            native_smoke.archived_settings('const settings = {"speed":true};')

    def test_probe_budget_covers_slowest_long_video_and_short_clips(self):
        timing = native_smoke.probe_timing({'duration': 30, 'speed': 0.5})
        self.assertGreater(timing['timeout'], 60000)
        self.assertGreaterEqual(timing['samples'] * timing['interval'], timing['timeout'])
        short = native_smoke.probe_timing({'duration': 0.5, 'speed': 2})
        self.assertLess(short['interval'], 250)

    def test_samples_verify_custom_size_parameters_and_completed_exit(self):
        animation = native_smoke.DEFAULT_SETTINGS | {
            'speed': 0.5, 'brightness': 1.25, 'contrast': 0.75, 'saturation': 0,
            'fit': 'contain', 'width': 640, 'height': 360, 'duration': 30,
        }
        bounds = {'x': 0, 'y': 0, 'width': 1920, 'height': 1080}
        frame = {'state': 'loading', 'layer': True,
                 'video': {'time': 0.2, 'paused': False, 'error': None, 'width': 640, 'height': 360,
                           'rate': 0.5, 'filter': 'brightness(1.25) contrast(0.75) saturate(0)', 'fit': 'contain'},
                 'native': {'fullscreen': True, 'visible': True, 'bounds': bounds, 'display': bounds},
                 'rect': bounds, 'viewport': bounds, 'rootChildren': 1}
        ended = frame | {'state': 'ended', 'layer': False, 'video': None, 'rect': None}
        samples = [frame, ended]
        playing, completed = native_smoke.validate_samples(samples, animation)
        self.assertEqual((len(playing), len(completed)), (1, 1))
        for field, value in [('width', 1920), ('height', 1080), ('rate', 1),
                             ('filter', 'none'), ('fit', 'cover')]:
            invalid = copy.deepcopy(samples)
            invalid[0]['video'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                native_smoke.validate_samples(invalid, animation)
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples([frame], animation)


if __name__ == '__main__':
    unittest.main()
