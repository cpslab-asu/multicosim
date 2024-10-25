from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeAlias

import docker
import docker.models.containers

import gzcm.docker

if TYPE_CHECKING:
    Client: TypeAlias = docker.DockerClient
    Container: TypeAlias = docker.models.containers.Container


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
class Config:
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


class Host(Protocol):
    """Container to attach simulation networking stack to."""

    @property
    def name(self) -> str:
        """Name of the networking host container."""
        ...


@dataclass()
class Gazebo:
    """Gazebo simulation executed in a docker container.
    
    Args:
        container: The simulation container
    """

    container: Container


@contextmanager
def gazebo(
    config: Config,
    host: Host,
    *,
    image: str = "ghcr.io/cpslab-asu/gzcm/gazebo:harmonic",
    base: Path = Path("resources/world/default.sdf"),
    world: Path = Path("/tmp/generated.sdf"),
    client: Client | None = None,
    remove: bool = False
) -> Generator[Gazebo, None, None]:
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

    image_ = gzcm.docker.ensure_image(image, client=client)
    cmd = f"gazebo --base {base} --world {world} {config.args}"
    container = client.containers.run(
        image=image_,
        command=cmd,
        detach=True,
        network_mode=f"container:{host.name}"
    )

    try:
        yield Gazebo(container)
    finally:
        container.kill()
        container.wait()

        if remove:
            container.remove()
