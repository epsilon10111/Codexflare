from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import background


def png(width, height, *, depth=8):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    pixel = bytes((100, 150, 200, 73)) if depth == 8 else struct.pack('>4H', 10000, 20000, 30000, 16384)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + pixel * width) * height))
            + chunk(b'IEND', b''))


class BackgroundPreparationTests(unittest.TestCase):
    def test_small_images_and_exact_bounds_remain_unchanged(self):
        for width, height in ((1, 1), (3840, 2160), (3840, 1), (1, 2160)):
            data = png(width, height)
            info = background.validate_png(data)
            with self.subTest(size=(width, height)), patch.object(background.shutil, 'which') as which:
                prepared, metadata = background.prepare_image(data, info)
                self.assertIs(prepared, data)
                self.assertIs(metadata, info)
                which.assert_not_called()

    def test_missing_ffmpeg_keeps_python_only_installation_compatible(self):
        data = png(4000, 2)
        info = background.validate_png(data)
        with patch.object(background.shutil, 'which', return_value=None), patch.object(background.subprocess, 'run') as run:
            prepared, metadata = background.prepare_image(data, info)
            self.assertIs(prepared, data)
            self.assertIs(metadata, info)
            run.assert_not_called()

    def test_conversion_failures_are_not_silently_ignored(self):
        data = png(4000, 2)
        info = background.validate_png(data)
        errors = (subprocess.CalledProcessError(1, ['ffmpeg']),
                  subprocess.TimeoutExpired(['ffmpeg'], 30), OSError('cannot start'))
        with patch.object(background.shutil, 'which', return_value='/ffmpeg'):
            for error in errors:
                with self.subTest(error=error), patch.object(background.subprocess, 'run', side_effect=error):
                    with self.assertRaisesRegex(ValueError, '背景预处理'):
                        background.prepare_image(data, info)
            for output in (b'not PNG', png(1, 1)):
                with self.subTest(output=output), patch.object(background.subprocess, 'run',
                        return_value=subprocess.CompletedProcess([], 0, output, b'')):
                    with self.assertRaises(ValueError):
                        background.prepare_image(data, info)

    @unittest.skipUnless(shutil.which('ffmpeg'), '缩图验证需要 FFmpeg')
    def test_real_conversion_limits_dimensions_and_preserves_aspect_ratio(self):
        for source_size, target_size in (((4096, 2304), (3840, 2160)),
                                         ((4000, 100), (3840, 96)),
                                         ((100, 4320), (50, 2160)),
                                         ((8192, 1), (3840, 1)),
                                         ((1, 8192), (1, 2160))):
            with self.subTest(size=source_size):
                data = png(*source_size)
                info = background.validate_png(data)
                original_info = info.copy()
                prepared, metadata = background.prepare_image(data, info)
                self.assertEqual((metadata['width'], metadata['height']), target_size)
                self.assertEqual(metadata, background.validate_png(prepared))
                self.assertNotEqual(prepared, data)
                self.assertEqual(info, original_info)
                self.assertEqual((info['width'], info['height']), source_size)

    @unittest.skipUnless(shutil.which('ffmpeg'), '透明度验证需要 FFmpeg')
    def test_real_conversion_preserves_alpha_and_bit_depth(self):
        for depth, pixel_format, alpha in ((8, 'rgba', 73), (16, 'rgba64be', 16384)):
            with self.subTest(depth=depth):
                data = png(4000, 4, depth=depth)
                prepared, _ = background.prepare_image(data, background.validate_png(data))
                self.assertEqual(prepared[24:26], bytes((depth, 6)))
                result = subprocess.run([
                    shutil.which('ffmpeg'), '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-protocol_whitelist', 'pipe', '-f', 'image2pipe', '-c:v', 'png', '-i', 'pipe:0',
                    '-frames:v', '1', '-pix_fmt', pixel_format, '-f', 'rawvideo', 'pipe:1',
                ], input=prepared, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=30)
                values = result.stdout if depth == 8 else struct.unpack(f'>{len(result.stdout) // 2}H', result.stdout)
                self.assertEqual(set(values[3::4]), {alpha})


if __name__ == '__main__':
    unittest.main()
