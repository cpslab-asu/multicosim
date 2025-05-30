from __future__ import annotations

from typing import ContextManager


class Simulation:
    pass


class Simulator:
    def start(self) -> ContextManager[Simulation]:
        ...
