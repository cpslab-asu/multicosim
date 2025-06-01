from __future__ import annotations

from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import ContextManager, Generic, TypeVar

from typing_extensions import ParamSpec, override

SimT = TypeVar("SimT")


class Simulator(Generic[SimT]):
    def start(self) -> ContextManager[SimT]:
        ...


class DefaultSimulator(Simulator[SimT]):
    def __init__(self, factory: Callable[[], ContextManager[SimT]]):
        self.factory = factory

    @override
    def start(self) -> ContextManager[SimT]:
        return self.factory()


P = ParamSpec("P")
 

def simulator(func: Callable[P, Generator[SimT, None, None]]) -> Callable[P, Simulator[SimT]]:
    """Transform a generator into a simulator instance."""

    def _wrapper(*args: P.args, **kwargs: P.kwargs) -> Simulator[SimT]:
        @contextmanager
        def _inner() -> Generator[SimT, None, None]:
            return func(*args, **kwargs)

        return DefaultSimulator(_inner)

    return _wrapper
