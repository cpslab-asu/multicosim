from __future__ import annotations

from typing import Final, Any

from attrs import field, frozen, define
from enum import Enum
from typing_extensions import override

from .__about__ import __version__
from .docker.firmware import (
    FirmwareConfig,
    GazeboFirmwareSimulator,
    JointGazeboFirmwareComponent,
    JointGazeboFirmwareNode,
)
from .docker.gazebo import BaseGazeboConfig, GazeboConfig, GazeboContainerNode
from .docker.simulation import Environment

PORT: Final[int] = 5556

class Vehicle(Enum):
    NONE = 0
    COPTER = 1
    PLANE = 2
    ROVER = 3
    SUB = 4

    def __str__(self):
        match self.value:
            case 0:
                return "none"
            case 1:
                return "copter"
            case 2:
                return "plane"
            case 3:
                return "rover"
            case 4:
                return "sub"

@frozen()
class Start:
    vehicle: Vehicle = field()
    frame: str = field(default="")
    world: str = field(default="")

@frozen()
class Pose:
    x: float = field()
    y: float = field()
    z: float = field()

@frozen()
class State:
    time: float = field()
    pose: Pose = field()

@frozen()
class Result:
    trajectory: list[State] = field()

class ArduPilotComponent(JointGazeboFirmwareComponent):
    def __init__(
        self, gazebo: BaseGazeboConfig, *, vehicle: Vehicle = Vehicle.NONE, frame: str = "", remove: bool = False
    ):
        gz = GazeboConfig(
            image="ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic",
            template=f"/app/resources/worlds/{gazebo.world}.sdf",
            backend=gazebo.backend,
            step_size=gazebo.step_size,
            remove=remove,
        )

        command = "firmware "

        if vehicle != Vehicle.NONE and frame != "":
            command += f"run --vehicle {str(vehicle)} --frame {frame}"
        else:
            command += f"listen --port {PORT}"

        fw = FirmwareConfig(
            image=f"ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:{__version__}",
            command=command,
            port=PORT,
            message_type=Start,
            response_type=Result,
            remove=remove,
            monitor=True,  # Early exit from PX4 firmware should be an error
        )

        super().__init__(gz, fw)

    def start(self, environment: Environment) -> JointGazeboFirmwareNode:
        return JointGazeboFirmwareNode(
            self.gazebo.start(environment),
            self.firmware.start(environment),
        )


class ArduPilot(GazeboFirmwareSimulator):
    def __init__(
        self, gazebo: BaseGazeboConfig, *, vehicle: Vehicle = Vehicle.NONE, frame: str = "", remove: bool = False
    ):
        super().__init__(ArduPilotComponent(gazebo, vehicle=vehicle, frame=frame, remove=remove))