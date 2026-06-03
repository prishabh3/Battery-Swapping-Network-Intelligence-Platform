from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional


class ChemistryType(str, Enum):
    LFP = "LFP"          # Lithium Iron Phosphate
    NMC = "NMC"          # Nickel Manganese Cobalt
    LTO = "LTO"          # Lithium Titanate
    LMFP = "LMFP"        # Lithium Manganese Iron Phosphate


class BatteryStatus(str, Enum):
    ACTIVE = "active"
    IN_TRANSIT = "in_transit"
    CHARGING = "charging"
    RETIRED = "retired"
    MAINTENANCE = "maintenance"


class ReplacementRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Battery:
    battery_id: str
    manufacturing_date: date
    chemistry_type: ChemistryType
    cycle_count: int
    current_health: float          # SOH 0.0–1.0
    nominal_capacity_kwh: float
    current_station_id: Optional[str]
    status: BatteryStatus
    thermal_stress_score: float = 0.0   # 0.0 (none) – 1.0 (severe)
    replacement_risk: ReplacementRisk = ReplacementRisk.LOW
    last_swap_at: Optional[datetime] = None
    avg_temperature: float = 25.0
    peak_temperature: float = 35.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def age_days(self) -> int:
        return (date.today() - self.manufacturing_date).days

    @property
    def is_eligible_for_swap(self) -> bool:
        return (
            self.status == BatteryStatus.ACTIVE
            and self.current_health >= 0.70
            and self.replacement_risk != ReplacementRisk.CRITICAL
        )

    @property
    def soh_category(self) -> str:
        if self.current_health >= 0.90:
            return "Excellent"
        if self.current_health >= 0.80:
            return "Good"
        if self.current_health >= 0.70:
            return "Fair"
        if self.current_health >= 0.60:
            return "Degraded"
        return "End-of-Life"

    def compute_replacement_risk(self) -> ReplacementRisk:
        score = 0.0
        if self.current_health < 0.70:
            score += 40
        elif self.current_health < 0.80:
            score += 20
        if self.cycle_count > 1500:
            score += 30
        elif self.cycle_count > 1000:
            score += 15
        if self.thermal_stress_score > 0.7:
            score += 20
        elif self.thermal_stress_score > 0.4:
            score += 10
        if self.age_days > 1460:  # > 4 years
            score += 10

        if score >= 70:
            return ReplacementRisk.CRITICAL
        if score >= 40:
            return ReplacementRisk.HIGH
        if score >= 20:
            return ReplacementRisk.MODERATE
        return ReplacementRisk.LOW
