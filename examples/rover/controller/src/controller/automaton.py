from __future__ import annotations

import abc
import dataclasses as dc
import enum
import logging
import math
import typing

Position: typing.TypeAlias = tuple[float, float, float]
Command: typing.TypeAlias = typing.Literal[55, 66]
Direction: typing.TypeAlias = typing.Literal[-1, 0, 1]


@dc.dataclass(frozen=True, slots=True)
class Flags:
    """State of the internal flags of the system."""

    autodrive: bool = dc.field(default=False)
    update_compass: bool = dc.field(default=False)
    update_gps: bool = dc.field(default=False)
    check_position: bool = dc.field(default=True)
    move: bool = dc.field(default=False)


class Model(typing.Protocol):
    """Wrapper class to avoid setting rover properties unintentionally in states."""

    @property
    def position(self) -> Position:
        ...

    @property
    def heading(self) -> float:
        ...


class Action(enum.IntEnum):
    DRIVE = 0
    TURN = 1
    STOP = 2


@dc.dataclass(frozen=True, slots=True)
class State(abc.ABC):
    """An abstract system state representing a behavior of the system."""
    flags: Flags
    
    @abc.abstractmethod
    def next(self, model: Model, cmd: Command | None) -> State:
        """Advance the system to the next state."""

        ...

    @property
    def action(self) -> Action:
        return Action.STOP

    def is_terminal(self) -> bool:
        return False


def _create_state_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(f"automaton.{name}")
    logger.addHandler(logging.NullHandler())

    return logger


