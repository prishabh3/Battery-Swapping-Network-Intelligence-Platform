"""
Multi-dimensional anomaly detection using Isolation Forest.
Detects: abnormal battery degradation, suspicious swap patterns,
unusual station demand, and inventory discrepancies.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


@dataclass
class AnomalyRecord:
    anomaly_id: str
    entity_type: str   # battery | station | swap
    entity_id: str
    anomaly_type: str
    severity: str      # info | warning | critical
    score: float       # 0–1, higher = more anomalous
    description: str
    detected_at: datetime
    is_resolved: bool = False


class BatteryAnomalyDetector:
    """Detects abnormal battery degradation and thermal events."""

    FEATURE_COLS = ["current_health", "cycle_count", "thermal_stress_score",
                    "avg_temperature", "peak_temperature", "degradation_rate"]

    def __init__(self, contamination: float = 0.05) -> None:
        self._model = IsolationForest(
            n_estimators=200, contamination=contamination,
            random_state=42, n_jobs=-1,
        )
        self._scaler = StandardScaler()
        self._trained = False

    def _prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "degradation_rate" not in df.columns:
            df["degradation_rate"] = (
                (1.0 - df["current_health"]) / df["cycle_count"].clip(lower=1) * 100
            )
        return df[self.FEATURE_COLS].fillna(df[self.FEATURE_COLS].median())

    def fit(self, batteries_df: pd.DataFrame) -> "BatteryAnomalyDetector":
        X = self._prepare_features(batteries_df)
        X_scaled = self._scaler.fit_transform(X)
        self._model.fit(X_scaled)
        self._trained = True
        logger.info("Battery anomaly model trained on %d samples", len(X))
        return self

    def detect(self, batteries_df: pd.DataFrame) -> list[AnomalyRecord]:
        if not self._trained:
            self.fit(batteries_df)

        X = self._prepare_features(batteries_df)
        X_scaled = self._scaler.transform(X)

        scores = -self._model.score_samples(X_scaled)
        predictions = self._model.predict(X_scaled)

        records = []
        for i, (_, row) in enumerate(batteries_df.iterrows()):
            if predictions[i] == -1:  # anomaly
                raw_score = float(scores[i])
                norm_score = min(1.0, max(0.0, (raw_score - 0.3) / 0.7))
                severity = "critical" if norm_score > 0.8 else "warning" if norm_score > 0.5 else "info"

                reasons = []
                if row.get("thermal_stress_score", 0) > 0.7:
                    reasons.append(f"high thermal stress ({row['thermal_stress_score']:.2f})")
                if row.get("current_health", 1) < 0.65:
                    reasons.append(f"critical SOH ({row['current_health']:.2f})")
                if row.get("cycle_count", 0) > 1600:
                    reasons.append(f"excessive cycle count ({row['cycle_count']})")
                if row.get("peak_temperature", 0) > 50:
                    reasons.append(f"peak temperature alert ({row['peak_temperature']:.1f}°C)")

                description = (
                    "Anomalous battery behaviour detected: " + (", ".join(reasons) if reasons else "statistical outlier")
                )

                records.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4()),
                    entity_type="battery",
                    entity_id=str(row.get("battery_id", f"BAT-{i}")),
                    anomaly_type="degradation_anomaly",
                    severity=severity,
                    score=round(norm_score, 4),
                    description=description,
                    detected_at=datetime.utcnow(),
                ))

        logger.info("Battery anomaly detection: %d anomalies found in %d batteries",
                    len(records), len(batteries_df))
        return records


class SwapPatternAnomalyDetector:
    """Detects suspicious or unusual swap patterns."""

    FEATURE_COLS = ["duration_seconds", "energy_delivered_kwh", "revenue_inr",
                    "soh_at_swap", "hour", "is_peak_hour"]

    def __init__(self, contamination: float = 0.03) -> None:
        self._model = IsolationForest(
            n_estimators=200, contamination=contamination,
            random_state=42, n_jobs=-1,
        )
        self._scaler = StandardScaler()
        self._trained = False

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["hour"] = df["timestamp"].dt.hour
            df["is_peak_hour"] = df["hour"].isin(list(range(7, 11)) + list(range(17, 21))).astype(int)
        existing = [c for c in self.FEATURE_COLS if c in df.columns]
        return df[existing].fillna(0)

    def fit(self, swaps_df: pd.DataFrame) -> "SwapPatternAnomalyDetector":
        X = self._prepare(swaps_df)
        X_scaled = self._scaler.fit_transform(X)
        self._model.fit(X_scaled)
        self._trained = True
        return self

    def detect(self, swaps_df: pd.DataFrame) -> list[AnomalyRecord]:
        if not self._trained:
            self.fit(swaps_df)

        X = self._prepare(swaps_df)
        X_scaled = self._scaler.transform(X)
        scores = -self._model.score_samples(X_scaled)
        predictions = self._model.predict(X_scaled)

        records = []
        for i, (_, row) in enumerate(swaps_df.iterrows()):
            if predictions[i] == -1:
                raw_score = float(scores[i])
                norm_score = min(1.0, max(0.0, (raw_score - 0.3) / 0.7))
                severity = "critical" if norm_score > 0.75 else "warning" if norm_score > 0.45 else "info"

                reasons = []
                if row.get("duration_seconds", 90) > 240:
                    reasons.append("unusually long swap duration")
                if row.get("duration_seconds", 90) < 20:
                    reasons.append("suspiciously fast swap")
                if row.get("energy_delivered_kwh", 2) > 5.0:
                    reasons.append("energy delivered exceeds battery capacity")
                if row.get("soh_at_swap", 0.8) < 0.60:
                    reasons.append("critically degraded battery dispensed")

                records.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4()),
                    entity_type="swap",
                    entity_id=str(row.get("event_id", f"EVT-{i}")),
                    anomaly_type="suspicious_swap",
                    severity=severity,
                    score=round(norm_score, 4),
                    description="Suspicious swap pattern: " + (", ".join(reasons) if reasons else "outlier"),
                    detected_at=datetime.utcnow(),
                ))

        return records


class StationDemandAnomalyDetector:
    """Detects stations with unusual demand or inventory patterns."""

    def detect_inventory_discrepancies(self, stations_df: pd.DataFrame) -> list[AnomalyRecord]:
        records = []
        for _, row in stations_df.iterrows():
            util = row.get("inventory_count", 0) / max(row.get("capacity", 1), 1)
            if util > 0.98:
                records.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4()),
                    entity_type="station",
                    entity_id=str(row.get("station_id", "")),
                    anomaly_type="inventory_discrepancy",
                    severity="warning",
                    score=0.85,
                    description=f"Station at {util * 100:.0f}% capacity — potential reporting error or outage.",
                    detected_at=datetime.utcnow(),
                ))
            elif util < 0.05 and row.get("status", "") == "operational":
                records.append(AnomalyRecord(
                    anomaly_id=str(uuid.uuid4()),
                    entity_type="station",
                    entity_id=str(row.get("station_id", "")),
                    anomaly_type="critical_low_inventory",
                    severity="critical",
                    score=0.95,
                    description=f"Operational station critically low: only {util * 100:.0f}% inventory.",
                    detected_at=datetime.utcnow(),
                ))
        return records


class AnomalyDetectionPipeline:
    """Orchestrates all anomaly detectors and produces a unified report."""

    def __init__(self) -> None:
        self._battery_detector = BatteryAnomalyDetector()
        self._swap_detector = SwapPatternAnomalyDetector()
        self._station_detector = StationDemandAnomalyDetector()

    def run(
        self,
        batteries_df: Optional[pd.DataFrame] = None,
        swaps_df: Optional[pd.DataFrame] = None,
        stations_df: Optional[pd.DataFrame] = None,
    ) -> dict:
        all_records: list[AnomalyRecord] = []

        if batteries_df is not None and len(batteries_df) > 0:
            all_records.extend(self._battery_detector.detect(batteries_df))

        if swaps_df is not None and len(swaps_df) > 0:
            all_records.extend(self._swap_detector.detect(swaps_df))

        if stations_df is not None and len(stations_df) > 0:
            all_records.extend(self._station_detector.detect_inventory_discrepancies(stations_df))

        severity_counts = {"critical": 0, "warning": 0, "info": 0}
        for r in all_records:
            severity_counts[r.severity] = severity_counts.get(r.severity, 0) + 1

        return {
            "total_anomalies": len(all_records),
            "severity_breakdown": severity_counts,
            "anomalies": [
                {
                    "anomaly_id": r.anomaly_id,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "anomaly_type": r.anomaly_type,
                    "severity": r.severity,
                    "score": r.score,
                    "description": r.description,
                    "detected_at": r.detected_at.isoformat(),
                }
                for r in sorted(all_records, key=lambda x: -x.score)
            ],
        }
