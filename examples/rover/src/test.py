from __future__ import annotations

import itertools
import pathlib
import typing

import click
import multicosim
import numpy.random as rand
import staliro
import staliro.optimizers
import staliro.specifications.rtamt

from controller.attacks import FixedSpeed, GaussianMagnet, SpeedController, Magnet
from controller.messages import Start, Result
from plots import Plot, plot

PORT: typing.Final[int] = 5556
GZ_BASE: typing.Final[pathlib.Path] = pathlib.Path("resources/worlds/default.sdf")
GZ_WORLD: typing.Final[pathlib.Path] = pathlib.Path("/tmp/generated.sdf")


def firmware(*, verbose: bool):
    prefix = "controller"

    if verbose:
        prefix = f"{prefix} --verbose"

    @multicosim.manage(
        firmware_image="ghcr.io/cpslab-asu/multicosim/rover/controller:latest",
        gazebo_image="ghcr.io/cpslab-asu/multicosim/rover/gazebo:harmonic",
        command=f"{prefix} serve --port {PORT}",
        port=PORT,
        rtype=Result,
    )
    def inner(world: str, magnet: Magnet | None, speed: SpeedController | None, freq: int) -> Start:
        return Start(world, freq, magnet, speed, commands=itertools.repeat(None))

    return inner


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

    gazebo = multicosim.Gazebo()
    firmware_ = firmware(verbose=verbose)
    result = firmware_.run(gazebo, freq=freq, magnet=magnet_, speed=FixedSpeed(speed))
    p = Plot(
        magnet=magnet,
        trajectory=staliro.Trace({
            step.time: [step.position[0], step.position[1]] for step in result.history
        }),
    )

    plot(p)


if __name__ == "__main__":
    simulation()
