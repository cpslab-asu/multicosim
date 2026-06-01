"""Simulation components implemented using containers.

This module exposes several components that are implemented using containers to
provide a uniform and portable runtime. The primary goals of these components
are to be composable and extensible so users can specialize them for their
needs. There are two primary components users should consider:

- Component
- ConnectedComponent

In addition, we also provide a container interface to the Gazebo simulator through the
Gazebo class.

To construct a simulation of container components, we provide the Simulator class,
which allows users to register components for simulation and declare dependencies
between registered components. Interaction with the running simulation is
accomplished using the Simulation class, which provides mechanisms for waiting for a
component to terminate, or communicating with a running component.
"""

from __future__ import annotations

import abc
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
    """Data class containing the resource handles necessary to start a container.

    Attributes:
        client: The docker client to use for starting the container
        network: The network to connect the container to
    """

    client: DockerClient
    network: Network


@attrs.frozen(eq=True, hash=True)
class ComponentId:
    """A unique identifier for a component."""

    value: uuid.UUID = attrs.field(init=False, factory=uuid.uuid4)


def _create_mount(source: pathlib.Path, target: str) -> docker.types.Mount:
    resolved = source.resolve()

    if not resolved.exists():
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(resolved))

    return docker.types.Mount(type="bind", source=str(resolved), target=target)


@attrs.define()
class ContainerOptions:
    image: str = attrs.field()
    command: str = attrs.field()
    ports: set[int] = attrs.field()
    files: dict[pathlib.Path, str] = attrs.field()
    tty: bool = attrs.field()

    def start(self, context: Context) -> Container:
        return context.client.containers.run(
            image=self.image,
            command=self.command,
            ports={f"{port}/tcp": None for port in self.ports},
            mounts=[_create_mount(file, target) for file, target in self.files.items()],
            tty=self.tty,
            detach=True,
        )


@attrs.define()
class BaseComponent(_Component[Context, Container], abc.ABC):
    id: ComponentId = attrs.field(init=False, factory=ComponentId)
    image: str = attrs.field()

    @abc.abstractmethod
    def to_options(self) -> ContainerOptions:
        raise NotImplementedError()

    @typing_extensions.override
    def start(self, context: Context) -> Container:
        return self.to_options().start(context)


@attrs.define()
class Component(BaseComponent):
    """A plain container-based simulation component.

    This class is suited for simulation components which just need to run without any additional
    interaction. This means the minimum amount of information to define a Component instance is
    just the container image and command.

    Attributes:
        id: The unique identifier for the container

    Args:
        image: The container image to use for execution
        command: The command to use to start the container image
        ports: Set of ports that should be bound from the container to random ports on the host
        files: Mapping of file paths to be bound from the host to the specified path in the container
        tty: Flag indicating if a psuedo-tty should be allocated for the container
    """

    command: str = attrs.field()
    ports: set[int] = attrs.field(kw_only=True, factory=set)
    files: dict[pathlib.Path, str] = attrs.field(kw_only=True, factory=dict)
    tty: bool = attrs.field(kw_only=True, default=True)

    @typing_extensions.override
    def to_options(self) -> ContainerOptions:
        return ContainerOptions(
            image=self.image,
            command=self.command,
            ports=self.ports,
            files=self.files,
            tty=self.tty,
        )


MsgT = typing.TypeVar("MsgT")
DataT = typing.TypeVar("DataT")


@attrs.define()
class ConnectedComponent(Component, typing.Generic[MsgT, DataT]):
    """A container-based simulation component that supports interaction.

    This class is suited for simulation components which need to be communicated with during
    the simulation. This class requires at least one port be bound to the host for communication.

    Attributes:
        id: The unique identifier for the container

    Args:
        image: The container image to use for execution
        command: The command to use to start the container image
        port: The required container port to be bound to the host
        msg_type: The type of the message to send to the component
        data_type: The type of the data returned from the component
        ports: Set of additional ports that should be bound from the container to random ports on the host
        files: Mapping of file paths to be bound from the host to the specified path in the container
        tty: Flag indicating if a psuedo-tty should be allocated for the container
    """

    port: int = attrs.field()
    msg_type: type[MsgT] = attrs.field(kw_only=True)
    data_type: type[DataT] = attrs.field(kw_only=True)

    @typing_extensions.override
    def to_options(self) -> ContainerOptions:
        options = super().to_options()
        options.ports.add(self.port)

        return options


@attrs.define()
class Gazebo(BaseComponent):
    """A container-based component that executed the Gazebo simulator.

    Attributes:
        id: The unique identifier for the container

    Args:
        image: The container image to use for execution
        template: The world to modify with the given simulation options
        model_dir: The directory containing the model files to use for simulation
        world: The name of the Gazebo world
        options: The gazebo simulation options
    """

    image: str = attrs.field(default="ghcr.io/cpslab-asu/multicosim/gazebo:harmonic")
    template: str = attrs.field(default="/app/resources/worlds/default.sdf")
    model_dir: str = attrs.field(default="/app/resources/models")
    world: str = attrs.field(default="generated")
    options: gazebo.Options = attrs.field(factory=gazebo.Options)

    @typing_extensions.override
    def to_options(self) -> ContainerOptions:
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

        return ContainerOptions(
            image=self.image,
            command=f"{prefix} {suffix}",
            ports=set(),
            files={},
            tty=True,
        )


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


async def _wait_for_exit(container: Container) -> None:
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
        """Wait for a component to exit.

        While waiting for the component, any dependencies declared when adding the component to the
        simulation are also monitored for failure. If a dependency exits before the specified
        component has terminated, an error is thrown.

        Args:
            component: The component to wait for

        Raises:
            MonitoredContainerError: If a component depended on by the specified component exits first
        """

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
        """Send a message to a component and return the response.

        While waiting for the response from the component, the component along with any dependencies
        declared when adding the component to the simulation are monitored for failure. If the
        component or any of its dependencies exits before the response is received, an error is thrown.
        This method will check the type of both the message and the returned response using the
        `msg_type` and `data_type` attributes of the component. This method expects the component to
        communicate using the `Server` class.

        Args:
            component: The component to communicate with
            msg: The data to send to the component

        Returns:
            The data returned from the component

        Raises:
            MonitoredContainerError: If the component or one of its dependencies exits before the response is received
            InternalComponentError: If the response from the container indicates an error occurred during execution
        """

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
    def stop(self) -> None:
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
    """Simulator implementation using container-based components."""

    def __init__(self) -> None:
        self.components: set[_Registration] = set()

    def add_component(
        self, component: BaseComponent, depends: Iterable[BaseComponent] | None = None
    ) -> None:
        """Add a component to the simulation.

        A list of dependencies D can also be provided alongside the component c which represents the
        set of components that c depends on. These components will also be monitored while interacting
        component c. This set of dependencies is flattened during interaction, which means that
        components can mutually depend on each other either explicitly or transitively. Dependencies
        are only considered while interacting with component c, not during start-up or shutdown.
        """

        if depends is not None:
            dependencies: frozenset[ComponentId] = frozenset(c.id for c in depends)
        else:
            dependencies = frozenset()

        self.components.add(_Registration(component, dependencies))

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

    def listen(self, port: int) -> None:
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
        A decorator function that transforms a function into a `Server`
    """

    def decorator(func: typing.Callable[[MsgT], DataT]) -> Server[MsgT, DataT]:
        return Server(func, msgtype)

    return decorator
