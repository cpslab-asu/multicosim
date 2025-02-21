from __future__ import annotations

from dataclasses import dataclass
from math import pi, pow
from typing import Protocol

from numpy import random

from .automaton import Model, euclidean_distance


class Magnet(Protocol):
    def offset(self, time: float, model: Model) -> float:
        ...


@dataclass()
class StationaryMagnet(Magnet):
    magnitude: float

    def offset(self, time: float, model: Model) -> float:
        return self.magnitude


@dataclass()
class GaussianMagnet(Magnet):
    x: float
    y: float
    rng: random.Generator

    def offset(self, time: float, model: Model) -> float:
        mu_0 = 4 * pi * 10e-7
        m = 0.8
        p = (self.x, self.y, 0.0)
        d = euclidean_distance(p, model.position)
        scale = (mu_0 + m) / pow(d, 3)

        return self.rng.normal(0.0, 1.0) * scale


class SpeedController:
    def speed(self, time: float) -> float:
        ...


@dataclass()
class FixedSpeed(SpeedController):
    magnitude: float

    def speed(self, time: float) -> float:
        return self.magnitude
