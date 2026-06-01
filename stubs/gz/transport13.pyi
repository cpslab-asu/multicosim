from collections.abc import Callable
from typing import TypeVar

class SubscribeOptions:
    msgs_per_sec: int

MsgT = TypeVar("MsgT")

class Node:
    def subscribe(self, msg_type: type[MsgT], topic: str, callback: Callable[[MsgT], None], options: SubscribeOptions = ...) -> bool: ...

class Publisher: ...
