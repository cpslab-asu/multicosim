from __future__ import annotations

import logging
import pprint

import click
import multicosim as mcs


@click.command("px4")
@click.option("-c", "--container", default=None)
@click.option("-v", "--verbose", is_flag=True)
@click.option("--rm", "--remove", "remove", is_flag=True)
def px4_example(container: str | None, verbose: bool, remove: bool):
    if verbose:
        logging.basicConfig()
        logging.getLogger("examples.px4").setLevel(logging.DEBUG)

    system = mcs.PX4()
    gazebo = mcs.Gazebo()
    trace = system.simulate(px4.DEFAULT_MISSION, gazebo, container=container, remove=remove)

    pprint.pprint(trace)


if __name__ == "__main__":
    px4_example()
