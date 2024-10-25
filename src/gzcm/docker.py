from __future__ import annotations

from logging import NullHandler, getLogger
from typing import TypeAlias, TYPE_CHECKING

import docker
import docker.errors
import docker.models
import docker.models.images

if TYPE_CHECKING:
    Client: TypeAlias = docker.DockerClient
    Image: TypeAlias = docker.models.images.Image


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

