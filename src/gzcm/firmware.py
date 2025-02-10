from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, TypeVar, TypedDict, Final, Generic, Protocol, ParamSpec, ContextManager, overload, cast

import attrs
import docker
import zmq

import gzcm.containers
import gzcm.gazebo as gz

if TYPE_CHECKING:
    from docker import DockerClient as Client
    from docker.models.containers import Container

PortProtocol: TypeAlias = Literal["tcp", "udp"]
DEFAULT_PORT: Final[int] = 5556


class SimulationError(Exception):
    pass


class MessageError(SimulationError):
    pass


def _has_port_mappings(container: Container, *ports: int, protocol: PortProtocol = "tcp") -> bool:
    for port in ports:
        if not container.ports.get(f"{port}/{protocol}"):
            return False

    return True


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


R = TypeVar("R", covariant=True)


@attrs.frozen()
class Success(Generic[R]):
    value: R


@attrs.frozen()
class Failure:
    error: Exception


P = ParamSpec("P")
T = TypeVar("T")
M = TypeVar("M", covariant=True)


class Process(Generic[T, R]):
    def __init__(self, client: Client, container: Container, socket: zmq.Socket, rtype: type[R]):
        self.container = container
        self.socket = socket
        self.client = client
        self.rtype = rtype

    def run(self, msg: T) -> R:
        self.socket.send_pyobj(msg)

        while True:
            self.container.reload()

            if self.container.status == "exited":
                raise SimulationError("Container exited without completing mission. Please check container logs for more information.")

            try:
                response = self.socket.recv_pyobj()
            except zmq.ZMQError:
                continue

            if isinstance(response, Success):
                if not isinstance(response.value, self.rtype):
                    raise TypeError(f"Expected response value of type {self.rtype}, got {type(response.value)}")

                return response.value

            if isinstance(response, Failure):
                if not isinstance(response.error, Exception):
                    raise TypeError(f"Expected error value of type Exception, got {type(response.error)}")

                raise response.error

            raise TypeError(f"Unsupported type {type(response)} received from firmware. Expected [Success, Failure].")

    def attach(
        self,
        gazebo: gz.Gazebo,
        image: str,
        world: Path,
        template: Path,
        *,
        remove: bool = False
    ) -> ContextManager[gz.Simulation]:
        return gz.start(
            config=gazebo,
            host=self.container,
            image=image,
            base=template,
            world=world,
            client=self.client,
            remove=remove,
        )


@dataclass()
class Firmware(Generic[M, R]):
    client: Client | None
    context: zmq.Context | None
    firmware_image: str
    command: str
    port: int
    remove: bool
    rtype: type[R]

    @contextmanager
    def start(self) -> Generator[Process[M, R], None, None]:
        client = self.client or docker.from_env()
        context = self.context or zmq.Context()
        ctx = gzcm.containers.start(
            client=client,
            image=self.firmware_image,
            command=self.command,
            ports={self.port: "tcp"},
            remove=self.remove,
        )

        try:
            with ctx as container:
                while not _has_port_mappings(container, self.port):
                    container.reload()

                port = _get_host_port(container, self.port)

                with context.socket(zmq.REQ) as socket:
                    with socket.connect(f"tcp://localhost:{port}"):
                        yield Process(client, container, socket, self.rtype)
        finally:
            pass


class MsgFactory(Protocol[P, M]):
    def __call__(self, world: str, *args: P.args, **kwargs: P.kwargs) -> M:
        ...


@dataclass()
class ManagedFirmware(Generic[P, M, R], Firmware[M, R]):
    msg_factory: MsgFactory[P, M]
    gazebo_image: str
    world: Path
    template: Path

    def run(self, gazebo: gz.Gazebo, remove: bool = False, *args: P.args, **kwargs: P.kwargs) -> R:
        with self.start() as fw:
            sim = fw.attach(
                gazebo,
                self.gazebo_image,
                self.world,
                self.template,
                remove=remove,
            )

            with sim:
                msg = self.msg_factory(self.world.stem, *args, **kwargs)
                states = fw.run(msg)

        return states


class Decorator(Protocol[R]):
    def __call__(self, func: MsgFactory[P, M]) -> ManagedFirmware[P, M, R]:
        ...


@overload
def manage(
    firmware_image: str,
    gazebo_image: str,
    command: str,
    rtype: None = ...,
    port: int = 5556,
    world: Path = Path("/tmp/generated.sdf"),
    template: Path = Path("resources/worlds/default.sdf"),
    remove: bool = False,
    client: Client | None = None,
    context: zmq.Context | None = None,
) -> Decorator[object]:
    ...


@overload
def manage(
    firmware_image: str,
    gazebo_image: str,
    command: str,
    rtype: type[R],
    port: int = 5556,
    world: Path = Path("/tmp/generated.sdf"),
    template: Path = Path("resources/worlds/default.sdf"),
    remove: bool = False,
    client: Client | None = None,
    context: zmq.Context | None = None,
) -> Decorator[R]:
    ...


def manage(
    firmware_image: str,
    gazebo_image: str,
    command: str,
    rtype: type[R] | None = None,
    port: int = 5556,
    world: Path = Path("/tmp/generated.sdf"),
    template: Path = Path("resources/worlds/default.sdf"),
    remove: bool = False,
    client: Client | None = None,
    context: zmq.Context | None = None,
) -> Decorator[R] | Decorator[object]:
    def decorator(func: MsgFactory[P, M]) -> ManagedFirmware[P, M, R | object]:
        return ManagedFirmware(
            client,
            context,
            firmware_image,
            command,
            port,
            remove,
            rtype or object,
            func,
            gazebo_image,
            world,
            template,
        )

    if rtype:
        return cast(Decorator[R], decorator)
    
    return cast(Decorator[object], decorator)


A = TypeVar("A")
B = TypeVar("B", covariant=True)


class Server(Generic[B]):
    def __init__(self, func: Callable[[A], B], msgtype: type[A] | None = None):
        self.msgtype = msgtype
        self.func = func
        self.logger = logging.getLogger("gzcm.program")
        self.logger.addHandler(logging.NullHandler())

    def __call__(self, port: int = DEFAULT_PORT):
        with zmq.Context() as ctx:
            with ctx.socket(zmq.REP) as socket:
                with socket.bind(f"tcp://*:{port}"):
                    self.logger.debug("Waiting for configuration message...")

                    msg = socket.recv_pyobj()

                    if self.msgtype is not None and not isinstance(msg, self.msgtype):
                        raise TypeError(f"Unknown start message type {type(msg)}. Expected {self.msgtype}")

                    try:
                        result: Success[B] | Failure = Success(self.func(msg))
                    except Exception as e:
                        result = Failure(e)

                    socket.send_pyobj(result)


C = TypeVar("C")
D = TypeVar("D")
E = TypeVar("E")


class ProgramDecorator(Protocol):
    def __call__(self, __func: Callable[[A], C], /) -> Server[C]:
        ...


def serve(*, msgtype: type[A] | None = None) -> ProgramDecorator:
    return lambda f: Server(f, msgtype)
