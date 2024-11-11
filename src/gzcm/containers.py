from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from logging import NullHandler, getLogger
from typing import Generator, Literal, TypeAlias

import docker
import docker.errors
import docker.models.containers
import docker.models.images

Client: TypeAlias = docker.DockerClient
Image: TypeAlias = docker.models.images.Image
Container: TypeAlias = docker.models.containers.Container
PortProtocol: TypeAlias = Literal["tcp", "udp"]


def ensure_image(name: str, *, client: Client) -> Image:
    logger = getLogger("gzcm.containers")
    logger.addHandler(NullHandler())

    if ":" not in name:
        name = f"{name}:latest"

    try:
        image = client.images.get(name)
    except docker.errors.ImageNotFound:
        logger.debug(f"Image {name} not found, pulling...")

        parts = name.split(":")
        repository = parts[0]
        tag = parts[1] if len(parts) > 1 else None
        image = client.images.pull(repository, tag)

        logger.debug(f"Image {name} pulled.")
    else:
        logger.debug(f"Image {name} found.")

    return image


@contextmanager
def find(name: str, *, client: Client) -> Generator[Container, None, None]:
    try:
        yield client.containers.get(name)
    finally:
        pass


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
    image_ = ensure_image(image, client=client)
    container = client.containers.run(
        image=image_,
        command=command,
        ports={f"{port}/{protocol}": None for port, protocol in ports.items()} if ports else {},
        network_mode=f"container:{host.name}" if host else None,
        detach=True,
        tty=True,
        stdin_open=True,
    )

    try:
        while container.status == "created":
            container.reload()

        yield container
    finally:
        container.reload()

        if container.status == "exited":
            status_code = int(container.attrs["State"]["ExitCode"])
            remove = remove and status_code == 0  # Only remove the container if it exited successfully, even if indicated
        else:
            container.kill()
            container.wait()

        if remove:
            container.remove()
