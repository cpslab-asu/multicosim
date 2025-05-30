from __future__ import annotations

import contextlib
import typing

import typing_extensions
import zmq

if typing.TYPE_CHECKING:
    from collections.abc import Callable, Generator

_T = typing.TypeVar("_T")


class Instance(typing.Generic[_T]):
    def run(self):
        ...


class DefaultInstance(Instance[_T]):
    def __init__(self, container, msg: _T):
        ...

    @typing_extensions.override
    def run(self):
        with contextlib.ExitStack() as stack:
            ctx = stack.enter_context(zmq.Context())
            sock = stack.enter_context


class Component(typing.Generic[_T]):
    def start(self) -> typing.ContextManager[Instance[_T]]:
        ...


class ComponentWrapper(Component[_T]):
    def __init__(self, factory: Callable[[], _T]):
        self.factory = factory

    def start(self) -> typing.ContextManager[Instance[_T]]:
        return DefaultInstance(None, self.factory())


def component(gen: Callable[[], _T]) -> Component[_T]:
    ...
