from __future__ import annotations

from enum import Enum
from typing import Final

from attrs import field, frozen

from . import simulations as _sims
from .__about__ import __version__
from .docker import firmware as _fw
from .docker import gazebo as _gz

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
class ArduPilotOptions:
    vehicle: Vehicle = field(default=Vehicle.COPTER)
    frame: str = field(default="quad")
    param_files: list[str] = field(factory=list)


@frozen()
class Start:
    vehicle: Vehicle = field()
    frame: str = field()
    param_files: list[str] = field()
    gazebo_host: str = field()
    firmware_host: str = field()


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


def _get_image(image: str):
    if image == "" or image == None:
        return "ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic"
    else:
        return image


class ArduPilotFirmwareNode(_sims.CommunicationNode[ArduPilotOptions, Result]):
    def __init__(self, node: _fw.JointGazeboFirmwareNode[Start, Result]):
        self._node = node

    def send(self, msg: ArduPilotOptions) -> Result:
        gazebo = self._node.gazebo
        firmware = self._node.firmware
        msg_ = Start(
            vehicle=msg.vehicle,
            frame=msg.frame,
            param_files=msg.param_files,
            gazebo_host=gazebo.node.name(),
            firmware_host=firmware.node.name(),
        )

        return firmware.send(msg_)

    def stop(self):
        # Only stop the firmware node because this node is supposed to only represent the firmware
        # component even though we store the joint component in order to access the gazebo information
        return self._node.firmware.stop()


class ArduPilotGazeboComponent(_fw.JointGazeboFirmwareComponent):
    def __init__(
        self,
        gazebo: _gz.GazeboConfig,
        *,
        name: str = "",
        vehicle: Vehicle = Vehicle.NONE,
        frame: str = "",
        remove: bool = False,
    ):
        gz = _gz.GazeboConfig(
            image=_get_image(gazebo.image),
            template=gazebo.template,
            world=gazebo.world,
            backend=gazebo.backend,
            step_size=gazebo.step_size,
            name=gazebo.name,
            remove=remove,
        )

        command = "firmware "

        if vehicle != Vehicle.NONE and frame != "":
            command += f"run --vehicle {str(vehicle)} --frame {frame}"
        else:
            command += f"listen --port {PORT}"

        fw = _fw.FirmwareConfig(
            image=f"ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:{__version__}",
            command=command,
            port=PORT,
            message_type=Start,
            response_type=Result,
            name=name,
            tty=True,
            remove=remove,
            monitor=True,  # Early exit from PX4 firmware should be an error
        )

        super().__init__(gz, fw)

    def start(self, environment: _fw.Environment) -> _fw.JointGazeboFirmwareNode:
        return _fw.JointGazeboFirmwareNode(
            self.gazebo.start(environment),
            self.firmware.start(environment),
        )


class Simulation(_sims.Simulation):
    def __init__(self, simulation: _fw.GazeboFirmwareSimulation):
        self.inner = simulation

    @property
    def gazebo(self) -> _gz.GazeboContainerNode:
        return self.inner.gazebo

    @property
    def firmware(self) -> ArduPilotFirmwareNode:
        return ArduPilotFirmwareNode(self.inner.simulation.get(self.inner.node_id))

    def stop(self):
        return self.inner.stop()


class Simulator(_sims.Simulator[_fw.Environment, Simulation]):
    def __init__(
        self,
        gazebo: _gz.GazeboConfig,
        *,
        name: str = "",
        vehicle: Vehicle = Vehicle.NONE,
        frame: str = "",
        remove: bool = False,
    ):
        self.component = ArduPilotGazeboComponent(
            gazebo=gazebo,
            name=name,
            vehicle=vehicle,
            frame=frame,
            remove=remove,
        )
        self.simulator = _fw.GazeboFirmwareSimulator(self.component)

    def start(self) -> Simulation:
        return Simulation(self.simulator.start())

