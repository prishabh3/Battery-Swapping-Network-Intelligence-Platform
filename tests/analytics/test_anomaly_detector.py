import pytest
import numpy as np
import pandas as pd
from analytics.anomaly_detection.anomaly_detector import (
    BatteryAnomalyDetector, SwapPatternAnomalyDetector,
    StationDemandAnomalyDetector, AnomalyDetectionPipeline,
)


def make_battery_df(n=200, seed=42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "battery_id": [f"BAT-{i}" for i in range(n)],
        "current_health": np.clip(rng.normal(0.82, 0.1, n), 0.55, 1.0),
        "cycle_count": rng.integers(50, 1600, n),
        "thermal_stress_score": rng.uniform(0, 0.9, n),
        "avg_temperature": rng.normal(28, 5, n),
        "peak_temperature": rng.normal(38, 7, n),
        "status": rng.choice(["active", "charging"], n),
    })


def make_station_df(n=30, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "station_id": [f"STN-{i}" for i in range(n)],
        "capacity": rng.integers(100, 300, n),
        "inventory_count": rng.integers(0, 300, n),
        "status": rng.choice(["operational", "operational", "operational", "offline"], n, p=[0.8, 0.0, 0.0, 0.2]),
        "name": [f"Station {i}" for i in range(n)],
        "city": rng.choice(["Mumbai", "Delhi", "Bengaluru"], n),
    })


class TestBatteryAnomalyDetector:
    def test_returns_list(self):
        df = make_battery_df()
        detector = BatteryAnomalyDetector()
        records = detector.detect(df)
        assert isinstance(records, list)

    def test_anomaly_scores_bounded(self):
        df = make_battery_df()
        detector = BatteryAnomalyDetector()
        records = detector.detect(df)
        for r in records:
            assert 0.0 <= r.score <= 1.0

    def test_severity_valid(self):
        df = make_battery_df()
        detector = BatteryAnomalyDetector()
        records = detector.detect(df)
        valid = {"info", "warning", "critical"}
        for r in records:
            assert r.severity in valid

    def test_entity_type_battery(self):
        df = make_battery_df()
        detector = BatteryAnomalyDetector()
        records = detector.detect(df)
        for r in records:
            assert r.entity_type == "battery"

    def test_fit_then_detect_consistent(self):
        df = make_battery_df(300)
        detector = BatteryAnomalyDetector()
        detector.fit(df)
        records = detector.detect(df)
        assert isinstance(records, list)


class TestStationAnomalyDetector:
    def test_detects_zero_inventory_operational(self):
        import pandas as pd
        df = pd.DataFrame([{
            "station_id": "STN-X",
            "capacity": 200,
            "inventory_count": 5,  # ~2.5% — triggers critical low
            "status": "operational",
            "name": "Test Station",
        }])
        detector = StationDemandAnomalyDetector()
        records = detector.detect_inventory_discrepancies(df)
        assert len(records) > 0
        assert any(r.severity == "critical" for r in records)


class TestAnomalyPipeline:
    def test_pipeline_runs_without_error(self):
        batt_df = make_battery_df(100)
        stn_df = make_station_df(20)
        pipeline = AnomalyDetectionPipeline()
        result = pipeline.run(batteries_df=batt_df, stations_df=stn_df)
        assert "total_anomalies" in result
        assert "severity_breakdown" in result
        assert "anomalies" in result

    def test_pipeline_empty_input(self):
        pipeline = AnomalyDetectionPipeline()
        result = pipeline.run()
        assert result["total_anomalies"] == 0
