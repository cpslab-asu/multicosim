from collections.abc import Callable
from typing import Any, Generic, TypeVar

class SubscribeOptions:
    msgs_per_sec: int

_MsgT = TypeVar("_MsgT")
_RepT = TypeVar("_RepT")

class Publisher(Generic[_MsgT]):
    def valid(self) -> bool: ...
    def publish(self, msg: _MsgT) -> None: ...

class Node:
    def advertise(self, topic: str, msg_type: type[_MsgT]) -> Publisher[_MsgT]: ...

    def subscribe(
        self,
        msg_type: type[_MsgT],
        topic: str,
        callback: Callable[[_MsgT], Any],
        options: SubscribeOptions = ...,
    ) -> bool: ...

    def request(
        self,
        service: str,
        request: _MsgT,
        request_type: type[_MsgT],
        response_type: type[_RepT],
        timeout: int,
    ) -> tuple[bool, _RepT]: ...
