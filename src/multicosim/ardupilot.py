from __future__ import annotations

from enum import Enum
from typing import Final

from attrs import define, field, frozen

from multicosim.docker.simulation import ContainerSimulation, ContainerSimulator

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


@frozen()
class FirmwareOptions:
    vehicle: Vehicle = field(default=Vehicle.COPTER)
    frame: str = field(default="quad")
    param_files: list[str] = field(factory=list)
    image: str = field(default=f"ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:{__version__}")


class ArduPilotFirmwareNode(_sims.CommunicationNode[FirmwareOptions, Result]):
    def __init__(self, node: ArduPilotGazeboNode):
        self._node = node

    def send(self, msg: FirmwareOptions) -> Result:
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


@frozen()
class Environment(_fw.Environment):
    gazebo_host: str


@define()
class ArduPilotComponent(_sims.Component[Environment, _fw.FirmwareContainerNode[Start, Result]]):
    image: str
    vehicle: Vehicle
    frame: str
    param_files: list[str] = field(factory=list)
    remove: bool = False

    def start(self, environment: Environment) -> _fw.FirmwareContainerNode[Start, Result]:
        command = f"firmware run --vehicle {self.vehicle} --frame {self.frame} --gazebo-host {environment.gazebo_host}"

        for param_file in self.param_files:
            command += f" --param-file {param_file}"

        component = _fw.FirmwareContainerComponent(
            image=self.image,
            command=command,
            port=PORT,
            message_type=Start,
            response_type=Result,
            tty=True,
            remove=self.remove,
        )

        return component.start(environment)


@define()
class ArduPilotGazeboNode(_sims.Node):
    gazebo: _gz.GazeboContainerNode
    firmware: _fw.FirmwareContainerNode[Start, Result]

    def stop(self):
        self.firmware.stop()
        self.gazebo.stop()


class ArduPilotGazeboComponent(_sims.Component[_fw.Environment, ArduPilotGazeboNode]):
    """Component to handle sequencing of ArduPilot start-up.

    The ArduPilot firmware component needs to have access to the already-running Gazebo component
    in order to properly set the sim-host parameter for the firmware to communicate. To support
    this, we start the Gazebo container first, and then provide an augmented environment to the
    firmware component that contains the name of the Gazebo container.

    Args:
        gazebo: The gazebo component
        firmare: The ArduPilot firmware component
    """

    def __init__(self, gazebo: _gz.GazeboContainerComponent, firmware: ArduPilotComponent):
        self.gazebo = gazebo
        self.firmware = firmware

    def start(self, environment: _fw.Environment) -> ArduPilotGazeboNode:
        gz = self.gazebo.start(environment)
        env_ext = Environment(environment.client, environment.network_name, gz.node.name())
        fw = self.firmware.start(env_ext)

        return ArduPilotGazeboNode(gz, fw)


class Simulation(_sims.Simulation):
    def __init__(self, simulation: ContainerSimulation, node_id: _sims.NodeId[ArduPilotGazeboNode]):
        self.inner = simulation
        self.node = self.inner.get(node_id)

    @property
    def gazebo(self) -> _gz.GazeboContainerNode:
        return self.node.gazebo

    @property
    def firmware(self) -> ArduPilotFirmwareNode:
        return ArduPilotFirmwareNode(self.node)

    def stop(self):
        return self.inner.stop()


@frozen()
class GazeboOptions:
    image: str = "ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic"
    world: str = "/app/resources/worlds/iris_runway.sdf"


class Simulator(_sims.Simulator[_fw.Environment, Simulation]):
    def __init__(self, gazebo: GazeboOptions, firmware: FirmwareOptions, *, remove: bool = False):
        gazebo_ = _gz.GazeboContainerComponent(
            image=gazebo.image,
            template=gazebo.world,
            remove=remove,
        )

        firmware_ = ArduPilotComponent(
            image=firmware.image,
            vehicle=firmware.vehicle,
            frame=firmware.frame,
            param_files=firmware.param_files,
        )

        self.simulator = ContainerSimulator()
        self.node_id = self.simulator.add(ArduPilotGazeboComponent(gazebo_, firmware_))

    def add(self, component: _sims.Component[_fw.Environment, _sims.NodeT]) -> _sims.NodeId[_sims.NodeT]:
        return self.simulator.add(component)

    def start(self) -> Simulation:
        return Simulation(self.simulator.start(), self.node_id)

