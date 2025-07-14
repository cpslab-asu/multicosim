from __future__ import annotations

from collections.abc import Iterable, Iterator
from enum import IntEnum
from typing import Final, TypeVar

import attrs
from typing_extensions import override

from .__about__ import __version__
from .docker import Environment
from .firmware import FirmwareContainerNode, FirmwareConfig
from .gazebo import GazeboContainerNode, GazeboConfig
from .gz_firmware import GZFirmwareComponent, GZFirmwareNode, GZFirmware

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

def _create_sensor_topics(gazebo: GazeboConfig, vehicle: Vehicle):
    model = _resolve_vehicle_model(vehicle)
    return [(model,data[1],data[2]) for data in gazebo.sensor_topics]

class PX4Configuration:
    def __init__(self, configuration: Configuration, vehicle: Vehicle, world: str):
        self.mission = configuration.mission
        self.vehicle = vehicle
        self.world = world

class PX4Node(GZFirmwareNode[Configuration, States]):
    def __init__(self, gazebo_node: GazeboContainerNode, fw_node: FirmwareContainerNode[Configuration, States], vehicle: Vehicle, world: str):
        self._vehicle: Vehicle = vehicle
        self._world: str = world
        super().__init__(gazebo_node,fw_node)

    @override
    def send(self, msg: Configuration) -> States:
        return self._firmware.send(PX4Configuration(msg, self._vehicle, self._world))

class PX4Component(GZFirmwareComponent):
    def __init__(self, gazebo: GazeboConfig, vehicle: Vehicle = Vehicle.X500, *, remove: bool = False):
        self.vehicle = vehicle
        gazebo.image = "ghcr.io/cpslab-asu/multicosim/px4/gazebo:harmonic"
        gazebo.template = f"/app/resources/worlds/{gazebo.world}.sdf"
        gazebo.sensor_topics = _create_sensor_topics(gazebo,vehicle)
        gazebo.remove = remove

        fw = FirmwareConfig( 
            image=f"ghcr.io/cpslab-asu/multicosim/px4/firmware:{__version__}",
            command=f"firmware --port {DEFAULT_PORT}",
            port=DEFAULT_PORT,
            message_type=PX4Configuration,
            response_type=States,
            remove=remove,
            monitor=True,  # Early exit from PX4 firmware should be an error
        )
        super().__init__(gazebo, fw)

    def start(self, environment: Environment) -> PX4Node:
        return PX4Node(
            self.gazebo.start(environment),
            self.firmware.start(environment),
            self.vehicle,
            self.gazebo.world,
        )

class PX4(GZFirmware):
    def __init__(self, gazebo: GazeboConfig, vehicle: Vehicle = Vehicle.X500, *, remove: bool = False):
        super().__init__(PX4Component(gazebo,vehicle,remove=remove))
    
