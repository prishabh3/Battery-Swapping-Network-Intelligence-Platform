import pytest
from analytics.optimization.inventory_optimizer import (
    InventoryOptimizer, ScenarioSimulator, StationNode, _haversine_km,
)


class TestHaversine:
    def test_same_point_zero(self):
        assert _haversine_km(19.076, 72.877, 19.076, 72.877) == pytest.approx(0.0, abs=0.001)

    def test_mumbai_to_delhi_approx(self):
        dist = _haversine_km(19.076, 72.877, 28.614, 77.209)
        assert 1100 < dist < 1500


class TestStationNode:
    def test_surplus_computed(self):
        n = StationNode("S1", "Hub", "Mumbai", 0, 0, inventory=300, capacity=400, expected_demand=120)
        assert n.surplus == 180

    def test_shortfall_computed(self):
        n = StationNode("S2", "Stn", "Mumbai", 0, 0, inventory=40, capacity=200, expected_demand=180)
        assert n.shortfall == 140

    def test_no_negative_surplus(self):
        n = StationNode("S3", "Stn", "Delhi", 0, 0, inventory=10, capacity=100, expected_demand=90)
        assert n.surplus == 0


class TestInventoryOptimizer:
    def test_optimize_returns_structure(self):
        opt = InventoryOptimizer()
        result = opt.optimize()
        assert "total_transfers" in result
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)

    def test_transfers_have_required_fields(self):
        opt = InventoryOptimizer()
        result = opt.optimize()
        for rec in result["recommendations"]:
            for field in ["from_station_id", "to_station_id", "quantity", "priority",
                          "urgency_score", "distance_km", "reason"]:
                assert field in rec

    def test_quantity_positive(self):
        opt = InventoryOptimizer()
        result = opt.optimize()
        for rec in result["recommendations"]:
            assert rec["quantity"] > 0

    def test_urgency_score_bounded(self):
        opt = InventoryOptimizer()
        result = opt.optimize()
        for rec in result["recommendations"]:
            assert 0.0 <= rec["urgency_score"] <= 1.0

    def test_priority_valid(self):
        opt = InventoryOptimizer()
        result = opt.optimize()
        valid = {"CRITICAL", "HIGH", "NORMAL"}
        for rec in result["recommendations"]:
            assert rec["priority"] in valid


class TestScenarioSimulator:
    sim = ScenarioSimulator()

    def test_new_stations_returns_all_keys(self):
        result = self.sim.simulate_new_stations("Mumbai", 10)
        for key in ["scenario_name", "inputs", "outputs", "recommendations",
                    "financial_impact", "risk_assessment"]:
            assert key in result

    def test_batteries_required_positive(self):
        result = self.sim.simulate_new_stations("Delhi", 5, avg_capacity=120)
        assert result["outputs"]["batteries_required"] > 0

    def test_risk_assessment_valid(self):
        result = self.sim.simulate_new_stations("Pune", 3)
        assert result["risk_assessment"] in ("LOW", "MODERATE", "HIGH")

    def test_demand_shock_revenue_positive(self):
        result = self.sim.simulate_demand_shock(30.0)
        assert result["financial_impact"]["additional_annual_revenue_inr"] > 0

    def test_retirement_salvage_positive(self):
        result = self.sim.simulate_battery_retirement(0.10)
        assert result["financial_impact"]["second_life_salvage_inr"] > 0
