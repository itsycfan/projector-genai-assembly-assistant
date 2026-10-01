"""Small shared helpers: timestamps, timing and console prompts."""

from __future__ import annotations

import time
from datetime import datetime


def timestamp() -> str:
    """Return a filesystem-safe timestamp, e.g. ``20250318_171604``."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class Timer:
    """Context manager that measures and reports the duration of a stage.

    Example::

        with Timer("Error detection") as t:
            run_detection()
        print(t.elapsed)
    """

    def __init__(self, label: str, verbose: bool = True):
        self.label = label
        self.verbose = verbose
        self.elapsed = 0.0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self.elapsed = time.perf_counter() - self._start
        if self.verbose:
            print(f"[time] {self.label}: {self.elapsed:.2f} s")


def ask_yes_no(question: str) -> bool:
    """Ask a yes/no question on the console until a valid answer is given."""
    while True:
        answer = input(f"{question} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def ask_choice(question: str, options: list[str]) -> str:
    """Ask the user to pick one of ``options`` (case-insensitive)."""
    normalised = {o.lower(): o for o in options}
    while True:
        answer = input(f"{question} [{'/'.join(options)}]: ").strip().lower()
        if answer in normalised:
            return normalised[answer]
        print(f"Please enter one of: {', '.join(options)}.")


def banner(text: str, char: str = "=", width: int = 60) -> None:
    print(f"\n{char * width}\n{text}\n{char * width}")
