from __future__ import annotations

import asyncio
import logging
import math
import subprocess
import typing

import click
import gzcm.px4 as px4
import gzcm.firmware as fw
import gz.transport13
import gz.msgs10.pose_v_pb2 as pose_v
import mavsdk
import mavsdk.action
import mavsdk.mission as mission
import zmq


def create_mission_item(waypoint: px4.Waypoint) -> mission.MissionItem:
    return mission.MissionItem(
        waypoint.lat,
        waypoint.lon,
        waypoint.alt,
        10,
        True,
        math.nan,
        math.nan,
        mission.MissionItem.CameraAction.NONE,
        math.nan,
        math.nan,
        math.nan,
        math.nan,
        math.nan,
        mission.MissionItem.VehicleAction.NONE,
    )


def create_mission(config: px4.StartMsg) -> mission.MissionPlan:
    return mission.MissionPlan([create_mission_item(wp) for wp in config.mission])


def gz_model_name(model: px4.Model) -> str:
    if model is px4.Model.X500:
        return "gz_x500"

    raise ValueError()


def find_state(msg: pose_v.Pose_V) -> fw.State:
    for pose in msg.pose:
        if pose.name == "x500_0":
            pose = px4.Pose(pose.position.x, pose.position.y, pose.position.z)
            time = msg.header.stamp.sec + msg.header.stamp.nsec / 1e9

            return fw.State(time, pose)

    raise ValueError()


class Handler(typing.Protocol):
    def __call__(self, __msg: pose_v.Pose_V) -> None:
        ...


def create_handler(socket: zmq.Socket) -> Handler:
    def handler(msg: pose_v.Pose_V):
        socket.send_pyobj(find_state(msg))

    return handler


async def execute_mission(plan: mission.MissionPlan, world: str, handler: Handler):
    logger = logging.getLogger("px4.mission")
    logger.addHandler(logging.NullHandler())
    drone = mavsdk.System()

    await drone.connect()

    async for state in drone.core.connection_state():
        if state.is_connected:
            break

    await drone.mission.upload_mission(plan)

    async for ok in drone.telemetry.health_all_ok():
        if ok:
            break

    await drone.action.arm()
    await drone.mission.start_mission()

    node = gz.transport13.Node()
    topic = f"/world/{world}/pose/info"
    opts = gz.transport13.SubscribeOptions()
    opts.msgs_per_sec = 1

    if not node.subscribe(pose_v.Pose_V, topic, handler, opts):
        raise RuntimeError()

    async for progress in drone.mission.mission_progress():
        if progress.current == progress.total:
            break


@click.command("firmware")
@click.option("-v", "--verbose", is_flag=True)
@click.option("-c", "--config-port", type=int, default=5555)
@click.option("-p", "--publisher-port", type=int, default=5556)
def firmware(verbose: bool, config_port: int, publisher_port: int):
    logger = logging.getLogger("px4.firmware")
    logger.addHandler(logging.NullHandler())

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    with zmq.Context() as ctx:
        with ctx.socket(zmq.REP) as socket:
            with socket.bind(f"tcp://*:{config_port}"):
                logger.debug("Waiting for configuration message...")

                msg = socket.recv_pyobj()

                if not isinstance(msg, px4.StartMsg):
                    raise TypeError(f"Unknown start message type {type(msg)}. Expected gzcm.px4.StartMsg")

        logger.debug("Configuration received. Starting mission...")
        mission = create_mission(msg)
        model = gz_model_name(msg.model)
        env = f"PX4_GZ_STANDALONE=1 PX4_SIM_MODEL={model} PX4_GZ_WORLD={msg.world}"
        cmd = f"{env} /opt/px4-autopilot/build/px4_sitl_default/bin/px4"

        logger.debug(f"Running PX4 firmware using command: {cmd}")
        process = subprocess.Popen(
            args=cmd,
            cwd="/opt/px4-autopilot/build/px4_sitl_default/src/modules/simulation/gz_bridge",
            shell=True,
            executable="/bin/bash",
        )

        with ctx.socket(zmq.PUB) as socket:
            with socket.bind(f"tcp://*:{publisher_port}"):
                try:
                    asyncio.run(execute_mission(mission, msg.world, create_handler(socket)), debug=True)
                    socket.send_pyobj(None)
                    logger.debug("Mission completed.")
                finally:
                    logger.debug("Shutting down PX4...")
                    process.kill()
                    process.wait()
                    logger.debug("Goodbye.")


if __name__ == "__main__":
    firmware()
