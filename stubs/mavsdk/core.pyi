from collections.abc import AsyncIterable

class ConnectionState:
    @property
    def is_connected(self) -> bool: ...

class Core:
    def connection_state(self) -> AsyncIterable[ConnectionState]: ...
