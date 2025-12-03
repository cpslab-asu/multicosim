from __future__ import annotations

from collections.abc import Generator, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import attrs
import docker
from typing_extensions import override

from ..simulations import Node, Component
from .component import ContainerComponent, ContainerNode
from .simulation import Environment

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
class _Gazebo:
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


@attrs.define()
class GazeboContainerNode(Node):
    """Node representing an executing Gazebo simulation.

    Args:
        world: The name of the world generated for execution
        node: The node managing the container execution
    """

    world: str
    node: ContainerNode

    @override
    def stop(self):
        return self.node.stop()


class GazeboContainerComponent(Component[Environment, GazeboContainerNode]):
    """A component that produces a Gazebo simulation inside of a container.

    Args:
        image: The container image that contains Gazebo
        template: The SDF file to use as a template to generate the final configuration
        model_dir: The directory of the Gazebo models
        world: The name of the generated world
        backend: The integration backend to use for the physics simulation
        step_size: The size of the integration step to use for the physics simulation
        sensor_topics: A list of (model, sensor, new_topic) tuples used to remap sensor topics
        name: The name of the container to use
        headless: Run the simulation without a graphical interface
        record: Have simulation record state and console logs to /app/logs
        remove: Remove the container when the simulation is stopped
        monitor: Raise an error if the container exists before it is stopped
    """

    def __init__(
        self,
        image: str = "ghcr.io/cpslab-asu/multicosim/gazebo:harmonic",
        template: str = "/app/resources/worlds/default.sdf",
        model_dir: Path = Path("/app/resources/models"),
        world: str = "generated",
        backend: Backend | None = None,
        step_size: float = 0.001,
        sensor_topics: Iterable[tuple[str, str, str]] | None = None,
        *,
        name: str = "",
        headless: bool = False,
        record: bool = False,
        remove: bool = False,
        monitor: bool = False,
    ):
        if not backend:
            backend = ODE()

        if not sensor_topics:
            sensor_topics = {}

        parts = [
            "gazebo",
            "--verbose",
            f"--base {template}",
            f"--world {world}",
            f"--step-size {step_size}",
            f"--model-dir {model_dir}",
        ]

        if headless:
            parts.append("--headless")

        if record:
            parts.append("--record")

        for model_name, sensor_name, topic_name in sensor_topics:
            parts.append(f"--sensor-topic {model_name} {sensor_name} {topic_name}")

        prefix = " ".join(parts)
        command = f"{prefix} {backend.args}"

        self.world = world
        self.component = ContainerComponent(
            image=image,
            command=command,
            name=name,
            remove=remove,
            monitor=monitor,
        )

    @override
    def start(self, environment: Environment) -> GazeboContainerNode:
        return GazeboContainerNode(self.world, self.component.start(environment))


@dataclass()
class Simulation:
    """Gazebo simulation executed in a docker container.

    Args:
        container: The simulation container
    """

    container: Container


class GazeboError(Exception):
    pass


@attrs.define()
class BaseGazeboConfig:
    world: str = attrs.field(default="generated")
    backend: Backend | None = attrs.field(default=None)
    step_size: float = attrs.field(default=0.001)
    name: str = attrs.field(default="", kw_only=True)
    remove: bool = attrs.field(default=True, kw_only=True)
    monitor: bool = attrs.field(default=True, kw_only=True)


@attrs.define()
class GazeboConfig(BaseGazeboConfig):
    image: str | None= attrs.field(default=None)
    template: str | None = attrs.field(default=None)
    model_dir: str | None = attrs.field(default=None)
    sensor_topics: list[tuple[str, str, str]] = attrs.field(factory=list)

    def params(self) -> dict[str, Any]:
        params = {}
        if self.image is not None:
            params["image"] = self.image
        if self.template is not None:
            params["template"] = self.template
        if self.model_dir is not None:
            params["template"] = self.model_dir
        params["world"] = self.world
        params["backend"] = self.backend
        params["step_size"] = self.step_size
        params["sensor_topics"] = self.sensor_topics
        params["name"] = self.name
        params["remove"] = self.remove
        params["monitor"] = self.monitor
        return params


@contextmanager
def start(
    config: _Gazebo,
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
