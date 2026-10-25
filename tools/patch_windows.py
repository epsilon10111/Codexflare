"""Reference build metadata and structural patch entry point; no version allowlist."""
VERSION = '26.1002.52244'
BUILD = '13536'
MAIN = '.vite/build/main-p91kJShj.js'
STARTUP_PRELOADS = (
    'rpc-c7a57a952402.js', 'app-main-9403f9647881.js',
    'app-initial-25361a10f2bf.js', 'app-primary-2b28b2369958.js',
    'app-initial-c43288484373.css', 'app-primary-c7f956fe5bad.css',
)


def require_supported(package):
    if (package.get('name') != 'openai-codex-electron'
            or package.get('codexWindowsPackageIdentity') != 'OpenAI.Codex'
            or not isinstance(package.get('version'), str) or not package['version']):
        raise ValueError('仅支持具有有效版本信息的 Windows Codex 正式版')


def patch_main(text, window_mode='restore', muted=True):
    if __package__:
        from .window_patch import patch_main as patch_window
    else:
        from window_patch import patch_main as patch_window
    return patch_window(text, window_mode, muted, protocol=True)
