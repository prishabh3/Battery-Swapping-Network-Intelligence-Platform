from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class FleetType(str, Enum):
    TWO_WHEELER = "2W"
    THREE_WHEELER = "3W"
    LIGHT_COMMERCIAL = "LCV"


class VehicleStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"


@dataclass
class Vehicle:
    vehicle_id: str
    fleet_type: FleetType
    region: str
    city: str
    operator_id: str
    registration_number: str
    status: VehicleStatus
    total_swaps: int = 0
    total_distance_km: float = 0.0
    avg_daily_swaps: float = 0.0
    last_swap_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_high_frequency_user(self) -> bool:
        return self.avg_daily_swaps >= 3.0

    @property
    def swap_frequency_category(self) -> str:
        if self.avg_daily_swaps >= 5:
            return "Very High"
        if self.avg_daily_swaps >= 3:
            return "High"
        if self.avg_daily_swaps >= 1.5:
            return "Medium"
        return "Low"
