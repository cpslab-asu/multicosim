from __future__ import annotations

import logging
import pathlib
import signal
import socket
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

    firmware_host = socket.gethostname()
    sim_cmd += f"-f {frame} --model JSON --sim-address={gazebo_host} --out=tcpin:{firmware_host}:14551"

    for pfile in param_files:
        if not pfile.exists():
            raise ValueError(f"Parameter file {pfile} does not exist.")

        sim_cmd += f" --add-param-file {pfile}"

    logger.info(f"Running ArduPilot sim using command: {sim_cmd}")

    return subprocess.Popen(sim_cmd, cwd=workdir, shell=True, encoding="utf-8")


def start_ardupilot(
    vehicle: ap.Vehicle,
    frame: str,
    gazebo_host: str,
    param_files: list[pathlib.Path],
):
    logger = logging.getLogger("ardupilot.firmware")
    logger.addHandler(logging.NullHandler())

    process = run_ardupilot(vehicle, frame, gazebo_host, param_files)

    def shutdown():
        process.kill()
        process.wait()

        return ap.Result()

    def handle(signum: int, frame: FrameType | None):
        logger.info("Gracefully shutting down!")
        shutdown()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)

    while process.poll() is None:
        try:
            pass
        except KeyboardInterrupt:
            return shutdown()
        
    logger.info("Process terminated with code: %d", process.poll())


@fw.firmware(msgtype=ap.Start)
def server(msg: ap.Start) -> ap.Result:
    return start_ardupilot(msg.vehicle, msg.frame, msg.gazebo_host, [pathlib.Path(p) for p in msg.param_files])


@click.group()
@click.option("--verbose", is_flag=True)
def firmware(*, verbose: bool):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
    )

    logger = logging.getLogger("ardupilot.firmware")
    logger.addHandler(logging.NullHandler())
    logger.info(f"Debug output enabled: {verbose}")


@firmware.command()
@click.option("--vehicle", type=click.Choice(ap.Vehicle, case_sensitive=False), default=ap.Vehicle.COPTER)
@click.option("--frame", type=str, default="quad")
@click.option("--gazebo-host", type=str)
@click.option("--param-file", type=click.Path(dir_okay=False, path_type=pathlib.Path), multiple=True)
def run(vehicle: ap.Vehicle, frame: str, gazebo_host: str, param_file: Sequence[pathlib.Path]):
    start_ardupilot(vehicle, frame, gazebo_host, list(param_file))


@firmware.command()
@click.option("--port", type=int, default=5556)
def listen(port: int):
    server.listen(port)


if __name__ == "__main__":
    firmware()
