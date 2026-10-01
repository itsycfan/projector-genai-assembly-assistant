#!/usr/bin/env python3
"""Display an image on the DLP projector framebuffer (runs on the BeagleBone).

The main application uploads a cue image over SFTP and calls this script.
The image is scaled to fit the framebuffer, keeping its aspect ratio, and
written directly to /dev/fb0. The DLPDLCR2000 cape overlay must be loaded.

Usage (on the BeagleBone):
    sudo python3 display_image.py <image>
    sudo python3 display_image.py            # latest image in ./images
"""

import sys
from pathlib import Path

from PIL import Image

FRAMEBUFFER = "/dev/fb0"
FB_SYSFS = Path("/sys/class/graphics/fb0")
IMAGE_DIR = Path(__file__).resolve().parent / "images"
SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def framebuffer_geometry():
    width, height = (int(v) for v in (FB_SYSFS / "virtual_size").read_text().strip().split(","))
    bpp = int((FB_SYSFS / "bits_per_pixel").read_text().strip())
    return width, height, bpp


def latest_image(directory: Path) -> Path:
    images = [p for p in directory.iterdir() if p.suffix.lower() in SUFFIXES]
    if not images:
        sys.exit(f"No images found in {directory}")
    return max(images, key=lambda p: p.stat().st_mtime)


def rgb565(image: Image.Image) -> bytes:
    """Pack an RGB image as little-endian RGB565."""
    try:
        import numpy as np

        rgb = np.asarray(image, dtype=np.uint16)
        packed = ((rgb[..., 0] >> 3) << 11) | ((rgb[..., 1] >> 2) << 5) | (rgb[..., 2] >> 3)
        return packed.astype("<u2").tobytes()
    except ImportError:  # slower pure-Python fallback
        out = bytearray()
        for r, g, b in image.getdata():
            value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out += value.to_bytes(2, "little")
        return bytes(out)


def to_framebuffer_bytes(image: Image.Image, width: int, height: int, bpp: int) -> bytes:
    image = image.convert("RGB")
    image.thumbnail((width, height))
    canvas = Image.new("RGB", (width, height), "black")
    canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
    if bpp == 16:
        return rgb565(canvas)
    if bpp == 32:
        return canvas.convert("RGBA").tobytes("raw", "BGRA")
    if bpp == 24:
        return canvas.tobytes("raw", "BGR")
    sys.exit(f"Unsupported framebuffer depth: {bpp} bpp")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_image(IMAGE_DIR)
    width, height, bpp = framebuffer_geometry()
    with Image.open(path) as img:
        data = to_framebuffer_bytes(img, width, height, bpp)
    with open(FRAMEBUFFER, "wb") as fb:
        fb.write(data)
    print(f"Displayed {path.name} on {FRAMEBUFFER} ({width}x{height}, {bpp} bpp)")


if __name__ == "__main__":
    main()
