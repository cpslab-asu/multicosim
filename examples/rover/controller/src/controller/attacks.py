from __future__ import annotations

from dataclasses import dataclass
from math import pi, pow
from typing import Protocol

from numpy import random

from .automaton import Model, euclidean_distance


class Magnet(Protocol):
    def offset(self, time: float, model: Model) -> tuple[float,float]:
        ...

@dataclass()
class StationaryMagnet(Magnet):
    magnitude: float
    x: float = 0.0
    y: float = 0.0

    def offset(self, time: float, model: Model) -> tuple[float,float]:
        p = (self.x, self.y, 0.0)
        d = euclidean_distance(p, model.position)
        scale =  self.magnitude / pow(d, 3)
        return ((p[0] - model.position[0]) * scale/d, (p[1] - model.position[1]) * scale/d)


@dataclass()
class GaussianMagnet(StationaryMagnet):
    rng: random.Generator = random.default_rng()

    def offset(self, time: float, model: Model) -> tuple[float,float]:
        p = (self.x, self.y, 0.0)
        d = euclidean_distance(p, model.position)
        scale =  self.rng.normal(0.0,1.0) * self.magnitude / pow(d, 3)
        return ((p[0] - model.position[0]) * scale/d, (p[1] - model.position[1]) * scale/d)


class SpeedController:
    def speed(self, time: float) -> float:
        ...


@dataclass()
class FixedSpeed(SpeedController):
    magnitude: float

    def speed(self, time: float) -> float:
        return self.magnitude
