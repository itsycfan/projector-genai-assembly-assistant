# Projector Setup

Visual cues are projected by a **TI DLP® LightCrafter™ Display 2000 EVM** (DLPDLCR2000EVM) mounted as a cape on a **BeagleBone Black**. The workstation PC talks to the BeagleBone over SSH, uploads each cue image with SFTP, and runs `display_image.py` on the board to write the image to the projector framebuffer.

```
Workstation PC ──USB networking / Ethernet (SSH, SFTP)──▶ BeagleBone Black ──cape──▶ DLPDLCR2000EVM
```

## Contents

| Path | Runs on | Purpose |
|---|---|---|
| `beaglebone/display_image.py` | BeagleBone | Shows an image on the projector framebuffer (called by the main application) |
| `beaglebone/test_patterns.py` | Any | Generates geometry and colour-bar test patterns at 640×360 |
| `beaglebone/dlp_video_test.py` | BeagleBone | Bring-up test: configures the DLP controller over I2C and plays a video |
| `overlay/DLPDLCR2000-00A0.dts` | BeagleBone | Device-tree overlay for the DLPDLCR2000 cape (GPL-2.0, © Texas Instruments) |

## 1. Prepare the BeagleBone Black

1. Flash a recent Debian image for the BeagleBone Black to a microSD card and boot the board from it.
2. Connect the board to the PC over USB. With USB networking, the board is reachable at `192.168.7.2`.
3. Log in over SSH and install the dependencies:
   ```bash
   ssh debian@192.168.7.2
   sudo apt update
   sudo apt install python3-pil python3-numpy python3-smbus mplayer
   ```
4. Change the default password of the `debian` user.

## 2. Enable the DLPDLCR2000 cape overlay

The projector needs the DLPDLCR2000 device-tree overlay so that the LCD interface and I2C pins are set up. If the overlay that comes with your image does not work, compile the one provided here:

```bash
# on the BeagleBone (requires the bb.org-overlays build environment)
dtc -O dtb -o DLPDLCR2000-00A0.dtbo -b 0 -@ DLPDLCR2000-00A0.dts
sudo cp DLPDLCR2000-00A0.dtbo /lib/firmware/
```

Then load it at boot by adding the following line to `/boot/uEnv.txt` and rebooting:

```
dtb_overlay=/lib/firmware/DLPDLCR2000-00A0.dtbo
```

After the reboot, check that the framebuffer exists:

```bash
cat /sys/class/graphics/fb0/virtual_size    # e.g. 640,360
```

Useful references:

- [TI E2E FAQ: DLPDLCR2000EVM quick-start tutorial](https://e2e.ti.com/support/dlp-products-group/dlp/f/dlp-products-forum)
- [TI E2E FAQ: DLPDLCR2000EVM BBB cape overlay customisation](https://e2e.ti.com/support/dlp-products-group/dlp/f/dlp-products-forum/663939/faq-dlpdlcr2000evm-bbb-cape-overlay-customization)
- [beagleboard/bb.org-overlays](https://github.com/beagleboard/bb.org-overlays)
- [DLPDLCR2000EVM user's guide and DLPC2607 programmer's guide](https://www.ti.com/tool/DLPDLCR2000EVM)

## 3. Install the display script

Copy the script to the directory set as `REMOTE_DIR` in `config/config.ini`:

```bash
scp hardware/projector/beaglebone/display_image.py debian@192.168.7.2:/tmp/
ssh debian@192.168.7.2 "sudo mkdir -p /opt/scripts/device/bone/capes/DLPDLCR2000/images && \
  sudo mv /tmp/display_image.py /opt/scripts/device/bone/capes/DLPDLCR2000/ && \
  sudo chown -R debian:debian /opt/scripts/device/bone/capes/DLPDLCR2000"
```

## 4. Test from the workstation

```bash
python hardware/projector/beaglebone/test_patterns.py outputs/test_patterns
export PROJECTOR_PASSWORD="..."
python -m projector_assembly_assistant.projector outputs/test_patterns/test_pattern.png
```

The test pattern should appear on the workbench. If the projector is mounted upside down, keep `ROTATE_180 = true` in the configuration.

## Security note

The default setup uses password authentication over a direct, local USB link, which is a laboratory setting. For any networked deployment, use SSH key authentication, configure passwordless `sudo` for the display script only, and set `USE_SUDO = false` if it is not needed.
