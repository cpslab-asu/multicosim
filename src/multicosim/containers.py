from __future__ import annotations

import asyncio
import errno
import logging
import os
import pathlib
import typing
import uuid

if typing.TYPE_CHECKING:
    from collections.abc import Iterable

import attrs
import docker
import docker.errors
import docker.models.containers
import docker.types
import namer
import typing_extensions
import zmq
import zmq.asyncio

if typing.TYPE_CHECKING:
    from docker import DockerClient
    from docker.models.networks import Network

from . import gazebo
from .simulations import Component as _Component
from .simulations import Simulation as _Simulation
from .simulations import Simulator as _Simulator

Container: typing_extensions.TypeAlias = docker.models.containers.Container


@attrs.define()
class Context:
    client: DockerClient
    network: Network


@attrs.frozen(eq=True, hash=True)
class ComponentId:
    value: uuid.UUID = attrs.field(init=False, factory=uuid.uuid4)


def _create_mounts(files: dict[pathlib.Path, str]) -> Iterable[docker.types.Mount]:
    for src, dst in files.items():
        resolved = src.resolve()

        if not resolved.exists():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(resolved))

        yield docker.types.Mount(type="bind", source=str(resolved), target=dst)


@attrs.define()
class BaseComponent(_Component[Context, Container]):
    id: ComponentId = attrs.field(factory=ComponentId, init=False)
    image: str = attrs.field()
    command: str = attrs.field()
    ports: set[int] = attrs.field()
    files: dict[pathlib.Path, str] = attrs.field()
    tty: bool = attrs.field()

    @typing_extensions.override
    def start(self, context: Context) -> Container:
        return context.client.containers.run(
            image=self.image,
            command=self.command,
            ports={f"{port}/tcp": None for port in self.ports},
            mounts=list(_create_mounts(self.files)),
            tty=self.tty,
            detach=True,
        )


@attrs.define()
class Component(BaseComponent):
    ports: set[int] = attrs.field(kw_only=True, factory=set)
    files: dict[pathlib.Path, str] = attrs.field(kw_only=True, factory=dict)
    tty: bool = attrs.field(kw_only=True, default=True)


MsgT = typing.TypeVar("MsgT")
DataT = typing.TypeVar("DataT")


@attrs.define()
class ConnectedComponent(Component, typing.Generic[MsgT, DataT]):
    port: int = attrs.field()
    msg_type: type[MsgT] = attrs.field(kw_only=True)
    data_type: type[DataT] = attrs.field(kw_only=True)

    def __attrs_post_init__(self):
        self.ports.add(self.port)


@attrs.define()
class Gazebo(BaseComponent):
    image: str = attrs.field(default="ghcr.io/cpslab-asu/multicosim/gazebo:harmonic")
    template: str = attrs.field(default="/app/resources/worlds/default.sdf")
    model_dir: str = attrs.field(default="/app/resources/models")
    world: str = attrs.field(default="generated")
    ports: set[int] = attrs.field(factory=set, init=False)
    command: str = attrs.field(init=False)
    options: gazebo.Options = attrs.field(factory=gazebo.Options)

    def __attrs_post_init__(self):
        parts = [
            "gazebo",
            "--verbose",
            f"--base {self.template}",
            f"--world {self.world}",
            f"--step-size {self.options.step_size}",
            f"--model-dir {self.model_dir}",
        ]

        prefix = " ".join(parts)
        suffix = gazebo.backend_args(self.options.backend)
        self.command = f"{prefix} {suffix}"


class MonitoredContainerError(Exception):
    def __init__(self, container: Container):
        super().__init__(f"Container {container.name} is no longer running")
        self.container: Container = container


async def _ensure_running(containers: Iterable[Container]):
    containers = list(containers)
    logger = logging.getLogger("multicosim.containers.monitor")
    logger.addHandler(logging.NullHandler())

    while True:
        for container in containers:
            container.reload()
            logger.debug("Container %s status is %s", container.name, container.status)

            if container.status != "running":
                logger.error("Container %s exited unexpectedly", container.name)
                raise MonitoredContainerError(container)

        await asyncio.sleep(0)


