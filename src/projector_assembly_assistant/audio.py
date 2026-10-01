"""Hardware control layer: audio output.

Text is synthesised with Google Text-to-Speech (gTTS), saved as MP3 and played
with the platform's native player:

* macOS: ``afplay``
* Windows: ``playsound`` (version 1.2.2)
* Linux: ``play`` from SoX

Run this module on its own to test speech output::

    python -m projector_assembly_assistant.audio "Please select the diffuser."
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import tempfile
from pathlib import Path

from gtts import gTTS


def play_audio(path: str | Path) -> bool:
    """Play an audio file and block until playback has finished."""
    path = str(path)
    system = platform.system().lower()
    try:
        if system == "darwin":
            subprocess.run(["afplay", path], check=True)
        elif system == "windows":
            from playsound import playsound

            playsound(path, block=True)
        elif system == "linux":
            subprocess.run(["play", "-q", path], check=True)
        else:
            print(f"Audio playback is not supported on {system}.")
            return False
        return True
    except FileNotFoundError:
        print("Audio player not found. On Linux install SoX: sudo apt install sox libsox-fmt-mp3")
    except Exception as exc:
        print(f"Audio playback failed: {exc}")
    return False


def speak(text: str, output_file: str | Path | None = None, lang: str = "en",
          play: bool = True) -> Path | None:
    """Synthesise ``text``, save it to ``output_file`` (MP3) and play it.

    Returns the path of the audio file, or ``None`` if synthesis failed.
    Without ``output_file``, a temporary file is used.
    """
    print(f"[voice] {text}")
    try:
        if output_file is None:
            output_file = Path(tempfile.gettempdir()) / "pga_tts.mp3"
        output_file = Path(output_file).with_suffix(".mp3")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        gTTS(text=text, lang=lang).save(str(output_file))
        if play:
            play_audio(output_file)
        return output_file
    except Exception as exc:  # gTTS needs network access
        print(f"Text-to-speech failed: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Text-to-speech test.")
    parser.add_argument("text", nargs="?", default="The assistive system audio channel is working.")
    args = parser.parse_args()
    speak(args.text)


if __name__ == "__main__":
    main()
