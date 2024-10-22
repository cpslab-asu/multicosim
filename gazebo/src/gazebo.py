from __future__ import annotations

import pathlib
import signal
import subprocess
from dataclasses import dataclass
from typing import Literal, TypeAlias
from types import FrameType
from xml.etree import ElementTree as etree

import click


@dataclass(frozen=True)
class Config:
    base_path: pathlib.Path
    world_path: pathlib.Path
    step_size: float

    def create_world(self, *, engine: etree.Element) -> pathlib.Path:
        with self.base_path.open("rb") as file:
            sdf = etree.parse(file)

        for elem in sdf.iter("world"):
            elem.attrib["name"] = self.world_path.stem

        for elem in sdf.iter("physics"):
            for child in elem.iter("max_step_size"):
                child.text = f"{self.step_size}"

            elem.attrib["type"] = engine.tag
            elem.append(engine)

        with self.world_path.open("wb") as file:
            sdf.write(file)

        return self.world_path.resolve()


def run_gazebo(ctx: click.Context, *, engine: etree.Element):
    config = ctx.find_object(Config)

    if not config:
        raise RuntimeError()

    world = config.create_world(engine=engine)
    cmd = f"gz sim -s -r -v4 {world}"

    with subprocess.Popen(args=cmd, shell=True, executable="/usr/bin/bash") as proc:
        def shutdown():
            proc.kill()
            proc.wait()

        def handle(signum: int, frame: FrameType | None):
            shutdown()

        signal.signal(signal.SIGTERM, handle)
        signal.signal(signal.SIGKILL, handle)

        while proc.poll() is None:
            try:
                pass
            except KeyboardInterrupt:
                return shutdown()


WorldPath = click.Path(writable=True, path_type=pathlib.Path)
BaseWorld = click.Path(exists=True, dir_okay=False, path_type=pathlib.Path)


@click.group()
@click.pass_context
@click.option("-w", "--world", type=WorldPath, default=pathlib.Path("generated.sdf"))
@click.option("-b", "--base", type=BaseWorld, default=pathlib.Path("resources/worlds/default.sdf"))
@click.option("-S", "--step-size", type=float, default=0.001)
def gazebo(ctx: click.Context, world: pathlib.Path, base: pathlib.Path, step_size: float):
    ctx.obj = Config(base_path=base, world_path=world, step_size=step_size)


ODESolver: TypeAlias = Literal["quick", "world"]


@gazebo.command("ode")
@click.pass_context
@click.option("-s", "--solver", type=click.Choice(["quick", "world"]), default="quick")
@click.option("-i", "--iterations", type=int, default=50)
def ode(ctx: click.Context, solver: ODESolver, iterations: int):
    engine_elem = etree.Element("ode")
    solver_elem = etree.SubElement(engine_elem, "solver")
    type_elem = etree.SubElement(solver_elem, "type")
    type_elem.text = solver
    iters_elem = etree.SubElement(solver_elem, "iters")
    iters_elem.text = f"{iterations}"
    
    run_gazebo(ctx, engine=engine_elem)


DartSolver: TypeAlias = Literal["dantzig", "pgs"]


@gazebo.command("dart")
@click.pass_context
@click.option("-s", "--solver", type=click.Choice(["dantzig", "pgs"]), default="dantzig")
def dart(ctx: click.Context, solver: DartSolver):
    engine_elem = etree.Element("dart")
    solver_elem = etree.SubElement(engine_elem, "solver")
    type_elem = etree.SubElement(solver_elem, "solver_type")
    type_elem.text = solver

    run_gazebo(ctx, engine=engine_elem)


@gazebo.command("bullet")
@click.pass_context
@click.option("-i", "--iterations", type=int, default=50)
def bullet(ctx: click.Context, iterations: int):
    engine_elem = etree.Element("bullet")
    solver_elem = etree.SubElement(engine_elem, "solver")
    type_elem = etree.SubElement(solver_elem, "iters")
    type_elem.text = f"{iterations}"

    run_gazebo(ctx, engine=engine_elem)


@gazebo.command("simbody")
@click.pass_context
def simbody(ctx: click.Context):
    run_gazebo(ctx, engine=etree.Element("simbody"))


if __name__ == "__main__":
    gazebo()
