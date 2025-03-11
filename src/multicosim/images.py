from __future__ import annotations

import logging
import typing

import docker.errors

if typing.TYPE_CHECKING:
    from docker import DockerClient as Client
    from docker.models.images import Image


def ensure(name: str, *, client: Client) -> Image:
    logger = logging.getLogger("multicosim.containers")
    logger.addHandler(logging.NullHandler())

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
