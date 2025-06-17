from __future__ import annotations

from collections.abc import Generator, Iterable, Mapping
from contextlib import ExitStack, contextmanager
from threading import Event, Thread
from typing import TYPE_CHECKING, Generic, Literal, Protocol, TypeVar, cast

import attrs
import docker
import nanoid
import zmq
from typing_extensions import override

from .simulations import CommunicationNode, Component, Node, NodeId, Simulation, Simulator

if TYPE_CHECKING:
    from docker import DockerClient
    from docker.models.containers import Container

NodeT = TypeVar("NodeT", bound=Node)


def _nodes(nodes: Mapping[NodeId, Node]) -> dict[NodeId, Node]:
    return dict(nodes)


@attrs.define()
class ContainerSimulation(Simulation):
    """A running simulation of multiple components executing in Docker containers.

    Args:
        nodes: The running simulation nodes with associated ids
    """

    nodes: dict[NodeId, Node] = attrs.field(converter=_nodes)

    def get(self, node_id: NodeId[NodeT]) -> NodeT:
        return cast(NodeT, self.nodes[node_id])

    def stop(self):
        for node in self.nodes.values():
            node.stop()


@attrs.frozen()
class Environment:
    client: DockerClient
    network_name: str


class ContainerSimulator(Simulator[Environment, ContainerSimulation]):
    """A tree of components representing a simulator for a given system using Docker containers.

    Args:
        *components: Components to add to the simulation to start

    Attributes:
        network: The docker network to which all containers are connected
        env: The environment used to start the components
        components: A mapping of components and their unique identifiers
    """

    def __init__(self, *components: Component[Environment, Node]):
        client = docker.from_env()
        network_name = nanoid.generate()

        self.network = client.networks.create(network_name)
        self.env = Environment(client, network_name)
        self.components = {
            NodeId(): component for component in components
        }

    def add(self, component: Component[Environment, NodeT]) -> NodeId[NodeT]:
        """Add a component to the simulation tree.

        Args:
            component: The component to add

        Returns:
            The randomly generated unique id associated with the newly added component
        """

        component_id = NodeId()
        self.components[component_id] = component

        return component_id

    @override
    def start(self) -> ContainerSimulation:
        nodes = {
            node_id: component.start(self.env)
            for node_id, component in self.components.items()
        }

        return ContainerSimulation(nodes)


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


@attrs.define()
class ContainerNode(Node):
    """A single component in the simulation tree running in a docker container.

    Args:
        container: The container executing the simulation component
        remove: Flag indicating if the container should be removed at completion
    """

    container: Container = attrs.field()
    remove: bool = attrs.field(kw_only=True, default=True)

    def host_port(self, container_port: int) -> int:
        ...

    def stop(self):
        self.container.stop()

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

    def stop(self):
        self.signal.set()  # Set stop signal to terminate watcher thread
        self.thread.join()  # Join thread to ensure termination before shutting down container
        super().stop()


@attrs.define()
class ContainerComponent(Component[Environment, ContainerNode]):
    image: str = attrs.field()
    command: str = attrs.field()
    ports: dict[int, Literal["tcp", "udp"]] = attrs.field(factory=dict)
    remove: bool = attrs.field(default=True, kw_only=True)
    monitor: bool = attrs.field(default=False, kw_only=True)

    def start(self, environment: Environment) -> ContainerNode:
        container = environment.client.containers.run(
            image=self.image,
            command=self.command,
            network=environment.network_name,
            detach=True,
            ports={
                f"{port}/{proto}": None for port, proto in self.ports.items()
            },
        )

        if self.monitor:
            return MonitoredContainerNode(container, remove=self.remove)

        return ContainerNode(container, remove=self.remove)


class ReporterNode(CommunicationNode[object, object]):
    """A simulation node that is responsible for returning data after the simulation.

    Args:
        container: The container executing the simulation component
        port: The exposed port from the container
        remove: Flag indicating if the container should be removed at completion
    """

    def __init__(self, node: ContainerNode, port: int):
        self.node = node
        self.container_port = port

    @property
    def host_port(self) -> int:
        ...

    def send(self, msg: object) -> object:
        """Send a message to the node and return its response.

        Args:
            msg: The python object to send as a message

        Returns:
            The python object returned from the node
        """

        with _transport_socket(self.host_port) as sock:
            frame = sock.send_pyobj(msg)

            if not frame:
                raise RuntimeError(f"Could not send message {msg} to container")

            return sock.recv_pyobj()

    @override
    def stop(self):
        return self.node.stop()


class ReporterComponent(Component[Environment, ReporterNode]):
    def __init__(self, image: str, command: str, port: int, *, remove: bool = True, monitor: bool = False):
        self.component = ContainerComponent(
            image,
            command,
            ports={port: "tcp"},
            remove=remove,
            monitor=monitor,
        )
        self.port = port

    def start(self, environment: Environment) -> ReporterNode:
        node = self.component.start(environment)
        port = node.host_port(self.port)

        return ReporterNode(node, port)


DataT = TypeVar("DataT")
MsgT = TypeVar("MsgT")


@attrs.define()
class Success(Generic[DataT]):
    data: DataT


@attrs.define()
class Failure:
    msg: str


@attrs.define()
class FirmwareNode(CommunicationNode[MsgT, DataT]):
    node: ReporterNode
    message_type: type[MsgT]
    response_type: type[DataT]

    @override
    def send(self, msg: MsgT) -> DataT:
        if not isinstance(msg, self.message_type):
            raise TypeError(f"Unsupported message type {type(msg)}, expected {self.message_type}")

        result = self.node.send(msg)

        if isinstance(result, Success):
            if isinstance(result.data, self.response_type):
                return result.data
            
            raise TypeError(f"Unsupported data type {type(result)} from firmware, expected {self.response_type}")

        if isinstance(result, Failure):
            raise RuntimeError(result.msg)

        raise TypeError(f"Unsupported return type from firmware container {type(result)}")

    @override
    def stop(self):
        self.node.stop()


@attrs.define()
class FirmwareComponent(Component[Environment, FirmwareNode[MsgT, DataT]]):
    """A component representing the firmware/controller of a system.

    Args:
        image: The docker image to use for execution
        command: The command to execute in the container
        port: The port to use for communication with the controller
    """

    def __init__(self,
        image: str,
        command: str,
        port: int,
        message_type: type[MsgT],
        response_type: type[DataT],
        *,
        remove: bool = False
    ):
        self.component = ReporterComponent(image, command, port, remove=remove)
        self.message_type = message_type
        self.response_type = response_type

    def start(self, environment: Environment) -> FirmwareNode[MsgT, DataT]:
        node = self.component.start(environment)
        return FirmwareNode(node, self.message_type, self.response_type)


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