async def _wait_for_exit(container: Container):
    logger = logging.getLogger("multicosim.containers.waiting")
    logger.addHandler(logging.NullHandler())

    while True:
        container.reload()
        logger.debug("Container %s status is %s", container.name, container.status)

        if container.status != "running":
            logger.debug("Container %s is finished", container.name)
            break

        await asyncio.sleep(0)


def find_host_port(container: Container, container_port: int) -> int:
    container.reload()
    port_str = f"{container_port}/tcp"
    mappings = container.ports[port_str]

    if mappings is not None:
        for mapping in mappings:
            try:
                return int(mapping["HostPort"])
            except KeyError:
                continue

    raise ValueError(f"No host port mappings for container port {container_port}")


class InternalComponentError(Exception):
    pass


@attrs.define()
class _ComponentSimulation:
    container: Container = attrs.field()
    dependencies: frozenset[ComponentId] = attrs.field()


@attrs.frozen()
class Simulation(_Simulation):
    context: Context
    children: dict[ComponentId, _ComponentSimulation]

    def _dependencies_for(self, component: BaseComponent) -> set[ComponentId]:
        seen = set(self.children[component.id].dependencies)
        processing = [self.children[dep] for dep in seen]

        for sim in processing:
            for dep in sim.dependencies:
                if dep not in seen:
                    seen.add(dep)
                    processing.append(self.children[dep])

        # A component cannot depend on itself
        return seen.difference((component.id,))

    async def wait_for(self, component: Component) -> None:
        dependencies = self._dependencies_for(component)
        monitor_task = asyncio.create_task(
            _ensure_running(self.children[dep].container for dep in dependencies)
        )

        container = self.children[component.id].container
        wait_task = asyncio.create_task(_wait_for_exit(container))
        done, pending = await asyncio.wait(
            [monitor_task, wait_task], return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            _ = task.cancel()

        for task in done:
            return task.result()

    async def send(self, component: ConnectedComponent[MsgT, DataT], msg: MsgT) -> DataT:
        if not isinstance(msg, component.msg_type):
            raise TypeError(f"Component expects messages of type {component.msg_type}")

        dependencies = self._dependencies_for(component).union({component.id})
        monitor_task = asyncio.create_task(
            _ensure_running(self.children[dep].container for dep in dependencies)
        )

        host_port = find_host_port(self.children[component.id].container, component.port)

        with (
            zmq.asyncio.Context() as ctx,
            ctx.socket(zmq.REQ) as sock,
            sock.connect(f"tcp://127.0.0.1:{host_port}"),
        ):
            _ = await sock.send_pyobj(msg)
            msg_task = asyncio.ensure_future(sock.recv_pyobj())
            done, pending = await asyncio.wait(
                [monitor_task, msg_task], return_when=asyncio.FIRST_COMPLETED
            )

        for task in pending:
            _ = task.cancel()

        if len(done) > 1:
            raise RuntimeError("More than one task completed")

        task = done.pop()
        value = task.result()

        if isinstance(value, Success):
            if not isinstance(value.data, component.data_type):
                raise TypeError(f"Component expects result data of type {component.data_type}")

            return value.data

        if isinstance(value, Failure):
            raise InternalComponentError(value.msg)

        raise TypeError(f"Unexpected type {type(value)} returned from component {component}")

    @typing_extensions.override
    def stop(self):
        for child in self.children.values():
            child.container.stop()


@attrs.define()
class _Registration:
    component: BaseComponent = attrs.field()
    dependencies: frozenset[ComponentId] = attrs.field()

    @typing_extensions.override
    def __hash__(self) -> int:
        return hash(self.component.id)

    def start(self, context: Context) -> _ComponentSimulation:
        return _ComponentSimulation(self.component.start(context), self.dependencies)


class Simulator(_Simulator[Context, Simulation]):
    def __init__(self) -> None:
        self.components: set[_Registration] = set()

    def add_component(
        self, component: BaseComponent, depends: Iterable[BaseComponent] | None = None
    ):
        if depends is None:
            depends = set()

        self.components.add(_Registration(component, frozenset(c.id for c in depends)))

    @typing_extensions.override
    def start(self) -> Simulation:
        ids = {c.component.id for c in self.components}

        for c in self.components:
            if c.component.id in c.dependencies:
                raise ValueError(f"Component {c.component} cannot depend on itself")

            if len(c.dependencies.difference(ids)) > 0:
                raise ValueError(
                    f"Component {c.component} depends on a component which has not been added to the simulation"
                )

        client = docker.from_env()
        network = client.networks.create(namer.generate())
        context = Context(client, network)
        children: dict[ComponentId, _ComponentSimulation] = {}

        try:
            for c in self.components:
                children[c.component.id] = c.start(context)

            return Simulation(context, children)
        except docker.errors.DockerException as e:
            for s in children.values():
                s.container.kill()

            raise e


@attrs.frozen()
class Success(typing.Generic[DataT]):
    data: DataT


@attrs.frozen()
class Failure:
    msg: str


class Server(typing.Generic[MsgT, DataT]):
    """A server for communicating with a ConnectedComponent implementation on the host from a container.

    This server awaits a message of the optionally specified type, and then calls the user-provided
    function with the message as the argument. If a type is specified then if the received message
    is a different type an error response will be sent. If a type is not specified then any message
    is accepted.

    If an error occurs during the execution of the simulation function, then an error response with
    a string representation of the error will be returned.

    This class can be called like a function, which provides the same behavior as calling the
    user-provided function directly.

    Args:
        func: The function responsible for starting the simulation once the message is received
        msgtype: The optional type of the message to wait for
    """

    def __init__(self, func: typing.Callable[[MsgT], DataT], msgtype: type[MsgT] | None = None):
        self.msgtype: type[MsgT] | None = msgtype
        self.func: typing.Callable[[MsgT], DataT] = func

    def __call__(self, msg: MsgT) -> DataT:
        if self.msgtype and not isinstance(msg, self.msgtype):
            raise TypeError(f"Unexpected argument type {type(msg)}, expected {self.msgtype}")

        return self.func(msg)

    def listen(self, port: int):
        """Start the server waiting for the required message.

        This function waits for a message, and then calls the user-provided function, and finally
        sends the response.

        Args:
            port: The port to listen on
        """

        with (
            zmq.Context() as ctx,
            ctx.socket(zmq.REP) as socket,
            socket.bind(f"tcp://*:{port}"),
        ):
            logger = logging.getLogger("multicosim.program")
            logger.addHandler(logging.NullHandler())
            logger.debug("Waiting for configuration message...")

            msg = socket.recv_pyobj()

            if self.msgtype is not None and not isinstance(msg, self.msgtype):
                raise TypeError(f"Unknown start message type {type(msg)}. Expected {self.msgtype}")

            logger.debug("Received configuration message. Running firmware...")

            try:
                result: Success[DataT] | Failure = Success(self.func(msg))
            except Exception as e:
                result = Failure(str(e))

            socket.send_pyobj(result)


A = typing.TypeVar("A")


class ServerDecorator(typing.Protocol[A]):
    def __call__(self, func: typing.Callable[[A], DataT], /) -> Server[A, DataT]: ...


def server(*, msgtype: type[MsgT]) -> ServerDecorator[MsgT]:
    """Transform a function into firmware server.

    This function is to provide an ergonomic way to transform functions into servers without needing
    to instantiate the class directly.

    Args:
        msgtype: The type of the message to accept

    Returns:
        A decorator function that transforms a function into a `FirmwareServer`
    """

    def decorator(func: typing.Callable[[MsgT], DataT]) -> Server[MsgT, DataT]:
        return Server(func, msgtype)

    return decorator
