"""Data management layer.

Loads the assembly task sequence, the error-history log and the operator
profiles, and derives the information the assistant needs at runtime:

* which steps are *critical* (error count above a threshold);
* which past errors are relevant to a step (used in preventive warnings);
* how an operator's preferred guidance modes are ranked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# Guidance modes, mapped to the preference column in the operator profile table.
GUIDANCE_MODES: dict[str, str] = {
    "voice": "Audio Preference (0-1)",
    "visual": "Visual Preference (0-1)",
    "robot_assistance": "Robot Assistance Preference (0-1)",
    "robot_demonstration": "Robot Demonstration Preference (0-1)",
}

# Modes with a working implementation in this release.
IMPLEMENTED_MODES: tuple[str, ...] = ("visual", "voice")

MODE_LABELS = {
    "voice": "voice instructions",
    "visual": "projected visual cues",
    "robot_assistance": "robot assistance",
    "robot_demonstration": "robot demonstration",
}

IMAGE_EXTENSIONS = (".jpeg", ".jpg", ".png")


def _clean(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


# --------------------------------------------------------------------------
# Assembly tasks
# --------------------------------------------------------------------------
@dataclass
class AssemblyTask:
    task_id: str
    task_type: str | None
    work_instruction: str
    operation_name: str | None = None
    required_components: str | None = None
    required_tools: str | None = None
    difficulty: int | None = None
    camera_id: int = 0

    @property
    def label(self) -> str:
        """A short human-readable name for the step."""
        return self.operation_name or self.task_type or self.task_id


def load_assembly_tasks(path: str | Path) -> list[AssemblyTask]:
    """Read the task sequence from an Excel sheet (one row per step)."""
    df = pd.read_excel(path, dtype={"task ID": str})
    df = df.dropna(subset=["task ID", "work instructions"])

    tasks = []
    for _, row in df.iterrows():
        difficulty = row.get("Task Difficulty(1-3)")
        camera = row.get("Camera")
        tasks.append(
            AssemblyTask(
                task_id=_clean(row["task ID"]),
                task_type=_clean(row.get("task type")),
                work_instruction=_clean(row["work instructions"]),
                operation_name=_clean(row.get("operation name")),
                required_components=_clean(row.get("required components")),
                required_tools=_clean(row.get("required tools")),
                difficulty=None if pd.isna(difficulty) else int(difficulty),
                camera_id=0 if pd.isna(camera) else int(camera),
            )
        )
    return tasks


def find_reference_image(reference_dir: str | Path, task_id: str) -> Path | None:
    """Return the reference image for a task ID, whatever its extension."""
    for ext in IMAGE_EXTENSIONS:
        candidate = Path(reference_dir) / f"{task_id}{ext}"
        if candidate.exists():
            return candidate
    return None


# --------------------------------------------------------------------------
# Error history
# --------------------------------------------------------------------------
class ErrorHistory:
    """Historical error log used for critical-step analysis."""

    def __init__(self, path: str | Path):
        self.df = pd.read_excel(path)
        self.df["Step Number"] = self.df["Step Number"].astype(str).str.strip()
        self._counts = self.df["Step Number"].value_counts().to_dict()

    def count(self, step_id: str) -> int:
        return int(self._counts.get(step_id, 0))

    def is_critical(self, step_id: str, threshold: int) -> bool:
        """A step is critical when its recorded error count exceeds ``threshold``."""
        return self.count(step_id) > threshold

    def records(self, step_id: str, limit: int = 10) -> list[dict]:
        """Return the most frequent (error type, description) pairs for a step."""
        subset = self.df[self.df["Step Number"] == step_id]
        if subset.empty:
            return []
        grouped = (
            subset.groupby(["Error Type", "Error Description"])
            .size()
            .sort_values(ascending=False)
            .head(limit)
        )
        return [
            {"error_type": etype, "description": desc, "occurrences": int(n)}
            for (etype, desc), n in grouped.items()
        ]


# --------------------------------------------------------------------------
# Operator profiles
# --------------------------------------------------------------------------
@dataclass
class OperatorProfile:
    operator_id: int
    experience_months: int | None = None
    cognitive_profile: str | None = None
    preferences: dict[str, float] = field(default_factory=dict)

    def ranked_modes(self) -> list[str]:
        """Guidance modes sorted by preference weight (highest first)."""
        return sorted(self.preferences, key=self.preferences.get, reverse=True)

    def summary(self) -> str:
        prefs = ", ".join(f"{MODE_LABELS[m]}={self.preferences[m]:.2f}" for m in self.ranked_modes())
        return (
            f"Operator {self.operator_id} | experience: {self.experience_months} months | "
            f"cognitive profile: {self.cognitive_profile or 'not specified'}\n"
            f"Preferences: {prefs}"
        )


def load_operator_profiles(path: str | Path) -> dict[int, OperatorProfile]:
    df = pd.read_excel(path)
    profiles: dict[int, OperatorProfile] = {}
    for _, row in df.iterrows():
        if pd.isna(row.get("Operator ID")):
            continue
        operator_id = int(row["Operator ID"])
        prefs = {
            mode: float(row[col]) if col in row and not pd.isna(row[col]) else 0.0
            for mode, col in GUIDANCE_MODES.items()
        }
        experience = row.get("Work Experience (months)")
        profiles[operator_id] = OperatorProfile(
            operator_id=operator_id,
            experience_months=None if pd.isna(experience) else int(experience),
            cognitive_profile=_clean(row.get("Cognitive Profile")),
            preferences=prefs,
        )
    return profiles
