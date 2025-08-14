from __future__ import annotations

import logging
import click
import asyncio
import subprocess
import signal

from pathlib import Path
from types import FrameType

import multicosim.docker.firmware as fw
import multicosim.px4 as px4
import multicosim.ardupilot as ap

def run_ardupilot(vehicle: ap.Vehicle, frame: str):
    logger = logging.getLogger("ardupilot.firmware.run")
    logger.addHandler(logging.NullHandler())

    workdir = Path("/opt/ardupilot")

    cmd = [
        "./waf",
        "configure",
        "--board",
        "sitl",
    ]

    waf_cmd = ["./waf"]
    
    sim_cmd = [
        "./Tools/autotest/sim_vehicle.py",
        "--no-configure",
        "--no-rebuild",
        "--frame", f"{frame}",
    ]

    match vehicle:
        case ap.Vehicle.COPTER:
            waf_cmd.append("copter")
            sim_cmd.append("--vehicle ArduCopter")
        case ap.Vehicle.ROVER:
            waf_cmd.append("rover")
            sim_cmd.append("--vehicle Rover")
        case ap.Vehicle.PLANE:
            waf_cmd.append("plane")
            sim_cmd.append("--vehicle ArduPlane")
        case ap.Vehicle.SUB:
            waf_cmd.append("sub")
            sim_cmd.append("--vehicle ArduSub")
        case _:
            raise Exception("Invalid ardupilot vehicle type!")

    logger.debug(f"Running ArduPilot waf config using command: {cmd}")
    subprocess.run(cmd, cwd=workdir, check=True, shell=True, encoding="utf-8")

    logger.debug(f"Running ArduPilot waf config using command: {waf_cmd}")
    subprocess.run(waf_cmd, cwd=workdir, shell=True, encoding="utf-8")

    logger.debug(f"Running ArduPilot sim using command: {sim_cmd}")
    return subprocess.Popen(sim_cmd, cwd=workdir, shell=True, encoding="utf-8")

def start_ardupilot(vehicle: ap.Vehicle, frame: str):
    logger = logging.getLogger("ardupilot.firmware")
    logger.addHandler(logging.NullHandler())
    logger.debug(f"Running ArduPilot firmware")

    process = run_ardupilot(vehicle, frame)

    def shutdown():
        process.kill()
        process.wait()
        return ap.Result()

    def handle(signum: int, frame: FrameType | None):
        shutdown()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGKILL, handle)

    while process.poll() is None:
        try:
            pass
        except KeyboardInterrupt:
            return shutdown()

@fw.firmware(msgtype=ap.Start)
def server(msg: ap.Start) -> ap.Result:
    start_ardupilot(msg.vehicle,msg.frame)

@click.group()
@click.option("--verbose", is_flag=True)
def firmware(*,verbose: bool):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

@click.command()
@click.option("--vehicle", type=click.Choice(ap.Vehicle, case_sensitive=False), default=ap.Vehicle.COPTER)
@click.option("--frame", type=str, default="quad")
def run(vehicle: ap.Vehicle, frame: str):
    start_ardupilot(vehicle,frame)

@click.command()
@click.option("--port", type=int, default=5556)
def listen(port: int):
    server.listen(port)

if __name__ == "__main__":
    firmware()