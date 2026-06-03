from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class StationStatus(str, Enum):
    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class UtilizationTier(str, Enum):
    UNDERUTILIZED = "underutilized"   # < 30%
    NORMAL = "normal"                  # 30–70%
    HIGH = "high"                      # 70–90%
    OVERLOADED = "overloaded"         # > 90%


@dataclass
class Station:
    station_id: str
    name: str
    city: str
    state: str
    latitude: float
    longitude: float
    capacity: int                   # max batteries
    inventory_count: int            # charged batteries on hand
    charging_slots: int
    status: StationStatus
    operator_name: str
    pincode: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_outage_at: Optional[datetime] = None

    @property
    def utilization_rate(self) -> float:
        return round(self.inventory_count / self.capacity, 4) if self.capacity > 0 else 0.0

    @property
    def utilization_tier(self) -> UtilizationTier:
        rate = self.utilization_rate
        if rate < 0.30:
            return UtilizationTier.UNDERUTILIZED
        if rate <= 0.70:
            return UtilizationTier.NORMAL
        if rate <= 0.90:
            return UtilizationTier.HIGH
        return UtilizationTier.OVERLOADED

    @property
    def available_charging_capacity(self) -> int:
        return max(0, self.capacity - self.inventory_count)

    def can_fulfill_swap(self) -> bool:
        return self.status == StationStatus.OPERATIONAL and self.inventory_count > 0
