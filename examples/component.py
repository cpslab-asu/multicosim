from __future__ import annotations

import logging
import pprint

import click

import multicosim as mcs
import multicosim.px4 as px4


@click.command("component")
@click.option("-c", "--container", default=None)
@click.option("-v", "--verbose", is_flag=True)
@click.option("--rm", "--remove", "remove", is_flag=True)
def component(container: str | None, *, verbose: bool, remove: bool):
    if verbose:
        logging.basicConfig()
        logging.getLogger("examples.px4").setLevel(logging.DEBUG)

    # Specify the topic for the GPS data produced by gazebo
    source_topic = "navsat_original"

    # Create the gazebo component specifying that the GPS sensor should broadcast on the specific topic
    gazebo = px4.Gazebo(
        sensor_topics={"navsat_sensor": source_topic},
    )

    # Create the noisy GPS component that reads from the source Gazebo topic and broadcasts to the topic PX4 is listening to
    noisy_gps = mcs.ContainerComponent(
        image="ghcr.io/cpslab-asu/multicosim/examples/noisy-gps:latest",
        command=f"noisy-gps --verbose --topic {source_topic}",
    )

    # Create the PX4 simulator with the Gazebo and GPS components
    simulator = px4.PX4(gazebo)

    # Add the noisy GPS component to the simulator tree. Ignore the returned identifier because we don't need it.
    simulator.add(noisy_gps)

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

    # Run the simulation and return the state trace from the drone
    trace = simulation.firmware.send(configuration)

    pprint.pprint(trace)


if __name__ == "__main__":
    component()
