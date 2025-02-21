from __future__ import annotations

from dataclasses import dataclass, field
from logging import Logger, NullHandler, getLogger
from math import atan, pi
from threading import Event, Lock
from typing import Literal, NewType

from gz.transport13 import Node, Publisher, SubscribeOptions
from gz.math7 import Quaterniond
from gz.msgs10.actuators_pb2 import Actuators
from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.double_pb2 import Double
from gz.msgs10.entity_factory_pb2 import EntityFactory
from gz.msgs10.magnetometer_pb2 import Magnetometer
from gz.msgs10.pose_v_pb2 import Pose_V

from controller import attacks, automaton


def _pose_logger() -> Logger:
    logger = getLogger("rover.pose")
    logger.addHandler(NullHandler())

    return logger


@dataclass()
class MagnetometerHandler:
    _vector: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0), init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    _ready: Event = field(default_factory=Event, init=False)

    def __call__(self, msg: Magnetometer):
        with self._lock:
            field = msg.field_tesla
            self._vector = (field.x, field.y, field.z)

        if not self._ready.is_set():
            self._ready.set()

    @property
    def vector(self) -> tuple[float, float, float]:
        with self._lock:
            return self._vector

    @property
    def x(self) -> float:
        with self._lock:
            return self._vector[0]

    @property
    def y(self) -> float:
        with self._lock:
            return self._vector[1]

    @property
    def z(self) -> float:
        with self._lock:
            return self._vector[2]

    def wait(self) -> bool:
        return self._ready.wait()


@dataclass()
class PoseHandler:
    name: str = field()
    _lock: Lock = field(default_factory=Lock, init=False)
    _heading: float = field(default=0.0, init=False)
    _roll: float = field(default=0.0, init=False)
    _position: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0), init=False)
    _clock: float = field(default=0.0, init=False)
    _logger: Logger = field(default_factory=_pose_logger, init=False)
    _ready: Event = field(default_factory=Event, init=False)

    def __call__(self, msg: Pose_V):
        for pose in msg.pose:
            if pose.name == self.name:
                self._logger.debug(f"Received pose: {pose}")

                time = msg.header.stamp.sec + msg.header.stamp.nsec / 1e9
                q = Quaterniond(
                    pose.orientation.w,
                    pose.orientation.x,
                    pose.orientation.y,
                    pose.orientation.z,
                )

                with self._lock:
                    euler = q.euler()
                    self._heading = euler.z()
                    self._roll = euler.y()
                    self._position = (pose.position.x, pose.position.y, pose.position.z)
                    self._clock = time

                break

        if not self._ready.is_set():
            self._ready.set()

    @property
    def clock(self) -> float:
        with self._lock:
            return self._clock

    @property
    def heading(self) -> float:
        with self._lock:
            return self._heading * (180 / pi)

    @property
    def roll(self) -> float:
        with self._lock:
            return self._roll

    @property
    def position(self) -> tuple[float, float, float]:
        with self._lock:
            return self._position

    def wait(self):
        self._ready.wait()


def _rover_logger() -> Logger:
    logger = getLogger("rover")
    logger.addHandler(NullHandler())

    return logger


InitializedNode = NewType("InitializedNode", Node)


@dataclass()
class Rover(automaton.Model):
    _node: InitializedNode = field()
    _motors: Publisher = field()
    _pose: PoseHandler = field()
    _logger: Logger = field(default_factory=_rover_logger, init=False)

    @property
    def clock(self) -> float:
        return self._pose.clock

    @property
    def position(self) -> tuple[float, float, float]:
        return self._pose.position

    @property
    def heading(self) -> float:
        return self._pose.heading

    @property
    def roll(self) -> float:
        return self._pose.roll

    def wait(self):
        self._pose.wait()


@dataclass()
class R1(Rover):
    _velocity: float | None = field(default=None, init=False)
    _omega: float | None = field(default=None, init=False)

    @property
    def omega(self) -> float:
        return self._omega or 0.0

    @omega.setter
    def omega(self, target: float):
        if self._omega is None or target != self._omega:
            msg = Actuators()
            msg.velocity.append(target)
            msg.velocity.append(target)

            self._motors.publish(msg)
            self._omega = target
            self._velocity = None
            self._logger.info(f"Setting angular velocity to {target}")

    @property
    def velocity(self) -> float:
        return self._velocity or 0.0

    @velocity.setter
    def velocity(self, target: float):
        if self._velocity is None or target != self._velocity:
            msg = Actuators()
            msg.velocity.append(-target)
            msg.velocity.append(target)

            self._motors.publish(msg)
            self._velocity = target
            self._omega = None
            self._logger.info(f"Setting velocity to {target}")