@dc.dataclass(frozen=True, slots=True)
class S1(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S1")

    time: float = dc.field()
    step_size: float = dc.field()

    def __post_init__(self):
        assert self.flags.check_position
        assert not self.flags.autodrive
        assert not self.flags.update_compass
        assert not self.flags.update_gps
        assert not self.flags.move

    def next(self, model: Model, cmd: Command | None) -> State:
        if self.time >= 5:
            self.LOGGER.info("Wait time exceeded. Transitioning to S2.")
            return S2(
                flags=dc.replace(self.flags, autodrive=True),
                initial_position=model.position,
            )

        self.LOGGER.info(f"Current time: {self.time}, Time remaining: {5 - self.time}")
        return S1(self.flags, step_size=self.step_size, time=self.time + self.step_size)


def euclidean_distance(p1: Position, p2: Position) -> float:
    return math.sqrt(
        math.pow(p2[0] - p1[0], 2) + math.pow(p2[1] - p1[1], 2) + math.pow(p2[2] - p1[2], 2)
    )


@dc.dataclass(frozen=True, slots=True)
class S2(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S2")

    initial_position: tuple[float, float, float] = dc.field()

    def __post_init__(self):
        assert self.flags.check_position
        assert self.flags.autodrive
        assert not self.flags.update_compass
        assert not self.flags.update_gps
        assert not self.flags.move

    @property
    def action(self) -> Action:
        return Action.DRIVE

    def next(self, model: Model, cmd: Command | None) -> State:
        if cmd == 66:
            self.LOGGER.info(f"Received command {cmd}, transitioning to S6")
            return S6(flags=dc.replace(self.flags, autodrive=False, check_position=False))

        position = model.position
        distance = euclidean_distance(position, self.initial_position)

        if distance >= 7:
            self.LOGGER.info("Distance threshold exceeded. Transitioning to S3.")
            return S3(
                flags=dc.replace(self.flags, check_position=False, update_compass=True),
                initial_heading=model.heading,
            )
        
        self.LOGGER.info(f"Rover position: <{position[0]:.4f}, {position[1]:.4f}, {position[2]:.4f}>.")
        self.LOGGER.info(f"Remaining distance: {7 - distance:.4f}")
        return S2(self.flags, self.initial_position)


@dc.dataclass(frozen=True, slots=True)
class S3(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S3")

    initial_heading: float = dc.field()
    
    def __post_init__(self):
        assert self.flags.autodrive
        assert self.flags.update_compass
        assert not self.flags.check_position
        assert not self.flags.update_gps
        assert not self.flags.move

    @property
    def action(self) -> Action:
        return Action.TURN

    def next(self, model: Model, cmd: Command | None) -> State:
        if cmd == 66:
            self.LOGGER.info(f"Received command {cmd}. Transitioning to S8")
            return S8(flags=dc.replace(self.flags, autodrive=False, check_position=False))

        heading = model.heading

        if heading > self.initial_heading:
            degrees = self.initial_heading + (360 - heading)
        else:
            degrees = self.initial_heading - heading

        self.LOGGER.info(f"Current heading: {heading: 0.4f}. Ground truth heading: {model.heading_real:.4f}")

        if degrees >= 70:
            self.LOGGER.info("Transitioning to S4")
            return S4(flags=dc.replace(self.flags, update_compass=False, update_gps=True))
        
        self.LOGGER.info(f"Degrees to target heading: {70 - degrees}")
        return S3(self.flags, self.initial_heading)


@dc.dataclass(frozen=True, slots=True)
class S4(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S4")

    def __post_init__(self):
        assert self.flags.autodrive
        assert self.flags.update_gps
        assert not self.flags.update_compass
        assert not self.flags.check_position
        assert not self.flags.move

    @property
    def action(self) -> Action:
        return Action.TURN
    
    def next(self, model: Model, cmd: Command | None) -> State:
        self.LOGGER.info("Transitioning to S5")
        return S5(
            flags=dc.replace(self.flags, update_gps=False, move=True),
            initial_position=model.position,
        )


@dc.dataclass(frozen=True, slots=True)
class S5(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S5")

    initial_position: Position
    
    def __post_init__(self):
        assert self.flags.autodrive
        assert self.flags.move
        assert not self.flags.update_gps
        assert not self.flags.update_compass
        assert not self.flags.check_position

    @property
    def action(self) -> Action:
        return Action.DRIVE
    
    def next(self, model: Model, cmd: Command | None) -> State:
        if cmd == 66:
            self.LOGGER.info(f"Received command {cmd}. Transitioning to S7")
            return S7(flags=dc.replace(self.flags, autodrive=False, check_position=False))

        position = model.position
        distance = euclidean_distance(self.initial_position, position)

        if distance >= 7:
            self.LOGGER.info("Distance threshold exceeded. Transitioning to S6.")
            return S6(flags=dc.replace(self.flags, autodrive=False, move=False))

        self.LOGGER.info(f"Rover position: <{position[0]:.4f}, {position[1]:.4f}, {position[2]:.4f}>.")
        self.LOGGER.info(f"Remaining distance: {7 - distance:.4f}")
        return S5(self.flags, self.initial_position)


@dc.dataclass(frozen=True, slots=True)
class S6(State):
    def __post_init__(self):
        assert not self.flags.autodrive
        assert not self.flags.move
        assert not self.flags.update_gps
        assert not self.flags.update_compass
        assert not self.flags.check_position

    def is_terminal(self) -> bool:
        return True

    def next(self, model: Model, cmd: Command | None) -> State:
         return S6(self.flags)


@dc.dataclass(frozen=True, slots=True)
class S7(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S7")

    def __post_init__(self):
        assert self.flags.move
        assert not self.flags.autodrive
        assert not self.flags.update_gps
        assert not self.flags.update_compass
        assert not self.flags.check_position

    @property
    def action(self) -> Action:
        return Action.DRIVE

    def next(self, model: Model, cmd: Command | None) -> State:
        if cmd == 55:
            self.LOGGER.info(f"Command receieved: {cmd}. Transitioning to S9")
            return S9(self.flags)
        
        self.LOGGER.info("Transitioning to S6")
        return S6(flags=dc.replace(self.flags, move=False))


@dc.dataclass(frozen=True, slots=True)
class S8(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S8")

    def __post_init__(self):
        assert self.flags.update_compass
        assert not self.flags.autodrive
        assert not self.flags.check_position
        assert not self.flags.update_gps
        assert not self.flags.move

    @property
    def action(self) -> Action:
        return Action.TURN

    def next(self, model: Model, cmd: Command | None) -> State:
        self.LOGGER.info("Transitioning to S7")
        return S7(flags=dc.replace(self.flags, move=True, update_compass=False))


@dc.dataclass(frozen=True, slots=True)
class S9(State):
    def __post_init__(self):
        assert not self.flags.move
        assert not self.flags.update_compass
        assert not self.flags.autodrive
        assert not self.flags.check_position
        assert not self.flags.update_gps

    def is_terminal(self) -> bool:
        return True

    def next(self, model: Model, cmd: Command | None) -> State:
        return S9(self.flags)


class Automaton:
    def __init__(self, model: Model, step_size: float):
        self.model = model
        self.state: State = S1(flags=Flags(), time=0.0, step_size=step_size)
        self.history: list[State] = []

    def step(self, cmd: Command | None):
        self.history.append(self.state)
        self.state = self.state.next(self.model, cmd)

    @property
    def action(self) -> Action:
        return self.state.action
