import pytest
from datetime import date, timedelta

from analytics.battery_health.health_engine import (
    SOHCalculator, DegradationTrendAnalyzer, BatteryHealthEngine,
)


class TestSOHCalculator:
    def test_healthy_lfp_battery_high_soh(self):
        soh = SOHCalculator.compute_soh("LFP", cycle_count=100, age_days=90)
        assert soh > 0.95

    def test_soh_decreases_with_cycles(self):
        soh_low = SOHCalculator.compute_soh("NMC", cycle_count=200, age_days=200)
        soh_high = SOHCalculator.compute_soh("NMC", cycle_count=1500, age_days=1000)
        assert soh_high < soh_low

    def test_soh_bounded(self):
        soh = SOHCalculator.compute_soh("LFP", cycle_count=2000, age_days=2000, avg_temperature=40)
        assert 0.50 <= soh <= 1.0

    def test_lfp_degrades_slower_than_nmc(self):
        soh_lfp = SOHCalculator.compute_soh("LFP", cycle_count=1000, age_days=800)
        soh_nmc = SOHCalculator.compute_soh("NMC", cycle_count=1000, age_days=800)
        assert soh_lfp >= soh_nmc

    def test_thermal_stress_computed(self):
        stress = SOHCalculator.compute_thermal_stress(avg_temp=35.0, peak_temp=55.0, cycle_count=500)
        assert 0.0 <= stress <= 1.0

    def test_high_temp_higher_stress(self):
        stress_low = SOHCalculator.compute_thermal_stress(20.0, 30.0, 100)
        stress_high = SOHCalculator.compute_thermal_stress(40.0, 60.0, 100)
        assert stress_high > stress_low


class TestDegradationTrendAnalyzer:
    analyzer = DegradationTrendAnalyzer()

    def test_insufficient_data_returns_status(self):
        result = self.analyzer.analyze([(100, 0.90), (200, 0.88)])
        assert result["status"] == "insufficient_data"

    def test_linear_degradation(self):
        history = [(i * 100, 1.0 - i * 0.05) for i in range(10)]
        result = self.analyzer.analyze(history)
        assert result["r_squared"] > 0.90
        assert result["slope_per_cycle"] < 0

    def test_eol_cycles_estimated(self):
        history = [(i * 100, 1.0 - i * 0.04) for i in range(10)]
        result = self.analyzer.analyze(history)
        assert result["projected_eol_cycles"] is not None
        assert result["projected_eol_cycles"] > history[-1][0]


class TestBatteryHealthEngine:
    engine = BatteryHealthEngine()

    def _sample_battery(self, **overrides):
        base = {
            "battery_id": "BAT-TEST-001",
            "chemistry_type": "LFP",
            "manufacturing_date": (date.today() - timedelta(days=365)).isoformat(),
            "cycle_count": 600,
            "current_health": 0.85,
            "nominal_capacity_kwh": 2.0,
            "avg_temperature": 28.0,
            "peak_temperature": 38.0,
            "thermal_stress_score": 0.25,
        }
        base.update(overrides)
        return base

    def test_lifecycle_report_returns_correct_type(self):
        from analytics.battery_health.health_engine import BatteryLifecycleReport
        report = self.engine.generate_lifecycle_report(self._sample_battery())
        assert isinstance(report, BatteryLifecycleReport)

    def test_effective_capacity_le_nominal(self):
        report = self.engine.generate_lifecycle_report(self._sample_battery(current_health=0.80))
        assert report.effective_capacity_kwh <= report.nominal_capacity_kwh

    def test_healthy_battery_low_risk(self):
        report = self.engine.generate_lifecycle_report(
            self._sample_battery(current_health=0.95, cycle_count=100)
        )
        assert report.replacement_risk in ("low", "moderate")

    def test_degraded_battery_high_risk(self):
        report = self.engine.generate_lifecycle_report(
            self._sample_battery(
                current_health=0.60,
                cycle_count=1800,
                thermal_stress_score=0.80,
                manufacturing_date=(date.today() - timedelta(days=1600)).isoformat(),
            )
        )
        assert report.replacement_risk in ("high", "critical")

    def test_recommendations_not_empty(self):
        report = self.engine.generate_lifecycle_report(self._sample_battery())
        assert len(report.recommendations) >= 1

    def test_explainability_present(self):
        report = self.engine.generate_lifecycle_report(self._sample_battery())
        assert "factor_breakdown" in report.explainability
        assert "risk_composite_score" in report.explainability
