from __future__ import annotations

from collections.abc import Iterable
from itertools import repeat
from pprint import pprint
from logging import DEBUG, INFO, WARNING, Logger, NullHandler, basicConfig, getLogger

import apscheduler.schedulers.blocking as sched
import click
import gzcm
import numpy.random as rand

import rover
import controller.messages as msgs
import controller.attacks as atk
import controller.automaton as ha


class PublisherError(Exception):
    pass


def run(
    world: str,
    frequency: int,
    magnet: atk.Magnet | None,
    speed: atk.SpeedController | None,
    commands: Iterable[ha.Command | None],
) -> list[msgs.Step]:
    logger = getLogger("controller.simulation")
    logger.addHandler(NullHandler())

    step_size: float = 1.0/frequency
    logger.info(f"Step size: {step_size}")

    magnet = magnet or atk.StationaryMagnet(0.0)
    logger.info(f"Magnet: {magnet}")

    speed_ctl = speed or atk.FixedSpeed(5.0)
    logger.info(f"Speed: {speed_ctl}")

    vehicle = rover.ngc(world, magnet=magnet)
    controller = ha.Automaton(vehicle, step_size)
    scheduler = sched.BlockingScheduler()
    history: list[msgs.Step] = []
    cmds = iter(commands)

    vehicle.wait()
    tstart = vehicle.clock

    def update():
        tsim = vehicle.clock - tstart
        logger.debug("Running controller step.")
        history.append(
            msgs.Step(
                time=tsim,
                position=vehicle.position,
                heading=vehicle.heading,
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
    scheduler.add_job(update, "interval", seconds=step_size, id="control_loop")

    logger.debug("Starting scheduler")
    scheduler.start()

    return history


@click.group()
@click.pass_context
@click.option("-v", "--verbose", is_flag=True)
def controller(ctx: click.Context, verbose: bool):
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


@gzcm.serve(msgtype=msgs.Start)
def server(msg: msgs.Start) -> msgs.Result:
    return msgs.Result(run(msg.world, msg.frequency, msg.magnet, msg.speed, msg.commands))


@controller.command()
@click.option("-p", "--port", type=int, default=5556)
def serve(port: int):
    server(port)


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
    magnet: tuple[float, float] | None
):
    logger: Logger = ctx.obj["logger"]
    logger.info("No port specified, starting controller using defaults.")
    magnet_: atk.Magnet = atk.GaussianMagnet(magnet[0], magnet[1], rand.default_rng()) if magnet else atk.StationaryMagnet(0.0)
    speed_ = atk.FixedSpeed(speed)
    history = run(world, frequency, magnet_, speed_, commands=repeat(None))

    pprint(history)


if __name__ == "__main__":
    controller()
