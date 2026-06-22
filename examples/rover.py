from __future__ import annotations

import asyncio
import typing
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

import click
import numpy.random as rand
from matplotlib import patches as patches
from matplotlib import pyplot as plt
from typing_extensions import override

from multicosim import __version__, containers
from roverctl.attacks import FixedSpeed, GaussianMagnet
from roverctl.messages import Result, Start


@dataclass()
class Plot:
    trajectory: dict[float, list[float]]
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
        times = list(plot.trajectory.keys())
        ax.plot(
            [plot.trajectory[time][0] for time in times],
            [plot.trajectory[time][1] for time in times],
            plot.color,
        )

    plt.show(block=True)


PORT: typing.Final[int] = 5556

_Param: TypeAlias = click.Parameter | None
_Context: TypeAlias = click.Context | None


class Magnet(click.ParamType[GaussianMagnet]):
    name = "Magnet"

    @override
    def convert(self, value: Any, param: _Param, ctx: _Context) -> GaussianMagnet:
        if not isinstance(value, tuple):
            self.fail("Expected multiple values")

        return GaussianMagnet(value[0], value[1], rand.default_rng())


def maybe_position(m: GaussianMagnet | None) -> tuple[float, float] | None:
    if m is not None:
        return m.position

    return None


@click.command("simulation")
@click.option("-f", "--frequency", "freq", type=int, default=2)
@click.option("-s", "--speed", type=float, default=5.0)
@click.option("-m", "--magnet", type=Magnet, nargs=2, default=None)
@click.option("-v", "--verbose", is_flag=True)
def simulation(speed: float, freq: int, magnet: GaussianMagnet | None, *, verbose: bool) -> None:
    gz = containers.Gazebo(
        image="ghcr.io/cpslab-asu/multicosim/rover/gazebo:harmonic",
    )

    ctl_args = ["python3", "-m", "roverctl"]

    if verbose:
        ctl_args.append("--verbose")

    ctl_args.extend([
        "serve",
        "--port",
        str(PORT),
        "--world",
        gz.options.world,
        "--frequency",
        str(freq),
    ])

    ctl_img = f"ghcr.io/cpslab-asu/multicosim/rover/controller:{__version__}",
    ctl = containers.ConnectedComponent(
        image=ctl_img,
        command=" ".join(ctl_args),
        port=PORT,
        msg_type=Start,
        data_type=Result,
    )

    sim = containers.Simulator()
    sim.add_component(gz)
    sim.add_component(ctl, depends=[gz])

    with sim.run() as sys:
        msg = Start(magnet, FixedSpeed(magnitude=speed))
        res = asyncio.run(sys.send(ctl, msg))

    p = Plot(
        magnet=maybe_position(magnet),
        trajectory={
            step.time: [step.position[0], step.position[1]] for step in res.history
        }
    )

    plot(p)


if __name__ == "__main__":
    simulation()
