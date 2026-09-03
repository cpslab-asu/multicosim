from __future__ import annotations

from collections.abc import Iterable, Iterator
from itertools import repeat
from logging import DEBUG, INFO, WARNING, Logger, NullHandler, basicConfig, getLogger
from pprint import pprint

import apscheduler.schedulers.blocking as sched
import click
import numpy.random as rand
import multicosim.containers

from . import attacks as atk
from . import automaton as ha
from . import messages as msgs
from . import vehicles


class PublisherError(Exception):
    pass


def run(
    world: str,
    frequency: int,
    magnet: atk.Magnet | None,
    speed: atk.SpeedController | None,
    commands: Iterable[ha.Command] | None,
) -> list[msgs.Step]:
    logger = getLogger("controller.simulation")
    logger.addHandler(NullHandler())

    step_size: float = 1.0 / frequency
    logger.info(f"Step size: {step_size}")

    magnet = magnet or atk.StationaryMagnet(0.0)
    logger.info(f"Magnet: {magnet}")

    speed_ctl = speed or atk.FixedSpeed(5.0)
    logger.info(f"Speed: {speed_ctl}")

    vehicle = vehicles.ngc(world, magnet=magnet)
    controller = ha.Automaton(vehicle, step_size)
    scheduler = sched.BlockingScheduler()
    history: list[msgs.Step] = []
    cmds: Iterator[ha.Command | None] = iter(commands) if commands is not None else repeat(None)

    vehicle.wait()
    tstart = vehicle.clock

    def update() -> None:
        tsim = vehicle.clock - tstart
        logger.debug("Running controller step.")
        history.append(
            msgs.Step(
                time=tsim,
                position=vehicle.position,
                heading=vehicle.heading.value,
                roll=vehicle.roll,
                state=controller.state,
            )
        )

        action = controller.action
        speed = speed_ctl.speed(tsim)

        if action is ha.Action.STOP:
            vehicle.velocity = 0.0
        else:
            vehicle.velocity = speed

        if action is ha.Action.TURN:
            vehicle.steering_angle = 0.5
        else:
            vehicle.steering_angle = 0.0

        if controller.state.is_terminal():
            logger.info("Found terminal state. Shutting down scheduler.")
            scheduler.remove_all_jobs()
            scheduler.shutdown(wait=False)
        else:
            controller.step(next(cmds))

    logger.debug("Creating controller scheduler job")
    _ = scheduler.add_job(update, "interval", seconds=step_size, id="control_loop")

    logger.debug("Starting scheduler")
    scheduler.start()

    return history


@click.group()
@click.pass_context
@click.option("-v", "--verbose", is_flag=True)
def controller(ctx: click.Context, *, verbose: bool) -> None:
    if verbose:
        basicConfig(level=DEBUG)
    else:
        basicConfig(level=INFO)
        getLogger("apscheduler").setLevel(WARNING)

    logger = getLogger("controller")
    logger.addHandler(NullHandler())
    logger.info("Rover hybrid automaton controller version 0.1.0")

    ctx.ensure_object(dict)
    ctx.obj["logger"] = logger


@multicosim.containers.server(msgtype=msgs.Start)
def server(msg: msgs.Start) -> msgs.Result:
    return msgs.Result(run(msg.world, msg.frequency, msg.magnet, msg.speed, msg.commands))


@controller.command()
@click.option("-p", "--port", type=int, default=5556)
def serve(port: int) -> None:
    server.listen(port)


def _create_magnet(position: tuple[float, float] | None) -> atk.Magnet:
    if position is None:
        return atk.StationaryMagnet(0.0)

    return atk.GaussianMagnet(position[0], position[1], rng=rand.default_rng())


@controller.command()
@click.pass_context
@click.option("-w", "--world", default="default")
@click.option("-f", "--frequency", type=int, default=1)
@click.option("-s", "--speed", type=float, default=5.0)
@click.option("-m", "--magnet", nargs=2, type=float, default=None)
def start(
    ctx: click.Context,
    world: str,
    frequency: int,
    speed: float,
    magnet: tuple[float, float] | None,
) -> None:
    logger: Logger = ctx.obj["logger"]
    logger.info("No port specified, starting controller using defaults.")
    magnet_: atk.Magnet = _create_magnet(magnet)
    speed_ = atk.FixedSpeed(speed)
    history = run(world, frequency, magnet_, speed_, commands=None)

    pprint(history)


if __name__ == "__main__":
    controller()
