from __future__ import annotations

import logging
import pprint
import typing

import click

import multicosim as mcs

MISSION: typing.Final[list[mcs.px4.Waypoint]] = [
    mcs.px4.Waypoint(47.398039859999997, 8.5455725400000002, 25),
    mcs.px4.Waypoint(47.398036222362471, 8.5450146439425509, 25),
    mcs.px4.Waypoint(47.397825620791885, 8.5450092830163271, 25),
]


@click.command("px4")
@click.option("-c", "--container", default=None)
@click.option("-v", "--verbose", is_flag=True)
@click.option("--rm", "--remove", "remove", is_flag=True)
def px4_example(container: str | None, *, verbose: bool, remove: bool):
    if verbose:
        logging.basicConfig()
        logging.getLogger("examples.px4").setLevel(logging.DEBUG)

    system = mcs.PX4()
    gazebo = mcs.Gazebo()
    trace = system.simulate(gazebo, MISSION, remove=remove)

    pprint.pprint(trace)


if __name__ == "__main__":
    px4_example()
