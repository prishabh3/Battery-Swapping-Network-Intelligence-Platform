import logging
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

from backend.domain.entities.battery import Battery, ReplacementRisk
from backend.domain.repositories.battery_repository import BatteryRepository
from backend.application.dtos.battery_dto import BatteryHealthReport

logger = logging.getLogger(__name__)


class BatteryService:
    def __init__(self, battery_repo: BatteryRepository) -> None:
        self._repo = battery_repo

    async def get_battery(self, battery_id: str) -> Optional[Battery]:
        return await self._repo.get_by_id(battery_id)

    async def list_batteries(self, limit: int = 100, offset: int = 0) -> Sequence[Battery]:
        return await self._repo.list_all(limit=limit, offset=offset)

    async def get_station_inventory(self, station_id: str) -> Sequence[Battery]:
        return await self._repo.list_by_station(station_id)

    async def get_critical_batteries(self) -> Sequence[Battery]:
        return await self._repo.list_by_risk(ReplacementRisk.CRITICAL)

    async def get_high_risk_batteries(self) -> Sequence[Battery]:
        high = await self._repo.list_by_risk(ReplacementRisk.HIGH)
        critical = await self._repo.list_by_risk(ReplacementRisk.CRITICAL)
        return list(high) + list(critical)

    async def generate_health_report(self, battery_id: str) -> Optional[BatteryHealthReport]:
        battery = await self._repo.get_by_id(battery_id)
        if not battery:
            return None

        degradation_rate = round((1.0 - battery.current_health) / max(battery.cycle_count, 1) * 100, 4)
        remaining_soh = max(0.0, battery.current_health - 0.60)
        estimated_remaining_cycles = int(remaining_soh / max(degradation_rate / 100, 1e-6))

        eol_date: Optional[date] = None
        if estimated_remaining_cycles > 0:
            days_per_cycle = battery.age_days / max(battery.cycle_count, 1)
            eol_date = date.today() + timedelta(days=estimated_remaining_cycles * days_per_cycle)

        recommendations: list[str] = []
        if battery.current_health < 0.70:
            recommendations.append("Schedule immediate replacement — SOH below 70%.")
        if battery.thermal_stress_score > 0.6:
            recommendations.append("Reduce peak-load operations to mitigate thermal stress.")
        if battery.cycle_count > 1500:
            recommendations.append("Prioritize for retirement in next maintenance cycle.")
        if battery.peak_temperature > 45.0:
            recommendations.append("Investigate thermal management — peak temperature exceeds safe limit.")
        if not recommendations:
            recommendations.append("Battery is healthy. Maintain regular monitoring schedule.")

        return BatteryHealthReport(
            battery_id=battery.battery_id,
            current_health=battery.current_health,
            soh_category=battery.soh_category,
            cycle_count=battery.cycle_count,
            thermal_stress_score=battery.thermal_stress_score,
            replacement_risk=battery.replacement_risk.value,
            degradation_rate_per_100_cycles=degradation_rate,
            estimated_remaining_cycles=estimated_remaining_cycles,
            estimated_end_of_life_date=eol_date,
            recommendations=recommendations,
        )

    async def get_degradation_candidates(self, soh_threshold: float = 0.75) -> Sequence[Battery]:
        return await self._repo.get_degradation_candidates(soh_threshold)

    async def update_health_metrics(
        self,
        battery_id: str,
        new_soh: float,
        new_cycle_count: int,
        thermal_score: float,
    ) -> Optional[Battery]:
        battery = await self._repo.get_by_id(battery_id)
        if not battery:
            logger.warning("Battery %s not found for health update", battery_id)
            return None

        battery.current_health = new_soh
        battery.cycle_count = new_cycle_count
        battery.thermal_stress_score = thermal_score
        battery.replacement_risk = battery.compute_replacement_risk()
        battery.updated_at = datetime.utcnow()

        return await self._repo.update(battery)
