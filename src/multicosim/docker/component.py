"""Containerized simulation components."""

from __future__ import annotations

from collections.abc import Generator, Iterable
from contextlib import ExitStack, contextmanager
from threading import Event, Thread
from typing import TYPE_CHECKING, Literal, TypedDict, TypeVar
from warnings import warn

import attrs
import zmq
from typing_extensions import TypeAlias, override

from ..simulations import CommunicationNode, Component, Node
from .simulation import Environment

if TYPE_CHECKING:
    from docker.models.containers import Container

NodeT = TypeVar("NodeT", bound=Node)
PortProtocol: TypeAlias = Literal["tcp", "udp"]


@contextmanager
def _transport_socket(port: int) -> Generator[zmq.Socket, None, None]:
    """Create a ZMQ socket to communicate with a component in a container.

    Args:
        port: The port on the docker host to connect to

    Returns:
        A context manager that yields a connected socket
    """

    with ExitStack() as stack:
        ctx = stack.enter_context(zmq.Context())
        sock = stack.enter_context(ctx.socket(zmq.REQ))
        sock_ = stack.enter_context(sock.connect(f"tcp://127.0.0.1:{port}"))

        try:
            yield sock_
        finally:
            pass


class PortMapping(TypedDict):
    """A Docker port binding mapping."""

    HostPort: str
    HostIp: str


def _get_host_port(container: Container, port: int, *, protocol: PortProtocol = "tcp") -> int:
    mappings: list[PortMapping] = container.ports[f"{port}/{protocol}"]

    for mapping in mappings:
        try:
            return int(mapping["HostPort"])
        except KeyError:
            pass

    raise ValueError("Could not find host port binding")


@attrs.define()
class ContainerNode(Node):
    """A single component in the simulation tree running in a docker container.

    Args:
        container: The container executing the simulation component
        remove: Flag indicating if the container should be removed at completion
    """

    container: Container = attrs.field()
    remove: bool = attrs.field(kw_only=True, default=True)

    def host_port(self, container_port: int, protocol: PortProtocol = "tcp") -> int:
        """Find the host port for a given container port.

        This method will reload the container until the port mapping is populated, so it is possible
        to get stuck in an infinite loop if the mapping is never populated.

        Args:
            container_port: The port bound from the container
            protocol: The communication protocol for the port

        Returns:
            The corresponding port on the host

        Raises:
            ValueError: If the port is not bound in the container
        """

        key = f"{container_port}/{protocol}"

        while len(self.container.ports[key]) == 0:
            self.container.reload()

        return _get_host_port(self.container, container_port, protocol=protocol)

    def name(self) -> str:
        """Name of the underlying container."""

        while self.container.name is None:
            self.container.reload()

        return self.container.name

    def stop(self):
        self.container.stop(timeout=10)
        self.container.wait()

        if self.remove:
            self.container.remove()


class MonitoredContainerError(Exception):
    def __init__(self, container: Container):
        super().__init__(self, f"Monitored container {container.name} has exited early.")


def _watch_container(container: Container, stop: Event):
    while True:
        if stop.is_set():
            break

        container.reload()

        if container.status != "running":
            raise MonitoredContainerError(container)


@attrs.define()
class MonitoredContainerNode(ContainerNode):
    def __init__(self, container: Container, *, remove: bool = False):
        super().__init__(container, remove=remove)
        self.signal = Event()
        self.thread = Thread(target=_watch_container, args=(container, self.signal), daemon=True)
        self.thread.start()

    def stop(self):
        self.signal.set()  # Set stop signal to terminate watcher thread
        self.thread.join()  # Join thread to ensure termination before shutting down container
        super().stop()


