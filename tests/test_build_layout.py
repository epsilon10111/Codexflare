import unittest
from tools.build_layout import discover_layout


class Archive:
    def __init__(self, suffix):
        self.directories = {
            '.vite/build': {f'main-{suffix}.js': {}},
            'webview/assets': {f'{role}-{suffix}.{ext}': {} for role, ext in (
                ('rpc', 'js'), ('app-main', 'js'), ('app-initial', 'js'),
                ('app-primary', 'js'), ('app-initial', 'css'), ('app-primary', 'css'))},
        }

    def entry(self, name):
        return {'files': self.directories[name]}

    def read(self, name):
        return b'fixture'


class LayoutTests(unittest.TestCase):
    def test_different_hashes_produce_correct_resource_links(self):
        for suffix in ('linux-old', 'windows-new', 'mac20586', 'mac21828', 'future'):
            main, assets = discover_layout(Archive(suffix))
            self.assertEqual(main, f'.vite/build/main-{suffix}.js')
            self.assertEqual(len(assets), 6)
            self.assertTrue(all(f'-{suffix}.' in name for name in assets))

    def test_missing_or_ambiguous_role_is_rejected(self):
        archive = Archive('current')
        del archive.directories['webview/assets']['rpc-current.js']
        with self.assertRaisesRegex(ValueError, 'rpc.js'):
            discover_layout(archive)
        archive = Archive('current')
        archive.directories['.vite/build']['main-stale.js'] = {}
        with self.assertRaisesRegex(ValueError, 'main.js'):
            discover_layout(archive)

    def test_unpacked_or_symlink_entries_are_not_patch_targets(self):
        for entry in ({'unpacked': True}, {'link': 'elsewhere'}):
            archive = Archive('current')
            archive.directories['.vite/build']['main-current.js'] = entry
            with self.assertRaises(ValueError):
                discover_layout(archive)
