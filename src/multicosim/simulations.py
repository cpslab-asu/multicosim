"""Interfaces for defining simulators and simulation components.

Defining a simulator is done by implementing the `Simulator` interface, which has only a
single required method called `start` that must return a value representing the executing
simulation. This return value must implement the `Simulation` interface, which also only
has a single required method called `stop` that is responsible for terminating the
simulation.

To represent a simulation of multiple discrete components, this module provides a more specialized
`Simulator` interface called `MultiComponentSimulator`. This interface introduces another required
method called `add` that is responsible for registering a given component with the simulation and
returning a unique identifier for that component.

Simulation components must implement the `Component` interface, which accepts a parameter
representing the execution environment of the component and returns a value representing the
executing component. The value returned from the component must implement the `Node` interface,
which requires a `stop` method that is used to terminate the simulation of the component.
"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

import attrs
import nanoid


class Node(Protocol):
    """A node in the executing simulation tree.

    Each node represents a running simulation, and each implementation must provide a `stop` method
    that will terminate the execution.
    """

    def stop(self):
        """Stop the simulation of the system component."""
        ...


NodeT = TypeVar("NodeT", covariant=True, bound=Node)


@attrs.frozen(hash=True)
class NodeId(Generic[NodeT]):
    """Unique identifier for a `Node` in a `Simulator`.

    NodeIds are frozen, and cannot be modified once created. Each NodeId has an associated type
    variable `NodeT` which represents the type of node that it references in the `Simulator`.
    However, this type variable is only relevant when type checking the program, and is not
    available at runtime.
    """

    _id: str = attrs.field(factory=nanoid.generate, init=False)


MsgT = TypeVar("MsgT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class CommunicationNode(Node, Protocol[MsgT, ResultT]):
    """Node that allows communication with the running simulation.

    This node enables sending and receiving messages from the simulation as it runs, which allows
    for implementations to request information or provide additional inputs to the simulator as
    it runs. Each implementation must provide the `send` method, which accepts a message as its
    parameter and returns the response from the simulation.

    This interface has two type parameters. `MsgT` is the type of the message to send to the
    simulation and `ResultT` is the type of the response. No type checking is done on these
    values by default.
    """

    def send(self, msg: MsgT) -> ResultT:
        """Send the given message to the simulation and return the response."""
        ...


EnvT = TypeVar("EnvT", contravariant=True)


class Component(Protocol[EnvT, NodeT]):
    """A component in the simulator tree.

    Each component must implement the `start` method, which receives an environment value that
    is implementation-specified and must return a `Node` implementation that represents the running
    simulation of this component. Components are intended to be composed into `Simulator` instances
    so that each element of the system is represented individually.

    This interface has one type parameter `EnvT` which represents the type of the environment
    required to start the component.
    """

    def start(self, __environment: EnvT) -> NodeT:
        """Start the simulator and return a handle to the executing simulation."""
        ...


class Simulation(Protocol):
    """An execution simulation of a system.

    This interface requires the implementation of the `stop` method, which is responsible for
    terminating the simulation and freeing all of the resources in use.
    """

    def stop(self):
        """Stop the simulation."""
        ...


EnvT_co = TypeVar("EnvT_co", covariant=True)
NodeIdT = TypeVar("NodeIdT", covariant=True)
SimT = TypeVar("SimT", bound=Simulation, covariant=True)


class Simulator(Protocol[EnvT_co, SimT]):
    """A representation of a system that can be executed.

    This interface requires implementers to define the `start` method, which is responsible for
    starting the simulation execution and returning a `Simulation` handle that can be used to
    stop the simulation.

    This interface has two type parameters. `EnvT` is the type of the environment used to start
    the simulation and `SimT` is the type of the `Simulation` instance returned.
    """

    def start(self) -> SimT:
        """Start the simulator and return a handle to the executing simulation."""
        ...


class MultiComponentSimulator(Simulator[EnvT_co, SimT], Protocol):
    """A simulator that is composed of several components representing system elements.

    This interface imposes a slightly more specific structure onto the simulator which assumes that
    the simulator is composed of several components. This requires an extra method `add` which is
    responsible for registering the component with the simulator and returning a NodeId that
    identifies the added component.
    """

    def add(self, component: Component[EnvT_co, NodeT]) -> NodeId[NodeT]:
        """Add a component to a simulator.

        The component to add should accept the type of environment value produced by this simulator,
        which can be checked using the type checker. The unique identifier produced by this
        method is parameterized by the type of node it creates so that the exact type can be
        used when retrieving the node from the running simulation.

        Args:
            component: The component to be added

        Returns:
            The unique id of the component
        """

        ...
