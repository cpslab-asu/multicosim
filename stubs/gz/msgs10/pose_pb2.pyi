from .header_pb2 import Header
from .vector3d_pb2 import Vector3d
from .quaternion_pb2 import Quaternion

class Pose:
    header: Header
    name: str
    id: int
    position: Vector3d
    orientation: Quaternion
