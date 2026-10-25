"""Frozen macOS entry point; subprocesses return here with an explicit command."""
import json
import os
from pathlib import Path
import shutil
import sys


def main():
    # Finder's PATH omits the usual user-installed media tools.
    os.environ['PATH'] = os.pathsep.join([
        os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin'),
        '/opt/homebrew/bin', '/usr/local/bin',
    ])
    from tools import editor, original_macos, manage
    if len(sys.argv) > 1 and sys.argv[1] == '--self-check':
        import AppKit
        import WebKit
        from tools import animation, background, paths
        required = ('ui/index.html', 'ui/editor.js', 'ui/editor.css', 'ui/mark.icns',
                    'src/boot.js', 'src/boot.css', 'src/background.css',
                    'assets/default.webm', 'assets/default1.png', 'assets/default2.png',
                    'assets/LICENSE', '.packaged')
        assert all((paths.ROOT / name).is_file() for name in required)
        assert not paths.LOCAL.is_relative_to(paths.ROOT)
        assert editor.original_manager() is original_macos
        images = [background.validate_png((paths.ROOT / 'assets' / name).read_bytes())
                  for name in ('default1.png', 'default2.png')]
        assert all(item['width'] <= 3840 and item['height'] <= 2160 for item in images)
        print(json.dumps({'passed': True, 'python': sys.version.split()[0],
                          'resources': str(paths.ROOT), 'data': str(paths.LOCAL),
                          'original_mode': True, 'video': animation.video_info('default'),
                          'backgrounds': images, 'ffmpeg': shutil.which('ffmpeg')}, ensure_ascii=False))
        return
    if len(sys.argv) > 1 and sys.argv[1] in ('--original', '--manage', '--smoke-test'):
        command = sys.argv.pop(1)
        if command == '--original':
            original_macos.main()
        elif command == '--manage':
            manage.main()
        else:
            from tools import macos_editor_smoke
            macos_editor_smoke.main()
        return
    editor.main()


if __name__ == '__main__':
    main()
