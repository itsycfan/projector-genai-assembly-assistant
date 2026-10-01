"""User interaction layer: operator feedback and session logging.

Two kinds of feedback are collected:

* **Detection feedback.** When the operator disagrees with a detection, they
  flag the problem area (error detection, error description or instruction
  generation) and can add details. This becomes a corrective prompt for a
  re-check.
* **Guidance feedback.** After corrective guidance has been delivered, the
  operator says whether it helped. Ineffective guidance makes the assistant
  switch to the next-ranked guidance mode.

All events are appended to a JSON-lines session log for later analysis.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

PROBLEM_AREAS = {
    "01": "error detection",
    "02": "error description",
    "03": "instruction generation",
}


def collect_detection_feedback() -> dict:
    """Ask the operator which part of the analysis was wrong."""
    menu = "\n".join(f"  {code}: {label}" for code, label in PROBLEM_AREAS.items())
    while True:
        answer = input(f"\nWhich part of the analysis is wrong? (codes separated by spaces)\n{menu}\nYour input: ")
        codes = [c for c in answer.split() if c in PROBLEM_AREAS]
        if codes:
            break
        print(f"Please enter one or more of: {', '.join(PROBLEM_AREAS)}.")
    details = input("Additional details (press Enter to skip): ").strip()
    return {
        "problem_areas": ", ".join(PROBLEM_AREAS[c] for c in codes),
        "details": details or "No additional details provided",
    }


def collect_rating(question: str) -> int:
    """Ask for a 1-5 rating."""
    while True:
        answer = input(f"{question} (1 = not helpful, 5 = very helpful): ").strip()
        if answer in {"1", "2", "3", "4", "5"}:
            return int(answer)
        print("Please enter a number between 1 and 5.")


class SessionLog:
    """Append-only JSON-lines log of everything that happens in a session."""

    def __init__(self, log_dir: Path, session_id: str, operator_id: int):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"session_{session_id}.jsonl"
        self.operator_id = operator_id

    def log(self, event: str, **data) -> None:
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "operator_id": self.operator_id,
            "event": event,
            **data,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
