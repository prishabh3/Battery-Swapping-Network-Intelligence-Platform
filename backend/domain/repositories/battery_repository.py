from abc import ABC, abstractmethod
from typing import Optional, Sequence
from uuid import UUID

from backend.domain.entities.battery import Battery, BatteryStatus, ReplacementRisk


class BatteryRepository(ABC):
    @abstractmethod
    async def get_by_id(self, battery_id: str) -> Optional[Battery]: ...

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> Sequence[Battery]: ...

    @abstractmethod
    async def list_by_station(self, station_id: str) -> Sequence[Battery]: ...

    @abstractmethod
    async def list_by_status(self, status: BatteryStatus) -> Sequence[Battery]: ...

    @abstractmethod
    async def list_by_risk(self, risk: ReplacementRisk) -> Sequence[Battery]: ...

    @abstractmethod
    async def save(self, battery: Battery) -> Battery: ...

    @abstractmethod
    async def update(self, battery: Battery) -> Battery: ...

    @abstractmethod
    async def count_by_station(self, station_id: str) -> int: ...

    @abstractmethod
    async def get_degradation_candidates(self, soh_threshold: float = 0.75) -> Sequence[Battery]: ...
