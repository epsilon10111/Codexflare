#!/usr/bin/env python3
"""Render the Linux SVG logo as a macOS icon using the existing Cocoa dependency."""
from pathlib import Path
import subprocess
import tempfile


def main():
    from AppKit import (NSImage, NSBitmapImageRep, NSGraphicsContext, NSDeviceRGBColorSpace,
                        NSCompositingOperationCopy, NSImageInterpolationHigh, NSPNGFileType)
    from Foundation import NSMakeRect

    root = Path(__file__).resolve().parents[1]
    source = NSImage.alloc().initWithContentsOfFile_(str(root / 'ui/mark.svg'))
    if source is None:
        raise ValueError('Cannot load ui/mark.svg')
    with tempfile.TemporaryDirectory(prefix='codexflare-icon-') as directory:
        iconset = Path(directory) / 'Codexflare.iconset'
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = size * scale
                bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
                    None, pixels, pixels, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0)
                context = NSGraphicsContext.graphicsContextWithBitmapImageRep_(bitmap)
                NSGraphicsContext.saveGraphicsState()
                try:
                    NSGraphicsContext.setCurrentContext_(context)
                    context.setImageInterpolation_(NSImageInterpolationHigh)
                    source.drawInRect_fromRect_operation_fraction_(
                        NSMakeRect(0, 0, pixels, pixels), NSMakeRect(0, 0, 128, 128),
                        NSCompositingOperationCopy, 1.0)
                finally:
                    NSGraphicsContext.restoreGraphicsState()
                name = f'icon_{size}x{size}' + ('@2x' if scale == 2 else '') + '.png'
                (iconset / name).write_bytes(bytes(bitmap.representationUsingType_properties_(NSPNGFileType, {})))
        output = root / 'ui/mark.icns'
        subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset), '-o', str(output)], check=True)
        image = NSImage.alloc().initWithContentsOfFile_(str(output))
        if image is None or len(image.representations()) != 10:
            raise ValueError('Incomplete macOS icon')
    print(output)


if __name__ == '__main__':
    main()
