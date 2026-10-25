#!/usr/bin/env python3
"""Rebuild the silent, four-second demo using Pillow, NumPy and FFmpeg."""

import json
import math
from pathlib import Path
import random
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FPS, SECONDS = 1920, 1080, 30, 4
FONT = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"


def render_frame(index):
    t = index / FPS
    visibility = min(1, t / 0.6, (SECONDS - t) / 0.55)
    y, x = np.mgrid[-1:1:270j, -1.7778:1.7778:480j]
    blue = np.exp(-(((x + 0.42 * math.cos(t)) / 0.8) ** 2 + ((y + 0.12) / 0.36) ** 2))
    violet = np.exp(-(((x - 0.45 * math.sin(t * 0.6)) / 0.75) ** 2 + ((y - 0.12) / 0.42) ** 2))
    rgb = np.stack((6 + 13 * violet, 8 + 14 * blue, 14 + 26 * blue + 14 * violet), axis=-1)
    base = Image.fromarray(np.uint8(np.clip(rgb * visibility, 0, 255))).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    trail = Image.new("RGB", base.size)
    draw = ImageDraw.Draw(trail)
    for j in range(220):
        angle = (j / 220) * 2 * math.pi + t * 0.45
        x1 = 960 + 510 * math.cos(angle)
        y1 = 540 + 186 * math.sin(angle) + 54 * math.cos(angle)
        angle2 = angle + 0.035
        x2 = 960 + 510 * math.cos(angle2)
        y2 = 540 + 186 * math.sin(angle2) + 54 * math.cos(angle2)
        bright = 0.15 + 0.85 * ((math.cos(angle - t * 1.8) + 1) / 2) ** 7
        color = (int(100 * bright * visibility), int(150 * bright * visibility), int(245 * bright * visibility))
        draw.line((x1, y1, x2, y2), fill=color, width=3)
    base = Image.fromarray(np.uint8(np.minimum(255, np.asarray(base, dtype=np.uint16) + np.asarray(trail.filter(ImageFilter.GaussianBlur(20)), dtype=np.uint16) * 2 + np.asarray(trail, dtype=np.uint16))))
    draw = ImageDraw.Draw(base)
    rng = random.Random(41)
    for _ in range(90):
        phase, radius, speed = rng.random() * math.tau, rng.uniform(230, 820), rng.uniform(0.06, 0.15)
        px = 960 + math.cos(phase + t * speed) * radius
        py = 540 + math.sin(phase + t * speed) * radius * 0.48
        alpha = int(rng.uniform(24, 100) * visibility)
        draw.ellipse((px, py, px + 2, py + 2), fill=(alpha // 2, alpha * 3 // 4, alpha))
    font = ImageFont.truetype(FONT, 110)
    spacing = 19
    widths = [draw.textlength(letter, font=font) for letter in "CODEX"]
    cursor = (WIDTH - sum(widths) - spacing * 4) / 2
    for letter, width in zip("CODEX", widths):
        draw.text((cursor, 540), letter, font=font, anchor="lm", fill=tuple(int(c * visibility) for c in (232, 239, 250)))
        cursor += width + spacing
    return base


def main():
    output = ROOT / "assets" / "boot.webm"
    temporary = output.with_name(".boot.tmp.webm")
    output.parent.mkdir(exist_ok=True)
    (ROOT / "work").mkdir(exist_ok=True)
    encoder = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libvpx-vp9",
        "-crf", "34", "-b:v", "0", "-row-mt", "1", "-cpu-used", "5", "-pix_fmt", "yuv420p", str(temporary),
    ], stdin=subprocess.PIPE)
    try:
        for index in range(FPS * SECONDS):
            frame = render_frame(index)
            if index == FPS * 2:
                frame.save(ROOT / "work" / "boot-preview.png")
            encoder.stdin.write(frame.tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("FFmpeg failed to encode the demo")
        metadata = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(temporary),
        ]))
        streams = metadata["streams"]
        assert len(streams) == 1 and streams[0]["codec_type"] == "video", "Expected silent video"
        assert (streams[0]["width"], streams[0]["height"]) == (WIDTH, HEIGHT)
        assert streams[0]["codec_name"] == "vp9" and streams[0]["r_frame_rate"] == "30/1"
        assert abs(float(metadata["format"]["duration"]) - SECONDS) < 0.05
        temporary.replace(output)
        print(f"Created {output}: {WIDTH}×{HEIGHT}, {FPS} fps, {SECONDS} s, {output.stat().st_size:,} bytes")
    finally:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
