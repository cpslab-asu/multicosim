from __future__ import annotations

from typing import Generic, Protocol, TypeVar

import attrs
import nanoid


class Node(Protocol):
    """A node in the executing simulation tree."""

    def stop(self):
        ...


NodeT = TypeVar("NodeT", covariant=True, bound=Node)


@attrs.frozen(hash=True)
class NodeId(Generic[NodeT]):
    _id: str = attrs.field(factory=nanoid.generate, init=False)


MsgT = TypeVar("MsgT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class CommunicationNode(Node, Protocol[MsgT, ResultT]):
    def send(self, msg: MsgT) -> ResultT:
        ...


EnvT = TypeVar("EnvT", contravariant=True)


class Component(Protocol[EnvT, NodeT]):
    """A component in the simulator tree."""

    def start(self, environment: EnvT) -> NodeT:
        ...


class Simulation(Protocol):
    def stop(self):
        ...


EnvT_co = TypeVar("EnvT_co", covariant=True)
NodeIdT = TypeVar("NodeIdT", covariant=True)
SimT = TypeVar("SimT", bound=Simulation, covariant=True)


class Simulator(Protocol[EnvT_co, SimT]):
    """A tree of components representing the system to be simulated."""

    def add(self, component: Component[EnvT_co, NodeT]) -> NodeId[NodeT]:
        ...

    def start(self) -> SimT:
        ...
