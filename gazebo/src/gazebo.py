from __future__ import annotations

import os
import pathlib
import signal
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, TypeAlias, Final
from types import FrameType

import click
import sdformat14 as sdf
import lxml.etree as xml
    
GZ_SIM_RESOURCE_PATH: Final[str] = "GZ_SIM_RESOURCE_PATH"


@dataclass(frozen=True)
class Config:
    base_path: pathlib.Path
    world_path: pathlib.Path
    step_size: float

    def create_world(self, *, engine: xml.Element) -> pathlib.Path:
        with self.base_path.open("rb") as file:
            parser = xml.XMLParser(strip_cdata=False)
            sdf = xml.parse(file, parser)

        world = sdf.find("world")

        if world is None:
            raise ValueError()

        world.attrib["name"] = self.world_path.stem
        physics = world.find("physics")

        if physics is None:
            physics = xml.Element("physics")
            world.append(physics)

        physics.attrib["type"] = engine.tag
        step_size = physics.find("max_step_size")

        if step_size is None:
            step_size = xml.SubElement(physics, "max_step_size")
            physics.append(step_size)

        step_size.text = f"{self.step_size}"
        physics.append(engine)

        with self.world_path.open("wb") as file:
            sdf.write(file)

        return self.world_path.resolve()


def model_sensors(model: sdf.Model) -> Iterable[sdf.Sensor]:
    n_links = model.link_count()

    for i in range(0, n_links):
        link = model.link_by_index(i)
        n_sensors = link.sensor_count()

        for j in range(0, n_sensors):
            yield link.sensor_by_index(j)

    n_joints = model.joint_count()

    for i in range(0, n_joints):
        joint = model.joint_by_index(i)
        n_sensors = joint.sensor_count()

        for j in range(0, n_sensors):
            yield joint.sensor_by_index(j)


def update_model_sensor_topics(model: sdf.Model, topics: Iterable[tuple[str, str]]):
    topics_map = dict(topics)

    for sensor in model_sensors(model):
        name = sensor.name()

        if name in topics_map:
            sensor.set_topic(topics_map[name])  # Set topic if sensor is specific in mapping, ignore otherwise


class ModelNotFoundError(Exception):
    def __init__(self, model: str, dirs: list[pathlib.Path]):
        joined = ";".join(str(path) for path in dirs)

        super().__init__(
            f"Could not locate {model} in search path: {joined}",
        )


def set_sensor_topics(model_dirs: list[pathlib.Path], model: str, topics: Iterable[tuple[str, str]]):
    for model_dir in model_dirs:
        for m in model_dir.iterdir():
            if m.name == model:
                model_file = m.resolve() / "model.sdf"
                root = sdf.Root()
                root.load(f"{model_file}")

                update_model_sensor_topics(root.model(), topics)
                
                with model_file.open("wt") as f:
                    f.write(root.to_string())

                return

    raise ModelNotFoundError(model, model_dirs)


def group_sensor_topics(mappings: list[tuple[str, str, str]]) -> dict[str, list[tuple[str, str]]]:
    groups: dict[str, list[tuple[str, str]]] = {}

    for model_file, sensor_name, topic_name in mappings:
        mapping = (sensor_name, topic_name)
        try:
            groups[model_file].append(mapping)
        except KeyError:
            groups[model_file] = [mapping]

    return groups


def run_gazebo(ctx: click.Context, *, engine: xml.Element):
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
ModelDirPath = click.Path(exists=True, file_okay=False, path_type=pathlib.Path)


@click.group()
@click.pass_context
@click.option("-w", "--world", type=WorldPath, default=pathlib.Path("generated.sdf"))
@click.option("-b", "--base", type=BaseWorld, default=pathlib.Path("resources/worlds/default.sdf"))
@click.option("-S", "--step-size", type=float, default=0.001)
@click.option("-m", "--model-dir", "model_dirs", type=ModelDirPath, multiple=True, default=[pathlib.Path("resources/models")])
@click.option("--sensor-topic", "sensor_topics", type=(str, str, str), multiple=True, default=[])
def gazebo(
    ctx: click.Context,
    world: pathlib.Path,
    base: pathlib.Path,
    step_size: float,
    model_dirs: list[pathlib.Path],
    sensor_topics: list[tuple[str, str, str]],
):
    topic_groups = group_sensor_topics(sensor_topics)

    for model, topics in topic_groups.items():
        set_sensor_topics(model_dirs, model, topics)

    ctx.obj = Config(base_path=base, world_path=world, step_size=step_size)


ODESolver: TypeAlias = Literal["quick", "world"]


@gazebo.command("ode")
@click.pass_context
@click.option("-s", "--solver", type=click.Choice(["quick", "world"]), default="quick")
@click.option("-i", "--iterations", type=int, default=50)
def ode(ctx: click.Context, solver: ODESolver, iterations: int):
    engine_elem = xml.Element("ode")
    solver_elem = xml.SubElement(engine_elem, "solver")
    type_elem = xml.SubElement(solver_elem, "type")
    type_elem.text = solver
    iters_elem = xml.SubElement(solver_elem, "iters")
    iters_elem.text = f"{iterations}"
    
    run_gazebo(ctx, engine=engine_elem)


DartSolver: TypeAlias = Literal["dantzig", "pgs"]


@gazebo.command("dart")
@click.pass_context
@click.option("-s", "--solver", type=click.Choice(["dantzig", "pgs"]), default="dantzig")
def dart(ctx: click.Context, solver: DartSolver):
    engine_elem = xml.Element("dart")
    solver_elem = xml.SubElement(engine_elem, "solver")
    type_elem = xml.SubElement(solver_elem, "solver_type")
    type_elem.text = solver

    run_gazebo(ctx, engine=engine_elem)


@gazebo.command("bullet")
@click.pass_context
@click.option("-i", "--iterations", type=int, default=50)
def bullet(ctx: click.Context, iterations: int):
    engine_elem = xml.Element("bullet")
    solver_elem = xml.SubElement(engine_elem, "solver")
    type_elem = xml.SubElement(solver_elem, "iters")
    type_elem.text = f"{iterations}"

    run_gazebo(ctx, engine=engine_elem)


@gazebo.command("simbody")
@click.pass_context
def simbody(ctx: click.Context):
    run_gazebo(ctx, engine=xml.Element("simbody"))


if __name__ == "__main__":
    gazebo()
