from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal, TypeAlias, TypeVar, TypedDict, Final, Generic

import attrs
import docker.models.containers
import zmq

import gzcm.containers

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


MsgT = TypeVar("MsgT")


@attrs.frozen()
class Success:
    states: list[State]


@attrs.frozen()
class Failure:
    error: Exception


@attrs.frozen()
class Firmware(Generic[MsgT]):
    container: Container = attrs.field()
    port: int = attrs.field()

    def run(self, msg: MsgT, *, context: zmq.Context) -> list[State]:
        while not _has_port_mappings(self.container, self.port):
            self.container.reload()

        port = _get_host_port(self.container, self.port)

        with context.socket(zmq.REQ) as socket:
            with socket.connect(f"tcp://localhost:{port}"):
                socket.send_pyobj(msg)

                while True:
                    self.container.reload()

                    if self.container.status == "exited":
                        raise SimulationError("Container exited without completing mission. Please check container logs for more information.")

                    try:
                        result = socket.recv_pyobj()
                    except zmq.ZMQError:
                        continue

                    if isinstance(result, Success):
                        return result.states

                    if isinstance(result, Failure):
                        raise result.error

                    raise TypeError("Unsupported type {type(result)} received from firmware. Expected [Success, Failure].")

    @classmethod
    @contextmanager
    def find(cls, name: str, *, client: Client, port: int = DEFAULT_PORT) -> FirmwareGenerator[MsgT]:
        try:
            with gzcm.containers.find(name, client=client) as container:
                yield cls(container=container, port=port)
        finally:
            pass

    @classmethod
    @contextmanager
    def start(
        cls,
        image: str,
        *,
        command: str,
        client: Client,
        port: int = DEFAULT_PORT,
        remove: bool = False
    ) -> FirmwareGenerator[MsgT]:
        ctx = gzcm.containers.start(
            image,
            command=command,
            ports={port: "tcp"},
            remove=remove,
            client=client
        )

        try:
            with ctx as container:
                yield cls(container, port)
        finally:
            pass


FirmwareGenerator:  TypeAlias = Generator[Firmware[MsgT], None, None]


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
