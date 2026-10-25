"""Reference build metadata and structural patch entry point; no version allowlist."""
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
