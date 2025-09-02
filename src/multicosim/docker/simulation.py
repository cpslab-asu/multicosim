from collections.abc import Mapping
from re import match
from typing import TypeVar, cast

import attrs
import docker
import nanoid
from typing_extensions import override

from ..simulations import Component, MultiComponentSimulator, Node, NodeId, Simulation, Simulator

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
    client: docker.DockerClient
    network_name: str


def _generate_network_name() -> str:
    network_name = nanoid.generate()

    while not match("^[a-zA-Z0-9].*", network_name):
        network_name = nanoid.generate()

    return network_name


class ContainerSimulator(MultiComponentSimulator[Environment, ContainerSimulation]):
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
        network_name = _generate_network_name()

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
