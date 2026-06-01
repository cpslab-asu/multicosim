from collections.abc import AsyncIterable

from .action import Action
from .core import Core
from .mission import Mission
from .telemetry import Telemetry

class System:
    @property
    def core(self) -> Core: ...

    @property
    def mission(self) -> Mission: ...

    @property
    def telemetry(self) -> Telemetry: ...

    @property
    def action(self) -> Action: ...

    async def connect(self) -> None: ...
