import pytest
from backend.domain.entities.station import Station, StationStatus, UtilizationTier
from datetime import datetime


def make_station(**overrides) -> Station:
    defaults = dict(
        station_id="STN-001",
        name="Test Hub",
        city="Mumbai",
        state="Maharashtra",
        latitude=19.076,
        longitude=72.877,
        capacity=200,
        inventory_count=100,
        charging_slots=50,
        status=StationStatus.OPERATIONAL,
        operator_name="SUN Mobility",
        pincode="400001",
    )
    defaults.update(overrides)
    return Station(**defaults)


class TestStationUtilization:
    def test_utilization_rate_correct(self):
        s = make_station(capacity=200, inventory_count=120)
        assert abs(s.utilization_rate - 0.6) < 0.001

    def test_zero_capacity_returns_zero(self):
        s = make_station(capacity=0, inventory_count=0)
        assert s.utilization_rate == 0.0

    def test_underutilized_tier(self):
        s = make_station(capacity=200, inventory_count=50)
        assert s.utilization_tier == UtilizationTier.UNDERUTILIZED

    def test_normal_tier(self):
        s = make_station(capacity=200, inventory_count=100)
        assert s.utilization_tier == UtilizationTier.NORMAL

    def test_high_tier(self):
        s = make_station(capacity=200, inventory_count=160)
        assert s.utilization_tier == UtilizationTier.HIGH

    def test_overloaded_tier(self):
        s = make_station(capacity=200, inventory_count=190)
        assert s.utilization_tier == UtilizationTier.OVERLOADED


class TestStationSwapEligibility:
    def test_operational_with_inventory_can_fulfill(self):
        s = make_station(status=StationStatus.OPERATIONAL, inventory_count=10)
        assert s.can_fulfill_swap() is True

    def test_offline_cannot_fulfill(self):
        s = make_station(status=StationStatus.OFFLINE, inventory_count=100)
        assert s.can_fulfill_swap() is False

    def test_zero_inventory_cannot_fulfill(self):
        s = make_station(status=StationStatus.OPERATIONAL, inventory_count=0)
        assert s.can_fulfill_swap() is False

    def test_available_charging_capacity(self):
        s = make_station(capacity=200, inventory_count=150)
        assert s.available_charging_capacity == 50

    def test_charging_capacity_floored_at_zero(self):
        s = make_station(capacity=100, inventory_count=100)
        assert s.available_charging_capacity == 0
