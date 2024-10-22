from __future__ import annotations

from contextlib import contextmanager
from enum import IntEnum
from pathlib import Path
from typing import Final, Generator, TypeAlias, TypedDict, TYPE_CHECKING

import attrs
import docker
import docker.models.containers
import zmq

import gzcm.gazebo as gz

GZ_IMG: Final[str] = "cpslabasu/px4-gazebo:harmonic"
BASE: Final[Path] = Path("resources/worlds/default.sdf")
WORLD: Final[Path] = Path("/tmp/generated.sdf")

if TYPE_CHECKING:
    Client: TypeAlias = docker.DockerClient
    Container: TypeAlias = docker.models.containers.Container


class Model(IntEnum):
    X500 = 0


@attrs.frozen()
class Waypoint:
    lat: float
    lon: float
    alt: float


def _waypoints() -> list[Waypoint]:
    return [
        Waypoint(47.398039859999997, 8.5455725400000002, 25),
        Waypoint(47.398036222362471, 8.5450146439425509, 25),
        Waypoint(47.397825620791885, 8.5450092830163271, 25),
    ]


@attrs.frozen()
class Config:
    model: Model = attrs.field(default=Model.X500)
    waypoints: list[Waypoint] = attrs.field(factory=_waypoints)
    world: str = attrs.field(default="generated")


@attrs.frozen()
class Pose:
    x: float
    y: float
    z: float


class PortMapping(TypedDict):
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
    config: int = attrs.field(converter=_get_host_port)
    pose: int = attrs.field(converter=_get_host_port)


@attrs.frozen()
class Firmware(gz.Host):
    container: Container

    @property
    def name(self) -> str:
        while not self.container.name:
            self.container.reload()

        return self.container.name

    @property
    def ports(self) -> Ports:
        config_mappings: list[PortMapping] = []
        pose_mappings: list[PortMapping] = []

        while not config_mappings and not pose_mappings:
            self.container.reload()
            config_mappings = self.container.ports.get("5555/tcp", [])
            pose_mappings = self.container.ports.get("5556/tcp", [])

        return Ports(config=config_mappings, pose=pose_mappings)


@contextmanager
def firmware(*, client: Client) -> Generator[Firmware, None, None]:
    container = client.containers.run(
        image="cpslabasu/px4-firmware:1.15.0",
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


def _simulate(px4cfg: Config, ports: Ports, *, context: zmq.Context) -> Generator[Pose, None, None]:
    with _pose_socket(ports.pose, context=context) as psock:
        with _config_socket(ports.config, context=context) as csock:
            csock.send_pyobj(px4cfg)

        pose = psock.recv_pyobj()

        while pose:
            if not isinstance(pose, Pose):
                raise ValueError()

            yield pose

            pose = psock.recv_pyobj()


def simulate(
    px4cfg: Config,
    gzcfg: gz.Config,
    *,
    container: str | None = None,
    client: Client | None = None,
    context: zmq.Context | None = None,
) -> list[Pose]:
    if not client:
        client = docker.from_env()

    if not context:
        context = zmq.Context.instance()

    if container:
        fwctx = _find_firmware(container, client=client)
    else:
        fwctx = firmware(client=client)

    with fwctx as fw:
        with gz.gazebo(gzcfg, fw, image=GZ_IMG, base=BASE, world=Path(f"/tmp/{px4cfg.world}.sdf"), client=client):
            poses = _simulate(px4cfg, fw.ports, context=context)
            poses = list(poses)

    return poses
