from collections.abc import Iterable

from .header_pb2 import Header
from .pose_pb2 import Pose

class Pose_V:  # noqa: N801
    header: Header
    pose: Iterable[Pose]
