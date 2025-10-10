"""Simulation component with improved communication and associated server."""

import logging
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from typing import Any, Final, Generic, Protocol, TypeVar

import attrs
import zmq
from typing_extensions import override

from ..simulations import CommunicationNode, Component, NodeId, Simulation, MultiComponentSimulator
from .component import ReporterComponent, ReporterNode
from .gazebo import GazeboConfig, GazeboContainerComponent, GazeboContainerNode
from .simulation import ContainerSimulation, ContainerSimulator, Environment, NodeT

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
    """A server for communicating with a FirmwareComponent implementation on the host from a container.

    This server awaits a message of the optionally specified type, and then calls the user-provided
    function with the message as the argument. If a type is specified then if the received message
    is a different type an error response will be sent. If a type is not specified then any message
    is accepted.

    If an error occurs during the execution of the simulation function, then an error response with
    a string representation of the error will be returned.

    This class can be called like a function, which provides the same behavior as calling the
    user-provided function directly.

    Args:
        func: The function responsible for starting the simulation once the message is received
        msgtype: The optional type of the message to wait for
    """

    def __init__(self, func: Callable[[MsgT], DataT], msgtype: type[MsgT] | None = None):
        self.msgtype = msgtype
        self.func = func

    def __call__(self, msg: MsgT) -> DataT:
        if self.msgtype and not isinstance(msg, self.msgtype):
            raise TypeError(f"Unexpected argument type {type(msg)}, expected {self.msgtype}")

        return self.func(msg)

    def listen(self, port: int = DEFAULT_PORT):
        """Start the server waiting for the required message.

        This function waits for a message, and then calls the user-provided function, and finally
        sends the response.

        Args:
            port: The port to listen on
        """

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
    """Transform a function into firmware server.

    This function is to provide an ergonomic way to transform functions into servers without needing
    to instantiate the class directly.

    Args:
        msgtype: The type of the message to accept

    Returns:
        A decorator function that transforms a function into a `FirmwareServer`
    """

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
    """A node representing a running simulation implementing the firmware server interface.

    This function will check both the type of the message and the type of the response. If an

    Args:
        node: The reporter node to use for communication
        message_type: The type of the message to send to the server
        response_type: The type of the data that will be received from the server
    """

    node: ReporterNode
    message_type: type[MsgT]
    response_type: type[DataT]

    @override
    def send(self, msg: MsgT) -> DataT:
        """Send the given message to the simulation and return the response.

        Args:
            msg: The message to send to the firmware

        Returns:
            The response from the simulation

        Raises:
            FirmwareError: If the firmware encountered an error during execution
            ResponseDataTypeError: If the type of the response data is incorrect
            ResponseTypeError: If the type of the response message is incorrect
        """

        if not isinstance(msg, self.message_type):
            raise TypeError(f"Unsupported message type {type(msg)}, expected {self.message_type}")

        return _extract_response_data(self.node.send(msg), self.response_type)

    @override
    def stop(self):
        self.node.stop()


@attrs.define()
class FirmwareContainerComponent(Component[Environment, FirmwareContainerNode[MsgT, DataT]]):
    """A component that creates a simulation implementing the firmware server interface.

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
        name: str = "",
        tty: bool = False,
        remove: bool = False,
        monitor: bool = False,
    ):
        self.component = ReporterComponent(image, command, port, tty=tty, name=name, remove=remove, monitor=monitor)
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
    name: str = attrs.field(default="", kw_only=True)
    tty: bool = attrs.field(default=False, kw_only=True)
    remove: bool = attrs.field(default=True, kw_only=True)
    monitor: bool = attrs.field(default=True, kw_only=True)

    def params(self) -> dict[str, Any]:
        return {"image" : self.image,
                "command" : self.command,
                "port" : self.port,
                "message_type" : self.message_type,
                "response_type" : self.response_type,
                "name" : self.name,
                "tty" : self.tty,
                "remove" : self.remove,
                "monitor" : self.monitor}


@attrs.define()
class JointGazeboFirmwareNode(CommunicationNode[MsgT, ResultT]):
    """Node representing the composition of a firmware simulation and gazebo simulation.

    This node provides named access to the gazebo and firmware nodes rather than requiring users
    to use NodeId values to retrieve them.

    Args:
        gazebo: The executing gazebo simulation
        firmware: The executing firmware simulation
    """

    gazebo: GazeboContainerNode
    firmware: FirmwareContainerNode[MsgT, ResultT]

    @override
    def send(self, msg: MsgT) ->ResultT:
        return self.firmware.send(msg)

    @override
    def stop(self):
        self.gazebo.stop()
        self.firmware.stop()


@attrs.define()
class JointGazeboFirmwareComponent(Component[Environment, JointGazeboFirmwareNode[MsgT, ResultT]]):
    """Component that represents the composition of a firmware and gazebo component.

    This component returns the specialized composition node that allows for named access to the
    sub-nodes.

    Args:
        gazebo: The gazebo component
        firmware The firmware component
    """

    gazebo: GazeboContainerComponent
    firmware: FirmwareContainerComponent[MsgT, ResultT]

    @override
    def start(self, environment: Environment) -> JointGazeboFirmwareNode[MsgT, ResultT]:
        return JointGazeboFirmwareNode(
            self.gazebo.start(environment),
            self.firmware.start(environment),
        )


@attrs.define()
class GazeboFirmwareSimulation(Simulation, Generic[MsgT, ResultT]):
    """Simulation that provides named access to the firmware and gazebo nodes it contains.

    Args:
        simulation: The container simulation
        node_id: The id of the firmware/gazebo composition node
    """

    simulation: ContainerSimulation
    node_id: NodeId[JointGazeboFirmwareNode[MsgT, ResultT]]

    @property
    def firmware(self) -> FirmwareContainerNode[MsgT, ResultT]:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id).firmware

    @property
    def gazebo(self) -> GazeboContainerNode:
        """The simulation node of the executing firmware."""

        return self.simulation.get(self.node_id).gazebo

    @override
    def stop(self):
        return self.simulation.stop()


class GazeboFirmwareSimulator(MultiComponentSimulator[Environment, GazeboFirmwareSimulation[MsgT, ResultT]]):
    """A simulator tree representing a simulation using a firmware that utilizes gazebo and acts as the system controller.

    Args:
        gazebo: The gazebo component to use for simulation
    """

    def __init__(self, component: JointGazeboFirmwareComponent[MsgT, ResultT]):
        self.simulator = ContainerSimulator()
        self.component = component
        self.node_id = self.simulator.add(self.component)

    @property
    def gazebo(self) -> GazeboContainerComponent:
        return self.component.gazebo

    @override
    def add(self, component: Component[Environment, NodeT]) -> NodeId[NodeT]:
        return self.simulator.add(component)

    @override
    def start(self) -> GazeboFirmwareSimulation[MsgT, ResultT]:
        return GazeboFirmwareSimulation(self.simulator.start(), self.node_id)
