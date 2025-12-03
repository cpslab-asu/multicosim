from __future__ import annotations

from enum import Enum
from typing import Final, TypeVar

from attrs import define, field, frozen
from typing_extensions import override

from multicosim.docker.component import ContainerComponent, ContainerNode
from multicosim.docker.simulation import ContainerSimulation, ContainerSimulator

from . import simulations as _sims
from .__about__ import __version__
from .docker import firmware as _fw
from .docker import gazebo as _gz

PORT: Final[int] = 5556
MsgT = TypeVar("MsgT", contravariant=True)
DataT = TypeVar("DataT", covariant=True)

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

@define()
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

@frozen()
class Environment(_fw.Environment):
    gazebo_host: str
    gcs_host: str | None = None


@define()
class ArduPilotContainerComponent(_sims.Component[Environment, ContainerNode]):
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
    def start(self, environment: Environment) -> ContainerNode:
        command = f"firmware --vehicle {str(self.vehicle)} --frame {self.frame} --gazebo-host {environment.gazebo_host}"

        for param_file in self.param_files:
            command += f" --param-file {param_file}"

        if environment.gcs_host is not None:
            command += f" --gcs-host {environment.gcs_host}"

        component = ContainerComponent(
            image=self.image,
            command=command,
            tty=True,
            remove=self.remove,
        )

        return component.start(environment)


@define()
class ArduPilotGazeboNode(_sims.Node):
    gazebo: _gz.GazeboContainerNode
    ardupilot: ContainerNode
    host: _fw.FirmwareContainerNode

    def stop(self):
        self.ardupilot.stop()
        self.gazebo.stop()
        self.host.stop()

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

    def __init__(self, gazebo: _gz.GazeboContainerComponent, ardupilot: ArduPilotContainerComponent, host: _fw.FirmwareContainerComponent):
        self.gazebo = gazebo
        self.host = host
        self.ardupilot = ardupilot

    @override
    def start(self, environment: _fw.Environment) -> ArduPilotGazeboNode:
        gz = self.gazebo.start(environment)
        hst = self.host.start(environment)
        env_ext = Environment(environment.client, 
                              environment.network_name, 
                              gz.node.name(), 
                              hst.node.name())
        fw = self.ardupilot.start(env_ext)

        return ArduPilotGazeboNode(gz, fw, hst)


class Simulation(_sims.Simulation):
    """Running ArduPilot simulation using SITL firmware and Gazebo.

    Attributes:
        gazebo: The gazebo simulation node
        firmware: The SITL firmware simulation node
    """

    def __init__(self, simulation: ContainerSimulation, node_id: _sims.NodeId[ArduPilotGazeboNode]):
        self.inner = simulation
        self.node = self.inner.get(node_id)

    @property
    def gazebo(self) -> _gz.GazeboContainerNode:
        return self.node.gazebo

    @property
    def ardupilot(self) -> ContainerNode:
        return self.node.ardupilot
    
    @property
    def host(self) -> _fw.FirmwareContainerNode:
        return self.node.host
    
    @property
    def container_node(self) -> ArduPilotGazeboNode:
        return self.node

    @override
    def stop(self):
        return self.inner.stop()

@define()
class GazeboOptions:
    image: str = "ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic"
    world: str = "/app/resources/worlds/iris_runway.sdf"
    headless: bool = False
    record: bool = False

class Simulator(_sims.MultiComponentSimulator[_fw.Environment, Simulation]):
    """ArduPilot simulator using SITL firmware and Gazebo.

    Args:
        gazebo: Configuration options for Gazebo physics simulation
        firmware: Configuration options for ArduPilot SITL firmware
        remove: Remove containers after simulation is stopped
    """

    def __init__(self, gazebo: GazeboOptions, firmware: FirmwareOptions, host: _fw.FirmwareConfig, *, remove: bool = False):
        gazebo_ = _gz.GazeboContainerComponent(
            image=gazebo.image,
            template=gazebo.world,
            headless=gazebo.headless,
            record=gazebo.record,
            remove=remove,
        )

        firmware_ = ArduPilotContainerComponent(
            image=firmware.image,
            vehicle=firmware.vehicle,
            frame=firmware.frame,
            param_files=firmware.param_files,
        )

        host_ = _fw.FirmwareContainerComponent(**host.params())

        self.simulator = ContainerSimulator()
        self.node_id = self.simulator.add(ArduPilotGazeboComponent(gazebo_, firmware_, host_))

    @override
    def add(self, component: _sims.Component[_fw.Environment, _sims.NodeT]) -> _sims.NodeId[_sims.NodeT]:
        return self.simulator.add(component)

    @override
    def start(self) -> Simulation:
        return Simulation(self.simulator.start(), self.node_id)