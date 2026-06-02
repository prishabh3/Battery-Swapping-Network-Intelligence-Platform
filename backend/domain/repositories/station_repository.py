from abc import ABC, abstractmethod
from typing import Optional, Sequence

from backend.domain.entities.station import Station, StationStatus


class StationRepository(ABC):
    @abstractmethod
    async def get_by_id(self, station_id: str) -> Optional[Station]: ...

    @abstractmethod
    async def list_all(self, limit: int = 200, offset: int = 0) -> Sequence[Station]: ...

    @abstractmethod
    async def list_by_city(self, city: str) -> Sequence[Station]: ...

    @abstractmethod
    async def list_by_status(self, status: StationStatus) -> Sequence[Station]: ...

    @abstractmethod
    async def save(self, station: Station) -> Station: ...

    @abstractmethod
    async def update(self, station: Station) -> Station: ...

    @abstractmethod
    async def get_low_inventory_stations(self, threshold: float = 0.20) -> Sequence[Station]: ...

    @abstractmethod
    async def get_network_summary(self) -> dict: ...
