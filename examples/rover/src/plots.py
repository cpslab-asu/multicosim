from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from matplotlib import pyplot as plt
from matplotlib import patches as patches
from staliro import Trace


@dataclass()
class Plot:
    trajectory: Trace[list[float]]
    magnet: tuple[float, float] | None
    color: Literal["r", "g", "b", "k"] = "k"


def plot(*plots: Plot):
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
