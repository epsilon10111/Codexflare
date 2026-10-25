import copy
import json
import unittest

from tools import native_smoke


class NativeSmokeTests(unittest.TestCase):
    def test_settings_come_from_archive_and_old_build_uses_defaults(self):
        self.assertEqual(native_smoke.archived_settings('(() => {})();'), native_smoke.DEFAULT_SETTINGS)
        self.assertEqual(native_smoke.archived_settings('const settings = /* CODEX_BOOT_SETTINGS */ null;'),
                         native_smoke.DEFAULT_SETTINGS)
        config = native_smoke.DEFAULT_SETTINGS | {'speed': 0.5, 'brightness': 1.25, 'muted': False, 'duration': 30}
        settings = native_smoke.archived_settings('  const settings = ' + json.dumps(config) + ';\n')
        self.assertEqual(settings['speed'], 0.5)
        self.assertEqual(settings['brightness'], 1.25)
        self.assertFalse(settings['muted'])
        self.assertNotIn('duration', settings)
        with self.assertRaises(ValueError):
            native_smoke.archived_settings('const settings = {"speed":true};')

    def test_probe_budget_covers_slowest_long_video_and_short_clips(self):
        timing = native_smoke.probe_timing({'duration': 30, 'speed': 0.5})
        self.assertGreater(timing['timeout'], 80000)
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
                 'backgroundRequired': False, 'backgroundState': 'none',
                 'rendererInitialized': True, 'startupPending': True, 'appInteractive': False,
                 'video': {'time': 0.2, 'paused': False, 'muted': True, 'error': None, 'width': 640, 'height': 360,
                           'rate': 0.5, 'filter': 'brightness(1.25) contrast(0.75) saturate(0)', 'fit': 'contain'},
                 'native': {'fullscreen': False, 'visible': True, 'maximized': False,
                            'bounds': bounds, 'display': bounds, 'workArea': bounds},
                 'rect': bounds, 'viewport': bounds, 'rootChildren': 1}
        ended = frame | {'state': 'ended', 'layer': False, 'video': None, 'rect': None,
                         'startupPending': False, 'appInteractive': True}
        samples = [frame, ended]
        playing, completed = native_smoke.validate_samples(samples, animation)
        self.assertEqual((len(playing), len(completed)), (1, 1))
        for field, value in [('width', 1920), ('height', 1080), ('rate', 1), ('muted', False),
                             ('filter', 'none'), ('fit', 'cover')]:
            invalid = copy.deepcopy(samples)
            invalid[0]['video'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                native_smoke.validate_samples(invalid, animation)
        audible = copy.deepcopy(samples)
        audible[0]['video']['muted'] = False
        native_smoke.validate_samples(audible, animation | {'muted': False})
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples([frame], animation)
        invalid = copy.deepcopy(samples)
        invalid[0]['native']['fullscreen'] = True
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples(invalid, animation)
        full = copy.deepcopy(samples)
        for sample in full:
            sample['native']['fullscreen'] = True
        native_smoke.validate_samples(full, animation | {'windowMode': 'fullscreen'})
        full[0]['native']['bounds'] = bounds | {'width': 1280}
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples(full, animation | {'windowMode': 'fullscreen'})
        centered = copy.deepcopy(samples)
        for sample in centered:
            sample['native']['bounds'] = {'x': 410, 'y': 160, 'width': 1100, 'height': 760}
        native_smoke.validate_samples(centered, animation | {'windowMode': 'centered'})
        centered[0]['native']['bounds']['x'] = 0
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples(centered, animation | {'windowMode': 'centered'})
        native_smoke.validate_samples(samples, animation, bounds)
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples(samples, animation, bounds | {'width': 980})
        for field, value in [('startupPending', True), ('appInteractive', False), ('state', 'app-timeout')]:
            invalid = copy.deepcopy(samples)
            invalid[-1][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                native_smoke.validate_samples(invalid, animation)
        invalid = copy.deepcopy(samples)
        invalid[0]['rendererInitialized'] = False
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples(invalid, animation)
        with_background = copy.deepcopy(samples)
        for sample in with_background:
            sample['backgroundRequired'] = True
        with_background[0]['backgroundState'] = 'decoded'
        with_background[-1]['backgroundState'] = 'ready'
        native_smoke.validate_samples(with_background, animation)
        waiting = copy.deepcopy(with_background[-1])
        waiting.update(state='waiting-app', layer=True, backgroundState='decoded')
        with_background[0]['backgroundState'] = 'loading'
        native_smoke.validate_samples([with_background[0], waiting, with_background[-1]], animation)
        with_background[0]['backgroundState'] = 'none'
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples([with_background[0], waiting, with_background[-1]], animation)
        with_background[0]['backgroundState'] = 'loading'
        with_background[-1]['backgroundState'] = 'loading'
        with self.assertRaises(AssertionError):
            native_smoke.validate_samples(with_background, animation)


if __name__ == '__main__':
    unittest.main()
