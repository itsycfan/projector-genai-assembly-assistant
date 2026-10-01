"""Visual cue generation for projection.

The generative model writes an SVG cue. The cue is validated and rendered to
PNG with CairoSVG so it can be projected. If the model returns invalid SVG, a
local high-contrast template is used instead, so the operator always receives
a cue.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from .utils import Timer

VIEWBOX = "0 0 800 600"
_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)


def sanitize_svg(raw: str) -> str | None:
    """Extract a usable SVG document from a model response, or return ``None``."""
    match = _SVG_RE.search(raw or "")
    if not match:
        return None
    svg = match.group(0)
    if "xmlns=" not in svg:
        svg = svg.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    if "viewBox" not in svg:
        svg = svg.replace("<svg", f'<svg viewBox="{VIEWBOX}"', 1)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg


def template_svg(headline: str, message: str, cue_type: str = "correction") -> str:
    """Build a high-contrast cue locally, without the generative model."""
    headline_color = "red" if cue_type == "correction" else "yellow"
    lines = textwrap.wrap(" ".join(message.split()), width=38)[:4]
    text_rows = "\n".join(
        f'    <text x="400" y="{300 + i * 40}" text-anchor="middle" font-family="Arial" '
        f'font-size="26" font-weight="bold" fill="black">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{VIEWBOX}">
  <rect width="100%" height="100%" fill="black"/>
  <circle cx="400" cy="90" r="36" fill="{headline_color}"/>
  <text x="400" y="106" text-anchor="middle" font-family="Arial" font-size="48" font-weight="bold" fill="black">!</text>
  <text x="400" y="190" text-anchor="middle" font-family="Arial" font-size="36" font-weight="bold" fill="{headline_color}">{escape(headline)}</text>
  <rect x="50" y="240" width="700" height="220" fill="yellow"/>
{text_rows}
</svg>
"""


def render_svg(svg: str, svg_path: Path, png_path: Path) -> Path:
    """Save the SVG and render it to PNG."""
    import cairosvg  # imported lazily: requires the Cairo system library

    svg_path.parent.mkdir(parents=True, exist_ok=True)
    svg_path.write_text(svg, encoding="utf-8")
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(png_path))
    return png_path


def create_visual_cue(genai, headline: str, message: str, cue_type: str,
                      output_dir: Path, stem: str) -> Path:
    """Generate, validate and render a visual cue. Returns the PNG path.

    ``cue_type`` is either ``"correction"`` or ``"warning"``.
    """
    output_dir = Path(output_dir)
    svg_path = output_dir / f"{stem}.svg"
    png_path = output_dir / f"{stem}.png"

    with Timer("Visual cue generation"):
        svg = None
        if genai is not None:
            try:
                svg = sanitize_svg(genai.generate_cue_svg(headline, message, cue_type))
            except Exception as exc:  # network or API failure
                print(f"Visual cue generation failed ({exc}); using local template.")
        if svg is not None:
            try:
                return render_svg(svg, svg_path, png_path)
            except Exception as exc:  # malformed SVG
                print(f"Generated SVG could not be rendered ({exc}); using local template.")
        return render_svg(template_svg(headline, message, cue_type), svg_path, png_path)
