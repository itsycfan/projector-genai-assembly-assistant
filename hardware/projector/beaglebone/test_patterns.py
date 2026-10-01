#!/usr/bin/env python3
"""Generate projector test patterns (frame, diagonals, circle; colour bars).

The patterns are saved as PNG files at the native nHD resolution of the
DLPDLCR2000 and can be shown with display_image.py to check focus,
alignment and colour.

Usage:
    python3 test_patterns.py [output_dir]
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 640, 360


def geometry_pattern():
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, WIDTH - 1, HEIGHT - 1], outline="white", width=2)
    draw.line([0, 0, WIDTH - 1, HEIGHT - 1], fill="white", width=2)
    draw.line([0, HEIGHT - 1, WIDTH - 1, 0], fill="white", width=2)
    cx, cy, r = WIDTH // 2, HEIGHT // 2, min(WIDTH, HEIGHT) // 4
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="white", width=2)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    text = "DLP2000 Test"
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (box[2] - box[0])) // 2, 30), text, fill="white", font=font)
    return image


def colour_bars():
    image = Image.new("RGB", (WIDTH, HEIGHT), "black")
    draw = ImageDraw.Draw(image)
    colours = ["red", "green", "blue", "white", "yellow", "cyan", "magenta"]
    bar = WIDTH // len(colours)
    for i, colour in enumerate(colours):
        draw.rectangle([i * bar, 0, (i + 1) * bar, HEIGHT], fill=colour)
    return image


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("images")
    out.mkdir(parents=True, exist_ok=True)
    geometry_pattern().save(out / "test_pattern.png")
    colour_bars().save(out / "colour_bars.png")
    print(f"Test patterns saved to {out}/")


if __name__ == "__main__":
    main()
