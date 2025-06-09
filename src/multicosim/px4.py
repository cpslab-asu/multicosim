from __future__ import annotations

from collections.abc import Generator, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, ContextManager, Final, Protocol, TypeVar, cast
from typing_extensions import override

import attrs
import docker
import docker.models.containers
import docker.models.networks
import numpy as np
import numpy.typing as npt

from . import __version__
from . import firmware as fw
from . import gazebo as gz
from .gazebo import Backend, GazeboContainerComponent, GazeboContainerNode
from .gazebo import Gazebo as _Gazebo
from .docker import ContainerSimulator, Environment, Firmware as _Firmware, FirmwareComponent, FirmwareNode, Simulation
from .docker import NodeId, Simulator
from .docker import Simulation
from .simulations import Node, simulator
from .simulations import Component

if TYPE_CHECKING:
    from numpy.typing import NDArray


@attrs.frozen()
class Waypoint:
    """A position in a mission plan for a PX4-controlled vehicle.

    Args:
        lat: The latitude to achieve
        lon: The longitude to achieve
        alt: The altitude to achieve
    """

    lat: float
    lon: float
    alt: float


@attrs.frozen()
class Pose:
    """The pose of the PX4 vehicle in meters."""

    x: float
    y: float
    z: float


@attrs.frozen()
class State:
    """The pose of the PX4 vehicle in meters, along with the associated time-stamp."""

    time: float
    pose: Pose


PORT: Final[int] = 5556


@attrs.frozen()
class StartMsg:
    mission: list[Waypoint]
    model: Model
    world: str


@attrs.frozen()
class States(Iterable[State]):
    values: list[State]

    def __iter__(self) -> Iterator[State]:
        return iter(self.values)


@fw.manage(
    firmware_image=f"ghcr.io/cpslab-asu/multicosim/px4/firmware:{__version__}",
    gazebo_image="ghcr.io/cpslab-asu/multicosim/px4/gazebo:harmonic",
    command=f"/usr/local/bin/firmware --port {PORT} --verbose",
    port=PORT,
    template=Path("resources/worlds/default.sdf"),
    rtype=States,
)
def firmware(world: str, mission: list[Waypoint], model: Model) -> StartMsg:
    return StartMsg(mission, model, world)


def simulate(
    mission: list[Waypoint],
    model: Model,
    gazebo: gz.Gazebo,
    *,
    remove: bool = False,
) -> dict[float, Pose]:
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


@attrs.frozen()
class _PX4:
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

    def simulate(
        self,
        gazebo: gz.Gazebo,
        mission: list[Waypoint] | None = None,
        *,
        remove: bool = False
    ) -> dict[float, Pose]:
        return simulate(mission or DEFAULT_MISSION, self.model, gazebo, remove=remove)

Model = PX4.Model

__all__ = ["DEFAULT_MISSION", "Model", "Pose", "PX4", "State", "Waypoint", "simulate"]


T = TypeVar("T", covariant=True)


class Attachable(Protocol[T]):
    def attach(self, container: docker.models.containers.Container) -> ContextManager[T]:
        ...


class Connectable(Protocol[T]):
    def connect(self, network: docker.models.networks.Network) -> ContextManager[T]:
        ...


@dataclass()
class Firmware:
    network: docker.models.networks.Network
    container: docker.models.containers.Container
    port: int

    def attach(self, component: Attachable[T]) -> ContextManager[T]:
        return component.attach(self.container)

    def connect(self, component: Connectable[T]) -> ContextManager[T]:
        return component.connect(self.network)

    def run(self, config: Configuration) -> npt.NDArray[np.float_]:
        ...


DEFAULT_PORT: Final[int] = 5556


@simulator
def px4(*, port: int = DEFAULT_PORT) -> Generator[Firmware, None, None]:
    client = docker.from_env()
    network_name = ""
    network = client.networks.create(network_name)
    container = client.containers.run(
        image="",
        command="",
        detach=True,
        network=network_name,
        ports={
            f"{port}/tcp": None,
        }
    )

    try:
        yield Firmware(network, container, port)
    finally:
        container.reload()

        if container.status != "exited":
            ...


def simulate(
    config: Configuration,
    gazebo: Gazebo,
    *,
    port: int = DEFAULT_PORT,
    remove: bool = False
) -> npt.NDArray[np.float_]:
    system = px4(port=port)

    with system.start() as fw, fw.attach(gazebo):
        result = fw.run(config)

    return result


def _mission(waypoints: Iterable[Waypoint]) -> list[Waypoint]:
    return list(waypoints)


@attrs.frozen()
class Configuration:
    mission: list[Waypoint] = attrs.field(converter=_mission)
    model: str = attrs.field(default="x500")


class Gazebo(Component[Environment, GazeboContainerNode]):
    def __init__(self,
        world: str = "iris_runway",
        backend: Backend | None = None,
        step_size: float = 0.001,
        sensor_topics: Mapping[str, str] | None = None,
        *,
        remove: bool = True,
    ):
        self.component = GazeboContainerComponent(
            image=f"ghcr.io/cpslab-asu/multicosim/px4/gazebo:{__version__}",
            template=f"/app/resources/worlds/{world}.sdf",
            backend=backend,
            step_size=step_size,
            sensor_topics=sensor_topics,
            remove=remove,
        )

    @property
    def world(self) -> str:
        return self.component.world

    @override
    def start(self, environment: Environment) -> GazeboContainerNode:
        return self.component.start(environment)


@attrs.define()
class PX4Simulation:
    """A PX4 simulation execution.

    Args:
        nodes: The executing simulation nodes
        fw_id: The id of the node executing the firmware
        gz_id: The id of the node executing the gazebo simulator
    """

    simulation: Simulation
    fw_id: NodeId[FirmwareNode]
    gz_id: NodeId[GazeboContainerNode]

    @property
    def firmware(self) -> FirmwareNode[Configuration, NDArray[np.float64]]:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.fw_id)

    @property
    def gazebo(self) -> GazeboContainerNode:
        """The simulation node of the executing gazebo simulator."""

        return self.simulation.get(self.gz_id)


NodeT = TypeVar("NodeT", bound=Node)


class PX4(Simulator[Environment, PX4Simulation]):
    """A simulator tree representing a simulation using the PX4 firmware as the system controller.

    Args:
        gazebo: The gazebo component to use for simulation
    """

    def __init__(self, gazebo: Gazebo):
        port = 5556
        firmware = FirmwareComponent(
            image=f"ghcr.io/cpslab-asu/multicosim/px4/firmware:{__version__}",
            command=f"firmware --port {port} --world {gazebo.world}",
            port=port,
            message_type=Configuration,
            response_type=np.ndarray,
        )
        
        self.simulator = ContainerSimulator()
        self.firmware_id = self.simulator.add(firmware)
        self.gazebo_id = self.simulator.add(gazebo)

    @override
    def add(self, component: Component[Environment, NodeT]) -> NodeId[NodeT]:
        return self.simulator.add(component)

    @override
    def start(self) -> PX4Simulation:
        return PX4Simulation(self.simulator.start(), self.firmware_id, self.gazebo_id)
