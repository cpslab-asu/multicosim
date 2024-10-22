from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeAlias

import docker
import docker.models.containers

if TYPE_CHECKING:
    Client: TypeAlias = docker.DockerClient
    Container: TypeAlias = docker.models.containers.Container


class Backend(Protocol):
    @property
    def args(self) -> str:
        ...


@dataclass()
class ODE(Backend):
    class Solver(IntEnum):
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
    class Solver(IntEnum):
        DANZIG = 0
        PGS = 1

    solver: Solver = Solver.DANZIG

    @property
    def args(self) -> str:
        if self.solver is Dart.Solver.DANZIG:
            solver = "danzig"
        else:
            solver = "pgs"

        return f"dart --solver {solver}"


@dataclass()
class Bullet(Backend):
    iterations: int = 50

    @property
    def args(self) -> str:
        return f"bullet --iterations {self.iterations}"


@dataclass()
class Simbody(Backend):
    @property
    def args(self) -> str:
        return "simbody"


@dataclass()
class Config:
    backend: Backend = field(default_factory=ODE)
    step_size: float = field(default=0.001)

    @property
    def args(self) -> str:
        return f"--step-size {self.step_size} {self.backend.args}"


class Host(Protocol):
    @property
    def name(self) -> str:
        ...


@dataclass()
class Gazebo:
    container: Container


@contextmanager
def gazebo(
    config: Config,
    host: Host,
    *,
    image: str = "cpslabasu/gazebo:harmonic",
    base: Path = Path("resources/world/default.sdf"),
    world: Path = Path("/tmp/generated.sdf"),
    client: Client | None = None,
    remove: bool = False
) -> Generator[Gazebo, None, None]:
    if not client:
        client = docker.from_env()

    cmd = f"gazebo --base {base} --world {world} {config.args}"
    container = client.containers.run(
        image=image,
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
