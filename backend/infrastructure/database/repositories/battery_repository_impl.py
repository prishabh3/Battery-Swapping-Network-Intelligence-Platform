from datetime import date, datetime
from typing import Optional, Sequence

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.entities.battery import Battery, BatteryStatus, ChemistryType, ReplacementRisk
from backend.domain.repositories.battery_repository import BatteryRepository
from backend.infrastructure.database.models import BatteryModel


def _to_entity(m: BatteryModel) -> Battery:
    return Battery(
        battery_id=m.battery_id,
        manufacturing_date=m.manufacturing_date,
        chemistry_type=ChemistryType(m.chemistry_type),
        cycle_count=m.cycle_count,
        current_health=m.current_health,
        nominal_capacity_kwh=m.nominal_capacity_kwh,
        current_station_id=m.current_station_id,
        status=BatteryStatus(m.status),
        thermal_stress_score=m.thermal_stress_score or 0.0,
        replacement_risk=ReplacementRisk(m.replacement_risk or "low"),
        avg_temperature=m.avg_temperature or 25.0,
        peak_temperature=m.peak_temperature or 35.0,
        last_swap_at=m.last_swap_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_model(b: Battery) -> BatteryModel:
    return BatteryModel(
        battery_id=b.battery_id,
        manufacturing_date=b.manufacturing_date,
        chemistry_type=b.chemistry_type.value,
        cycle_count=b.cycle_count,
        current_health=b.current_health,
        nominal_capacity_kwh=b.nominal_capacity_kwh,
        current_station_id=b.current_station_id,
        status=b.status.value,
        thermal_stress_score=b.thermal_stress_score,
        replacement_risk=b.replacement_risk.value,
        avg_temperature=b.avg_temperature,
        peak_temperature=b.peak_temperature,
        last_swap_at=b.last_swap_at,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


class SQLAlchemyBatteryRepository(BatteryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, battery_id: str) -> Optional[Battery]:
        result = await self._session.get(BatteryModel, battery_id)
        return _to_entity(result) if result else None

    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[Battery]:
        stmt = select(BatteryModel).limit(limit).offset(offset)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows]

    async def list_by_station(self, station_id: str) -> Sequence[Battery]:
        stmt = select(BatteryModel).where(BatteryModel.current_station_id == station_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows]

    async def list_by_status(self, status: BatteryStatus) -> Sequence[Battery]:
        stmt = select(BatteryModel).where(BatteryModel.status == status.value)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows]

    async def list_by_risk(self, risk: ReplacementRisk) -> Sequence[Battery]:
        stmt = select(BatteryModel).where(BatteryModel.replacement_risk == risk.value)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows]

    async def save(self, battery: Battery) -> Battery:
        model = _to_model(battery)
        self._session.add(model)
        await self._session.flush()
        return battery

    async def update(self, battery: Battery) -> Battery:
        model = await self._session.get(BatteryModel, battery.battery_id)
        if not model:
            raise ValueError(f"Battery {battery.battery_id} not found")
        model.cycle_count = battery.cycle_count
        model.current_health = battery.current_health
        model.current_station_id = battery.current_station_id
        model.status = battery.status.value
        model.thermal_stress_score = battery.thermal_stress_score
        model.replacement_risk = battery.replacement_risk.value
        model.avg_temperature = battery.avg_temperature
        model.peak_temperature = battery.peak_temperature
        model.last_swap_at = battery.last_swap_at
        model.updated_at = datetime.utcnow()
        await self._session.flush()
        return battery

    async def count_by_station(self, station_id: str) -> int:
        stmt = select(func.count()).where(BatteryModel.current_station_id == station_id)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_degradation_candidates(self, soh_threshold: float = 0.75) -> Sequence[Battery]:
        stmt = (
            select(BatteryModel)
            .where(BatteryModel.current_health <= soh_threshold)
            .where(BatteryModel.status == "active")
            .order_by(BatteryModel.current_health.asc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(r) for r in rows]
