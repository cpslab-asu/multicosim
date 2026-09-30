import asyncio

from multicosim import gazebo as gz
from multicosim import px4

if __name__ == "__main__":
    mission = px4.Mission(
        waypoints=[
            px4.Waypoint(47.398039859999997, 8.5455725400000002, 25),
            px4.Waypoint(47.398036222362471, 8.5450146439425509, 25),
            px4.Waypoint(47.397825620791885, 8.5450092830163271, 25),
        ]
    )

    gazebo = gz.Options()
    firmware = px4.Firmware()

    # It is also possible to create a firmware component directly for more customization
    # using the standard constructr arguments for `containers.Component`.
    #
    # firmware = px4.FirmwareComponent(
    #     ....
    # )
    #
    # In practice however, this is never really necessary unless you are trying not to
    # use the stock PX4 firmware. You can create a default component implementation and
    # customize it to avoid having to specify all the details manually.
    #
    # gazebo = gz.Options()
    # firmware = px4.Firmware()
    # component = px4.FirmwareComponent.from_firmware(firmware, gazebo)
    # component.image = "..."

    sim = px4.PX4(firmware, gazebo)

    with sim.run() as sys:
        history = asyncio.run(sys.run_mission(mission))

    for step in history.steps:
        print(f"Time: {step.time}\tPose: {step.pose}")
