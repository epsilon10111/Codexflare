"""Windows x64 Owl 26.1002.52244 / build 13536 (MSIX 26.1002.7124.0)."""
if __package__:
    from .patch_app import patch_main as patch_shared_main, replace_once
else:
    from patch_app import patch_main as patch_shared_main, replace_once

VERSION = '26.1002.52244'
BUILD = '13536'
MAIN = '.vite/build/main-p91kJShj.js'
STARTUP_PRELOADS = (
    'rpc-c7a57a952402.js', 'app-main-9403f9647881.js',
    'app-initial-25361a10f2bf.js', 'app-primary-2b28b2369958.js',
    'app-initial-c43288484373.css', 'app-primary-c7f956fe5bad.css',
)


def require_supported(package):
    if (package.get('name'), package.get('version'), package.get('codexBuildNumber'),
            package.get('codexWindowsPackageIdentity')) != (
            'openai-codex-electron', VERSION, BUILD, 'OpenAI.Codex'):
        raise ValueError(f'仅支持 Windows Codex {VERSION} / build {BUILD} 正式版')


def patch_main(text, window_mode='restore', muted=True):
    # This Windows build shares the Linux window anchors; each must match exactly once.
    text = patch_shared_main(text, window_mode, muted)
    return replace_once(text, 'Ge.deepLinks.registerProtocolClient()', 'void 0')
