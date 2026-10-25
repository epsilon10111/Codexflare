"""Exact anchors reviewed against the macOS arm64 26.1021.31345 / 21828 build."""
VERSION = '26.1021.31345'
BUILD = '21828'
MAIN = '.vite/build/main-0FVbxCQU.js'
STARTUP_PRELOADS = (
    'rpc-f4d8744cf30b.js', 'app-main-a7fcc565935a.js',
    'app-initial-feb30b196d11.js', 'app-primary-7d7313419f84.js',
    'app-initial-56db6e0bcb8b.css', 'app-primary-5fa64a4ee99d.css',
)


def patch_main(text, window_mode='restore', muted=True):
    if __package__:
        from .window_patch import patch_main as patch_window
    else:
        from window_patch import patch_main as patch_window
    return patch_window(text, window_mode, muted, protocol=True)

# CSS-module names are build-specific just like the main-process anchors.
BACKGROUND_CLASSES = {
    '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_azz1c_2',
    '_MainContentSurface_yl8z4_2': '_MainContentSurface_azz1c_2',
    '_MainContentViewport_yl8z4_2': '_MainContentViewport_azz1c_2',
    '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_1q7o3_2',
    '_compactScrollMask_121j8_2': '_compactScrollMask_mpt93_2',
}
BACKGROUND_STYLES = ('app-shared-bd3e4e649b69.css', 'app-initial-56db6e0bcb8b.css',
                     'app-primary-5fa64a4ee99d.css')


def adapt_background_classes(text):
    for old, new in BACKGROUND_CLASSES.items():
        text = text.replace(old, new)
    return text.replace('.bg-gradient-to-t.from-surface',
                        '._background_106nk_2._fade_106nk_2.from-surface')


def patch_background_css(text, archive):
    styles = '\n'.join(archive.read('webview/assets/' + name).decode() for name in BACKGROUND_STYLES)
    for current in (*BACKGROUND_CLASSES.values(), '_background_106nk_2', '_fade_106nk_2', '_surface_106nk_2'):
        if '.' + current not in styles:
            raise ValueError(f'Background selector missing from the supported macOS build: {current}')
    return adapt_background_classes(text)


def adapt_background_fixture(text):
    text = adapt_background_classes(text)
    replacements = {
        'pointer-events-none absolute inset-x-0 -top-8 z-0 h-8 bg-gradient-to-t from-surface':
            '_background_106nk_2 _fade_106nk_2 pointer-events-none absolute inset-x-0 z-0 from-surface',
        'pointer-events-none absolute inset-x-0 -top-8 z-0 bottom-0 mt-8 bg-surface':
            '_background_106nk_2 _surface_106nk_2 pointer-events-none absolute inset-x-0 z-0 bottom-0 bg-surface',
    }
    for old, new in replacements.items():
        if text.count(old) != 2:
            raise ValueError('Unexpected footer fixture structure')
        text = text.replace(old, new)
    return text
