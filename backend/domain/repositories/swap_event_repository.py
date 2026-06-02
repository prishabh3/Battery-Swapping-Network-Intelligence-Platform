from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Sequence

from backend.domain.entities.swap_event import SwapEvent


class SwapEventRepository(ABC):
    @abstractmethod
    async def get_by_id(self, event_id: str) -> Optional[SwapEvent]: ...

    @abstractmethod
    async def list_by_station(
        self, station_id: str, start: datetime, end: datetime
    ) -> Sequence[SwapEvent]: ...

    @abstractmethod
    async def list_by_vehicle(
        self, vehicle_id: str, limit: int = 100
    ) -> Sequence[SwapEvent]: ...

    @abstractmethod
    async def list_anomalous(self, limit: int = 500) -> Sequence[SwapEvent]: ...

    @abstractmethod
    async def save(self, event: SwapEvent) -> SwapEvent: ...

    @abstractmethod
    async def get_daily_counts(
        self, station_id: str, days: int = 30
    ) -> Sequence[dict]: ...

    @abstractmethod
    async def get_hourly_distribution(self, station_id: str) -> Sequence[dict]: ...

    @abstractmethod
    async def get_network_total_swaps(self, start: datetime, end: datetime) -> int: ...
