from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from tools import manage_macos as mac


class MacProcessTests(unittest.TestCase):
    def setUp(self):
        self.runtime = Path('/tmp/Codexflare Process Tests/Codexflare Runtime.app').resolve()
        self.enterContext(patch.object(mac, 'RUNTIME', self.runtime))
        self.ps = self.enterContext(patch.object(mac.subprocess, 'run'))
        self.crashpad = (f'{self.runtime}/Contents/Frameworks/Codex Framework.framework'
                         '/Versions/155.0.8059.80/Helpers/browser_crashpad_handler')

    def processes(self, lines):
        self.ps.return_value = subprocess.CompletedProcess([], 0, stdout='\n'.join(lines))

    def test_only_leftover_crash_reporters_do_not_block_apply(self):
        self.processes([f' 93769 {self.crashpad}', f' 93771 {self.crashpad}'])
        self.assertEqual(mac.running_pids(), [])
        mac.require_stopped()
        self.ps.assert_called_with(['/bin/ps', '-axo', 'pid=,comm='],
                                   capture_output=True, text=True, check=True)

    def test_main_and_renderer_processes_still_block_apply(self):
        self.processes([
            f' 100 {self.runtime}/Contents/MacOS/Codex',
            f' 101 {self.runtime}/Contents/Frameworks/Codex Helper (Renderer).app/Contents/MacOS/Codex Helper (Renderer)',
            f' 102 {self.runtime}/Contents/Frameworks/Codex Helper (GPU).app/Contents/MacOS/Codex Helper (GPU)',
            f' 103 {self.crashpad}',
        ])
        self.assertEqual(mac.running_pids(), [100, 101, 102])
        with self.assertRaisesRegex(ValueError, '100, 101, 102'):
            mac.require_stopped()

    def test_crash_reporter_exception_is_limited_to_frameworks_and_exact_name(self):
        self.processes([
            f' 200 {self.runtime}/Contents/MacOS/browser_crashpad_handler',
            f' 201 {self.crashpad}-other',
        ])
        self.assertEqual(mac.running_pids(), [200, 201])

    def test_other_apps_similar_paths_and_shell_arguments_are_not_matches(self):
        self.processes([
            ' 300 /Applications/ChatGPT.app/Contents/MacOS/Codex',
            f' 301 {self.runtime}.old/Contents/MacOS/Codex',
            f' 302 /bin/zsh {self.runtime}/Contents/MacOS/Codex',
            f' bad {self.runtime}/Contents/MacOS/Codex',
            ' 303',
            '',
        ])
        self.assertEqual(mac.running_pids(), [])


if __name__ == '__main__':
    unittest.main()
