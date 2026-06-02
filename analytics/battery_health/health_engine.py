"""
Battery Health Analytics Engine.
Computes State of Health (SOH), degradation trends, thermal stress scores,
replacement risk scores, and generates lifecycle reports.
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BatteryLifecycleReport:
    battery_id: str
    chemistry_type: str
    age_days: int
    current_soh: float
    soh_category: str
    cycle_count: int
    nominal_capacity_kwh: float
    effective_capacity_kwh: float
    thermal_stress_score: float
    thermal_risk_level: str
    degradation_rate_per_100_cycles: float
    estimated_remaining_cycles: int
    estimated_eol_date: Optional[date]
    replacement_risk: str
    replacement_urgency_days: Optional[int]
    lifetime_energy_delivered_kwh: float
    lifetime_revenue_inr: float
    recommendations: list[str] = field(default_factory=list)
    explainability: dict = field(default_factory=dict)


class SOHCalculator:
    """
    State-of-Health calculation using multi-factor model.
    SOH reflects capacity retention relative to nominal, accounting for:
      - Cycle aging (primary degradation)
      - Calendar aging (secondary degradation)
      - Thermal stress (accelerated degradation multiplier)
    """

    CHEMISTRY_PARAMS = {
        "LFP":  {"cycle_deg": 0.000035, "calendar_deg": 0.0001, "thermal_factor": 0.8},
        "NMC":  {"cycle_deg": 0.000050, "calendar_deg": 0.0001, "thermal_factor": 1.2},
        "LTO":  {"cycle_deg": 0.000015, "calendar_deg": 0.00008, "thermal_factor": 0.6},
        "LMFP": {"cycle_deg": 0.000040, "calendar_deg": 0.0001, "thermal_factor": 0.9},
    }

    @classmethod
    def compute_soh(
        cls,
        chemistry: str,
        cycle_count: int,
        age_days: int,
        avg_temperature: float = 25.0,
        thermal_stress_score: float = 0.0,
    ) -> float:
        params = cls.CHEMISTRY_PARAMS.get(chemistry, cls.CHEMISTRY_PARAMS["LFP"])

        # Arrhenius thermal acceleration (reference: 25°C)
        thermal_acceleration = math.exp(params["thermal_factor"] * (avg_temperature - 25.0) / 300.0)

        cycle_loss = params["cycle_deg"] * cycle_count * thermal_acceleration
        calendar_loss = params["calendar_deg"] * age_days * thermal_acceleration
        stress_penalty = thermal_stress_score * 0.05

        soh = 1.0 - cycle_loss - calendar_loss - stress_penalty
        return float(np.clip(soh, 0.50, 1.0))

    @classmethod
    def compute_thermal_stress(cls, avg_temp: float, peak_temp: float, cycle_count: int) -> float:
        temp_stress = max(0.0, (avg_temp - 20.0) / 35.0)
        peak_stress = max(0.0, (peak_temp - 35.0) / 25.0)
        cycle_stress = min(1.0, cycle_count / 2000.0) * 0.2
        return float(np.clip(temp_stress * 0.5 + peak_stress * 0.3 + cycle_stress, 0.0, 1.0))


class DegradationTrendAnalyzer:
    """Fits degradation curves and projects end-of-life."""

    EOL_SOH = 0.60  # 60% SOH is end-of-life threshold

    def analyze(self, soh_history: list[tuple[int, float]]) -> dict:
        """
        soh_history: list of (cycle_count, soh) tuples, sorted by cycle_count.
        Returns degradation rate, projected EOL, and confidence.
        """
        if len(soh_history) < 3:
            return {"status": "insufficient_data"}

        cycles = np.array([h[0] for h in soh_history], dtype=float)
        sohs = np.array([h[1] for h in soh_history], dtype=float)

        # Linear regression on degradation
        coeffs = np.polyfit(cycles, sohs, deg=1)
        slope = coeffs[0]  # SOH change per cycle
        intercept = coeffs[1]

        # R² for fit quality
        y_pred = np.polyval(coeffs, cycles)
        ss_res = np.sum((sohs - y_pred) ** 2)
        ss_tot = np.sum((sohs - sohs.mean()) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        current_soh = sohs[-1]
        current_cycles = cycles[-1]
        degradation_per_100 = abs(slope) * 100

        eol_cycles: Optional[int] = None
        if slope < 0:
            eol_cycles_delta = (self.EOL_SOH - current_soh) / slope
            if eol_cycles_delta > 0:
                eol_cycles = int(current_cycles + eol_cycles_delta)

        return {
            "slope_per_cycle": round(float(slope), 6),
            "degradation_per_100_cycles": round(float(degradation_per_100), 4),
            "r_squared": round(float(r2), 4),
            "projected_eol_cycles": eol_cycles,
            "current_soh": round(float(current_soh), 4),
            "fit_quality": "good" if r2 > 0.85 else "moderate" if r2 > 0.60 else "poor",
        }


class BatteryHealthEngine:
    """Main analytics engine for battery health assessment."""

    SOH_CALC = SOHCalculator()
    TREND_ANALYZER = DegradationTrendAnalyzer()

    REPLACEMENT_RISK_THRESHOLDS = {
        "critical": {"soh": 0.65, "cycles": 1700, "thermal": 0.80, "age": 1460},
        "high":     {"soh": 0.72, "cycles": 1300, "thermal": 0.60, "age": 1095},
        "moderate": {"soh": 0.80, "cycles": 900,  "thermal": 0.40, "age": 730},
    }

    def compute_replacement_risk_score(
        self, soh: float, cycle_count: int, thermal_stress: float, age_days: int
    ) -> tuple[str, float, dict]:
        """Returns (risk_level, composite_score, factor_breakdown)."""
        scores = {
            "soh_factor":     max(0.0, (0.90 - soh) / 0.35) * 40,
            "cycle_factor":   min(1.0, cycle_count / 2000) * 30,
            "thermal_factor": thermal_stress * 20,
            "age_factor":     min(1.0, age_days / 1825) * 10,
        }
        composite = sum(scores.values())

        risk = "low"
        for level in ["critical", "high", "moderate"]:
            th = self.REPLACEMENT_RISK_THRESHOLDS[level]
            if (soh <= th["soh"] or cycle_count >= th["cycles"]
                    or thermal_stress >= th["thermal"] or age_days >= th["age"]):
                risk = level
                break

        return risk, round(composite, 2), scores

    def generate_lifecycle_report(self, battery_data: dict) -> BatteryLifecycleReport:
        batt_id = battery_data["battery_id"]
        chemistry = battery_data.get("chemistry_type", "LFP")
        mfg_date = battery_data.get("manufacturing_date")
        if isinstance(mfg_date, str):
            mfg_date = date.fromisoformat(mfg_date)
        age_days = (date.today() - mfg_date).days if mfg_date else 365

        cycle_count = battery_data.get("cycle_count", 0)
        current_soh = battery_data.get("current_health", 0.85)
        nominal_kwh = battery_data.get("nominal_capacity_kwh", 2.0)
        avg_temp = battery_data.get("avg_temperature", 28.0)
        peak_temp = battery_data.get("peak_temperature", 38.0)
        thermal_stress = battery_data.get("thermal_stress_score") or \
                         SOHCalculator.compute_thermal_stress(avg_temp, peak_temp, cycle_count)

        risk_level, risk_score, factor_breakdown = self.compute_replacement_risk_score(
            current_soh, cycle_count, thermal_stress, age_days
        )

        effective_kwh = round(nominal_kwh * current_soh, 3)
        degradation_rate = round(abs((1.0 - current_soh) / max(cycle_count, 1)) * 100, 4)
        remaining_soh = max(0.0, current_soh - 0.60)
        estimated_remaining_cycles = int(remaining_soh / max(degradation_rate / 100, 1e-6))

        eol_date: Optional[date] = None
        urgency_days: Optional[int] = None
        if estimated_remaining_cycles > 0 and cycle_count > 0:
            days_per_cycle = age_days / max(cycle_count, 1)
            eol_days = int(estimated_remaining_cycles * days_per_cycle)
            eol_date = date.today() + timedelta(days=eol_days)
            urgency_days = eol_days

        lifetime_energy = round(cycle_count * effective_kwh, 1)
        lifetime_revenue = round(lifetime_energy * 14.5, 2)

        recommendations = self._generate_recommendations(
            current_soh, cycle_count, thermal_stress, peak_temp, age_days, risk_level
        )

        soh_category = (
            "Excellent" if current_soh >= 0.90 else
            "Good" if current_soh >= 0.80 else
            "Fair" if current_soh >= 0.70 else
            "Degraded" if current_soh >= 0.60 else "End-of-Life"
        )
        thermal_risk = (
            "Severe" if thermal_stress > 0.7 else
            "High" if thermal_stress > 0.5 else
            "Moderate" if thermal_stress > 0.3 else "Low"
        )

        return BatteryLifecycleReport(
            battery_id=batt_id,
            chemistry_type=chemistry,
            age_days=age_days,
            current_soh=round(current_soh, 4),
            soh_category=soh_category,
            cycle_count=cycle_count,
            nominal_capacity_kwh=nominal_kwh,
            effective_capacity_kwh=effective_kwh,
            thermal_stress_score=round(thermal_stress, 4),
            thermal_risk_level=thermal_risk,
            degradation_rate_per_100_cycles=degradation_rate,
            estimated_remaining_cycles=estimated_remaining_cycles,
            estimated_eol_date=eol_date,
            replacement_risk=risk_level,
            replacement_urgency_days=urgency_days,
            lifetime_energy_delivered_kwh=lifetime_energy,
            lifetime_revenue_inr=lifetime_revenue,
            recommendations=recommendations,
            explainability={
                "risk_composite_score": risk_score,
                "factor_breakdown": factor_breakdown,
                "model": "multi_factor_v2",
                "note": "Scores are weighted contributions to replacement risk (0-100 scale).",
            },
        )

    def fleet_health_summary(self, batteries_df: pd.DataFrame) -> dict:
        distribution = {
            "Excellent": int((batteries_df["current_health"] >= 0.90).sum()),
            "Good":      int(((batteries_df["current_health"] >= 0.80) & (batteries_df["current_health"] < 0.90)).sum()),
            "Fair":      int(((batteries_df["current_health"] >= 0.70) & (batteries_df["current_health"] < 0.80)).sum()),
            "Degraded":  int(((batteries_df["current_health"] >= 0.60) & (batteries_df["current_health"] < 0.70)).sum()),
            "EOL":       int((batteries_df["current_health"] < 0.60).sum()),
        }
        risk_counts = batteries_df["replacement_risk"].value_counts().to_dict() if "replacement_risk" in batteries_df.columns else {}

        return {
            "total_batteries": len(batteries_df),
            "avg_soh": round(float(batteries_df["current_health"].mean()), 4),
            "median_soh": round(float(batteries_df["current_health"].median()), 4),
            "avg_cycle_count": round(float(batteries_df["cycle_count"].mean()), 1),
            "soh_distribution": distribution,
            "risk_distribution": risk_counts,
            "batteries_needing_replacement_30d": int(
                ((batteries_df["current_health"] < 0.68) & (batteries_df["status"] == "active")).sum()
            ),
        }

    def _generate_recommendations(
        self, soh, cycles, thermal, peak_temp, age_days, risk_level
    ) -> list[str]:
        recs = []
        if risk_level == "critical":
            recs.append("URGENT: Schedule immediate decommission and replacement.")
        if soh < 0.70:
            recs.append(f"SOH at {soh * 100:.1f}% — below 70% service threshold. Replace within 30 days.")
        if thermal > 0.65:
            recs.append("High thermal stress detected. Reduce high-load cycles and improve cooling.")
        if peak_temp > 50:
            recs.append(f"Peak temperature {peak_temp:.1f}°C exceeds 50°C — inspect thermal management system.")
        if cycles > 1500:
            recs.append(f"High cycle count ({cycles}) — accelerated degradation likely. Monitor weekly.")
        if age_days > 1460:
            recs.append(f"Battery age {age_days // 365}+ years. Schedule end-of-life planning.")
        if not recs:
            recs.append("Battery is within healthy operating parameters. Continue standard monitoring.")
        return recs
