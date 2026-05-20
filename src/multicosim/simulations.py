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

import contextlib
from typing import Protocol, TypeVar

EnvT = TypeVar("EnvT", contravariant=True)


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

    @contextlib.contextmanager
    def run(self):
        sys = self.start()

        try:
            yield sys
        finally:
            sys.stop()


class Component(Protocol[EnvT, SimT]):
    """A component in the simulator tree.

    Each component must implement the `start` method, which receives an environment value that
    is implementation-specified and must return a `Node` implementation that represents the running
    simulation of this component. Components are intended to be composed into `Simulator` instances
    so that each element of the system is represented individually.

    This interface has one type parameter `EnvT` which represents the type of the environment
    required to start the component.
    """

    def start(self, environment: EnvT, /) -> SimT:
        """Start the simulator and return a handle to the executing simulation."""
        ...
