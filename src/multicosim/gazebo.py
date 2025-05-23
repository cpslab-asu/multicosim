from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import docker

from . import containers

if TYPE_CHECKING:
    from docker import DockerClient as Client
    from docker.models.containers import Container


class Backend(Protocol):
    """Backend to use for physics computations during simulation."""

    @property
    def args(self) -> str:
        """Arguments to gazebo program representing the backend options."""
        ...


@dataclass()
class ODE(Backend):
    """Open Dynamics Engine physics backend.

    Args:
        solver: Selected solver for physics dynamics
        iterations: Number of solver iterations at each time step
    """

    class Solver(IntEnum):
        """Open Dynamics Engine backend dynamics equations solver.
        
        The `QUICK` solver uses an iterative Projected Gauss-Seidel method whose accuracy scales with
        the number of iterations. The `WORLD` solver uses a direct method called Dantzig that always
        produces an accurate solution if one exists.
        """

        QUICK = 0
        WORLD = 1

    solver: Solver = Solver.QUICK
    iterations: int = 50

    @property
    def args(self) -> str:
        if self.solver is ODE.Solver.QUICK:
            solver = "quick"
        else:
            solver = "world"

        return f"ode --solver {solver} --iterations {self.iterations}"


@dataclass()
class Dart(Backend):
    """Dart physics backend.

    Args:
        solver: Selected solver for physics dynamics equations.
    """

    class Solver(IntEnum):
        """Dart backend dynamics equations solver.
        
        The `PGS` solver uses an iterative Projected Gauss-Seidel approximation method. The
        `DANTZIG` solver uses a direct method called Dantzig that always produces an accurate
        solution if one exists.
        """

        DANTZIG = 0
        PGS = 1

    solver: Solver = Solver.DANTZIG

    @property
    def args(self) -> str:
        if self.solver is Dart.Solver.DANTZIG:
            solver = "dantzig"
        else:
            solver = "pgs"

        return f"dart --solver {solver}"


@dataclass()
class Bullet(Backend):
    """Bullet physics backend.

    Args:
        iterations: Number of computation iterations per time-step
    """

    iterations: int = 50

    @property
    def args(self) -> str:
        return f"bullet --iterations {self.iterations}"


@dataclass()
class Simbody(Backend):
    """Simbody physics backend."""

    @property
    def args(self) -> str:
        return "simbody"


@dataclass()
class Gazebo:
    """Gazebo simulation configuration.

    Args:
        backend: The backed to use for the simulation physics dynamics
        step_size: The duration of each time step in the simulation
    """

    backend: Backend = field(default_factory=ODE)
    step_size: float = field(default=0.001)

    @property
    def args(self) -> str:
        """Arguments to gazebo program representing the backend options."""

        return f"--step-size {self.step_size} {self.backend.args}"


@dataclass()
class Simulation:
    """Gazebo simulation executed in a docker container.
    
    Args:
        container: The simulation container
    """

    container: Container


class GazeboError(Exception):
    pass


@contextmanager
def start(
    config: Gazebo,
    host: Container,
    *,
    image: str = "ghcr.io/cpslab-asu/multicosim/gazebo:harmonic",
    base: Path = Path("resources/world/default.sdf"),
    world: Path = Path("/tmp/generated.sdf"),
    client: Client | None = None,
    remove: bool = False
) -> Generator[Simulation, None, None]:
    """Execute a gazebo simulation and attach it to the given host container.

    Args:
        config: Simulation configuration options,
        host: Host container to attach simulation container networking stack to
        image: The container image to use to execute the simulation
        base: The world to use as a template for the configured world
        world: The path of the world file to generate
        client: The docker client to use to create the containers
        remove: Remove containers after execution

    Returns:
        A context manager that provides a handle to the gazebo simulation and terminates and cleans
        up the simulation when the context is exited.
    """

    if not client:
        client = docker.from_env()

    # Reload container until it defines a name
    while not host.name:
        host.reload()

    # Ensure host container is running before trying to attach
    if host.status != "running":
        raise GazeboError("Host container is not running")

    cmd = f"gazebo --base {base} --world {world} {config.args}"
    ctx = containers.start(image, command=cmd, host=host, remove=remove, client=client)

    with ctx as container:
        try:
            yield Simulation(container)
        finally:
            pass
