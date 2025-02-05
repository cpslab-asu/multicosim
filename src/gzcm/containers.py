from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator, Literal, TypeAlias, cast

from . import images

if TYPE_CHECKING:
    from collections.abc import Mapping

    from docker import DockerClient as Client
    from docker.models.containers import Container

PortProtocol: TypeAlias = Literal["tcp", "udp"]


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
        container.reload()

        if container.status != "exited":
            container.kill()

        result = container.wait()
        exit_code = int(result["StatusCode"])
        good_exit = exit_code == 0 or exit_code == 137

        if not good_exit:
            raise AbnormalExitError(cast(str, container.name), exit_code)  # Throw an error if the container exited unsuccessfully
        elif remove:
            container.remove()  # If the container exited successfully, remove if indicated
