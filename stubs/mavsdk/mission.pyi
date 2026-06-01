from collections.abc import AsyncIterable
from enum import Enum

class MissionItem:
    class CameraAction(Enum):
        NONE = ...

    class VehicleAction(Enum):
        NONE = ...

    def __init__(
        self,
        latitude_deg: float,
        longitude_deg: float,
        relative_altitude_m: float,
        speed_m_s: float,
        is_fly_through: bool,
        gimbal_pitch_deg: float,
        gimbal_yaw_deg: float,
        camera_action: CameraAction,
        loiter_time_s: float,
        camera_photo_interval_s: float,
        acceptance_radius_m: float,
        yaw_deg: float,
        camera_photo_distance_m: float,
        vehicle_action: VehicleAction,
    ): ...

class MissionPlan:
    def __init__(self, mission_items: list[MissionItem]): ...

class MissionProgress:
    @property
    def current(self) -> int: ...

    @property
    def total(self) -> int: ...

class Mission:
    async def upload_mission(self, mission_plan: MissionPlan) -> None: ...
    async def start_mission(self) -> None: ...
    def mission_progress(self) -> AsyncIterable[MissionProgress]: ...
