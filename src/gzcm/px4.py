from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Final, TypeAlias

import attrs

from gzcm import gazebo as gz
from gzcm import firmware as fw
from gzcm.__about__ import __version__
from gzcm.firmware import Pose, State, Waypoint

Mission: TypeAlias = list[fw.Waypoint]
Trace: TypeAlias = dict[float, fw.Pose]

PORT: Final[int] = 5556


@attrs.frozen()
class StartMsg:
    mission: Mission
    model: Model
    world: str


@fw.manage(
    firmware_image=f"ghcr.io/cpslab-asu/gzcm/px4/firmware:{__version__}",
    gazebo_image="ghcr.io/cpslab-asu/gzcm/px4/gazebo:harmonic",
    command=f"/usr/local/bin/firmware --port {PORT} --verbose",
    port=PORT,
    template=Path("resources/worlds/default.sdf"),
)
def firmware(world: str, mission: Mission, model: Model) -> StartMsg:
    return StartMsg(mission, model, world)


def simulate(
    mission: Mission,
    model: Model,
    gazebo: gz.Gazebo,
    *,
    remove: bool = False,
) -> Trace:
    """Execute a simulation using the PX4 using the given configuration.

    Args:
        px4cfg: The configuration for the PX4 system
        gzcfg: The configuration for the simulator
        container: The existing PX4 container to use instead of creating a new one
        client: The docker client to use, if any
        context: The ZeroMQ context to use, if any

    Returns:
        A list of poses representing the position of the vehicle in meters over the
        course of the mission provided in the PX4 configuration.
    """

    states = firmware.run(gazebo, mission=mission, model=model, remove=remove)
    return {state.time: state.pose for state in states}


DEFAULT_MISSION: Final[Mission] = [
    fw.Waypoint(47.398039859999997, 8.5455725400000002, 25),
    fw.Waypoint(47.398036222362471, 8.5450146439425509, 25),
    fw.Waypoint(47.397825620791885, 8.5450092830163271, 25),
]


@attrs.frozen()
class PX4:
    """Configuration parameters for a simulated PX4-controlled vehicle.

    Args:
        model: The vehicle model to use for the simulation
        waypoints: The mission for the vehicle to execute during the simulation
        world: The name of the Gazebo world
    """

    class Model(IntEnum):
        """PX4 Vehicle model to use for simulation.

        The X500 is a light-weight quadrotor aircraft model.
        """

        X500 = 0

    model: Model = attrs.field(default=Model.X500)

    def simulate(self, gazebo: gz.Gazebo, mission: Mission | None = None, *, remove: bool = False) -> Trace:
        return simulate(mission or DEFAULT_MISSION, self.model, gazebo, remove=remove)

Model = PX4.Model

__all__ = ["DEFAULT_MISSION", "Model", "Pose", "PX4", "State", "Waypoint", "simulate"]
