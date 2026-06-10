from __future__ import annotations

import itertools
import pathlib
import typing
from dataclasses import dataclass
from typing import Literal

import click
import numpy.random as rand
import staliro
from controller.attacks import FixedSpeed, GaussianMagnet
from controller.messages import Result, Start
from matplotlib import patches as patches
from matplotlib import pyplot as plt
from staliro import Trace

import multicosim
import multicosim.docker


@dataclass()
class Plot:
    trajectory: Trace[list[float]]
    magnet: tuple[float, float] | None
    color: Literal["r", "g", "b", "k"] = "k"


def plot(*plots: Plot) -> None:
    _, ax = plt.subplots()
    ax.set_title("Trajectory")
    # ax.set_xlim(left=0, right=16)
    ax.set_ylim(bottom=-2, top=10)
    ax.add_patch(patches.Rectangle((0, 0), 8, 8, linewidth=1, edgecolor="r", fill=False))
    magnets = [plot.magnet for plot in plots if plot.magnet is not None]

    if magnets:
        ax.scatter(
            [magnet[0] for magnet in magnets],
            [magnet[1] for magnet in magnets],
            s=None,
            c="b",
        )

    for plot in plots:
        # ax.add_patch(patches.Circle(plot.magnet, 0.1, linewidth=1, edgecolor="b"))

        times = list(plot.trajectory.times)
        ax.plot(
            [plot.trajectory[time][0] for time in times],
            [plot.trajectory[time][1] for time in times],
            plot.color,
        )

    plt.show(block=True)


PORT: typing.Final[int] = 5556
GZ_BASE: typing.Final[pathlib.Path] = pathlib.Path("resources/worlds/default.sdf")
GZ_WORLD: typing.Final[pathlib.Path] = pathlib.Path("/tmp/generated.sdf")


@click.command("simulation")
@click.option("-f", "--frequency", "freq", type=int, default=2)
@click.option("-s", "--speed", type=float, default=5.0)
@click.option("-m", "--magnet", type=float, nargs=2, default=None)
@click.option("-v", "--verbose", is_flag=True)
def simulation(
    speed: float,
    freq: int,
    magnet: tuple[float, float] | None,
    *,
    verbose: bool,
) -> None:
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
