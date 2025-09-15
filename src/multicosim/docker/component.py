from __future__ import annotations

from collections.abc import Generator, Iterable
from contextlib import ExitStack, contextmanager
from threading import Event
from typing import TYPE_CHECKING, Any, Literal, TypedDict, TypeVar

import attrs
import zmq
from typing_extensions import TypeAlias, override

from ..simulations import CommunicationNode, Component, Node

if TYPE_CHECKING:
    from docker import DockerClient
    from docker.models.containers import Container
    from docker.models.networks import Network

NodeT = TypeVar("NodeT", bound=Node)
PortProtocol: TypeAlias = Literal["tcp", "udp"]
Ports: TypeAlias = dict[int, PortProtocol]


@attrs.frozen()
class Environment:
    client: DockerClient
    network: Network


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


class ContainerError(Exception):
    pass


class ContainerStatusError(ContainerError):
    def __init__(self, actual: str, expected: str):
        super().__init__(
            f"Unexpected container status <{actual}>, expected <{expected}> after waiting"
        )


@attrs.define()
class ContainerNode(Node):
    """A single component in the simulation tree running in a docker container.

    Args:
        container: The container executing the simulation component
        remove: Flag indicating if the container should be removed at completion
    """

    container: Container = attrs.field()

    def get_host_port(self, container_port: int, protocol: PortProtocol = "tcp") -> int:
        key = f"{container_port}/{protocol}"

        while len(self.container.ports[key]) == 0:
            self.container.reload()

        return _get_host_port(self.container, container_port, protocol=protocol)

    def name(self) -> str:
        while self.container.name is None:
            self.container.reload()

        return self.container.name

    def stop(self):
        self.container.stop(timeout=10)
        self.container.wait()
        self.container.reload()

        if not self.container.status == "exited":
            raise ContainerStatusError(self.container.status, "exited")

        if self.remove:
            self.container.remove()

    def remove(self):
        self.container.reload()

        if self.container.status != "exited":
            self.container.stop()

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
    task: None

    @classmethod
    def from_node(cls, node: ContainerNode) -> MonitoredContainerNode:
        container = node.container
        task = None

        return cls(container, task)


@attrs.define()
class ContainerOptions:
    image: str = attrs.field()
    command: str = attrs.field()
    ports: Ports = attrs.field()
    name: str = attrs.field(default="", kw_only=True)
    tty: bool = attrs.field(default=False, kw_only=True)
    monitor: bool = attrs.field(default=False, kw_only=True)

    # This method is defined here because we are interested in starting the container node from
    # multiple derived classes with several different behaviors.
    def start_container_node(self, env: Environment) -> ContainerNode:
        # Wait for network name to be set
        while not env.network.name:
            env.network.reload()

        container = env.client.containers.run(
            image=self.image,
            command=self.command,
            network=env.network.name,
            tty=self.tty,
            name=self.name,
            detach=True,
            ports={
                f"{port}/{proto}": None for port, proto in self.ports.items()
            },
        )

        # Wait for container to report that it is running
        while container.status != "running":
            container.reload()

        node = ContainerNode(container)

        if self.monitor:
            return MonitoredContainerNode.from_node(node)

        return node


@attrs.define()
class ContainerComponent(ContainerOptions, Component[Environment, ContainerNode]):
    ports = attrs.Factory(dict)

    @override
    def start(self, environment: Environment) -> ContainerNode:
        return self.start_container_node(environment)


@attrs.define()
class ReporterNode(CommunicationNode[Any, Any]):
    """A simulation node that is responsible for returning data after the simulation.

    Args:
        container: The container executing the simulation component
        port: The exposed port from the container
        remove: Flag indicating if the container should be removed at completion
    """

    node: ContainerNode = attrs.field()
    port: int = attrs.field(alias="port")

    @property
    def container(self) -> Container:
        return self.node.container

    def name(self) -> str:
        return self.node.name()

    def send(self, msg: Any) -> Any:
        """Send a message to the node and return its response.

        Args:
            msg: The python object to send as a message

        Returns:
            The python object returned from the node
        """

        host_port = self.node.get_host_port(self.port)

        with _transport_socket(host_port) as sock:
            frame = sock.send_pyobj(msg)

            """
            if not frame:
                raise RuntimeError(f"Could not send message {msg} to container")
            """

            return sock.recv_pyobj()

    @override
    def stop(self):
        return self.node.stop()

    def remove(self):
        self.node.remove()


@attrs.define()
class ReporterComponentOptions(ContainerOptions):
    ports: Ports = attrs.field(init=False)  # Remove ports from init argument
    port: int = attrs.field()  # Add port argument that will be converted into ports

    def __attrs_post_init__(self):
        self.ports = {self.port: "tcp"}


@attrs.define()
class ReporterComponent(ReporterComponentOptions, Component[Environment, ReporterNode]):
    def start(self, environment: Environment) -> ReporterNode:
        return ReporterNode(self.start_container_node(environment), self.port)


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
