from __future__ import annotations

import pprint

import click
import gzcm.px4 as px4
import gzcm.gazebo as gz


@click.command("px4")
@click.option("-c", "--container", default=None)
def px4_example(container: str | None):
    px4cfg = px4.Config()
    gzcfg = gz.Config()
    poses = px4.simulate(px4cfg, gzcfg, container=container)

    pprint.pprint(poses)


if __name__ == "__main__":
    px4_example()
