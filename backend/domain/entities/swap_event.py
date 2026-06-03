from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SwapOutcome(str, Enum):
    SUCCESS = "success"
    FAILED_INVENTORY = "failed_inventory"
    FAILED_STATION_OFFLINE = "failed_station_offline"
    FAILED_BATTERY_HEALTH = "failed_battery_health"
    CANCELLED = "cancelled"


@dataclass
class SwapEvent:
    event_id: str
    timestamp: datetime
    station_id: str
    battery_in_id: str          # battery returned by vehicle
    battery_out_id: str         # battery taken by vehicle
    vehicle_id: str
    duration_seconds: int
    energy_delivered_kwh: float
    outcome: SwapOutcome
    revenue_inr: float
    soh_at_swap: float          # SOH of battery_out at time of swap
    is_anomalous: bool = False
    anomaly_score: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_fast_swap(self) -> bool:
        return self.duration_seconds <= 120

    @property
    def hour_of_day(self) -> int:
        return self.timestamp.hour

    @property
    def is_peak_hour(self) -> bool:
        return self.hour_of_day in range(7, 11) or self.hour_of_day in range(17, 21)

    @property
    def day_of_week(self) -> int:
        return self.timestamp.weekday()

    @property
    def is_weekend(self) -> bool:
        return self.day_of_week >= 5
