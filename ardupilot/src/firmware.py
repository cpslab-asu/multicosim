from __future__ import annotations

from pathlib import Path
from subprocess import Popen


def run():
    cmd = [
        "./Tools/autotest/sim_vehicle.py",
        "--vehicle", "ArduCopter",
        "--frame", "gazebo-iris",
        "--no-configure",
        "--no-rebuild",
    ]
    workdir = Path("/opt/ardupilot")

    with Popen(cmd, cwd=workdir, shell=True, encoding="utf-8"):
        pass


def main():
    print("Hello from ardupilot!")


if __name__ == "__main__":
    main()
