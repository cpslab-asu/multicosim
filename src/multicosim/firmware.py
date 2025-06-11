from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Final, Generic, Protocol, TypedDict, TypeVar

import attrs
import typing_extensions
import zmq

from .docker import Environment, ReporterComponent, ReporterNode
from .simulations import CommunicationNode, Component

if TYPE_CHECKING:
    from .containers import Container, PortProtocol

DEFAULT_PORT: Final[int] = 5556


class SimulationError(Exception):
    pass


class MessageError(SimulationError):
    pass


def _has_port_mappings(container: Container, *ports: int, protocol: PortProtocol = "tcp") -> bool:
    return all(
        container.ports.get(f"{port}/{protocol}") is not None for port in ports
    )


class PortMapping(TypedDict):
    """A Docker port binding mapping."""

    HostPort: str
    HostIp: str


def _get_host_port(container: Container, port: int, *, protocol: PortProtocol = "tcp") -> int:
    mappings: list[PortMapping] = container.ports[f"{port}/{protocol}"]

    for mapping in mappings:
        try:
            return int(mapping["HostPort"])
        except KeyError:
            pass

    raise ValueError("Could not find host port binding")


DataT = TypeVar("DataT", covariant=True)
MsgT = TypeVar("MsgT", contravariant=True)


@attrs.frozen()
class Success(Generic[DataT]):
    data: DataT


@attrs.frozen()
class Failure:
    msg: str


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

    @typing_extensions.override
    def send(self, msg: MsgT) -> DataT:
        if not isinstance(msg, self.message_type):
            raise TypeError(f"Unsupported message type {type(msg)}, expected {self.message_type}")

        return _extract_response_data(self.node.send(msg), self.response_type)

    @typing_extensions.override
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
        remove: bool = False
    ):
        self.component = ReporterComponent(image, command, port, remove=remove)
        self.message_type = message_type
        self.response_type = response_type

    @typing_extensions.override
    def start(self, environment: Environment) -> FirmwareContainerNode[MsgT, DataT]:
        return FirmwareContainerNode(
            self.component.start(environment),
            self.message_type,
            self.response_type,
        )
