import pytest
from datetime import date, timedelta

from backend.domain.entities.battery import Battery, BatteryStatus, ChemistryType, ReplacementRisk


def make_battery(**overrides) -> Battery:
    defaults = dict(
        battery_id="BAT-001",
        manufacturing_date=date.today() - timedelta(days=365),
        chemistry_type=ChemistryType.LFP,
        cycle_count=500,
        current_health=0.88,
        nominal_capacity_kwh=2.0,
        current_station_id="STN-001",
        status=BatteryStatus.ACTIVE,
        thermal_stress_score=0.2,
    )
    defaults.update(overrides)
    return Battery(**defaults)


class TestBatteryProperties:
    def test_age_days_positive(self):
        b = make_battery()
        assert b.age_days >= 0

    def test_soh_category_excellent(self):
        b = make_battery(current_health=0.95)
        assert b.soh_category == "Excellent"

    def test_soh_category_good(self):
        b = make_battery(current_health=0.85)
        assert b.soh_category == "Good"

    def test_soh_category_degraded(self):
        b = make_battery(current_health=0.65)
        assert b.soh_category == "Degraded"

    def test_soh_category_eol(self):
        b = make_battery(current_health=0.55)
        assert b.soh_category == "End-of-Life"

    def test_eligible_for_swap_healthy_battery(self):
        b = make_battery(current_health=0.85, status=BatteryStatus.ACTIVE)
        assert b.is_eligible_for_swap is True

    def test_not_eligible_low_soh(self):
        b = make_battery(current_health=0.65)
        assert b.is_eligible_for_swap is False

    def test_not_eligible_retired(self):
        b = make_battery(status=BatteryStatus.RETIRED)
        assert b.is_eligible_for_swap is False

    def test_not_eligible_critical_risk(self):
        b = make_battery(replacement_risk=ReplacementRisk.CRITICAL)
        assert b.is_eligible_for_swap is False


class TestReplacementRiskComputation:
    def test_low_risk_healthy_battery(self):
        b = make_battery(current_health=0.92, cycle_count=200, thermal_stress_score=0.1)
        assert b.compute_replacement_risk() == ReplacementRisk.LOW

    def test_critical_risk_very_degraded(self):
        b = make_battery(
            current_health=0.60,
            cycle_count=1800,
            thermal_stress_score=0.85,
            manufacturing_date=date.today() - timedelta(days=1600),
        )
        assert b.compute_replacement_risk() == ReplacementRisk.CRITICAL

    def test_high_risk_high_cycles(self):
        b = make_battery(current_health=0.75, cycle_count=1600)
        risk = b.compute_replacement_risk()
        assert risk in (ReplacementRisk.HIGH, ReplacementRisk.CRITICAL)

    def test_moderate_risk_medium_degradation(self):
        b = make_battery(current_health=0.77, cycle_count=950)
        risk = b.compute_replacement_risk()
        assert risk in (ReplacementRisk.MODERATE, ReplacementRisk.HIGH)

    def test_thermal_stress_escalates_risk(self):
        low_stress = make_battery(current_health=0.88, cycle_count=300, thermal_stress_score=0.1)
        high_stress = make_battery(current_health=0.88, cycle_count=300, thermal_stress_score=0.85)
        risk_low = low_stress.compute_replacement_risk()
        risk_high = high_stress.compute_replacement_risk()
        # Higher thermal stress should produce same or higher risk
        risk_order = [ReplacementRisk.LOW, ReplacementRisk.MODERATE,
                      ReplacementRisk.HIGH, ReplacementRisk.CRITICAL]
        assert risk_order.index(risk_high) >= risk_order.index(risk_low)
