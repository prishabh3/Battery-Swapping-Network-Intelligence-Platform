"""
Synthetic data generator for the Battery Swapping Intelligence Platform.
Generates realistic datasets reflecting India-wide battery-swapping operations.
"""
import random
import uuid
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from faker import Faker

logger = logging.getLogger(__name__)
fake = Faker("en_IN")
rng = np.random.default_rng(seed=42)

# ── Geographic constants ──────────────────────────────────────────────────────

CITY_COORDINATES = {
    "Mumbai":     (19.0760,  72.8777, "Maharashtra"),
    "Delhi":      (28.6139,  77.2090, "Delhi"),
    "Bengaluru":  (12.9716,  77.5946, "Karnataka"),
    "Hyderabad":  (17.3850,  78.4867, "Telangana"),
    "Chennai":    (13.0827,  80.2707, "Tamil Nadu"),
    "Pune":       (18.5204,  73.8567, "Maharashtra"),
    "Ahmedabad":  (23.0225,  72.5714, "Gujarat"),
    "Jaipur":     (26.9124,  75.7873, "Rajasthan"),
    "Lucknow":    (26.8467,  80.9462, "Uttar Pradesh"),
    "Kochi":      ( 9.9312,  76.2673, "Kerala"),
    "Kolkata":    (22.5726,  88.3639, "West Bengal"),
    "Surat":      (21.1702,  72.8311, "Gujarat"),
}

CITY_DEMAND_MULTIPLIERS = {
    "Mumbai": 1.6, "Delhi": 1.5, "Bengaluru": 1.4, "Hyderabad": 1.2,
    "Chennai": 1.1, "Pune": 1.0, "Ahmedabad": 0.9, "Jaipur": 0.85,
    "Lucknow": 0.80, "Kochi": 0.75, "Kolkata": 1.1, "Surat": 0.9,
}

STATION_NAME_PATTERNS = [
    "{city} Central Hub", "{city} North", "{city} South", "{city} East",
    "{city} West", "{city} Airport", "{city} Tech Park", "{city} Market",
    "{city} Station Rd", "{city} Phase {n}", "{city} Sector {n}",
]

CHEMISTRY_DISTRIBUTION = {
    "LFP": 0.60, "NMC": 0.25, "LTO": 0.10, "LMFP": 0.05,
}

