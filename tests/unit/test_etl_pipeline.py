import pytest
import pandas as pd
import numpy as np
from data.etl.pipeline import DataValidator, FeatureEngineer


class TestDataValidator:
    validator = DataValidator()

    def _minimal_battery_df(self, n=10) -> pd.DataFrame:
        rng = np.random.default_rng(1)
        return pd.DataFrame({
            "battery_id": [f"BAT-{i}" for i in range(n)],
            "manufacturing_date": ["2022-01-01"] * n,
            "chemistry_type": rng.choice(["LFP", "NMC"], n),
            "cycle_count": rng.integers(0, 1000, n),
            "current_health": rng.uniform(0.60, 1.0, n),
            "nominal_capacity_kwh": [2.0] * n,
            "status": ["active"] * n,
        })

    def _minimal_station_df(self, n=5) -> pd.DataFrame:
        return pd.DataFrame({
            "station_id": [f"STN-{i}" for i in range(n)],
            "name": [f"Station {i}" for i in range(n)],
            "city": ["Mumbai"] * n,
            "latitude": [19.0 + i * 0.01 for i in range(n)],
            "longitude": [72.8 + i * 0.01 for i in range(n)],
            "capacity": [200] * n,
            "inventory_count": [100] * n,
            "status": ["operational"] * n,
        })

    def test_validate_batteries_removes_invalid_health(self):
        df = self._minimal_battery_df()
        df.loc[0, "current_health"] = 1.5   # invalid
        df.loc[1, "current_health"] = -0.1  # invalid
        cleaned, issues = self.validator.validate_batteries(df)
        assert len(cleaned) == len(df) - 2
        assert len(issues) > 0

    def test_validate_batteries_removes_duplicates(self):
        df = self._minimal_battery_df(5)
        df = pd.concat([df, df.iloc[:2]], ignore_index=True)
        cleaned, _ = self.validator.validate_batteries(df)
        assert len(cleaned) == 5

    def test_validate_stations_rejects_bad_lat(self):
        df = self._minimal_station_df()
        df.loc[0, "latitude"] = 200.0  # invalid
        cleaned, issues = self.validator.validate_stations(df)
        assert len(cleaned) == len(df) - 1

    def test_validate_stations_rejects_inventory_gt_capacity(self):
        df = self._minimal_station_df()
        df.loc[0, "inventory_count"] = 999  # > capacity
        cleaned, issues = self.validator.validate_stations(df)
        assert len(cleaned) == len(df) - 1

    def test_missing_required_column_raises(self):
        df = self._minimal_battery_df()
        df = df.drop(columns=["current_health"])
        with pytest.raises(ValueError):
            self.validator.validate_batteries(df)


class TestFeatureEngineer:
    engineer = FeatureEngineer()

    def _battery_df(self) -> pd.DataFrame:
        return pd.DataFrame({
            "battery_id": ["BAT-001", "BAT-002"],
            "manufacturing_date": ["2021-06-01", "2022-01-15"],
            "current_health": [0.85, 0.72],
            "cycle_count": [500, 900],
        })

    def test_battery_features_age_computed(self):
        df = self.engineer.engineer_battery_features(self._battery_df())
        assert "age_days" in df.columns
        assert (df["age_days"] > 0).all()

    def test_battery_features_soh_category(self):
        df = self.engineer.engineer_battery_features(self._battery_df())
        assert "soh_category" in df.columns
        assert set(df["soh_category"]).issubset({"Excellent", "Good", "Fair", "Degraded", "End-of-Life"})

    def test_station_features_utilization_rate(self):
        df = pd.DataFrame({
            "station_id": ["S1", "S2"],
            "capacity": [200, 100],
            "inventory_count": [100, 90],
        })
        out = self.engineer.engineer_station_features(df)
        assert "utilization_rate" in out.columns
        assert abs(out.iloc[0]["utilization_rate"] - 0.5) < 0.001

    def test_swap_features_hour_extracted(self):
        df = pd.DataFrame({
            "event_id": ["E1", "E2"],
            "timestamp": ["2024-01-01 08:30:00", "2024-01-01 19:00:00"],
            "station_id": ["S1", "S1"],
            "energy_delivered_kwh": [2.0, 1.8],
            "revenue_inr": [30.0, 27.0],
        })
        out = self.engineer.engineer_swap_features(df)
        assert "hour" in out.columns
        assert 8 in out["hour"].values
        assert "is_peak_hour" in out.columns
