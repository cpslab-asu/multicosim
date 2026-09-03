from __future__ import annotations

from enum import IntEnum
from functools import singledispatch
from typing import TypeAlias

import attrs
import namer


@attrs.frozen()
class ODE:
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


@attrs.frozen()
class Dart:
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


@attrs.frozen()
class Bullet:
    """Bullet physics backend.

    Args:
        iterations: Number of computation iterations per time-step
    """

    iterations: int = 50


@attrs.frozen()
class Simbody:
    """Simbody physics backend."""


Backend: TypeAlias = ODE | Dart | Bullet | Simbody


@singledispatch
def backend_args(b: Backend) -> str:
    raise NotImplementedError()


@backend_args.register(ODE)
def _(b: ODE) -> str:
    solver = "quick" if b.solver is b.Solver.QUICK else "world"
    return f"ode --solver {solver} --iterations {b.iterations}"


@backend_args.register(Dart)
def _(b: Dart) -> str:
    solver = "pgs" if b.solver is b.Solver.PGS else "dantzig"
    return f"dart --solver {solver}"


@backend_args.register(Bullet)
def _(b: Bullet) -> str:
    return f"bullet --iterations {b.iterations}"


@backend_args.register(Simbody)
def _(b: Simbody) -> str:
    return "simbody"


@attrs.define()
class Options:
    backend: Backend = attrs.field(factory=ODE)
    step_size: float = attrs.field(kw_only=True, default=0.001)
    world: str = attrs.field(kw_only=True, factory=namer.generate)
    run: bool = attrs.field(kw_only=True, default=True)
