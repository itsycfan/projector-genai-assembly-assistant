"""Hardware control layer: DLP projector.

The projector (TI DLP LightCrafter Display 2000 EVM) is attached to a
BeagleBone Black. This module connects to the BeagleBone over SSH, uploads the
cue image with SFTP and runs a display script on the board, which writes the
image to the projector framebuffer.

The board-side display script is in ``hardware/projector/beaglebone/``.

Run this module on its own to project an image::

    python -m projector_assembly_assistant.projector path/to/cue.png
    python -m projector_assembly_assistant.projector          # latest cue
"""

from __future__ import annotations

import argparse
import io
import shlex
from pathlib import Path

import paramiko
from PIL import Image

from .config import Config, get_secret

SUPPORTED_FORMATS = (".png", ".jpg", ".jpeg", ".bmp")


class ProjectorController:
    """SSH/SFTP controller for the BeagleBone-driven DLP projector."""

    def __init__(self, host: str, username: str, password: str,
                 remote_dir: str, display_script: str,
                 rotate_180: bool = True, use_sudo: bool = True):
        self.host = host
        self.username = username
        self.password = password
        self.remote_dir = remote_dir.rstrip("/")
        self.remote_image_dir = f"{self.remote_dir}/images"
        self.display_script = display_script
        self.rotate_180 = rotate_180
        self.use_sudo = use_sudo
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    @classmethod
    def from_config(cls, config: Config) -> "ProjectorController":
        return cls(
            host=config.get("Projector", "HOST"),
            username=config.get("Projector", "USERNAME"),
            password=get_secret("PROJECTOR_PASSWORD"),
            remote_dir=config.get("Projector", "REMOTE_DIR"),
            display_script=config.get("Projector", "DISPLAY_SCRIPT", fallback="display_image.py"),
            rotate_180=config.getboolean("Projector", "ROTATE_180", fallback=True),
            use_sudo=config.getboolean("Projector", "USE_SUDO", fallback=True),
        )

    # Connection ------------------------------------------------------------
    def connect(self) -> bool:
        try:
            self._ssh = paramiko.SSHClient()
            # Lab setting: the board is reached over a direct USB/Ethernet link.
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(self.host, username=self.username, password=self.password, timeout=10)
            self._sftp = self._ssh.open_sftp()
            self._run(f"mkdir -p {shlex.quote(self.remote_image_dir)}")
            print(f"Connected to projector host {self.host}")
            return True
        except Exception as exc:
            print(f"Projector connection failed: {exc}")
            self.close()
            return False

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
        if self._ssh:
            self._ssh.close()
        self._sftp = self._ssh = None

    def __enter__(self) -> "ProjectorController":
        if not self.connect():
            raise ConnectionError(f"Cannot connect to projector host {self.host}")
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # Commands --------------------------------------------------------------
    def _run(self, command: str, sudo: bool = False) -> bool:
        if self._ssh is None:
            raise RuntimeError("Not connected to the projector host.")
        if sudo and self.use_sudo:
            command = f"sudo -S -p '' {command}"
        stdin, stdout, stderr = self._ssh.exec_command(command)
        if sudo and self.use_sudo:
            stdin.write(self.password + "\n")
            stdin.flush()
        status = stdout.channel.recv_exit_status()
        if status != 0:
            print(f"Remote command failed ({status}): {stderr.read().decode().strip()}")
        return status == 0

    def _prepare_image(self, path: Path) -> bytes:
        """Return the image bytes, rotated by 180 degrees if the projector is mounted upside down."""
        with Image.open(path) as img:
            if self.rotate_180:
                img = img.rotate(180)
            buffer = io.BytesIO()
            img.convert("RGB").save(buffer, format="PNG")
            return buffer.getvalue()

    def display_image(self, image_path: str | Path) -> bool:
        """Upload an image and display it on the projector."""
        image_path = Path(image_path)
        if not image_path.exists() or image_path.suffix.lower() not in SUPPORTED_FORMATS:
            print(f"Cannot project {image_path}: file missing or unsupported format.")
            return False

        safe_name = "".join(c for c in image_path.stem if c.isalnum() or c in "._-") + ".png"
        remote_file = f"{self.remote_image_dir}/{safe_name}"
        with self._sftp.open(remote_file, "wb") as f:
            f.write(self._prepare_image(image_path))

        script = f"{self.remote_dir}/{self.display_script}"
        ok = self._run(f"python3 {shlex.quote(script)} {shlex.quote(remote_file)}", sudo=True)
        if ok:
            print(f"Projected {image_path.name}")
        return ok


def project(config: Config, image_path: str | Path) -> bool:
    """Connect, project one image and disconnect."""
    controller = ProjectorController.from_config(config)
    if not controller.connect():
        return False
    try:
        return controller.display_image(image_path)
    finally:
        controller.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Project an image with the DLP projector.")
    parser.add_argument("image", nargs="?", help="Image to project (default: latest visual cue)")
    parser.add_argument("--config", help="Path to config.ini")
    args = parser.parse_args()

    config = Config(args.config)
    image = args.image
    if image is None:
        cues = sorted(config.path("VISUAL_CUES_DIR").glob("*.png"), key=lambda p: p.stat().st_mtime)
        if not cues:
            parser.error("No visual cues found; pass an image path.")
        image = cues[-1]
    project(config, image)


if __name__ == "__main__":
    main()
