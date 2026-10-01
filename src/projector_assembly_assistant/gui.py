"""Optional monitoring GUI (Tkinter).

Shows the latest captured image next to the reference image for the same
step, plus the tail of the most recent session log. Run it in a second
terminal while the assistant is running::

    python -m projector_assembly_assistant.gui
"""

from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

from PIL import Image, ImageTk

from .config import Config
from .data_management import find_reference_image

CANVAS_W, CANVAS_H = 560, 400
REFRESH_MS = 1000


def latest_file(directory: Path, pattern: str) -> Path | None:
    files = [p for p in directory.glob(pattern) if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


class MonitorGUI:
    def __init__(self, root: tk.Tk, config: Config):
        self.root = root
        self.captured_dir = config.path("CAPTURED_IMAGES_DIR", create=True)
        self.reference_dir = config.path("REFERENCE_IMAGES_DIR")
        self.log_dir = config.path("LOG_DIR", create=True)
        self._shown: dict[str, Path | None] = {"live": None, "ref": None}

        root.title("Assembly Assistant Monitor")
        frame = tk.Frame(root)
        frame.pack(fill=tk.X, padx=10, pady=10)
        self.live_canvas = self._canvas(frame, "Captured image")
        self.ref_canvas = self._canvas(frame, "Reference image")

        self.log_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, height=14)
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        tk.Button(root, text="Exit", command=root.destroy, width=10).pack(anchor=tk.E, padx=10, pady=(0, 10))
        self.refresh()

    @staticmethod
    def _canvas(parent: tk.Frame, title: str) -> tk.Canvas:
        box = tk.Frame(parent)
        box.pack(side=tk.LEFT, padx=5)
        tk.Label(box, text=title, font=("Arial", 12, "bold")).pack()
        canvas = tk.Canvas(box, width=CANVAS_W, height=CANVAS_H, bg="white", relief=tk.SUNKEN, bd=2)
        canvas.pack()
        return canvas

    def _show(self, key: str, path: Path | None, canvas: tk.Canvas) -> None:
        if path is None or path == self._shown[key]:
            return
        img = Image.open(path)
        img.thumbnail((CANVAS_W, CANVAS_H))
        photo = ImageTk.PhotoImage(img)
        canvas.delete("all")
        canvas.create_image(CANVAS_W // 2, CANVAS_H // 2, image=photo)
        canvas.image = photo  # keep a reference
        self._shown[key] = path

    def refresh(self) -> None:
        live = latest_file(self.captured_dir, "*.jpg")
        self._show("live", live, self.live_canvas)
        if live is not None:
            task_id = live.stem.split("_")[0]  # captured files are named <taskID>_<timestamp>
            self._show("ref", find_reference_image(self.reference_dir, task_id), self.ref_canvas)

        log = latest_file(self.log_dir, "session_*.jsonl")
        if log is not None:
            lines = log.read_text(encoding="utf-8").splitlines()[-30:]
            self.log_area.delete("1.0", tk.END)
            self.log_area.insert(tk.END, "\n".join(lines))
            self.log_area.see(tk.END)
        self.root.after(REFRESH_MS, self.refresh)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitoring GUI for the assembly assistant.")
    parser.add_argument("--config", help="Path to config.ini")
    args = parser.parse_args()
    root = tk.Tk()
    MonitorGUI(root, Config(args.config))
    root.mainloop()


if __name__ == "__main__":
    main()
