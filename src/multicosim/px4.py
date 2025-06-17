from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from enum import IntEnum
from typing import Final, TypeVar

import attrs
from typing_extensions import override

from .__about__ import __version__
from .docker import ContainerSimulation, ContainerSimulator, Environment, NodeId, Simulator
from .firmware import FirmwareContainerComponent, FirmwareContainerNode
from .gazebo import Backend, GazeboContainerNode
from .gazebo import GazeboContainerComponent as _GazeboContainerComponent
from .simulations import CommunicationNode, Component, Node, Simulation


class Vehicle(IntEnum):
    X500 = 0

    def __str__(self) -> str:
        if self is Vehicle.X500:
            return "x500"

        raise ValueError(f"Unknown vehicle type {self}")


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


def _mission(waypoints: Iterable[Waypoint]) -> list[Waypoint]:
    return list(waypoints)


@attrs.frozen()
class Data:
    mission: list[Waypoint] = attrs.field(converter=_mission)


@attrs.frozen()
class States(Iterable[State]):
    values: list[State]

    def __iter__(self) -> Iterator[State]:
        return iter(self.values)


__all__ = ["Pose", "PX4", "State", "Waypoint"]


T = TypeVar("T", covariant=True)


DEFAULT_PORT: Final[int] = 5556


@attrs.frozen()
class Configuration:
    mission: list[Waypoint] = attrs.field(converter=_mission)


@attrs.define()
class Gazebo:
    world: str = attrs.field(default="iris_runway")
    backend: Backend | None = attrs.field(default=None)
    step_size: float = attrs.field(default=0.001)
    sensor_topics: Mapping[str, str] = attrs.field(factory=dict)
    remove: bool = attrs.field(default=True, kw_only=True)


class GazeboContainerComponent(Component[Environment, GazeboContainerNode]):
    def __init__(self,
        world: str = "iris_runway",
        backend: Backend | None = None,
        step_size: float = 0.001,
        sensor_topics: Iterable[tuple[str, str, str]] | None = None,
        *,
        remove: bool = True,
    ):
        self.component = _GazeboContainerComponent(
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

    @classmethod
    def from_configuration(cls, config: Gazebo, model: str) -> GazeboContainerComponent:
        return cls(
            world=config.world,
            backend=config.backend,
            step_size=config.step_size,
            sensor_topics=[
                (model, sensor, topic) for sensor, topic in config.sensor_topics.items()
            ],
            remove=config.remove,
        )


def _resolve_vehicle_model(vehicle: Vehicle) -> str:
    """Determine the name of the actual model to edit.

    The names for the PX4 models loaded by the firmware are often built off of a common base model
    that contains all of the actual sensor definitions. Therefore, this function ensures that the
    proper model file is modified.

    Args:
        model: The PX4 model being simulated

    Returns:
        The name of the base model containing the sensor definitions.
    """

    if vehicle is Vehicle.X500:
        return "x500_base"

    raise ValueError(f"Unknown PX4 vehicle: {vehicle}")


class FirmwareConfiguration:
    def __init__(self, configuration: Configuration, vehicle: Vehicle, world: str):
        self.mission = configuration.mission
        self.vehicle = vehicle
        self.world = world


@attrs.define()
class PX4Node(CommunicationNode[Configuration, States]):
    gazebo: GazeboContainerNode
    _firmware: FirmwareContainerNode[FirmwareConfiguration, States]
    _vehicle: Vehicle
    _world: str

    @override
    def send(self, msg: Configuration) -> States:
        return self._firmware.send(FirmwareConfiguration(msg, self._vehicle, self._world))

    def stop(self):
        self.gazebo.stop()
        self._firmware.stop()


class PX4Component(Component[Environment, PX4Node]):
    def __init__(self, gazebo: Gazebo, vehicle: Vehicle = Vehicle.X500, *, remove: bool = False):
        self.port = 5556
        self.vehicle = vehicle
        self.gazebo = GazeboContainerComponent.from_configuration(gazebo, _resolve_vehicle_model(vehicle))
        self.firmware = FirmwareContainerComponent(
            image=f"ghcr.io/cpslab-asu/multicosim/px4/firmware:{__version__}",
            command=f"firmware --port {self.port} --world {gazebo.world} --model {vehicle}",
            port=self.port,
            message_type=FirmwareConfiguration,
            response_type=States,
            remove=remove,
        )

    def start(self, environment: Environment) -> PX4Node:
        return PX4Node(
            self.gazebo.start(environment),
            self.firmware.start(environment),
            self.vehicle,
            self.gazebo.world,
        )


@attrs.define()
class PX4Simulation(Simulation):
    """A PX4 simulation execution.

    Args:
        nodes: The executing simulation nodes
        fw_id: The id of the node executing the firmware
        gz_id: The id of the node executing the gazebo simulator
    """

    simulation: ContainerSimulation
    node_id: NodeId[PX4Node]

    @property
    def firmware(self) -> PX4Node:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id)

    @property
    def gazebo(self) -> GazeboContainerNode:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id).gazebo

    def stop(self):
        return self.simulation.stop()


NodeT = TypeVar("NodeT", bound=Node)


class PX4(Simulator[Environment, PX4Simulation]):
    """A simulator tree representing a simulation using the PX4 firmware as the system controller.

    Args:
        gazebo: The gazebo component to use for simulation
    """

    def __init__(self, gazebo: Gazebo, vehicle: Vehicle = Vehicle.X500, *, remove: bool = False):
        self.simulator = ContainerSimulator()
        self.component = PX4Component(gazebo, vehicle, remove=remove)
        self.node_id = self.simulator.add(self.component)

    @property
    def px4(self) -> PX4Component:
        return self.component

    @property
    def gazebo(self) -> GazeboContainerComponent:
        return self.component.gazebo

    @override
    def add(self, component: Component[Environment, NodeT]) -> NodeId[NodeT]:
        return self.simulator.add(component)

    @override
    def start(self) -> PX4Simulation:
        return PX4Simulation(self.simulator.start(), self.node_id)
