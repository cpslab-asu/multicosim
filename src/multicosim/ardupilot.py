from __future__ import annotations

from typing import Final

from attrs import field, frozen
from strenum import StrEnum

from . import Gazebo, __version__, firmware

PORT: Final[int] = 5556


class Frame(StrEnum):
    COPTER = "gazebo-iris"


@frozen()
class Start:
    frame: Frame = field()


@frozen()
class Pose:
    x: float = field()
    y: float = field()
    z: float = field()


@frozen()
class State:
    time: float = field()
    pose: Pose = field()


@frozen()
class Result:
    trajectory: list[State] = field()


@firmware.manage(
    firmware_image=f"ghcr.io/cpslab-asu/multicosim/ardupilot/firmware:{__version__}",
    gazebo_image="ghcr.io/cpslab-asu/multicosim/ardupilot/gazebo:harmonic",
    command=f"firmware --port {PORT}",
    port=PORT,
    rtype=Result,
)
def _ardupilot(world: str, frame: Frame) -> Start:
    ...


def simulate(gazebo: Gazebo, frame: Frame, *, remove: bool = False) -> dict[float, Pose]:
    result = _ardupilot.run(gazebo, remove=remove, frame=frame)
    return {state.time: state.pose for state in result.trajectory}


class ArduPilot:
    Frame = Frame

    def __init__(self, frame: Frame):
        self.frame = frame

    def simulate(self, gazebo: Gazebo, *, remove: bool = False) -> dict[float, Pose]:
        return simulate(gazebo, self.frame, remove=remove)


__all__ = ["ArduPilot", "Frame", "Pose", "Result", "Start", "State", "simulate"]
