"""Interactive assembly assistant: main loop.

For each assembly step the assistant:

1. announces the work instruction;
2. issues a preventive warning if the step is critical;
3. waits for the operator, then captures the assembly state;
4. runs reference-based error detection with the generative AI model, with
   an operator-feedback loop for misclassifications;
5. on error, delivers corrective guidance (projected visual cue or voice) in
   the operator's preferred mode, switching to the next-ranked mode if the
   guidance is reported as ineffective;
6. repeats capture and detection until the step is correct.

Usage::

    python -m projector_assembly_assistant.main [--operator 1] [--task S15.2]
                                                [--no-projector] [--no-audio]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .audio import speak
from .camera import capture_for_task
from .config import Config
from .data_management import (
    IMPLEMENTED_MODES,
    MODE_LABELS,
    AssemblyTask,
    ErrorHistory,
    OperatorProfile,
    find_reference_image,
    load_assembly_tasks,
    load_operator_profiles,
)
from .feedback import SessionLog, collect_detection_feedback, collect_rating
from .genai import GenAIClient
from .projector import ProjectorController
from .utils import Timer, ask_choice, ask_yes_no, banner, timestamp
from .visual_cues import create_visual_cue


class AssemblyAssistant:
    """Coordinates the data, generative AI, hardware and interaction layers."""

    def __init__(self, config: Config, genai: GenAIClient, profile: OperatorProfile,
                 history: ErrorHistory, use_projector: bool = True, use_audio: bool = True):
        self.config = config
        self.genai = genai
        self.profile = profile
        self.history = history
        self.use_projector = use_projector
        self.use_audio = use_audio
        self.threshold = config.getint("CriticalSteps", "ERROR_THRESHOLD", fallback=5)
        self.reference_dir = config.path("REFERENCE_IMAGES_DIR")
        self.results_dir = config.path("RESULTS_DIR", create=True)
        self.cues_dir = config.path("VISUAL_CUES_DIR", create=True)
        self.audio_dir = config.path("AUDIO_DIR", create=True)
        self.session = SessionLog(config.path("LOG_DIR", create=True), timestamp(), profile.operator_id)

        # Rank the guidance modes; modes without an implementation are skipped.
        ranked = profile.ranked_modes()
        self.modes = [m for m in ranked if m in IMPLEMENTED_MODES]
        skipped = [m for m in ranked if m not in IMPLEMENTED_MODES]
        if skipped:
            print("Not available in this release (skipped): " + ", ".join(MODE_LABELS[m] for m in skipped))
        print("Guidance mode ranking: " + " > ".join(MODE_LABELS[m] for m in self.modes))

    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        return self.modes[0]

    def switch_mode(self) -> bool:
        """Demote the current mode and move to the next-ranked one."""
        if len(self.modes) < 2:
            return False
        previous = self.modes.pop(0)
        self.modes.append(previous)
        print(f"Switching guidance from {MODE_LABELS[previous]} to {MODE_LABELS[self.mode]}.")
        self.session.log("mode_switch", previous=previous, current=self.mode)
        return True

    def say(self, text: str, stem: str) -> None:
        if self.use_audio:
            speak(text, self.audio_dir / f"{stem}.mp3")
        else:
            print(f"[voice] {text}")

    def project(self, image: Path) -> None:
        if not self.use_projector:
            print(f"[projector disabled] Cue saved to {image}")
            return
        controller = ProjectorController.from_config(self.config)
        if controller.connect():
            try:
                controller.display_image(image)
            finally:
                controller.close()

    def deliver(self, message: str, headline: str, cue_type: str, task: AssemblyTask) -> None:
        """Deliver a warning or correction in the current guidance mode."""
        stem = f"{cue_type}_{task.task_id}_{timestamp()}"
        if self.mode == "visual":
            cue = create_visual_cue(self.genai, headline, message, cue_type, self.cues_dir, stem)
            self.project(cue)
            self.session.log("guidance", task_id=task.task_id, mode="visual", cue_type=cue_type,
                             message=message, cue=str(cue))
        else:
            self.say(message, stem)
            self.session.log("guidance", task_id=task.task_id, mode="voice", cue_type=cue_type,
                             message=message)

    # ------------------------------------------------------------------
    def preventive_warning(self, task: AssemblyTask) -> None:
        count = self.history.count(task.task_id)
        with Timer("Critical step identification"):
            critical = self.history.is_critical(task.task_id, self.threshold)
        if not critical:
            print(f"Step {task.task_id}: {count} recorded errors (not critical).")
            return

        print(f"Step {task.task_id} is CRITICAL: {count} recorded errors.")
        warning = self.genai.generate_preventive_warning(task, count, self.history.records(task.task_id))
        self.session.log("preventive_warning", task_id=task.task_id, error_count=count, warning=warning)
        self.deliver(warning, "CAUTION: CRITICAL STEP", "warning", task)

    def wait_for_operator(self) -> None:
        self.say("Tell me when you have completed this step.", f"prompt_{timestamp()}")
        input("Press Enter when the step is completed...")

    def verify(self, task: AssemblyTask, reference: Path, live: Path):
        """Run detection with the operator-feedback loop until the operator agrees."""
        result = self.genai.detect_errors(task, reference, live)
        while True:
            print(f"\n--- Detection log ---\n{result.text}\n---------------------")
            self.session.log("detection", task_id=task.task_id, image=str(live),
                             has_error=result.has_error, elapsed_s=round(result.elapsed, 2),
                             analysis=result.text)
            if ask_yes_no("Do you agree with this analysis?"):
                return result
            feedback = collect_detection_feedback()
            self.session.log("detection_feedback", task_id=task.task_id, **feedback)
            result = self.genai.detect_errors(task, reference, live, feedback, result.text)

    def process_task(self, task: AssemblyTask, index: int, total: int) -> None:
        banner(f"Step {index}/{total}  {task.task_id}  {task.label}\n"
               f"Instruction: {task.work_instruction}\nCamera: {task.camera_id}")
        self.session.log("task_start", task_id=task.task_id)

        self.say(task.work_instruction, f"instruction_{task.task_id}_{timestamp()}")
        self.preventive_warning(task)

        reference = find_reference_image(self.reference_dir, task.task_id)
        if reference is None:
            print(f"No reference image for {task.task_id}; skipping verification.")
            self.wait_for_operator()
            return

        while True:
            self.wait_for_operator()
            live = capture_for_task(self.config, task.task_id, task.camera_id)
            if live is None:
                if ask_yes_no("Image capture failed. Retry?"):
                    continue
                return

            result = self.verify(task, reference, live)
            self._save_result(task, result.text)
            if not result.has_error:
                print(f"Step {task.task_id} verified as correct. Proceeding to the next step.")
                self.session.log("task_complete", task_id=task.task_id)
                return

            instructions = self.genai.generate_correction_instructions(task, result.text)
            self.deliver(instructions, "ERROR DETECTED", "correction", task)

            rating = collect_rating("How helpful was this guidance?")
            self.session.log("guidance_feedback", task_id=task.task_id, mode=self.mode, rating=rating)
            if rating <= 2 and self.switch_mode():
                self.deliver(instructions, "ERROR DETECTED", "correction", task)

    def _save_result(self, task: AssemblyTask, analysis: str) -> None:
        path = self.results_dir / f"detection_{task.task_id}_{timestamp()}.txt"
        path.write_text(
            f"Task ID: {task.task_id}\nOperation: {task.label}\n"
            f"Instruction: {task.work_instruction}\n\n{analysis}\n",
            encoding="utf-8",
        )


# ----------------------------------------------------------------------
def select_operator(profiles: dict[int, OperatorProfile], operator_id: int | None) -> OperatorProfile:
    while operator_id not in profiles:
        try:
            operator_id = int(input(f"Enter your operator ID {sorted(profiles)}: "))
        except ValueError:
            pass
    return profiles[operator_id]


def select_tasks(tasks: list[AssemblyTask], task_id: str | None) -> list[AssemblyTask]:
    if task_id:
        selected = [t for t in tasks if t.task_id == task_id]
        if not selected:
            raise SystemExit(f"Task {task_id} not found.")
        return selected

    mode = ask_choice("Run a single step (s) or the full sequence (f)?", ["s", "f"])
    if mode == "f":
        return tasks
    for i, t in enumerate(tasks, 1):
        print(f"{i:2d}. {t.task_id:6s} {t.label}")
    while True:
        try:
            return [tasks[int(input("Step number: ")) - 1]]
        except (ValueError, IndexError):
            print(f"Enter a number between 1 and {len(tasks)}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Projector-based generative AI assembly assistant.")
    parser.add_argument("--config", help="Path to config.ini")
    parser.add_argument("--operator", type=int, help="Operator ID")
    parser.add_argument("--task", help="Run a single step by task ID, e.g. S15.2")
    parser.add_argument("--no-projector", action="store_true", help="Save cues without projecting them")
    parser.add_argument("--no-audio", action="store_true", help="Print voice messages instead of speaking")
    args = parser.parse_args()

    config = Config(args.config)
    banner("Projector-Based Generative AI Assembly Assistant")

    tasks = load_assembly_tasks(config.path("ASSEMBLY_TASKS_FILE"))
    history = ErrorHistory(config.path("ERROR_HISTORY_FILE"))
    profiles = load_operator_profiles(config.path("OPERATOR_PROFILES_FILE"))
    print(f"Loaded {len(tasks)} assembly steps and {len(profiles)} operator profiles.")

    profile = select_operator(profiles, args.operator)
    print(profile.summary())

    assistant = AssemblyAssistant(
        config, GenAIClient(config), profile, history,
        use_projector=not args.no_projector, use_audio=not args.no_audio,
    )
    selected = select_tasks(tasks, args.task)
    for i, task in enumerate(selected, 1):
        assistant.process_task(task, i, len(selected))

    banner("All selected assembly steps completed.")
    print(f"Session log: {assistant.session.path}")


if __name__ == "__main__":
    main()
