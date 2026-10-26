"""Exact Windows x64 Owl builds: MSIX 26.1002.7124.0 and 26.1021.3705.0."""
from types import SimpleNamespace

if __package__:
    from . import patch_macos
    from .patch_app import patch_main as patch_shared_main, replace_once
else:
    import patch_macos
    from patch_app import patch_main as patch_shared_main, replace_once

VERSION = '26.1002.52244'
BUILD = '13536'
MAIN = '.vite/build/main-p91kJShj.js'
STARTUP_PRELOADS = (
    'rpc-c7a57a952402.js', 'app-main-9403f9647881.js',
    'app-initial-25361a10f2bf.js', 'app-primary-2b28b2369958.js',
    'app-initial-c43288484373.css', 'app-primary-c7f956fe5bad.css',
)
CURRENT_VERSION = '26.1021.31345'
CURRENT_BUILD = '21828'
CURRENT_MAIN = '.vite/build/main-BPBEjAxi.js'
CURRENT_STARTUP_PRELOADS = (
    'rpc-5912801b45db.js', 'app-main-f6d324e432da.js',
    'app-initial-438d1df57f70.js', 'app-primary-844e405f2b90.js',
    'app-initial-56db6e0bcb8b.css', 'app-primary-5fa64a4ee99d.css',
)
SUPPORTED_BUILDS = ((VERSION, BUILD), (CURRENT_VERSION, CURRENT_BUILD))


def require_supported(package):
    if ((package.get('name'), package.get('codexWindowsPackageIdentity')) !=
            ('openai-codex-electron', 'OpenAI.Codex') or
            (package.get('version'), package.get('codexBuildNumber')) not in SUPPORTED_BUILDS):
        versions = '、'.join(f'{version} / build {build}' for version, build in SUPPORTED_BUILDS)
        raise ValueError(f'仅支持 Windows Codex {versions} 正式版')


def select_build(package):
    require_supported(package)
    if package['version'] == CURRENT_VERSION:
        # Both build 21828 platforms share the checked window anchors and CSS modules.
        return SimpleNamespace(VERSION=CURRENT_VERSION, MAIN=CURRENT_MAIN,
            STARTUP_PRELOADS=CURRENT_STARTUP_PRELOADS, patch_main=patch_macos.patch_main,
            patch_background_css=patch_macos.patch_background_css)
    return SimpleNamespace(VERSION=VERSION, MAIN=MAIN, STARTUP_PRELOADS=STARTUP_PRELOADS,
        patch_main=patch_main, patch_background_css=None)


def patch_main(text, window_mode='restore', muted=True):
    # This Windows build shares the Linux window anchors; each must match exactly once.
    text = patch_shared_main(text, window_mode, muted)
    return replace_once(text, 'Ge.deepLinks.registerProtocolClient()', 'void 0')
