from __future__ import annotations

from enum import Enum
from typing import Final

from attrs import define, field, frozen
from typing_extensions import override

from . import docker
from . import simulations as _sims
from .__about__ import __version__

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
class FirmwareOptions:
    """Options for ArduPilot SITL firmware.

    Args:
        vehicle: The vehicle model to use for control
        frame: The physical configuration of the system
        param_files: Additional ArduPilot parameter files
        image: The ArduPilot firmware container image
    """

    vehicle: Vehicle = field(default=Vehicle.COPTER)
    frame: str = field(default="quad")
    param_files: list[str] = field(factory=list)
    image: str = field(default=f"ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:{__version__}")


class ArduPilotFirmwareNode(_sims.Node):
    def __init__(self, node: ArduPilotGazeboNode):
        self._node: ArduPilotGazeboNode = node

    @override
    def stop(self):
        # Only stop the firmware node because this node is supposed to only represent the firmware
        # component even though we store the joint component in order to access the gazebo information
        return self._node.firmware.stop()


@frozen()
class Environment(docker.Environment):
    gazebo_host: str
    gcs_host: str | None = None


@define()
class ArduPilotComponent(_sims.Component[Environment, ArduPilotFirmwareNode]):
    """Component repesenting the ArduPilot SITL firmware.

    Args:
        image: The container image to use
        vehicle: The vehicle model to use for control
        frame: The physical configuration of the system
        param_files: Additional ArduPilot parameter files
        remove: Remove the container after simulation exits
    """

    image: str
    vehicle: Vehicle
    frame: str
    param_files: list[str] = field(factory=list)
    remove: bool = False

    @override
    def start(self, environment: Environment) -> ArduPilotFirmwareNode:
        command = f"firmware --vehicle {self.vehicle} --frame {self.frame} --gazebo-host {environment.gazebo_host}"

        for param_file in self.param_files:
            command += f" --param-file {param_file}"

        if environment.gcs_host is not None:
            command += f" --gcs-host {environment.gcs_host}"

        component = docker.FirmwareContainerComponent(
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
    gazebo: docker.GazeboContainerNode
    firmware: docker.FirmwareContainerNode[Start, Result]

    def stop(self):
        self.firmware.stop()
        self.gazebo.stop()


class ArduPilotGazeboComponent(_sims.Component[docker.Environment, ArduPilotGazeboNode]):
    """Component to handle sequencing of ArduPilot start-up.

    The ArduPilot firmware component needs to have access to the already-running Gazebo component
    in order to properly set the sim-host parameter for the firmware to communicate. To support
    this, we start the Gazebo container first, and then provide an augmented environment to the
    firmware component that contains the name of the Gazebo container.

    Args:
        gazebo: The gazebo component
        firmare: The ArduPilot firmware component
    """

    def __init__(self, gazebo: docker.GazeboContainerComponent, firmware: ArduPilotComponent):
        self.gazebo = gazebo
        self.firmware = firmware

    @override
    def start(self, environment: docker.Environment) -> ArduPilotGazeboNode:
        gz = self.gazebo.start(environment)
        env_ext = Environment(environment.client, environment.network_name, gz.node.name())
        fw = self.firmware.start(env_ext)

        return ArduPilotGazeboNode(gz, fw)


class Simulation(_sims.Simulation):
    """Running ArduPilot simulation using SITL firmware and Gazebo.

    Attributes:
        gazebo: The gazebo simulation node
        firmware: The SITL firmware simulation node
    """

    def __init__(
        self, simulation: docker.ContainerSimulation, node_id: _sims.NodeId[ArduPilotGazeboNode]
    ):
        self.inner = simulation
        self.node = self.inner.get(node_id)

    @property
    def gazebo(self) -> docker.GazeboContainerNode:
        return self.node.gazebo

    @property
    def firmware(self) -> ArduPilotFirmwareNode:
        return ArduPilotFirmwareNode(self.node)

    @override
    def stop(self):
        return self.inner.stop()


@frozen()
class GazeboOptions:
    image: str = "ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic"
    world: str = "/app/resources/worlds/iris_runway.sdf"


class Simulator(_sims.MultiComponentSimulator[docker.Environment, Simulation]):
    """ArduPilot simulator using SITL firmware and Gazebo.

    Args:
        gazebo: Configuration options for Gazebo physics simulation
        firmware: Configuration options for ArduPilot SITL firmware
        remove: Remove containers after simulation is stopped
    """

    def __init__(self, gazebo: GazeboOptions, firmware: FirmwareOptions, *, remove: bool = False):
        gazebo_ = docker.GazeboContainerComponent(
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

        self.simulator = docker.ContainerSimulator()
        self.node_id = self.simulator.add(ArduPilotGazeboComponent(gazebo_, firmware_))

    @override
    def add(
        self, component: _sims.Component[docker.Environment, _sims.NodeT]
    ) -> _sims.NodeId[_sims.NodeT]:
        return self.simulator.add(component)

    @override
    def start(self) -> Simulation:
        return Simulation(self.simulator.start(), self.node_id)
