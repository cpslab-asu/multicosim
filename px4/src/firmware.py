from __future__ import annotations

import asyncio
import logging
import math
import subprocess
import threading

import click
import gz.transport13
import gz.msgs10.pose_v_pb2 as pose_v
import mavsdk
import mavsdk.mission as mission
import multicosim.firmware as fw
import multicosim.px4 as px4


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


def create_mission(config: px4.FirmwareConfiguration) -> mission.MissionPlan:
    return mission.MissionPlan([create_mission_item(wp) for wp in config.mission])


def gz_model_name(vehicle: px4.Vehicle) -> str:
    if vehicle is px4.Vehicle.X500:
        return "gz_x500"

    raise ValueError()


def find_state(msg: pose_v.Pose_V) -> px4.State:
    for pose in msg.pose:
        if pose.name == "x500_0":
            pose = px4.Pose(pose.position.x, pose.position.y, pose.position.z)
            time = msg.header.stamp.sec + msg.header.stamp.nsec / 1e9

            return px4.State(time, pose)

    raise ValueError()


class Handler:
    def __init__(self):
        self._states: list[px4.State] = []
        self._lock = threading.Lock()

    def __call__(self, msg: pose_v.Pose_V):
        with self._lock:
            self._states.append(find_state(msg))

    @property
    def states(self) -> px4.States:
        with self._lock:
            return px4.States(self._states.copy())


async def execute_mission(plan: mission.MissionPlan, world: str, handler: Handler):
    logger = logging.getLogger("px4.mission")
    logger.addHandler(logging.NullHandler())
    drone = mavsdk.System()

    await drone.connect()

    async for state in drone.core.connection_state():
        if state.is_connected:
            break

    await drone.mission.upload_mission(plan)

    async for health in drone.telemetry.health():
        armable = all([
            health.is_home_position_ok,
            health.is_local_position_ok,
            health.is_global_position_ok,
            health.is_armable,
        ])

        if armable:
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


@fw.firmware(msgtype=px4.FirmwareConfiguration)
def server(msg: px4.FirmwareConfiguration) -> px4.States:
    handler = Handler()
    mission = create_mission(msg)
    gz_model = gz_model_name(msg.vehicle)
    env = f"PX4_GZ_STANDALONE=1 PX4_SIM_MODEL={gz_model} PX4_GZ_WORLD={msg.world}"
    cmd = f"{env} /opt/px4-autopilot/build/px4_sitl_default/bin/px4"

    logger = logging.getLogger("px4.firmware")
    logger.addHandler(logging.NullHandler())
    logger.debug(f"Running PX4 firmware using command: {cmd}")

    process = subprocess.Popen(
        args=cmd,
        cwd="/opt/px4-autopilot/build/px4_sitl_default/src/modules/simulation/gz_bridge",
        shell=True,
        executable="/bin/bash",
    )

    try:
        asyncio.run(execute_mission(mission, msg.world, handler), debug=True)
        logger.debug("Mission completed.")
    finally:
        logger.debug("Shutting down PX4...")
        process.kill()
        process.wait()
        logger.debug("Goodbye.")

    return handler.states


@click.command("firmware")
@click.option("--verbose", is_flag=True)
@click.option("--port", type=int, default=5556)
def firmware(*, verbose: bool, port: int):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    
    server.listen(port)


if __name__ == "__main__":
    firmware()
