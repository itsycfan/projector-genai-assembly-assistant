"""Generative AI layer.

Wraps a vision-language model (OpenAI Chat Completions API) for:

* reference-based **error detection** (reference image vs. live capture);
* **re-checking** a detection using the operator's corrective feedback;
* generating **preventive warnings** for critical steps;
* generating concise **corrective instructions**;
* generating **SVG visual cues** for projection.

Every detection session is independent: no conversation state is carried over
between calls.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from .config import Config, get_secret
from .data_management import AssemblyTask
from .prompts import render
from .utils import Timer

DETECTION_SYSTEM_PROMPT = (
    "You are an industrial assembly quality-control expert. Compare a reference image "
    "of the correct assembly state with a real-time image of the current state. Focus "
    "ONLY on the components and tools mentioned in the instruction and give a clear "
    "CORRECT/ERROR assessment."
)
INSTRUCTION_SYSTEM_PROMPT = (
    "You are a manufacturing process expert who writes short, clear guidance for "
    "assembly operators."
)
SVG_SYSTEM_PROMPT = (
    "You create SVG visual cues for a workbench projector. Always return valid SVG "
    "code that starts with <?xml and ends with </svg>. Never include Markdown or "
    "explanations."
)

_STATUS_RE = re.compile(r"status\W*\s*(correct|pass|error|incorrect)", re.IGNORECASE)
_ERROR_KEYWORDS = ("error", "incorrect", "wrong", "misaligned", "missing")


@dataclass
class DetectionResult:
    text: str
    has_error: bool
    elapsed: float


def parse_has_error(analysis: str) -> bool:
    """Decide whether a detection log reports an error.

    The ``Status:`` line requested in the prompt is used first. If the model
    ignored the format, fall back to keyword matching, which is the conservative
    choice: a possible error is reported to the operator.
    """
    match = _STATUS_RE.search(analysis)
    if match:
        return match.group(1).lower() in ("error", "incorrect")
    lowered = analysis.lower()
    return any(word in lowered for word in _ERROR_KEYWORDS)


def encode_image(path: str | Path) -> str:
    """Return an image as a base64 data URL."""
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


class GenAIClient:
    """High-level interface to the generative AI model."""

    def __init__(self, config: Config, client: OpenAI | None = None):
        self.vision_model = config.get("Models", "VISION_MODEL", fallback="gpt-4o-mini")
        self.text_model = config.get("Models", "TEXT_MODEL", fallback="gpt-4o-mini")
        self.max_tokens = config.getint("Models", "MAX_TOKENS", fallback=500)
        self.svg_max_tokens = config.getint("Models", "SVG_MAX_TOKENS", fallback=1000)
        self.detection_temperature = config.getfloat("Models", "DETECTION_TEMPERATURE", fallback=0.2)
        self.generation_temperature = config.getfloat("Models", "GENERATION_TEMPERATURE", fallback=0.7)
        self.client = client or OpenAI(api_key=get_secret("OPENAI_API_KEY"))

    # ------------------------------------------------------------------
    def _chat(self, model: str, system: str, content, max_tokens: int, temperature: float) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()

    def _vision_content(self, prompt: str, reference_image: Path, live_image: Path) -> list[dict]:
        return [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": encode_image(reference_image)}},
            {"type": "image_url", "image_url": {"url": encode_image(live_image)}},
        ]

    # ------------------------------------------------------------------
    def detect_errors(
        self,
        task: AssemblyTask,
        reference_image: Path,
        live_image: Path,
        operator_feedback: dict | None = None,
        previous_analysis: str | None = None,
    ) -> DetectionResult:
        """Compare the live image with the reference image for ``task``.

        If ``operator_feedback`` is given, the detection is re-run with the
        operator's corrective prompt appended.
        """
        if operator_feedback is None:
            prompt = render(
                "error_detection",
                operation=task.label,
                instruction=task.work_instruction,
                components=task.required_components,
                tools=task.required_tools,
            )
            label = "Error detection"
        else:
            prompt = render(
                "error_detection_recheck",
                instruction=task.work_instruction,
                problem_areas=operator_feedback.get("problem_areas"),
                details=operator_feedback.get("details"),
                previous_analysis=previous_analysis,
            )
            label = "Error detection (re-check)"

        with Timer(label) as timer:
            text = self._chat(
                self.vision_model,
                DETECTION_SYSTEM_PROMPT,
                self._vision_content(prompt, reference_image, live_image),
                self.max_tokens,
                self.detection_temperature,
            )
        return DetectionResult(text=text, has_error=parse_has_error(text), elapsed=timer.elapsed)

    def generate_correction_instructions(self, task: AssemblyTask, analysis: str) -> str:
        prompt = render(
            "correction_instructions",
            step_id=task.task_id,
            operation=task.label,
            instruction=task.work_instruction,
            analysis=analysis,
        )
        with Timer("Corrective instruction generation"):
            return self._chat(
                self.text_model, INSTRUCTION_SYSTEM_PROMPT, prompt,
                self.max_tokens, self.generation_temperature,
            )

    def generate_preventive_warning(
        self, task: AssemblyTask, error_count: int, error_records: list[dict]
    ) -> str:
        records = "\n".join(
            f"- {r['error_type']}: {r['description']} ({r['occurrences']}x)" for r in error_records
        ) or "- No detailed records available"
        prompt = render(
            "preventive_warning",
            step_id=task.task_id,
            operation=task.label,
            instruction=task.work_instruction,
            error_count=error_count,
            error_records=records,
        )
        with Timer("Preventive warning generation"):
            return self._chat(
                self.text_model, INSTRUCTION_SYSTEM_PROMPT, prompt,
                self.max_tokens, self.generation_temperature,
            )

    def generate_cue_svg(self, headline: str, message: str, cue_type: str) -> str:
        prompt = render(
            "visual_cue_svg",
            cue_type=cue_type,
            headline=headline,
            headline_color="red" if cue_type == "correction" else "yellow",
            message=message,
        )
        return self._chat(
            self.text_model, SVG_SYSTEM_PROMPT, prompt,
            self.svg_max_tokens, self.generation_temperature,
        )
