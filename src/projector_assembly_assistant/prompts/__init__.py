"""Prompt templates used by the generative AI layer.

Templates are plain-text files in this folder and use ``$placeholder`` syntax
(:class:`string.Template`), so they can be edited without touching the code.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parent


def render(name: str, **values) -> str:
    """Load ``<name>.txt`` and substitute ``values``.

    Missing values are left as-is rather than raising an error.
    """
    template = Template((PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8"))
    cleaned = {k: ("None" if v is None else str(v)) for k, v in values.items()}
    return template.safe_substitute(cleaned)