@attrs.define()
class ContainerComponent(Component[Environment, ContainerNode]):
    """A component for executing a simulation in a container.

    Args:
        image: The container image to use
        command: The command to execute in the container
        ports: Set of container ports and their associated protocols to be bound from the container
        name: The name of the container
        tty: Allocate a tty in the container
        remove: Remove the container when the simulation is terminated
        monitor: Raise an exception if the container exits before the simulation is terminated
    """

    image: str = attrs.field()
    command: str = attrs.field()
    ports: dict[int, Literal["tcp", "udp"]] = attrs.field(factory=dict)
    name: str = attrs.field(default="", kw_only=True)
    tty: bool = attrs.field(default=False, kw_only=True)
    remove: bool = attrs.field(default=True, kw_only=True)
    monitor: bool = attrs.field(default=False, kw_only=True)

    @override
    def start(self, environment: Environment) -> ContainerNode:
        container = environment.client.containers.run(
            image=self.image,
            command=self.command,
            network=environment.network_name,
            tty=self.tty,
            name=self.name,
            detach=True,
            ports={
                f"{port}/{proto}": None for port, proto in self.ports.items()
            },
        )

        while container.status == "created":
            container.reload()

        if self.monitor:
            warn("Monitoring is not currently supported")
            # return MonitoredContainerNode(container, remove=self.remove)

        return ContainerNode(container, remove=self.remove)


class ReporterNode(CommunicationNode[object, object]):
    """A simulation node that supports communication with the underlying simulator using 0MQ sockets.

    Args:
        container: The container executing the simulation component
        port: The host port to use for communication
        remove: Flag indicating if the container should be removed at completion
    """

    def __init__(self, node: ContainerNode, port: int):
        self.node = node
        self.host_port = port

    def name(self) -> str:
        """The name of the container running the simulation."""

        return self.node.name()

    @override
    def send(self, msg: object) -> object:
        """Send a message to the node and return its response.

        Args:
            msg: The python object to send as a message

        Returns:
            The python object returned from the node
        """

        with _transport_socket(self.host_port) as sock:
            frame = sock.send_pyobj(msg)

            """
            if not frame:
                raise RuntimeError(f"Could not send message {msg} to container")
            """

            return sock.recv_pyobj()

    @override
    def stop(self):
        return self.node.stop()


class ReporterComponent(Component[Environment, ReporterNode]):
    """A component that produces a simulator that supports communication.

    Args:
        image: The container image to use for execution
        command: The command to execute in the container
        port: The container port to bind for the 0MQ socket
        tty: Allocate a tty in the container
        name: The name to use for the container
        remove: Remove the container when the simulation exits
        monitor: Raise an error if the container exits before the simulation is stopped
    """

    def __init__(self, image: str, command: str, port: int, *, tty: bool = False, name: str = "", remove: bool = True, monitor: bool = False):
        self.component: ContainerComponent = ContainerComponent(
            image,
            command,
            ports={port: "tcp"},
            tty=tty,
            name=name,
            remove=remove,
            monitor=monitor,
        )
        self.port: int = port

    @override
    def start(self, environment: Environment) -> ReporterNode:
        node = self.component.start(environment)
        port = node.host_port(self.port)

        return ReporterNode(node, port)


class AttachedNode(Node):
    """A node representing the execution of multiple containers using a single networking stack.

    Args:
        parent: The node to use as the host networking stack
        children: The nodes to attach to the parent
    """

    def __init__(self, parent: Node, children: Iterable[Node]):
        self.parent = parent
        self.children = list(children)

    def stop(self):
        # Stop all the attached children before stopping the parent
        for child in self.children:
            child.stop()

        self.parent.stop()


class Attached(Component[Environment, AttachedNode]):
    """A component representing multiple containers sharing a single networking stack.

    Args:
        c1: The component to use as the shared networking stack
        c2: The first component to attach
        *rest: Further components to attach
    """

    def __init__(self, c1: Component, c2: Component, *rest: Component):
        self.parent = c1
        self.children = [c2, *rest]

    def start(self, environment: Environment) -> AttachedNode:
        parent = self.parent.start(environment)

        while parent.container.name is None:
            parent.container.reload()

        env = Environment(environment.client, f"container:{parent.container.name}")
        children = [child.start(env) for child in self.children]

        return AttachedNode(parent, children)
