from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, ContextManager, Generator, Literal, TypeVar, cast

import docker.errors
import docker.models.containers
import typing_extensions

from . import images
from .components import Component, Instance
from .simulations import Simulation, Simulator

if TYPE_CHECKING:
    from collections.abc import Mapping

    from docker import DockerClient as Client
    from docker.models.networks import Network

Container: typing_extensions.TypeAlias = docker.models.containers.Container
PortProtocol: typing_extensions.TypeAlias = Literal["tcp", "udp"]


@contextmanager
def find(name: str, *, client: Client) -> Generator[Container, None, None]:
    try:
        yield client.containers.get(name)
    finally:
        pass


class ContainerError(Exception):
    pass


class AbnormalExitError(ContainerError):
    def __init__(self, name: str, exit_code: int):
        super().__init__(f"Container {name} exited abnormally with code {exit_code}. Please check the container logs.")


def cleanup(container: Container, *, remove: bool):
    container.reload()

    while container.status != "exited":
        try:
            container.kill()
        except docker.errors.APIError:
            pass

        container.reload()

    result = container.wait()
    exit_code = result["StatusCode"]
    good_exit = exit_code == 0 or exit_code == 137

    if not good_exit:
        raise AbnormalExitError(cast(str, container.name), exit_code)  # Throw an error if the container exited unsuccessfully
    elif remove:
        container.remove()  # If the container exited successfully, remove if indicated


@contextmanager
def start(
    image: str,
    *,
    command: str,
    client: Client,
    ports: Mapping[int, PortProtocol] | None = None,
    host: Container | None = None,
    remove: bool = False,
) -> Generator[Container, None, None]:
    image_ = images.ensure(image, client=client)
    container = client.containers.run(
        image=image_,
        command=command,
        ports={f"{port}/{protocol}": None for port, protocol in ports.items()} if ports else {},
        network_mode=f"container:{host.name}" if host else None,
        detach=True,
        tty=True,
        stdin_open=True,
    )

    while container.status != "running":
        # Wait for the container to have the proper state before yielding to the user
        container.reload()

    try:
        yield container
    finally:
        cleanup(container, remove=remove)


_T =  TypeVar("_T")


@dataclass()
class ContainerInstance(Instance[_T]):
    container: Container

    @typing_extensions.override
    def run(self):
        ...


@dataclass()
class ContainerComponent(Component[_T]):
    image: str

    @typing_extensions.override
    def start(self) -> ContextManager[ContainerInstance[_T]]:
        ...


@dataclass()
class DockerSimulation(Simulation):
    network: Network


@dataclass()
class ContainerSimulator(Simulator):
    ...
