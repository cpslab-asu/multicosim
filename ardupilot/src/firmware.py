from __future__ import annotations

import logging
import pathlib
import signal
import subprocess
import typing

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType

import click

import multicosim.ardupilot as ap
import multicosim.docker.firmware as fw


def run_ardupilot(
    vehicle: ap.Vehicle,
    frame: str,
    gazebo_host: str,
    firmware_host: str,
    param_files: list[pathlib.Path],
):
    logger = logging.getLogger("ardupilot.firmware.run")
    logger.addHandler(logging.NullHandler())

    workdir = pathlib.Path("/opt/ardupilot")
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

    sim_cmd += f"-f {frame} --model JSON --sim-address={gazebo_host} --out=tcpin:{firmware_host}:14551"

    for pfile in param_files:
        sim_cmd += f" --add-param-file {pfile}"

    logger.debug(f"Running ArduPilot sim using command: {sim_cmd}")
    return subprocess.Popen(sim_cmd, cwd=workdir, shell=True, encoding="utf-8")


def start_ardupilot(
    vehicle: ap.Vehicle,
    frame: str,
    gazebo_host: str,
    firmware_host: str,
    param_files: list[pathlib.Path],
):
    logger = logging.getLogger("ardupilot.firmware")
    logger.addHandler(logging.NullHandler())
    logger.debug("Running ArduPilot firmware")

    process = run_ardupilot(vehicle, frame, gazebo_host, firmware_host, param_files)

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
    return start_ardupilot(msg.vehicle, msg.frame, msg.gazebo_host, msg.firmware_host, msg.param_files)


@click.group()
@click.option("--verbose", is_flag=True)
def firmware(*, verbose: bool):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
    )


@firmware.command()
@click.option("--vehicle", type=click.Choice(ap.Vehicle, case_sensitive=False), default=ap.Vehicle.COPTER)
@click.option("--frame", type=str, default="quad")
@click.option("--param-file", type=click.Path(), multiple=True)
def run(vehicle: ap.Vehicle, frame: str, param_files: Sequence[pathlib.Path]):
    start_ardupilot(vehicle, frame, list(param_files))


@firmware.command()
@click.option("--port", type=int, default=5556)
def listen(port: int):
    server.listen(port)


if __name__ == "__main__":
    firmware()
