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


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def png(width, height, *, depth=8):
    pixel = bytes((100, 150, 200, 73)) if depth == 8 else struct.pack('>4H', 10000, 20000, 30000, 16384)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, depth, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + pixel * width) * height))
            + chunk(b'IEND', b''))


class BackgroundPreparationTests(unittest.TestCase):
    def test_corrupt_pixel_streams_fail_even_with_valid_chunk_crcs(self):
        header = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
        valid = zlib.compress(b'\0\xff\xff\xff\xff')
        streams = [b'not-a-zlib-stream', valid[:-1], valid + b'extra', valid + valid,
                   zlib.compress(b'\0\xff\xff\xff'), zlib.compress(b'\0' + b'\xff' * 5),
                   zlib.compress(b'\x05\xff\xff\xff\xff'), zlib.compress(b'\0' * 1_000_000)]
        for compressed in streams:
            with self.subTest(compressed=compressed[:20]), self.assertRaisesRegex(ValueError, '像素'):
                background.validate_png(header + chunk(b'IDAT', compressed) + chunk(b'IEND', b''))

    def test_color_depths_and_adam7_scanlines_accept_valid_streams(self):
        for color, depths, channels in ((0, (1, 2, 4, 8, 16), 1), (2, (8, 16), 3),
                                        (3, (1, 2, 4, 8), 1), (4, (8, 16), 2), (6, (8, 16), 4)):
            for depth in depths:
                for interlace in (0, 1):
                    # Explicit Adam7 pass dimensions for a 9x9 image.
                    passes = ((9, 9),) if not interlace else ((2, 2), (1, 2), (3, 1), (2, 3),
                                                            (5, 2), (4, 5), (9, 4))
                    rows = b''.join((bytes((line % 5,)) + bytes((width * channels * depth + 7) // 8))
                                    for width, height in passes for line in range(height))
                    data = (b'\x89PNG\r\n\x1a\n'
                            + chunk(b'IHDR', struct.pack('>IIBBBBB', 9, 9, depth, color, 0, 0, interlace)))
                    if color == 3:
                        data += chunk(b'PLTE', b'\0\0\0') + chunk(b'tRNS', b'\xff')
                    compressed = zlib.compress(rows)
                    # Chunk boundaries may split zlib headers, scanlines and checksums.
                    data += chunk(b'IDAT', b'') + b''.join(chunk(b'IDAT', bytes((byte,))) for byte in compressed)
                    data += chunk(b'IEND', b'')
                    with self.subTest(color=color, depth=depth, interlace=interlace):
                        info = background.validate_png(data)
                        self.assertEqual((info['width'], info['height']), (9, 9))

    def test_small_adam7_images_skip_empty_passes(self):
        for width, height, raw in ((1, 1, b'\0\0'), (1, 2, b'\0\0\0\0'), (2, 1, b'\0\0\0\0')):
            data = (b'\x89PNG\r\n\x1a\n'
                    + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 1, 0, 0, 0, 1))
                    + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
            with self.subTest(size=(width, height)):
                self.assertEqual(background.validate_png(data)['width'], width)

    def test_indexed_images_require_valid_palette_before_image_data(self):
        header = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 1, 3, 0, 0, 0))
        image = chunk(b'IDAT', zlib.compress(b'\0\0'))
        palette = chunk(b'PLTE', b'\0\0\0')
        for body in (image, image + palette, palette * 2 + image,
                     chunk(b'PLTE', b'\0') + image, chunk(b'PLTE', b'\0' * 9) + image,
                     palette + image + chunk(b'tEXt', b'key\0value') + chunk(b'IDAT', b'')):
            with self.subTest(body=body[:20]), self.assertRaises(ValueError):
                background.validate_png(header + body + chunk(b'IEND', b''))

    def test_pixel_decompression_is_bounded_and_crosses_block_boundaries(self):
        real_decoder = zlib.decompressobj()
        with patch.object(background.zlib, 'decompressobj', return_value=MockDecoder(real_decoder)):
            self.assertEqual(background.validate_png(png(8192, 5, depth=16))['height'], 5)

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


class MockDecoder:
    def __init__(self, decoder):
        self.decoder = decoder

    def decompress(self, data, max_length):
        assert len(data) <= 65536
        assert 0 < max_length <= 65536
        return self.decoder.decompress(data, max_length)

    def __getattr__(self, name):
        return getattr(self.decoder, name)


if __name__ == '__main__':
    unittest.main()
