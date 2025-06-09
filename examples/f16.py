from __future__ import annotations

from typing import Dict, Literal

import attrs
from aerobench import run_f16_sim as f16
from aerobench.examples.gcas import gcas_autopilot as gcas
from aerobench.highlevel.autopilot import Autopilot
from aerobench.util import StateIndex
from typing_extensions import TypeAlias, override

from multicosim.simulations import CommunicationNode, Component

Model: TypeAlias = Literal["morelli", "stevens"]
Integrator: TypeAlias = Literal["RK45", "euler"]


@attrs.define()
class Position:
    north: float
    east: float


@attrs.define()
class State:
    velocity: float
    angle_of_attack: float
    side_slip_angle: float
    roll: float
    pitch: float
    yaw: float
    roll_rate: float
    pitch_rate: float
    yaw_rate: float
    position: Position
    altitude: float
    power: int


@attrs.define()
class GCASNode(CommunicationNode[State, Dict[float, Dict[str, float]]]):
    autopilot: Autopilot
    integrator: Integrator
    step_size: float

    @override
    def send(self, msg: State) -> dict[float, dict[str, float]]:
        initial_state = [
            msg.velocity,
            msg.angle_of_attack,
            msg.side_slip_angle,
            msg.roll,
            msg.pitch,
            msg.yaw,
            msg.roll_rate,
            msg.pitch_rate,
            msg.yaw_rate,
            msg.position.north,
            msg.position.east,
            msg.altitude,
            msg.power,
        ]

        results = f16.run_16_sim(
            initial_state,
            tmax=3.51,
            ap=self.autopilot,
            step=self.step_size,
            extended_states=True,
            integrator_str=self.integrator,
        )

        return {
            time: {
                "north": state[StateIndex.POS_N],
                "east": state[StateIndex.POS_E],
                "altitude": state[StateIndex.ALT],
            }
            for time, state in zip(results["times"], results["states"])
        }

    @override
    def stop(self):
        pass


@attrs.define()
class GCASComponent(Component[None, GCASNode]):
    model: Model = "morelli"
    integrator: Integrator = "RK45"
    step_size: float = 0.001

    @override
    def start(self, environment: None) -> GCASNode:
        autopilot = gcas.GcasAutopilot(init_mode="roll", gain_str="old")
        autopilot.llc.model_str = self.model

        return GCASNode(autopilot, self.integrator, self.step_size)


if __name__ == "__main__":
    gcas = GCASComponent()
    initial_state = State()  # type: ignore
    
    node = gcas.start(None)
    result = node.send(initial_state)
