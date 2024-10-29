from __future__ import annotations

from contextlib import contextmanager
from enum import IntEnum
from logging import NullHandler, getLogger
from pathlib import Path
from types import NoneType
from typing import Final, Generator, TypeAlias, TypedDict, TYPE_CHECKING

import attrs
import docker
import docker.models.containers
import zmq

import gzcm.docker
import gzcm.gazebo as gz

GZ_IMG: Final[str] = "ghcr.io/cpslab-asu/gzcm/px4/gazebo:harmonic"
PX4_IMG: Final[str] = "ghcr.io/cpslab-asu/gzcm/px4/firmware:1.15.0"
BASE: Final[Path] = Path("resources/worlds/default.sdf")
WORLD: Final[Path] = Path("/tmp/generated.sdf")

logger = getLogger("gzcm.px4")
logger.addHandler(NullHandler())

if TYPE_CHECKING:
    Client: TypeAlias = docker.DockerClient
    Container: TypeAlias = docker.models.containers.Container


class Model(IntEnum):
    """PX4 Vehicle model to use for simulation.

    The X500 is a light-weight quadrotor aircraft model.
    """

    X500 = 0


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


def _waypoints() -> list[Waypoint]:
    """The default set of waypoints for a mission."""

    return [
        Waypoint(47.398039859999997, 8.5455725400000002, 25),
        Waypoint(47.398036222362471, 8.5450146439425509, 25),
        Waypoint(47.397825620791885, 8.5450092830163271, 25),
    ]


@attrs.frozen()
class Config:
    """Configuration parameters for a simulated PX4-controlled vehicle.

    Args:
        model: The vehicle model to use for the simulation
        waypoints: The mission for the vehicle to execute during the simulation
        world: The name of the Gazebo world
    """

    model: Model = attrs.field(default=Model.X500)
    waypoints: list[Waypoint] = attrs.field(factory=_waypoints)
    world: str = attrs.field(default="generated")


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


class PortMapping(TypedDict):
    """A Docker port binding mapping."""

    HostPort: str
    HostIp: str


def _get_host_port(mappings: list[PortMapping]) -> int:
    for mapping in mappings:
        try:
            return int(mapping["HostPort"])
        except KeyError:
            pass

    raise ValueError("Could not find host port binding")


@attrs.frozen()
class Ports:
    """The bound ports for the PX4 container.

    Args:
        config: The port of the socket listening for the configuration message
        pose: The port of the socket publishing the vehicle pose messages
    """

    config: int = attrs.field(converter=_get_host_port)
    pose: int = attrs.field(converter=_get_host_port)


@attrs.frozen()
class Firmware(gz.Host):
    """A PX4 controller executing in a docker container.

    Args:
        container: The firmware container
    """
    
    container: Container

    @property
    def name(self) -> str:
        while not self.container.name:
            self.container.reload()

        return self.container.name

    @property
    def ports(self) -> Ports:
        """The bound ports of the PX4 container.

        Returns:
            The host ports of the PX4 container
        """

        config_mappings: list[PortMapping] = []
        pose_mappings: list[PortMapping] = []

        while not config_mappings and not pose_mappings:
            self.container.reload()
            config_mappings = self.container.ports.get("5555/tcp", [])
            pose_mappings = self.container.ports.get("5556/tcp", [])

        return Ports(config=config_mappings, pose=pose_mappings)


@contextmanager
def firmware(*, client: Client, remove: bool = False) -> Generator[Firmware, None, None]:
    """Create and execute a PX4 simulation.

    Args:
        client: The docker client to use to create the container
    """

    image = gzcm.docker.ensure_image(PX4_IMG, client=client)
    container = client.containers.run(
        image=image,
        command="firmware --verbose",
        detach=True,
        ports={"5555/tcp": None, "5556/tcp": None},
        tty=True,
        stdin_open=True,
    )

    container.reload()

    try:
        yield Firmware(container)
    finally:
        container.reload()

        if container.status == "running":
            container.kill()
            container.wait()

        status_code = int(container.attrs['State']['ExitCode'])

        if remove and status_code == 0:
            container.remove()


@contextmanager
def _config_socket(port: int, *, context: zmq.Context) -> Generator[zmq.Socket, None, None]:
    with context.socket(zmq.REQ) as sock:
        with sock.connect(f"tcp://localhost:{port}"):
            try:
                yield sock
            finally:
                pass


@contextmanager
def _pose_socket(port: int, *, context: zmq.Context) -> Generator[zmq.Socket, None, None]:
    with context.socket(zmq.SUB) as sock:
        with sock.connect(f"tcp://localhost:{port}"):
            sock.setsockopt(zmq.SUBSCRIBE, b"")

            try:
                yield sock
            finally:
                pass


@contextmanager
def _find_firmware(name: str, *, client: Client) -> Generator[Firmware, None, None]:
    container = client.containers.get(name)
    fw = Firmware(container)

    try:
        yield fw
    finally:
        pass


class SimulationError(Exception):
    pass


class MessageError(SimulationError):
    pass


def _recv_state(container: Container, socket: zmq.Socket) -> State | None:
    while True:
        container.reload()

        if container.status == "exited":
            raise SimulationError("Container exited without completing mission. Please check container logs for more information.")

        try:
            state = socket.recv_pyobj(zmq.NOBLOCK)

            if not isinstance(state, (State, NoneType)):
                raise MessageError(f"Unknown message type {type(state)} received from firmware.")

            return state
        except zmq.ZMQError:
            pass


def _simulate(px4cfg: Config, fw: Firmware, *, context: zmq.Context) -> Generator[State, None, None]:
    ports = fw.ports

    with _pose_socket(ports.pose, context=context) as psock:
        with _config_socket(ports.config, context=context) as csock:
            csock.send_pyobj(px4cfg)

        state = _recv_state(fw.container, psock)

        while state is not None:
            yield state
            state = _recv_state(fw.container, psock)


Trace: TypeAlias = dict[float, Pose]


def simulate(
    px4cfg: Config,
    gzcfg: gz.Config,
    *,
    container: str | None = None,
    client: Client | None = None,
    context: zmq.Context | None = None,
    remove: bool = False,
) -> Trace:
    """Execute a simulation using the PX4 using the given configuration.

    Args:
        px4cfg: The configuration for the PX4 system
        gzcfg: The configuration for the simulator
        container: The existing PX4 container to use instead of creating a new one
        client: The docker client to use, if any
        context: The ZeroMQ context to use, if any

    Returns:
        A list of poses representing the position of the vehicle in meters over the
        course of the mission provided in the PX4 configuration.
    """

    if not client:
        client = docker.from_env()

    if not context:
        context = zmq.Context.instance()

    if container:
        fwctx = _find_firmware(container, client=client)
    else:
        fwctx = firmware(client=client, remove=remove)

    world = Path(f"/tmp/{px4cfg.world}.sdf")

    with fwctx as fw:
        with gz.gazebo(gzcfg, fw, image=GZ_IMG, base=BASE, world=world, client=client, remove=remove):
            logger.debug("Running simulation...")

            trace = {
                state.time: state.pose for state in _simulate(px4cfg, fw, context=context)
            }

            logger.debug("Simulation complete.")

    return trace
