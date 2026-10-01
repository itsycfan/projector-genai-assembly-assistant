#!/usr/bin/env python3
"""Projector bring-up test: configure the DLP controller over I2C and play a video.

Runs on the BeagleBone Black with the DLPDLCR2000 cape overlay loaded.
Requires the `smbus` Python package and `mplayer`.

Usage:
    sudo python3 dlp_video_test.py [video_file]
"""

import subprocess
import sys
import time

import smbus

I2C_BUS = 2          # The BeagleBone Black exposes the cape I2C on bus 2
SLAVE_ADDR = 0x1B    # I2C address of the DLPC2607 controller


def init_i2c():
    try:
        return smbus.SMBus(I2C_BUS)
    except Exception as exc:
        print(f"Failed to initialise I2C: {exc}")
        return None


def send_i2c_command(bus, command):
    try:
        bus.write_i2c_block_data(SLAVE_ADDR, command[0], command[1:])
        time.sleep(0.1)
    except Exception as exc:
        print(f"Failed to send I2C command: {exc}")


def init_dlp(bus):
    send_i2c_command(bus, [0x0B, 0x00, 0x00, 0x00, 0x00])  # system reset
    time.sleep(1)
    send_i2c_command(bus, [0x0C, 0x00, 0x00, 0x00, 0x1B])  # video source: external
    send_i2c_command(bus, [0x0D, 0x00, 0x00, 0x00, 0x03])  # video format: RGB888
    send_i2c_command(bus, [0x0E, 0x00, 0x00, 0x00, 0x02])  # resolution: nHD landscape 640x360


def play_video(video_file):
    cmd = ["mplayer", "-vo", "fbdev2:/dev/fb0", "-fs", video_file]
    try:
        process = subprocess.run(cmd, capture_output=True)
        if process.returncode != 0:
            print(f"Video playback failed: {process.stderr.decode()}")
        return process.returncode
    except Exception as exc:
        print(f"Failed to run mplayer: {exc}")
        return -1


def main():
    video = sys.argv[1] if len(sys.argv) > 1 else "nhd_test.mp4"
    print("Initialising DLP display...")
    bus = init_i2c()
    if not bus:
        return
    init_dlp(bus)
    time.sleep(2)
    print(f"Playing {video}...")
    print("Playback finished" if play_video(video) == 0 else "Playback failed")


if __name__ == "__main__":
    main()
