from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal, TypeAlias, TypedDict, Final
from types import NoneType

import attrs
import docker.models.containers
import zmq

if TYPE_CHECKING:
    Container: TypeAlias = docker.models.containers.Container

PortProtocol: TypeAlias = Literal["tcp", "udp"]


@attrs.frozen()
class Ports:
    """The bound ports for the PX4 container.

    Args:
        config: The port of the socket listening for the configuration message
        pose: The port of the socket publishing the vehicle pose messages
    """

    config: int = attrs.field(default=5555)
    pose: int = attrs.field(default=5556)


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


@attrs.frozen()
class PoseSubscriber:
    socket: zmq.Socket

    def recv_state(self) -> State | None:
        state = self.socket.recv_pyobj(zmq.NOBLOCK)

        if not isinstance(state, (State, NoneType)):
            raise MessageError(f"Unknown message type {type(state)} received from firmware.")

        return state


@contextmanager
def _pose_subscriber(msg: object, pose_port: int, config_port: int, *, context: zmq.Context) -> Generator[PoseSubscriber, None, None]:
    with context.socket(zmq.SUB) as psock:
        with psock.connect(f"tcp://localhost:{pose_port}"):
            psock.setsockopt(zmq.SUBSCRIBE, b"")

            with context.socket(zmq.REQ) as csock:
                with csock.connect(f"tcp://localhost:{config_port}"):
                    csock.send_pyobj(msg)

            try:
                yield PoseSubscriber(psock)
            finally:
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


def _ports() -> Ports:
    return Ports()


@attrs.frozen()
class Firmware:
    container: Container = attrs.field()
    ports: Ports = attrs.field(factory=_ports)

    def run(self, msg: object, *, context: zmq.Context) -> Generator[State, None, None]:
        while not _has_port_mappings(self.container, self.ports.config, self.ports.pose):
            self.container.reload()

        pose_port = _get_host_port(self.container, self.ports.pose)
        config_port = _get_host_port(self.container, self.ports.config)

        with _pose_subscriber(msg, pose_port, config_port, context=context) as sub:
            while True:
                self.container.reload()

                if self.container.status == "exited":
                    raise SimulationError("Container exited without completing mission. Please check container logs for more information.")

                try:
                    state = sub.recv_state()
                except zmq.ZMQError:
                    continue

                if state is None:
                    break
                
                yield state


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
