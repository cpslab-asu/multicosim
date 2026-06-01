from collections.abc import AsyncIterable

class Health:
    @property
    def is_home_position_ok(self) -> bool: ...

    @property
    def is_local_position_ok(self) -> bool: ...

    @property
    def is_global_position_ok(self) -> bool: ...

    @property
    def is_armable(self) -> bool: ...

class Telemetry:
    def health(self) -> AsyncIterable[Health]: ...
