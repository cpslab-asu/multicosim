from __future__ import annotations

import abc
import dataclasses as dc
import enum
import logging
import math
import typing
import numpy as np

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

    time: float = dc.field(default=0.0)
    
    @abc.abstractmethod
    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
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

    def __post_init__(self):
        assert self.flags.check_position
        assert not self.flags.autodrive
        assert not self.flags.update_compass
        assert not self.flags.update_gps
        assert not self.flags.move

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
        if self.time >= 5:
            self.LOGGER.info("Wait time exceeded. Transitioning to S2.")
            return S2(
                flags=dc.replace(self.flags, autodrive=True),
                time=0.0,
                initial_position=model.position
            )

        self.LOGGER.info(f"Current time: {self.time}, Time remaining: {5 - self.time}")
        return S1(self.flags, time=self.time + step_size)


def euclidean_distance(p1: Position, p2: Position) -> float:
    return math.sqrt(
        math.pow(p2[0] - p1[0], 2) + math.pow(p2[1] - p1[1], 2) + math.pow(p2[2] - p1[2], 2)
    )


@dc.dataclass(frozen=True, slots=True)
class S2(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S2")

    initial_position: tuple[float, float, float] = dc.field(default=(0.0,0.0,0.0))

    def __post_init__(self):
        assert self.flags.check_position
        assert self.flags.autodrive
        assert not self.flags.update_compass
        assert not self.flags.update_gps
        assert not self.flags.move

    @property
    def action(self) -> Action:
        return Action.DRIVE

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
        if cmd == 66:
            self.LOGGER.info(f"Received command {cmd}, transitioning to S6")
            return S6(flags=dc.replace(self.flags, autodrive=False, check_position=False))

        position = model.position
        distance = euclidean_distance(position, self.initial_position)

        if distance >= 7:
            self.LOGGER.info("Distance threshold exceeded. Transitioning to S3.")
            return S3(
                flags=dc.replace(self.flags, check_position=False, update_compass=True),
                time=0.0,
                initial_heading=model.heading
            )
        
        self.LOGGER.info(f"Rover position: <{position[0]:.4f}, {position[1]:.4f}, {position[2]:.4f}>.")
        self.LOGGER.info(f"Remaining distance: {7 - distance:.4f}")
        return S2(self.flags, time=0.0, initial_position=self.initial_position)


@dc.dataclass(frozen=True, slots=True)
class S3(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S3")

    initial_heading: float = dc.field(default=0.0)

    def __post_init__(self):
        assert self.flags.autodrive
        assert self.flags.update_compass
        assert not self.flags.check_position
        assert not self.flags.update_gps
        assert not self.flags.move

    @property
    def action(self) -> Action:
        return Action.TURN

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
        if cmd == 66:
            self.LOGGER.info(f"Received command {cmd}. Transitioning to S8")
            return S8(flags=dc.replace(self.flags, autodrive=False, check_position=False))

        heading_delta = model.heading - self.initial_heading

        # Determines shortest distance and direction when differencing values between pi and -pi
        if(heading_delta > np.pi):
            heading_delta =  heading_delta - 2.0*np.pi
        elif(heading_delta < -np.pi):
            heading_delta = 2.0*np.pi + heading_delta 

        degrees = heading_delta*180/np.pi

        self.LOGGER.info((f"Time: {self.time: 0.4f}. "
                          f"Current heading: {model.heading*180.0/np.pi: 0.4f}. "
                          f"Ground truth heading: {model.heading_real*180.0/np.pi:.4f}. "
                          f"Initial heading: {self.initial_heading*180.0/np.pi:.4f}. "
                          f"True heading: {model.true_heading*180.0/np.pi:.4f}"))
        model.log_mag_data()

        if degrees >= 70:
            self.LOGGER.info("Transitioning to S4")
            return S4(flags=dc.replace(self.flags, update_compass=False, update_gps=True))
        elif self.time >= 30:
            self.LOGGER.info("S3 Timeout. Transitioning to S8")
            return S8(flags=dc.replace(self.flags, autodrive=False, check_position=False))
        
        self.LOGGER.info(f"Degrees to target heading: {70 - degrees}")
        return S3(self.flags, self.time + step_size, self.initial_heading)


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
    
    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
        self.LOGGER.info("Transitioning to S5")
        return S5(
            flags=dc.replace(self.flags, update_gps=False, move=True),
            time=0.0,
            initial_position=model.position,
        )


@dc.dataclass(frozen=True, slots=True)
class S5(State):
    LOGGER: typing.ClassVar[logging.Logger] = _create_state_logger("S5")

    initial_position: Position = dc.field(default=(0.0,0.0,0.0))
    
    def __post_init__(self):
        assert self.flags.autodrive
        assert self.flags.move
        assert not self.flags.update_gps
        assert not self.flags.update_compass
        assert not self.flags.check_position

    @property
    def action(self) -> Action:
        return Action.DRIVE
    
    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
        if cmd == 66:
            self.LOGGER.info(f"Received command {cmd}. Transitioning to S7")
            return S7(flags=dc.replace(self.flags, autodrive=False, check_position=False))

        position = model.position
        distance = euclidean_distance(self.initial_position, position)

        if distance >= 7:
            self.LOGGER.info("Distance threshold exceeded. Transitioning to S6.")
            return S6(flags=dc.replace(self.flags, autodrive=False, move=False))

        self.LOGGER.info(f"Rover position: <{position[0]:.4f}, {position[1]:.4f}, {position[2]:.4f}>. Heading: {model.true_heading:.4f}")
        self.LOGGER.info(f"Remaining distance: {7 - distance:.4f}")
        return S5(self.flags, 0.0, self.initial_position)


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

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
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

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
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

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
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

    def next(self, model: Model, cmd: Command | None, step_size: float) -> State:
        return S9(self.flags)


class Automaton:
    def __init__(self, model: Model, step_size: float):
        self.model = model
        self.state: State = S1(flags=Flags())
        self.step_size = step_size
        self.history: list[State] = []

    def step(self, cmd: Command | None):
        self.history.append(self.state)
        self.state = self.state.next(self.model, cmd, self.step_size)

    @property
    def action(self) -> Action:
        return self.state.action
