from collections.abc import Callable
from datetime import datetime
from typing import Any

from ..job import Job

class BlockingScheduler:
    def add_job(
        self,
        func: Callable[[], Any],
        trigger: str = ...,
        args: list[Any] | tuple[Any, ...] = ...,
        kwargs: dict[str, Any] = ...,
        id: str = ...,
        name: str = ...,
        misfire_grace_time: int = ...,
        coalesce: bool = ...,
        max_instances: int = ...,
        next_run_time: datetime = ...,
        jobstore: str = ...,
        executor: str = ...,
        replace_existing: bool = ...,
        *,
        seconds: float = ...,
    ) -> Job: ...
    def start(self, paused: bool = ...) -> None: ...
    def remove_all_jobs(self) -> None: ...
    def shutdown(self, *, wait: bool = ...) -> None: ...
