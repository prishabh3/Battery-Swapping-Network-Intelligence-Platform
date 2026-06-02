"""
Automated ETL pipeline: Raw data → Validation → Cleaning → Feature Engineering → PostgreSQL.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    stage: str
    rows_in: int = 0
    rows_out: int = 0
    rows_dropped: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    started_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def drop_rate(self) -> float:
        return round(self.rows_dropped / max(self.rows_in, 1), 4)


class DataValidator:
    """Schema validation for raw datasets."""

    BATTERY_REQUIRED = ["battery_id", "manufacturing_date", "chemistry_type",
                        "cycle_count", "current_health", "nominal_capacity_kwh", "status"]
    STATION_REQUIRED = ["station_id", "name", "city", "latitude", "longitude",
                        "capacity", "inventory_count", "status"]
    SWAP_REQUIRED = ["event_id", "timestamp", "station_id", "battery_in_id",
                     "battery_out_id", "vehicle_id", "duration_seconds",
                     "energy_delivered_kwh", "outcome"]

    def validate_batteries(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        issues = []
        df = df.copy()
        missing = [c for c in self.BATTERY_REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"Battery schema missing columns: {missing}")

        before = len(df)
        df = df.dropna(subset=["battery_id", "current_health"])
        df = df[df["current_health"].between(0.0, 1.0)]
        df = df[df["cycle_count"] >= 0]
        df = df[df["chemistry_type"].isin(["LFP", "NMC", "LTO", "LMFP"])]
        df = df.drop_duplicates(subset=["battery_id"])

        dropped = before - len(df)
        if dropped:
            issues.append(f"Batteries: dropped {dropped} invalid rows")
        return df, issues

    def validate_stations(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        issues = []
        df = df.copy()
        missing = [c for c in self.STATION_REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"Station schema missing columns: {missing}")

        before = len(df)
        df = df.dropna(subset=["station_id", "latitude", "longitude"])
        df = df[df["latitude"].between(-90, 90)]
        df = df[df["longitude"].between(-180, 180)]
        df = df[df["capacity"] > 0]
        df = df[df["inventory_count"] >= 0]
        df = df[df["inventory_count"] <= df["capacity"]]
        df = df.drop_duplicates(subset=["station_id"])

        dropped = before - len(df)
        if dropped:
            issues.append(f"Stations: dropped {dropped} invalid rows")
        return df, issues

    def validate_swap_events(self, df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
        issues = []
        df = df.copy()
        missing = [c for c in self.SWAP_REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"Swap schema missing columns: {missing}")

        before = len(df)
        df = df.dropna(subset=["event_id", "timestamp", "station_id"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df[df["duration_seconds"] > 0]
        df = df[df["energy_delivered_kwh"] >= 0]
        df = df[df["battery_in_id"] != df["battery_out_id"]]
        df = df.drop_duplicates(subset=["event_id"])

        dropped = before - len(df)
        if dropped:
            issues.append(f"Swap events: dropped {dropped} invalid rows")
        return df, issues


class FeatureEngineer:
    """Add analytics-ready features to clean datasets."""

    def engineer_battery_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        today = pd.Timestamp.today().normalize()
        df["manufacturing_date"] = pd.to_datetime(df["manufacturing_date"])
        df["age_days"] = (today - df["manufacturing_date"]).dt.days
        df["soh_category"] = pd.cut(
            df["current_health"],
            bins=[0, 0.60, 0.70, 0.80, 0.90, 1.01],
            labels=["End-of-Life", "Degraded", "Fair", "Good", "Excellent"],
            right=False,
        ).astype(str)
        df["degradation_rate"] = (1.0 - df["current_health"]) / df["cycle_count"].clip(lower=1) * 100
        df["estimated_remaining_cycles"] = (
            (df["current_health"] - 0.60).clip(lower=0) / df["degradation_rate"].clip(lower=1e-6) * 100
        ).astype(int)
        return df

    def engineer_station_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["utilization_rate"] = df["inventory_count"] / df["capacity"].clip(lower=1)
        df["utilization_tier"] = pd.cut(
            df["utilization_rate"],
            bins=[-0.01, 0.30, 0.70, 0.90, 1.01],
            labels=["underutilized", "normal", "high", "overloaded"],
        ).astype(str)
        df["available_capacity"] = df["capacity"] - df["inventory_count"]
        return df

    def engineer_swap_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["month"] = df["timestamp"].dt.month
        df["is_weekend"] = df["day_of_week"] >= 5
        df["is_peak_hour"] = df["hour"].isin(list(range(7, 11)) + list(range(17, 21)))
        df["revenue_per_kwh"] = df["revenue_inr"] / df["energy_delivered_kwh"].clip(lower=0.01)
        df["swap_date"] = df["timestamp"].dt.date
        df["week"] = df["timestamp"].dt.isocalendar().week.astype(int)
        df["quarter"] = df["timestamp"].dt.quarter

        # rolling station demand (requires sort by station+timestamp)
        df.sort_values(["station_id", "timestamp"], inplace=True)
        df["station_daily_swaps"] = (
            df.groupby(["station_id", df["timestamp"].dt.date])["event_id"].transform("count")
        )
        return df


class ETLPipeline:
    def __init__(self, db_url: str) -> None:
        self._db_url = db_url
        self._engine = create_engine(db_url, echo=False)
        self._validator = DataValidator()
        self._engineer = FeatureEngineer()
        self.metrics: list[PipelineMetrics] = []

    def _run_stage(self, name: str, func, *args) -> Any:
        m = PipelineMetrics(stage=name)
        t0 = time.perf_counter()
        try:
            result = func(*args)
            m.duration_seconds = round(time.perf_counter() - t0, 3)
            if isinstance(result, pd.DataFrame):
                m.rows_out = len(result)
            self.metrics.append(m)
            logger.info("[ETL] %s completed in %.2fs", name, m.duration_seconds)
            return result
        except Exception as e:
            m.errors.append(str(e))
            m.duration_seconds = round(time.perf_counter() - t0, 3)
            self.metrics.append(m)
            logger.error("[ETL] %s failed: %s", name, e, exc_info=True)
            raise

    def load_raw(self, data_dir: str = "data/raw") -> dict[str, pd.DataFrame]:
        def _load():
            result = {}
            for name in ["stations", "batteries", "vehicles", "swap_events"]:
                path = Path(data_dir) / f"{name}.parquet"
                if not path.exists():
                    logger.warning("File not found: %s — skipping", path)
                    continue
                df = pd.read_parquet(path)
                logger.info("Loaded %s: %d rows", name, len(df))
                result[name] = df
            return result

        return self._run_stage("load_raw", _load)

    def validate(self, datasets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        def _validate():
            cleaned = {}
            all_issues = []

            if "stations" in datasets:
                df, issues = self._validator.validate_stations(datasets["stations"])
                cleaned["stations"] = df
                all_issues.extend(issues)

            if "batteries" in datasets:
                df, issues = self._validator.validate_batteries(datasets["batteries"])
                cleaned["batteries"] = df
                all_issues.extend(issues)

            if "vehicles" in datasets:
                cleaned["vehicles"] = datasets["vehicles"].drop_duplicates(subset=["vehicle_id"])

            if "swap_events" in datasets:
                df, issues = self._validator.validate_swap_events(datasets["swap_events"])
                cleaned["swap_events"] = df
                all_issues.extend(issues)

            for issue in all_issues:
                logger.warning("[ETL] Validation: %s", issue)
            return cleaned

        return self._run_stage("validate", _validate)

    def feature_engineer(self, datasets: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        def _engineer():
            result = {}
            if "batteries" in datasets:
                result["batteries"] = self._engineer.engineer_battery_features(datasets["batteries"])
            if "stations" in datasets:
                result["stations"] = self._engineer.engineer_station_features(datasets["stations"])
            if "swap_events" in datasets:
                result["swap_events"] = self._engineer.engineer_swap_features(datasets["swap_events"])
            result["vehicles"] = datasets.get("vehicles", pd.DataFrame())
            return result

        return self._run_stage("feature_engineering", _engineer)

    def load_to_db(self, datasets: dict[str, pd.DataFrame]) -> None:
        def _load():
            table_map = {
                "stations": ("stations", ["station_id", "name", "city", "state", "latitude",
                                          "longitude", "capacity", "inventory_count",
                                          "charging_slots", "status", "operator_name",
                                          "pincode", "created_at", "updated_at"]),
                "batteries": ("batteries", ["battery_id", "manufacturing_date", "chemistry_type",
                                            "cycle_count", "current_health", "nominal_capacity_kwh",
                                            "current_station_id", "status", "thermal_stress_score",
                                            "replacement_risk", "avg_temperature", "peak_temperature",
                                            "last_swap_at", "created_at", "updated_at"]),
                "vehicles": ("vehicles", ["vehicle_id", "fleet_type", "region", "city",
                                          "operator_id", "registration_number", "status",
                                          "total_swaps", "total_distance_km", "avg_daily_swaps",
                                          "last_swap_at", "created_at"]),
                "swap_events": ("swap_events", ["event_id", "timestamp", "station_id",
                                                "battery_in_id", "battery_out_id", "vehicle_id",
                                                "duration_seconds", "energy_delivered_kwh",
                                                "outcome", "revenue_inr", "soh_at_swap",
                                                "is_anomalous", "anomaly_score", "created_at"]),
            }
            with self._engine.begin() as conn:
                for key, (table, cols) in table_map.items():
                    if key not in datasets:
                        continue
                    df = datasets[key][[c for c in cols if c in datasets[key].columns]]
                    df.to_sql(table, conn, if_exists="append", index=False, method="multi",
                              chunksize=5000)
                    logger.info("[ETL] Loaded %d rows → %s", len(df), table)

        self._run_stage("load_to_db", _load)

    def run(self, data_dir: str = "data/raw") -> list[PipelineMetrics]:
        logger.info("=== BSIP ETL Pipeline starting ===")
        raw = self.load_raw(data_dir)
        validated = self.validate(raw)
        engineered = self.feature_engineer(validated)
        self.load_to_db(engineered)
        logger.info("=== ETL Pipeline complete. Stages: %d ===", len(self.metrics))
        return self.metrics

    def print_metrics_report(self) -> None:
        print("\n" + "=" * 60)
        print("ETL Pipeline Metrics")
        print("=" * 60)
        for m in self.metrics:
            status = "OK" if not m.errors else "FAILED"
            print(f"  [{status}] {m.stage:<30} {m.duration_seconds:>6.2f}s")
            for err in m.errors:
                print(f"         ERROR: {err}")
        print("=" * 60)


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    db_url = os.getenv("SYNC_DATABASE_URL", "postgresql+psycopg2://bsip:bsip_secret@localhost:5432/battery_swapping")
    pipeline = ETLPipeline(db_url)
    pipeline.run()
    pipeline.print_metrics_report()
