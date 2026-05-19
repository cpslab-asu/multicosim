from __future__ import annotations

from enum import IntEnum
from typing import Final

import attrs
import typing_extensions

from . import __version__
from . import containers as _containers
from . import gazebo as _gz
from . import simulations as _simulations

DEFAULT_PORT: Final[int] = 5556


class Vehicle(IntEnum):
    X500 = 0

    @typing_extensions.override
    def __str__(self) -> str:
        if self is Vehicle.X500:
            return "x500"

        raise ValueError(f"Unknown vehicle type {self}")


@attrs.define()
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


@attrs.define()
class Mission:
    waypoints: list[Waypoint]


@attrs.define()
class Configuration:
    mission: Mission
    vehicle: Vehicle
    world: str


@attrs.define()
class Pose:
    lat: float
    lon: float
    alt: float


@attrs.define()
class Step:
    time: float
    pose: Pose


@attrs.define()
class History:
    steps: list[Step]


@attrs.frozen()
class Firmware:
    vehicle: Vehicle = attrs.field(default=Vehicle.X500)
    port: int = attrs.field(default=DEFAULT_PORT)


@attrs.define()
class FirmwareComponent(_containers.ConnectedComponent[Configuration, History]):
    vehicle: Vehicle = attrs.field(kw_only=True)


@attrs.frozen()
class Simulation(_simulations.Simulation):
    simulation: _containers.Simulation
    firmware: FirmwareComponent
    gazebo: _containers.Gazebo

    async def run_mission(self, mission: Mission) -> History:
        return await self.simulation.send(
            self.firmware, Configuration(mission, self.firmware.vehicle, self.gazebo.world)
        )

    @typing_extensions.override
    def stop(self):
        self.simulation.stop()


class PX4(_simulations.Simulator[_containers.Context, Simulation]):
    def __init__(self, firmware: Firmware, gazebo: _gz.Options | None = None):
        # Use default Gazebo options if none are provided
        if gazebo is None:
            gazebo = _gz.Options()

        self.gazebo: _containers.Gazebo = _containers.Gazebo(
            image="ghcr.io/cpslab-asu/multicosim/px4/gazebo:harmonic",
            options=gazebo,
        )

        self.firmware: FirmwareComponent = FirmwareComponent(
            image=f"ghcr.io/cpslab-asu/multicosim/px4/firmware:{__version__}",
            command=f"firmware --port {firmware.port}",
            port=firmware.port,
            msg_type=Configuration,
            data_type=History,
            vehicle=firmware.vehicle,
        )

        self.simulator: _containers.Simulator = _containers.Simulator()
        self.simulator.add_component(self.gazebo)
        self.simulator.add_component(self.firmware, depends=[self.gazebo])

    @typing_extensions.override
    def start(self) -> Simulation:
        return Simulation(self.simulator.start(), self.firmware, self.gazebo)
