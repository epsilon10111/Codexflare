"""Native validation reference metadata; installation discovers structure independently."""
BUILDS = {
    '26.1013.31256': {
        'version': '26.1013.31256', 'build': '20586',
        'main': '.vite/build/main-CLu1A25j.js',
        'preloads': (
            'rpc-44f82a48298e.js', 'app-main-aa050bc301e8.js',
            'app-initial-3ccf4886957f.js', 'app-primary-a33cb51a1875.js',
            'app-initial-e7c27dd40beb.css', 'app-primary-71492d0e9e92.css',
        ),
        'electron': 'D', 'saved_bounds': 'C', 'onboarding': 'YPe', 'equal': 'Fe',
        'protocol': 'Ke.deepLinks.registerProtocolClient()',
        'background_classes': {
            '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_etoz9_2',
            '_MainContentSurface_yl8z4_2': '_MainContentSurface_etoz9_2',
            '_MainContentViewport_yl8z4_2': '_MainContentViewport_etoz9_2',
            '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_5est5_2',
            '_compactScrollMask_121j8_2': '_compactScrollMask_121j8_2',
        },
        'background_styles': ('app-shared-ae384120d279.css', 'app-initial-e7c27dd40beb.css',
                              'thread-scroll-layout-24b9bd243051.css'),
    },
    '26.1021.31345': {
        'version': '26.1021.31345', 'build': '21828',
        'main': '.vite/build/main-0FVbxCQU.js',
        'preloads': (
            'rpc-f4d8744cf30b.js', 'app-main-a7fcc565935a.js',
            'app-initial-feb30b196d11.js', 'app-primary-7d7313419f84.js',
            'app-initial-56db6e0bcb8b.css', 'app-primary-5fa64a4ee99d.css',
        ),
        'electron': 'O', 'saved_bounds': 'S', 'onboarding': 'A5e', 'equal': 'q',
        'protocol': 'We.deepLinks.registerProtocolClient()',
        'background_classes': {
            '_WorkspaceContent_yl8z4_2': '_WorkspaceContent_azz1c_2',
            '_MainContentSurface_yl8z4_2': '_MainContentSurface_azz1c_2',
            '_MainContentViewport_yl8z4_2': '_MainContentViewport_azz1c_2',
            '_ComposerLayoutRoot_15oep_2': '_ComposerLayoutRoot_1q7o3_2',
            '_compactScrollMask_121j8_2': '_compactScrollMask_mpt93_2',
        },
        'background_styles': ('app-shared-bd3e4e649b69.css', 'app-initial-56db6e0bcb8b.css',
                              'app-primary-5fa64a4ee99d.css'),
    },
}
# Reference fixtures retain the original release default; these values do not gate installation.
VERSION = '26.1013.31256'
BUILD = BUILDS[VERSION]['build']
MAIN = BUILDS[VERSION]['main']
STARTUP_PRELOADS = BUILDS[VERSION]['preloads']
BACKGROUND_CLASSES = BUILDS[VERSION]['background_classes']
BACKGROUND_STYLES = BUILDS[VERSION]['background_styles']
SUPPORTED = '、'.join(f"{item['version']} / build {item['build']}" for item in BUILDS.values())


def select_build(version, build=None):
    selected = BUILDS.get(version) if isinstance(version, str) else None
    if selected is None or (build is not None and str(build) != selected['build']):
        raise ValueError(f'仅支持 macOS Codex {SUPPORTED}；当前 {version} / {build}')
    return selected


def patch_main(text, window_mode='restore', muted=True, *, preserve_identity=False, version=VERSION):
    if __package__:
        from .window_patch import patch_main as patch_window
    else:
        from window_patch import patch_main as patch_window
    return patch_window(text, window_mode, muted, protocol=True, preserve_identity=preserve_identity)
