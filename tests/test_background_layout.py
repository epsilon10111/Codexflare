import unittest
from tools.background_layout import BackgroundLayout, loading_class


class Styles:
    def __init__(self, suffix='new_2', modern=True):
        self.data = {
            'app-shared-new.css': ':root{--color-surface:black}',
            'app-initial-new.css': f'._ComposerLayoutRoot_{suffix}{{}}._delayedBlossom_{suffix}{{}}',
            'moved-workspace-new.css': ''.join('._'+role+'_'+suffix+'{}' for role in
                ('WorkspaceContent', 'MainContentSurface', 'MainContentViewport', 'compactScrollMask')),
        }
        self.data['app-initial-new.css'] += (''.join('._'+role+'_'+suffix+'{}' for role in
            ('background', 'fade', 'surface')) if modern else '.bg-gradient-to-t{}.from-surface{}')

    def entry(self, name):
        return {'files': {name: {} for name in self.data}}

    def read(self, name):
        return self.data[name.removeprefix('webview/assets/')].encode()


class BackgroundLayoutTests(unittest.TestCase):
    def test_renamed_classes_and_moved_chunks_are_resolved(self):
        for suffix in ('etoz9_2', 'azz1c_2', 'future_14'):
            archive = Styles(suffix)
            layout = BackgroundLayout(archive)
            text = layout.adapt('._WorkspaceContent_yl8z4_2::before{} ._ComposerLayoutRoot_15oep_2{} '
                                '.bg-gradient-to-t.from-surface{}')
            self.assertIn('._WorkspaceContent_'+suffix+'::before', text)
            self.assertIn('._ComposerLayoutRoot_'+suffix, text)
            self.assertIn('._background_'+suffix+'._fade_'+suffix, text)
            self.assertIn('moved-workspace-new.css', layout.styles)
            self.assertEqual(loading_class(archive), '_delayedBlossom_'+suffix)

    def test_legacy_footer_is_retained(self):
        layout = BackgroundLayout(Styles(modern=False))
        self.assertIsNone(layout.footer)
        self.assertEqual(layout.adapt('.bg-gradient-to-t.from-surface'), '.bg-gradient-to-t.from-surface')

    def test_missing_or_ambiguous_roles_fail(self):
        archive = Styles()
        archive.data['other.css'] = '._WorkspaceContent_other_2{}'
        with self.assertRaisesRegex(ValueError, 'WorkspaceContent'):
            BackgroundLayout(archive)
        del archive.data['other.css']
        del archive.data['moved-workspace-new.css']
        with self.assertRaisesRegex(ValueError, 'WorkspaceContent'):
            BackgroundLayout(archive)

    def test_unrelated_background_modules_are_ignored_and_ambiguous_footers_fail(self):
        archive = Styles()
        archive.data['modal.css'] = '._background_modal_2{}._surface_modal_2{}'
        self.assertEqual(BackgroundLayout(archive).footer, '_new_2')
        archive.data['modal.css'] += '._fade_modal_2{}'
        with self.assertRaisesRegex(ValueError, 'FooterFade'):
            BackgroundLayout(archive)
