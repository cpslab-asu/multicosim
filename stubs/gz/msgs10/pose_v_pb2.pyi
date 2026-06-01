from collections.abc import Iterable

from .header_pb2 import Header
from .pose_pb2 import Pose

class Pose_V:
    header: Header
    pose: Iterable[Pose]
