
from __future__ import annotations

import logging
import pprint

import click

import multicosim.px4 as px4


@click.command("px4")
@click.option("-c", "--container", default=None)
@click.option("-v", "--verbose", is_flag=True)
@click.option("--rm", "--remove", "remove", is_flag=True)
def quickstart(container: str | None, *, verbose: bool, remove: bool):
    if verbose:
        logging.basicConfig()
        logging.getLogger("examples.px4").setLevel(logging.DEBUG)

    # Create the Gazebo component
    gazebo = px4.Gazebo()

    # Create the PX4 simulator
    simulator = px4.PX4(gazebo)

    # Launch the simulation
    simulation = simulator.start()

    # Create the PX4 configuration message
    configuration = px4.Configuration(
        mission=[
            px4.Waypoint(47.398039859999997, 8.5455725400000002, 25),
            px4.Waypoint(47.398036222362471, 8.5450146439425509, 25),
            px4.Waypoint(47.397825620791885, 8.5450092830163271, 25),
        ],
    )

    # Start the PX4 mission and return the system state trajectory
    trace = simulation.firmware.send(configuration)

    pprint.pprint(trace)


if __name__ == "__main__":
    quickstart()
