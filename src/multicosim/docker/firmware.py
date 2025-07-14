import logging
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from typing import Any, Final, Generic, Protocol, TypeVar

import attrs
import zmq
from typing_extensions import override

from ..simulations import CommunicationNode, Component, NodeId, Simulation, Simulator
from .component import ReporterComponent, ReporterNode
from .gazebo import GazeboConfig, GazeboContainerComponent, GazeboContainerNode
from .simulation import ContainerSimulation, ContainerSimulator, Environment

DEFAULT_PORT: Final[int] = 5556

MsgT = TypeVar("MsgT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)
DataT = TypeVar("DataT", covariant=True)


@attrs.frozen()
class Success(Generic[DataT]):
    data: DataT


@attrs.frozen()
class Failure:
    msg: str


class SimulationError(Exception):
    pass


class MessageError(SimulationError):
    pass


@contextmanager
def _transport_socket(port: int) -> Generator[zmq.Socket, None, None]:
    with ExitStack() as stack:
        ctx = stack.enter_context(zmq.Context())
        sock = stack.enter_context(ctx.socket(zmq.REP))
        sock_ = stack.enter_context(sock.bind(f"tcp://*:{port}"))

        try:
            yield sock_
        finally:
            pass


class FirmwareServer(Generic[MsgT, DataT]):
    def __init__(self, func: Callable[[MsgT], DataT], msgtype: type[MsgT] | None = None):
        self.msgtype = msgtype
        self.func = func

    def __call__(self, msg: MsgT) -> DataT:
        if self.msgtype and not isinstance(msg, self.msgtype):
            raise TypeError(f"Unexpected argument type {type(msg)}, expected {self.msgtype}")

        return self.func(msg)

    def listen(self, port: int = DEFAULT_PORT):
        with _transport_socket(port) as socket:
            logger = logging.getLogger("multicosim.program")
            logger.addHandler(logging.NullHandler())
            logger.debug("Waiting for configuration message...")

            msg = socket.recv_pyobj()

            if self.msgtype is not None and not isinstance(msg, self.msgtype):
                raise TypeError(f"Unknown start message type {type(msg)}. Expected {self.msgtype}")

            logger.debug("Received configuration message. Running firmware...")

            try:
                result: Success[DataT] | Failure = Success(self.func(msg))
            except Exception as e:
                result = Failure(str(e))

            socket.send_pyobj(result)


A = TypeVar("A")


class FirmwareDecorator(Protocol[A]):
    def __call__(self, func: Callable[[A], DataT]) -> FirmwareServer[A, DataT]:
        ...


def firmware(*, msgtype: type[MsgT]) -> FirmwareDecorator[MsgT]:
    def decorator(func: Callable[[MsgT], DataT]) -> FirmwareServer[MsgT, DataT]:
        return FirmwareServer(func, msgtype)

    return decorator


class FirmwareError(Exception):
    def __init__(self, msg: str):
        super().__init__(f"Error during firmware execution: {msg}")


class ResponseDataTypeError(Exception):
    def __init__(self, actual: object, expected: type):
        super().__init__(f"Unsupported response data type {type(actual)}, expected {expected}")


class ResponseTypeError(Exception):
    def __init__(self, response: object):
        super().__init__(
            f"Unsupported response type {type(response)}, expected {type(Success)} or {type(Failure)}"
        )


def _extract_response_data(response: object, data_type: type[DataT]) -> DataT:
    if isinstance(response, Failure):
        raise FirmwareError(response.msg)

    if isinstance(response, Success):
        if isinstance(response.data, data_type):
            return response.data
        
        raise ResponseDataTypeError(response.data, data_type)

    raise ResponseTypeError(response)


@attrs.define()
class FirmwareContainerNode(CommunicationNode[MsgT, DataT]):
    node: ReporterNode
    message_type: type[MsgT]
    response_type: type[DataT]

    @override
    def send(self, msg: MsgT) -> DataT:
        if not isinstance(msg, self.message_type):
            raise TypeError(f"Unsupported message type {type(msg)}, expected {self.message_type}")

        return _extract_response_data(self.node.send(msg), self.response_type)

    @override
    def stop(self):
        self.node.stop()


@attrs.define()
class FirmwareContainerComponent(Component[Environment, FirmwareContainerNode[MsgT, DataT]]):
    """A component representing the firmware/controller of a system.

    Args:
        image: The docker image to use for execution
        command: The command to execute in the container
        port: The port to use for communication with the controller
    """

    def __init__(
        self,
        image: str,
        command: str,
        port: int,
        message_type: type[MsgT],
        response_type: type[DataT],
        *,
        remove: bool = False,
        monitor: bool = False,
    ):
        self.component = ReporterComponent(image, command, port, remove=remove, monitor=monitor)
        self.message_type = message_type
        self.response_type = response_type

    @override
    def start(self, environment: Environment) -> FirmwareContainerNode[MsgT, DataT]:
        return FirmwareContainerNode(
            self.component.start(environment),
            self.message_type,
            self.response_type,
        )


@attrs.define()
class FirmwareConfig(Generic[MsgT, DataT]):
    image: str = attrs.field()
    command: str = attrs.field()
    port: int = attrs.field()
    message_type: type[MsgT] = attrs.field()
    response_type: type[DataT] = attrs.field()
    remove: bool = attrs.field(default=True, kw_only=True)
    monitor: bool = attrs.field(default=True, kw_only=True)

    def params(self) -> dict[str, Any]:
        return {"image" : self.image,
                "command" : self.command,
                "port" : self.port,
                "message_type" : self.message_type,
                "response_type" : self.response_type,
                "remove" : self.remove,
                "monitor" : self.monitor}


@attrs.define()
class JointGazeboFirmwareNode(CommunicationNode[MsgT, ResultT]):
    gazebo: GazeboContainerNode
    firmware: FirmwareContainerNode[MsgT, ResultT]

    def send(self, msg: MsgT):
        return self.firmware.send(msg)

    def stop(self):
        self.gazebo.stop()
        self.firmware.stop()


class JointGazeboFirmwareComponent(Component[Environment, JointGazeboFirmwareNode]):
    def __init__(self, gazebo: GazeboConfig, fw: FirmwareConfig):
        self.port = fw.port
        self.gazebo = GazeboContainerComponent(**(gazebo.params()))
        self.firmware = FirmwareContainerComponent(**(fw.params()))

    def start(self, environment: Environment) -> JointGazeboFirmwareNode:
        return JointGazeboFirmwareNode(
            self.gazebo.start(environment),
            self.firmware.start(environment),
        )

@attrs.define()
class GazeboFirmwareSimulation(Simulation):
    simulation: ContainerSimulation
    node_id: NodeId[JointGazeboFirmwareNode]

    @property
    def firmware(self) -> FirmwareContainerNode:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id)

    @property
    def gazebo(self) -> GazeboContainerNode:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id).gazebo

    def stop(self):
        return self.simulation.stop()
    
class GazeboFirmwareSimulator(Simulator[Environment, GazeboFirmwareSimulation]):
    """A simulator tree representing a simulation using a firmware that utilizes gazebo and acts as the system controller.

    Args:
        gazebo: The gazebo component to use for simulation
    """
    def __init__(self, fwcomponent: JointGazeboFirmwareComponent):
        self.simulator = ContainerSimulator()
        self.fwcomponent = fwcomponent
        self.node_id = self.simulator.add(self.fwcomponent)

    @property
    def component(self) -> JointGazeboFirmwareComponent:
        return self.fwcomponent

    @property
    def gazebo(self) -> GazeboContainerComponent:
        return self.component.gazebo

    @override
    def add(self, component: Component[Environment, NodeT]) -> NodeId[NodeT]:
        return self.simulator.add(component)
    
    @override
    def start(self) -> GazeboFirmwareSimulation:
        return GazeboFirmwareSimulation(self.simulator.start(), self.node_id)
