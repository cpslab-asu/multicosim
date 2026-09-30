from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from typing_extensions import override

from . import attacks, automaton


@dataclass(frozen=True)
class Step:
    time: float = field()
    position: tuple[float, float, float] = field()
    heading: float = field()
    roll: float = field()
    state: automaton.State = field()


@dataclass(frozen=True)
class Result(Iterable[Step]):
    history: list[Step] = field()

    @override
    def __iter__(self) -> Iterator[Step]:
        return iter(self.history)


@dataclass()
class Start:
    magnet: attacks.Magnet | None = field(default=None)
    speed: attacks.SpeedController | None = field(default=None)
    commands: Iterable[automaton.Command] | None = field(default=None)
