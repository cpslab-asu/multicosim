from google.protobuf.internal.containers import RepeatedScalarFieldContainer

from .header_pb2 import Header

class Actuators:
    header: Header
    position: RepeatedScalarFieldContainer[float]
    velocity: RepeatedScalarFieldContainer[float]