FLEET_TYPE_DISTRIBUTION = {"2W": 0.65, "3W": 0.30, "LCV": 0.05}


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def generate_stations(n_stations: int = 120) -> pd.DataFrame:
    logger.info("Generating %d stations...", n_stations)
    records = []
    cities = list(CITY_COORDINATES.keys())
    per_city = max(1, n_stations // len(cities))
    remainder = n_stations - per_city * len(cities)

    station_idx = 0
    for i, city in enumerate(cities):
        lat, lon, state = CITY_COORDINATES[city]
        count = per_city + (1 if i < remainder else 0)
        for j in range(count):
            pattern = STATION_NAME_PATTERNS[j % len(STATION_NAME_PATTERNS)]
            name = pattern.format(city=city, n=j + 1)
            capacity = int(rng.integers(60, 250))
            inventory = int(rng.integers(int(capacity * 0.3), int(capacity * 0.9)))
            records.append({
                "station_id": str(uuid.uuid4()),
                "name": name,
                "city": city,
                "state": state,
                "latitude": lat + rng.uniform(-0.08, 0.08),
                "longitude": lon + rng.uniform(-0.08, 0.08),
                "capacity": capacity,
                "inventory_count": inventory,
                "charging_slots": max(10, capacity // 4),
                "status": rng.choice(
                    ["operational", "operational", "operational", "degraded", "offline"],
                    p=[0.80, 0.0, 0.0, 0.12, 0.08],
                ),
                "operator_name": f"SUN Mobility Ops {city[:3].upper()}",
                "pincode": fake.postcode(),
                "created_at": datetime.utcnow() - timedelta(days=int(rng.integers(180, 730))),
                "updated_at": datetime.utcnow(),
                "last_outage_at": (
                    datetime.utcnow() - timedelta(days=int(rng.integers(1, 30)))
                    if rng.random() < 0.15 else None
                ),
            })
            station_idx += 1

    return pd.DataFrame(records)


def generate_batteries(n_batteries: int = 5000, stations_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    logger.info("Generating %d batteries...", n_batteries)
    chemistry_choices = list(CHEMISTRY_DISTRIBUTION.keys())
    chemistry_weights = list(CHEMISTRY_DISTRIBUTION.values())

    station_ids = stations_df["station_id"].tolist() if stations_df is not None else [None]
    records = []

    for _ in range(n_batteries):
        chemistry = rng.choice(chemistry_choices, p=chemistry_weights)
        mfg_date = date.today() - timedelta(days=int(rng.integers(30, 1460)))
        age_days = (date.today() - mfg_date).days
        cycle_count = int(age_days * rng.uniform(0.5, 2.0))
        cycle_count = min(cycle_count, 2000)

        # SOH degrades with cycles and time; LFP degrades slower
        base_degradation = {"LFP": 0.0003, "NMC": 0.0004, "LTO": 0.0002, "LMFP": 0.00035}
        soh = max(0.55, 1.0 - base_degradation[chemistry] * cycle_count + rng.normal(0, 0.02))
        soh = float(np.clip(soh, 0.55, 1.0))

        avg_temp = float(rng.normal(28.0, 4.0))
        peak_temp = avg_temp + float(rng.uniform(5, 20))
        thermal_stress = float(np.clip((avg_temp - 20.0) / 30.0, 0.0, 1.0))

        status_weights = [0.75, 0.10, 0.08, 0.04, 0.03]
        status = rng.choice(["active", "charging", "in_transit", "maintenance", "retired"], p=status_weights)

        replacement_risk = _compute_risk(soh, cycle_count, thermal_stress, age_days)

        records.append({
            "battery_id": str(uuid.uuid4()),
            "manufacturing_date": mfg_date,
            "chemistry_type": chemistry,
            "cycle_count": cycle_count,
            "current_health": round(soh, 4),
            "nominal_capacity_kwh": float(rng.choice([1.5, 2.0, 3.0, 4.0])),
            "current_station_id": rng.choice(station_ids) if status in ["active", "charging"] else None,
            "status": status,
            "thermal_stress_score": round(thermal_stress, 4),
            "replacement_risk": replacement_risk,
            "avg_temperature": round(avg_temp, 2),
            "peak_temperature": round(peak_temp, 2),
            "last_swap_at": datetime.utcnow() - timedelta(hours=int(rng.integers(1, 72))),
            "created_at": datetime.combine(mfg_date, datetime.min.time()),
            "updated_at": datetime.utcnow(),
        })

    return pd.DataFrame(records)


def _compute_risk(soh: float, cycles: int, thermal: float, age_days: int) -> str:
    score = 0.0
    if soh < 0.70: score += 40
    elif soh < 0.80: score += 20
    if cycles > 1500: score += 30
    elif cycles > 1000: score += 15
    if thermal > 0.7: score += 20
    elif thermal > 0.4: score += 10
    if age_days > 1460: score += 10

    if score >= 70: return "critical"
    if score >= 40: return "high"
    if score >= 20: return "moderate"
    return "low"


def generate_vehicles(n_vehicles: int = 2500) -> pd.DataFrame:
    logger.info("Generating %d vehicles...", n_vehicles)
    fleet_types = list(FLEET_TYPE_DISTRIBUTION.keys())
    fleet_weights = list(FLEET_TYPE_DISTRIBUTION.values())
    cities = list(CITY_COORDINATES.keys())
    records = []

    for _ in range(n_vehicles):
        city = rng.choice(cities)
        fleet_type = rng.choice(fleet_types, p=fleet_weights)
        total_swaps = int(rng.integers(10, 1500))
        created_days_ago = int(rng.integers(30, 730))
        avg_daily = round(total_swaps / max(created_days_ago, 1), 2)

        records.append({
            "vehicle_id": str(uuid.uuid4()),
            "fleet_type": fleet_type,
            "region": CITY_COORDINATES[city][2],
            "city": city,
            "operator_id": str(uuid.uuid4()),
            "registration_number": f"{city[:2].upper()}{rng.integers(10, 99):02d}{rng.integers(1000, 9999):04d}",
            "status": rng.choice(["active", "inactive", "maintenance"], p=[0.82, 0.12, 0.06]),
            "total_swaps": total_swaps,
            "total_distance_km": round(total_swaps * rng.uniform(40, 120), 1),
            "avg_daily_swaps": avg_daily,
            "last_swap_at": datetime.utcnow() - timedelta(hours=int(rng.integers(1, 168))),
            "created_at": datetime.utcnow() - timedelta(days=created_days_ago),
        })

    return pd.DataFrame(records)


def _hour_weight(hour: int) -> float:
    """Demand multiplier by hour — peaks in morning commute and evening."""
    if 7 <= hour <= 10:
        return 2.2
    if 11 <= hour <= 13:
        return 1.3
    if 14 <= hour <= 16:
        return 1.0
    if 17 <= hour <= 20:
        return 2.5
    if 21 <= hour <= 22:
        return 1.4
    return 0.4


def generate_swap_events(
    stations_df: pd.DataFrame,
    batteries_df: pd.DataFrame,
    vehicles_df: pd.DataFrame,
    n_events: int = 500_000,
    start_date: date = None,
    end_date: date = None,
) -> pd.DataFrame:
    if start_date is None:
        start_date = date.today() - timedelta(days=365)
    if end_date is None:
        end_date = date.today()

    logger.info("Generating %d swap events (%s → %s)...", n_events, start_date, end_date)

    active_batteries = batteries_df[batteries_df["current_health"] >= 0.65]["battery_id"].tolist()
    active_vehicles = vehicles_df[vehicles_df["status"] == "active"]["vehicle_id"].tolist()
    operational_stations = stations_df[stations_df["status"] == "operational"]["station_id"].tolist()

    total_days = (end_date - start_date).days
    records = []

    for _ in range(n_events):
        day_offset = int(rng.integers(0, total_days))
        swap_date = start_date + timedelta(days=day_offset)

        hour = _weighted_hour_sample()
        minute = int(rng.integers(0, 60))
        timestamp = datetime(swap_date.year, swap_date.month, swap_date.day, hour, minute)

        station_id = rng.choice(operational_stations)
        city = stations_df[stations_df["station_id"] == station_id]["city"].values[0]
        city_multiplier = CITY_DEMAND_MULTIPLIERS.get(city, 1.0)

        # seasonal demand: higher in summer (May-Aug), lower in winter (Dec-Jan)
        month = swap_date.month
        seasonal = 1.0 + 0.2 * math.sin(math.pi * (month - 1) / 6)

        battery_in = rng.choice(active_batteries)
        battery_out = rng.choice(active_batteries)
        while battery_out == battery_in:
            battery_out = rng.choice(active_batteries)

        soh_at_swap = float(rng.uniform(0.70, 0.98))
        duration = int(rng.normal(90, 30))
        duration = max(30, min(300, duration))

        capacity_kwh = 2.0
        energy = round(capacity_kwh * rng.uniform(0.6, 0.95), 3)
        revenue = round(energy * rng.uniform(12, 18), 2)

        is_anomalous = rng.random() < 0.03  # 3% anomaly rate
        anomaly_score = float(rng.uniform(0.6, 1.0)) if is_anomalous else float(rng.uniform(0.0, 0.3))

        outcome_weights = [0.94, 0.02, 0.01, 0.015, 0.015]
        outcome = rng.choice(
            ["success", "failed_inventory", "failed_station_offline", "failed_battery_health", "cancelled"],
            p=outcome_weights,
        )

        records.append({
            "event_id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "station_id": station_id,
            "battery_in_id": battery_in,
            "battery_out_id": battery_out,
            "vehicle_id": rng.choice(active_vehicles),
            "duration_seconds": duration,
            "energy_delivered_kwh": energy,
            "outcome": outcome,
            "revenue_inr": revenue if outcome == "success" else 0.0,
            "soh_at_swap": round(soh_at_swap, 4),
            "is_anomalous": bool(is_anomalous),
            "anomaly_score": round(anomaly_score, 4),
            "created_at": timestamp,
        })

    df = pd.DataFrame(records)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    logger.info("Generated %d swap events", len(df))
    return df


def _weighted_hour_sample() -> int:
    weights = [_hour_weight(h) for h in range(24)]
    total = sum(weights)
    probs = [w / total for w in weights]
    return rng.choice(range(24), p=probs)


def save_datasets(output_dir: str = "data/raw") -> dict[str, str]:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    logger.info("=== Generating full synthetic dataset ===")
    stations = generate_stations(120)
    batteries = generate_batteries(5000, stations)
    vehicles = generate_vehicles(2500)
    swaps = generate_swap_events(stations, batteries, vehicles, n_events=500_000)

    paths = {}
    for name, df in [("stations", stations), ("batteries", batteries),
                     ("vehicles", vehicles), ("swap_events", swaps)]:
        path = f"{output_dir}/{name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        paths[name] = path
        logger.info("  Saved %s: %d rows → %s", name, len(df), path)

    logger.info("=== Dataset generation complete ===")
    return paths


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    save_datasets()
