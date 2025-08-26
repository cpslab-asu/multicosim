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
    
    sim_cmd = "./Tools/autotest/sim_vehicle.py --no-configure --no-rebuild "

    match vehicle:
        case ap.Vehicle.COPTER:
            sim_cmd += "-v ArduCopter "
        case ap.Vehicle.ROVER:
            sim_cmd += "-v Rover "
        case ap.Vehicle.PLANE:
            sim_cmd += "-v ArduPlane "
        case ap.Vehicle.SUB:
            sim_cmd += "-v ArduSub "
        case _:
            raise Exception("Invalid ardupilot vehicle type!")

    sim_cmd += f"-f {frame} --model JSON --sim-address=gazebo_harmonic --out=tcpin:ardupilot_sitl:14551"

    print(f"Running ArduPilot sim using command: {sim_cmd}")
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
        print("Shutting down!")
        shutdown()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    while process.poll() is None:
        try:
            pass
        except KeyboardInterrupt:
            return shutdown()
        
    print(f"Process terminated! {process.poll()}")

@fw.firmware(msgtype=ap.Start)
def server(msg: ap.Start) -> ap.Result:
    start_ardupilot(msg.vehicle,msg.frame)

@click.group()
@click.option("--verbose", is_flag=True)
def firmware(*,verbose: bool):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)

@firmware.command("run")
@click.option("--vehicle", type=click.Choice(ap.Vehicle, case_sensitive=False), default=ap.Vehicle.COPTER)
@click.option("--frame", type=str, default="quad")
def run(vehicle: ap.Vehicle, frame: str):
    start_ardupilot(vehicle,frame)

@firmware.command("listen")
@click.option("--port", type=int, default=5556)
def listen(port: int):
    server.listen(port)

if __name__ == "__main__":
    firmware()