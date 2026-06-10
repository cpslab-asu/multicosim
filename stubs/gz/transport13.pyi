from collections.abc import Callable
from typing import TypeVar

class SubscribeOptions:
    msgs_per_sec: int

_MsgT = TypeVar("_MsgT")

class Node:
    def subscribe(
        self,
        msg_type: type[_MsgT],
        topic: str,
        callback: Callable[[_MsgT], None],
        options: SubscribeOptions = ...,
    ) -> bool: ...

class Publisher: ...
