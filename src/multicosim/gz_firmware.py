from collections.abc import Iterable, Iterator, Mapping
from enum import IntEnum
from typing import Final, TypeVar

import attrs
from typing_extensions import override

from .docker import ContainerSimulation, ContainerSimulator, Environment, NodeId, Simulator
from .firmware import FirmwareContainerComponent, FirmwareContainerNode, FirmwareConfig
from .gazebo import GazeboContainerNode, GazeboConfig
from .gazebo import GazeboContainerComponent as GazeboContainerComponent
from .simulations import CommunicationNode, Component, Simulation, MsgT, ResultT, NodeT
    
FWConfig = TypeVar("FWConfig", contravariant=True)

@attrs.define()
class GZFirmwareNode(CommunicationNode[MsgT, ResultT]):
    gazebo: GazeboContainerNode
    _firmware: FirmwareContainerNode[MsgT|FWConfig, ResultT]

    def send(self, msg: MsgT):
        return self._firmware.send(msg)

    def stop(self):
        self.gazebo.stop()
        self._firmware.stop()

class GZFirmwareComponent(Component[Environment, GZFirmwareNode]):
    def __init__(self, gazebo: GazeboConfig, fw: FirmwareConfig):
        self.port = fw.port
        self.gazebo = GazeboContainerComponent(**(gazebo.params()))
        self.firmware = FirmwareContainerComponent(**(fw.params()))

    def start(self, environment: Environment) -> GZFirmwareNode:
        return GZFirmwareNode(
            self.gazebo.start(environment),
            self.firmware.start(environment),
        )

@attrs.define()
class GZFirmwareSimulation(Simulation):

    simulation: ContainerSimulation
    node_id: NodeId[GZFirmwareNode]

    @property
    def firmware(self) -> GZFirmwareNode:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id)

    @property
    def gazebo(self) -> GazeboContainerNode:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id).gazebo

    def stop(self):
        return self.simulation.stop()
    
class GZFirmware(Simulator[Environment, GZFirmwareSimulation]):
    """A simulator tree representing a simulation using a firmware that utilizes gazebo and acts as the system controller.

    Args:
        gazebo: The gazebo component to use for simulation
    """
    def __init__(self, fwcomponent: GZFirmwareComponent):
        self.simulator = ContainerSimulator()
        self.fwcomponent = fwcomponent
        self.node_id = self.simulator.add(self.fwcomponent)

    @property
    def component(self) -> GZFirmwareComponent:
        return self.fwcomponent

    @property
    def gazebo(self) -> GazeboContainerComponent:
        return self.component.gazebo

    @override
    def add(self, component: Component[Environment, NodeT]) -> NodeId[NodeT]:
        return self.simulator.add(component)
    
    @override
    def start(self) -> GZFirmwareSimulation:
        return GZFirmwareSimulation(self.simulator.start(), self.node_id)