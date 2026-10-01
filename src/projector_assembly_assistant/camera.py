"""Image acquisition from the workstation cameras (top and side view).

Run this module on its own to capture a test image::

    python -m projector_assembly_assistant.camera --camera 1
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from .config import Config
from .utils import timestamp


def capture_image(camera_id: int, output_dir: str | Path, stem: str,
                  width: int = 1280, height: int = 720, warmup_frames: int = 10) -> Path | None:
    """Capture a single frame and save it as ``<output_dir>/<stem>.jpg``.

    A few frames are discarded first so that auto-exposure and white balance
    can settle.
    """
    cap = cv2.VideoCapture(camera_id)
    try:
        if not cap.isOpened():
            print(f"Unable to open camera {camera_id}.")
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        time.sleep(0.5)
        for _ in range(warmup_frames):
            cap.read()

        ok, frame = cap.read()
        if not ok:
            print(f"Unable to read a frame from camera {camera_id}.")
            return None

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{stem}.jpg"
        cv2.imwrite(str(path), frame)
        print(f"Captured image saved to {path}")
        return path
    finally:
        cap.release()


def capture_for_task(config: Config, task_id: str, camera_id: int) -> Path | None:
    return capture_image(
        camera_id,
        config.path("CAPTURED_IMAGES_DIR", create=True),
        f"{task_id}_{timestamp()}",
        width=config.getint("Camera", "WIDTH", fallback=1280),
        height=config.getint("Camera", "HEIGHT", fallback=720),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a test image.")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--task", default="test", help="Task ID used in the file name")
    parser.add_argument("--config", help="Path to config.ini")
    args = parser.parse_args()
    capture_for_task(Config(args.config), args.task, args.camera)


if __name__ == "__main__":
    main()
