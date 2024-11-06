from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from logging import NullHandler, getLogger
from typing import TypeAlias, TYPE_CHECKING

import docker
import docker.errors
import docker.models
import docker.models.containers
import docker.models.images

if TYPE_CHECKING:
    Client: TypeAlias = docker.DockerClient
    Image: TypeAlias = docker.models.images.Image
    Container: TypeAlias = docker.models.containers.Container


def ensure_image(name: str, *, client: Client) -> Image:
    logger = getLogger("gzcm.docker")
    logger.addHandler(NullHandler())

    try:
        image = client.images.get(name)
        logger.debug(f"Image {name} found.")
    except docker.errors.ImageNotFound:
        logger.debug(f"Image {name} not found, pulling...")

        parts = name.split(":")
        repository = parts[0]
        tag = parts[1] if len(parts) > 1 else None
        image = client.images.pull(repository, tag)

        logger.debug(f"Image {name} pulled.")

    return image


@contextmanager
def start_container(
    image: str,
    command: str,
    ports: list[int],
    *,
    client: Client,
    remove: bool = False
) -> Generator[Container, None, None]:
    image_ = ensure_image(image, client=client)
    container = client.containers.run(
        image=image_,
        command=command,
        detach=True,
        ports={f"{port}/tcp": None for port in ports},
        tty=True,
        stdin_open=True,
    )

    try:
        yield container
    finally:
        container.reload()

        if container.status != "exited":
            container.kill()
            container.wait()

        status_code = int(container.attrs['State']['ExitCode'])

        if remove and status_code != 0:
            container.remove()
