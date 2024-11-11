from __future__ import annotations

from enum import IntEnum
from logging import NullHandler, getLogger
from pathlib import Path
from typing import ContextManager, Final, TypeAlias

import attrs
import docker
import docker.models.containers
import zmq

from gzcm import gazebo as gz
from gzcm.__about__ import __version__
from gzcm.firmware import Firmware, Ports, Waypoint, Pose

Client: TypeAlias = docker.DockerClient
Container: TypeAlias = docker.models.containers.Container
Mission: TypeAlias = list[Waypoint]
Trace: TypeAlias = dict[float, Pose]

GZ_IMG: Final[str] = "ghcr.io/cpslab-asu/gzcm/px4/gazebo:harmonic"
PX4_IMG: Final[str] = f"ghcr.io/cpslab-asu/gzcm/px4/firmware:{__version__}"
BASE: Final[Path] = Path("resources/worlds/default.sdf")
WORLD: Final[Path] = Path("/tmp/generated.sdf")
DEFAULT_MISSION: Final[Mission] = [
    Waypoint(47.398039859999997, 8.5455725400000002, 25),
    Waypoint(47.398036222362471, 8.5450146439425509, 25),
    Waypoint(47.397825620791885, 8.5450092830163271, 25),
]


class Model(IntEnum):
    """PX4 Vehicle model to use for simulation.

    The X500 is a light-weight quadrotor aircraft model.
    """

    X500 = 0


def firmware(name: str | None = None, *, client: Client, remove: bool = False) -> ContextManager[Firmware]:
    """Create and execute a PX4 simulation.

    Args:
        client: The docker client to use to create the container
    """

    if name is not None:
        return Firmware.find(name, client=client)

    return Firmware.start(PX4_IMG, command="firmware --verbose", ports=Ports(), client=client, remove=remove)


@attrs.frozen()
class StartMsg:
    mission: Mission
    model: Model
    world: str


def simulate(
    mission: Mission,
    model: Model,
    world: str,
    gazebo: gz.Gazebo,
    *,
    container: str | None = None,
    client: Client | None = None,
    context: zmq.Context | None = None,
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

    if not client:
        client = docker.from_env()

    if not context:
        context = zmq.Context.instance()

    path = Path(f"/tmp/{world}.sdf")
    logger = getLogger("gzcm.px4")
    logger.addHandler(NullHandler())

    with firmware(container, client=client, remove=remove) as fw:
        with gz.gazebo(gazebo, fw.container, image=GZ_IMG, base=BASE, world=path, remove=remove, client=client):
            logger.debug("Running simulation...")

            states = fw.run(StartMsg(mission, model, world), context=context)
            trace = {state.time: state.pose for state in states}

            logger.debug("Simulation complete.")

    return trace


@attrs.frozen()
class PX4:
    """Configuration parameters for a simulated PX4-controlled vehicle.

    Args:
        model: The vehicle model to use for the simulation
        waypoints: The mission for the vehicle to execute during the simulation
        world: The name of the Gazebo world
    """
    DEFAULT_MISSION = DEFAULT_MISSION
    Model = Model

    model: Model = attrs.field(default=Model.X500)
    world: str = attrs.field(default="generated")

    def simulate(
        self,
        mission: Mission,
        gazebo: gz.Gazebo,
        *,
        remove: bool = False,
        container: str | None = None,
        client: Client | None = None,
        context: zmq.Context | None = None,
    ) -> Trace:
        return simulate(
            mission=mission,
            model=self.model,
            world=self.world,
            gazebo=gazebo,
            remove=remove,
            container=container,
            client=client,
            context=context,
        )
