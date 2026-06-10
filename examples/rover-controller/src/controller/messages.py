from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from controller import attacks, automaton


@dataclass()
class Step:
    time: float = field()
    position: tuple[float, float, float] = field()
    heading: float = field()
    roll: float = field()
    state: automaton.State = field()


@dataclass()
class Result(Iterable[Step]):
    history: list[Step] = field()

    def __iter__(self) -> Iterator[Step]:
        return iter(self.history)


@dataclass()
class Start:
    world: str = field()
    frequency: int = field()
    magnet: attacks.Magnet | None = field()
    speed: attacks.SpeedController | None = field()
    commands: Iterable[automaton.Command | None] = field()
