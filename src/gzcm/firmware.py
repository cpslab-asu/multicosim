from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeAlias, TypeVar, TypedDict, Final, Generic, Protocol, ParamSpec, ContextManager

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


@attrs.frozen()
class Pose:
    """The pose of the PX4 vehicle in meters."""

    x: float
    y: float
    z: float


@attrs.frozen()
class State:
    """The pose of the PX4 vehicle in meters, along with the associated time-stamp."""

    time: float
    pose: Pose


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


@attrs.frozen()
class Success:
    states: list[State]


@attrs.frozen()
class Failure:
    error: Exception


@attrs.frozen()
class Waypoint:
    """A position in a mission plan for a PX4-controlled vehicle.

    Args:
        lat: The latitude to achieve
        lon: The longitude to achieve
        alt: The altitude to achieve
    """

    lat: float
    lon: float
    alt: float


Mission: TypeAlias = list[Waypoint]

DEFAULT_MISSION: Final[Mission] = [
    Waypoint(47.398039859999997, 8.5455725400000002, 25),
    Waypoint(47.398036222362471, 8.5450146439425509, 25),
    Waypoint(47.397825620791885, 8.5450092830163271, 25),
]

P = ParamSpec("P")
T = TypeVar("T")
M = TypeVar("M", covariant=True)


class Firmware(Generic[T]):
    def __init__(self, client: Client, container: Container, socket: zmq.Socket):
        self.container = container
        self.socket = socket
        self.client = client

    def run(self, msg: T) -> list[State]:
        self.socket.send_pyobj(msg)

        while True:
            self.container.reload()

            if self.container.status == "exited":
                raise SimulationError("Container exited without completing mission. Please check container logs for more information.")

            try:
                result = self.socket.recv_pyobj()
            except zmq.ZMQError:
                continue

            if isinstance(result, Success):
                return result.states

            if isinstance(result, Failure):
                raise result.error

            raise TypeError(f"Unsupported type {type(result)} received from firmware. Expected [Success, Failure].")

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
class FirmwareManager(Generic[M]):
    client: Client | None
    context: zmq.Context | None
    firmware_image: str
    command: str
    port: int
    remove: bool

    @contextmanager
    def start(self) -> Generator[Firmware[M], None, None]:
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
                        yield Firmware(client, container, socket)
        finally:
            pass


class MsgFactory(Protocol[P, M]):
    def __call__(self, world: str, *args: P.args, **kwargs: P.kwargs) -> M:
        ...


@dataclass()
class FirmwareWrapper(Generic[P, M], FirmwareManager[M]):
    msg_factory: MsgFactory[P, M]
    gazebo_image: str
    world: Path
    template: Path

    def run(self, gazebo: gz.Gazebo, remove: bool = False, *args: P.args, **kwargs: P.kwargs) -> list[State]:
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


class Decorator(Protocol):
    def __call__(self, func: MsgFactory[P, M]) -> FirmwareWrapper[P, M]:
        ...


def manage(
    firmware_image: str,
    gazebo_image: str,
    command: str,
    port: int = 5556,
    world: Path = Path("/tmp/generated.sdf"),
    template: Path = Path("resources/worlds/default.sdf"),
    remove: bool = False,
    client: Client | None = None,
    context: zmq.Context | None = None,
) -> Decorator:
    def decorator(func: MsgFactory[P, M]) -> FirmwareWrapper[P, M]:
        return FirmwareWrapper(
            client,
            context,
            firmware_image,
            command,
            port,
            remove,
            func,
            gazebo_image,
            world,
            template,
        )

    return decorator
