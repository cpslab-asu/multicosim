from __future__ import annotations

import itertools
import pathlib
import typing

import click
import numpy.random as rand
import staliro
from controller.attacks import FixedSpeed, GaussianMagnet
from controller.messages import Result, Start
from plots import Plot, plot

import multicosim
import multicosim.docker

PORT: typing.Final[int] = 5556
GZ_BASE: typing.Final[pathlib.Path] = pathlib.Path("resources/worlds/default.sdf")
GZ_WORLD: typing.Final[pathlib.Path] = pathlib.Path("/tmp/generated.sdf")


@click.command("simulation")
@click.option("-f", "--frequency", "freq", type=int, default=2)
@click.option("-s", "--speed", type=float, default=5.0)
@click.option("-m", "--magnet", type=float, nargs=2, default=None)
@click.option("-v", "--verbose", is_flag=True)
def simulation(speed: float, freq: int, magnet: tuple[float, float] | None, *, verbose: bool):
    if magnet:
        rng = rand.default_rng()
        magnet_ = GaussianMagnet(x=magnet[0], y=magnet[1], rng=rng)
    else:
        magnet_ = None

    prefix = "controller"

    if verbose:
        prefix = f"{prefix} --verbose"

    fw = multicosim.docker.FirmwareContainerComponent(
        image="ghcr.io/cpslab-asu/multicosim/rover/controller:latest",
        command=f"{prefix} serve --port {PORT}",
        port=PORT,
        message_type=Start,
        response_type=Result,
    )

    gz = multicosim.docker.GazeboContainerComponent(
        image="ghcr.io/cpslab-asu/multicosim/rover/gazebo:harmonic",
    )

    sim = multicosim.docker.ContainerSimulator(gz)
    fw_id = sim.add(fw)
    sys = sim.start()
    msg = Start(gz.world, freq, magnet_, FixedSpeed(magnitude=speed), itertools.repeat(None))
    res = sys.get(fw_id).send(msg)
    p = Plot(
        magnet=magnet,
        trajectory=staliro.Trace(
            {step.time: [step.position[0], step.position[1]] for step in res.history}
        ),
    )

    plot(p)


if __name__ == "__main__":
    simulation()