@dataclass()
class NGC(Rover):
    _magnet: attacks.Magnet = field()
    _magnetometer: MagnetometerHandler = field()
    _servos: Publisher = field()
    _velocity: float = field(default=0.0, init=False)
    _steering_angle: float  = field(default=0.0, init=False)

    @property
    def _heading(self) -> float:
        x, y, _ = self._magnetometer.vector

        if y > 0:
            heading_ = 90 - (atan(x/y) * 180/pi)
        elif y < 0:
            heading_ = 270 - (atan(x/y) * 180/pi)
        elif x > 0:
            heading_ = 180.0
        else:
            heading_ = 0.0

        return heading_

    @property
    def heading_real(self) -> float:
        return self._heading

    @property
    def heading(self) -> float:
        return self._heading + self._magnet.offset(self.clock, self)

    @property
    def steering_angle(self) -> float:
        return self._steering_angle

    @steering_angle.setter
    def steering_angle(self, target: float):
        if not -0.5 <= target <= 0.5:
            raise ValueError("Steering angle must be within interval [-0.5, 0.5]")

        if target != self._steering_angle:
            msg = Double()
            msg.data = target

            self._servos.publish(msg)
            self._steering_angle = target
            self._logger.info(f"Setting steering angle to {target}")

    @property
    def velocity(self) -> float:
        return self._velocity

    @velocity.setter
    def velocity(self, target: float):
        if target != self._velocity:
            msg = Actuators()
            msg.velocity.append(target)

            self._motors.publish(msg)
            self._velocity = target
            self._logger.info(f"Setting velocity to {target}")

    def wait(self):
        self._pose.wait()
        self._magnetometer.wait()


class RoverError(Exception):
    pass


class TransportError(RoverError):
    pass


def _create_model(
    world: str,
    model: Literal["r1_rover", "ngc_rover"],
    *,
    name: str,
    logger: Logger,
) -> InitializedNode:
    client = Node()
    msg = EntityFactory()
    msg.sdf_filename = f"{model}/model.sdf"
    msg.name = name
    msg.allow_renaming = False
    res, rep = client.request(f"/world/{world}/create", msg, EntityFactory, Boolean, timeout=5000)

    logger.debug(f"Response: {res}")
    logger.debug(f"Reply: {rep}")

    if not res:
        raise TransportError("Failed to send Gazebo message for rover creation")

    if not rep.data:
        raise RoverError("Could not create rover Gazebo model")

    return InitializedNode(client)


def _pose_handler(
    node: InitializedNode,
    world: str,
    *,
    name:str,
) -> PoseHandler:
    pose = PoseHandler(name)
    pose_options = SubscribeOptions()
    pose_options.msgs_per_sec = 10

    if not node.subscribe(Pose_V, f"/world/{world}/pose/info", pose, pose_options):
        raise TransportError()

    return pose

def _magnetometer_handler(
    node: InitializedNode,
    world: str,
    *,
    name:str,
) -> MagnetometerHandler:
    topic = f"/world/{world}/model/{name}/link/base_link/sensor/magnetometer_sensor/magnetometer"
    magnetometer = MagnetometerHandler()
    magnetometer_options = SubscribeOptions()
    magnetometer_options.msgs_per_sec = 10

    if not node.subscribe(Magnetometer, topic, magnetometer, magnetometer_options):
        raise TransportError()

    return magnetometer


def r1(world: str, *, name: str = "r1_rover") -> R1:
    logger = getLogger("rover.r1")
    logger.addHandler(NullHandler())

    node = _create_model(world, name=name, model="r1_rover", logger=logger)
    logger.info(f"Created rover model {name} in gazebo world {world}.")

    pose = _pose_handler(node, world, name=name)
    logger.info("Initialized pose topic handler.")

    motors = node.advertise(f"/model/{name}/command/motor_speed", Actuators)

    if not motors.valid():
        raise TransportError("Could not register publisher for motor control")

    logger.info("Initialized motor topic publisher.")

    return R1(node, motors, pose)


def ngc(world: str, *, magnet: attacks.Magnet, name: str = "ackermann") -> NGC:
    logger = getLogger("rover.ackermann")
    logger.addHandler(NullHandler())

    node = _create_model(world, name=name, model="ngc_rover", logger=logger)
    logger.info(f"Created rover model {name} in gazebo world {world}.")

    pose = _pose_handler(node, world, name=name)
    logger.info("Initialized pose topic handler")

    magnetometer = _magnetometer_handler(node, world, name=name)
    logger.info("Initialized magnetometer topic handler")

    motors = node.advertise(f"/model/{name}/command/motor_speed", Actuators)

    if not motors.valid():
        raise TransportError("Could not register publisher for motor control")

    logger.info("Initialized motor topic publisher.")
    servos = node.advertise(f"/model/{name}/servo_0", Double)

    if not servos.valid():
        raise TransportError("Could not register publisher for servo_0 control")

    logger.info("Initialized servo topic publisher.")

    return NGC(node, motors, pose, magnet, magnetometer, servos)
