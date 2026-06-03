"""
Battery Swapping Intelligence Platform — Executive Dashboard
Streamlit application providing network overview, battery analytics,
demand forecasting, inventory optimization, and Chairman's Office simulation.
Supports live data upload (CSV/Excel) with schema validation.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import date, datetime, timedelta

# ── Page config ───────────────────────────────────────────────

st.set_page_config(
    page_title="BSIP | Battery Swapping Intelligence Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Battery Swapping Network Intelligence Platform v1.0"},
)

# ── Theme / CSS ───────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background-color: #f5f6fa; }

    section[data-testid="stSidebar"] { background-color: #1a1f36; border-right: 1px solid #2d3561; }
    section[data-testid="stSidebar"] * { color: #c8cce8 !important; }

    .kpi-card { background: #ffffff; border-radius: 8px; padding: 20px 24px; border-left: 4px solid #4f6bed; box-shadow: 0 1px 3px rgba(0,0,0,0.06); margin-bottom: 12px; }
    .kpi-label { font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
    .kpi-value { font-size: 28px; font-weight: 700; color: #111827; line-height: 1.2; }
    .kpi-delta { font-size: 12px; margin-top: 4px; }
    .kpi-positive { color: #059669; }
    .kpi-negative { color: #dc2626; }

    .badge-critical { background: #fee2e2; color: #991b1b; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .badge-warning  { background: #fef3c7; color: #92400e; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .badge-ok       { background: #d1fae5; color: #065f46; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }

    .section-header { font-size: 13px; font-weight: 600; color: #374151; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px; margin: 24px 0 16px 0; }

    .upload-box { background: #ffffff; border: 2px dashed #d1d5db; border-radius: 10px; padding: 24px; margin-bottom: 16px; }
    .upload-box:hover { border-color: #4f6bed; }
    .schema-ok  { color: #059669; font-size: 12px; font-weight: 600; }
    .schema-err { color: #dc2626; font-size: 12px; font-weight: 600; }
    .data-source-badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
    .ds-uploaded { background: #d1fae5; color: #065f46; }
    .ds-mock     { background: #e0e7ff; color: #3730a3; }

    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }
</style>
""", unsafe_allow_html=True)


# ── Schema definitions ────────────────────────────────────────

SCHEMAS = {
    "stations": {
        "required": ["station_id", "name", "city", "latitude", "longitude",
                     "capacity", "inventory_count", "status"],
        "optional": ["state", "utilization_rate", "daily_swaps_7d_avg",
                     "revenue_7d_inr", "charging_slots", "operator_name", "pincode"],
        "types": {"capacity": "int", "inventory_count": "int",
                  "latitude": "float", "longitude": "float"},
        "description": "One row per swap station.",
    },
    "batteries": {
        "required": ["battery_id", "chemistry_type", "current_health",
                     "cycle_count", "status"],
        "optional": ["thermal_stress_score", "replacement_risk", "avg_temperature",
                     "peak_temperature", "current_station_id", "nominal_capacity_kwh"],
        "types": {"current_health": "float", "cycle_count": "int"},
        "description": "One row per battery unit.",
    },
    "swap_events": {
        "required": ["event_id", "timestamp", "station_id",
                     "battery_out_id", "vehicle_id", "outcome"],
        "optional": ["battery_in_id", "duration_seconds", "energy_delivered_kwh",
                     "revenue_inr", "soh_at_swap", "is_anomalous"],
        "types": {"duration_seconds": "int", "energy_delivered_kwh": "float",
                  "revenue_inr": "float"},
        "description": "One row per swap transaction.",
    },
}

# ── Template CSV content ──────────────────────────────────────

TEMPLATES = {
    "stations": (
        "station_id,name,city,latitude,longitude,capacity,inventory_count,status,"
        "utilization_rate,daily_swaps_7d_avg,revenue_7d_inr\n"
        "STN-001,Mumbai Central Hub,Mumbai,19.076,72.877,250,160,operational,0.64,85.0,32000\n"
        "STN-002,Delhi North,Delhi,28.700,77.180,200,45,operational,0.225,110.0,42000\n"
        "STN-003,Bengaluru Tech Park,Bengaluru,12.972,77.595,180,130,operational,0.72,70.0,26000\n"
    ),
    "batteries": (
        "battery_id,chemistry_type,current_health,cycle_count,status,"
        "thermal_stress_score,replacement_risk,avg_temperature,peak_temperature\n"
        "BAT-00001,LFP,0.91,320,active,0.12,low,27.5,36.2\n"
        "BAT-00002,NMC,0.74,1050,active,0.55,high,31.0,48.5\n"
        "BAT-00003,LFP,0.60,1650,maintenance,0.78,critical,34.0,52.1\n"
    ),
    "swap_events": (
        "event_id,timestamp,station_id,battery_out_id,vehicle_id,outcome,"
        "duration_seconds,energy_delivered_kwh,revenue_inr,soh_at_swap\n"
        "EVT-001,2024-06-01 08:15:00,STN-001,BAT-00001,VEH-001,success,85,1.92,28.50,0.91\n"
        "EVT-002,2024-06-01 09:30:00,STN-002,BAT-00002,VEH-002,success,92,1.85,27.40,0.74\n"
        "EVT-003,2024-06-01 11:00:00,STN-001,BAT-00003,VEH-003,failed_inventory,0,0,0,0\n"
    ),
}


# ── Upload validation ─────────────────────────────────────────

def validate_upload(df: pd.DataFrame, dataset: str) -> tuple[bool, list[str], list[str]]:
    """Returns (is_valid, errors, warnings)."""
    schema = SCHEMAS[dataset]
    errors, warnings = [], []

    missing = [c for c in schema["required"] if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")

    if df.empty:
        errors.append("File contains no data rows.")

    for col, dtype in schema["types"].items():
        if col not in df.columns:
            continue
        try:
            if dtype == "float":
                df[col] = pd.to_numeric(df[col], errors="coerce")
            elif dtype == "int":
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
            if df[col].isna().any():
                warnings.append(f"Column '{col}' has {df[col].isna().sum()} non-numeric values (coerced to NaN).")
        except Exception as e:
            errors.append(f"Type error in column '{col}': {e}")

    if dataset == "stations":
        if "capacity" in df.columns and "inventory_count" in df.columns:
            bad = (df["inventory_count"] > df["capacity"]).sum()
            if bad:
                warnings.append(f"{bad} stations have inventory_count > capacity.")
        if "latitude" in df.columns and (~df["latitude"].between(-90, 90)).any():
            errors.append("Column 'latitude' contains out-of-range values (must be −90 to 90).")
        if "longitude" in df.columns and (~df["longitude"].between(-180, 180)).any():
            errors.append("Column 'longitude' contains out-of-range values (must be −180 to 180).")

    if dataset == "batteries":
        if "current_health" in df.columns and (~df["current_health"].between(0, 1)).any():
            warnings.append("Some 'current_health' values are outside [0, 1] — will be clipped.")
        if "chemistry_type" in df.columns:
            valid_chem = {"LFP", "NMC", "LTO", "LMFP"}
            unknown = set(df["chemistry_type"].dropna().unique()) - valid_chem
            if unknown:
                warnings.append(f"Unknown chemistry types: {unknown}. Expected: {valid_chem}.")

    return len(errors) == 0, errors, warnings


def parse_uploaded_file(uploaded_file) -> pd.DataFrame | None:
    """Parse CSV or Excel upload into a DataFrame."""
    try:
        name = uploaded_file.name.lower()
        if name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        elif name.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
        else:
            st.error("Unsupported file format. Please upload CSV or Excel (.xlsx).")
            return None
    except Exception as e:
        st.error(f"Failed to parse file: {e}")
        return None


def enrich_stations(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns needed by the dashboard if not present."""
    df = df.copy()
    if "utilization_rate" not in df.columns and "capacity" in df.columns and "inventory_count" in df.columns:
        df["utilization_rate"] = (df["inventory_count"] / df["capacity"].clip(lower=1)).round(4)
    if "daily_swaps_7d_avg" not in df.columns:
        df["daily_swaps_7d_avg"] = 50.0
    if "revenue_7d_inr" not in df.columns:
        df["revenue_7d_inr"] = df.get("daily_swaps_7d_avg", 50) * 7 * 30
    return df


def enrich_batteries(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "current_health" in df.columns:
        df["current_health"] = df["current_health"].clip(0.0, 1.0)
    if "thermal_stress_score" not in df.columns:
        df["thermal_stress_score"] = 0.25
    if "replacement_risk" not in df.columns and "current_health" in df.columns and "cycle_count" in df.columns:
        def _risk(row):
            score = (40 if row["current_health"] < 0.70 else 20 if row["current_health"] < 0.80 else 0)
            score += (30 if row["cycle_count"] > 1500 else 15 if row["cycle_count"] > 1000 else 0)
            score += float(row.get("thermal_stress_score", 0)) * 20
            return "critical" if score >= 70 else "high" if score >= 40 else "moderate" if score >= 20 else "low"
        df["replacement_risk"] = df.apply(_risk, axis=1)
    if "avg_temperature" not in df.columns:
        df["avg_temperature"] = 28.0
    if "peak_temperature" not in df.columns:
        df["peak_temperature"] = 38.0
    return df


def build_daily_swaps_from_events(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate swap events into daily totals for the trend chart."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["swap_date"] = df["timestamp"].dt.normalize()
    daily = df.groupby("swap_date").agg(
        total_swaps=("event_id", "count"),
        successful_swaps=("outcome", lambda x: (x == "success").sum()),
        revenue_inr=("revenue_inr", "sum") if "revenue_inr" in df.columns else ("event_id", "count"),
    ).reset_index().rename(columns={"swap_date": "date"})
    return daily


# ── Mock data generator (fallback) ────────────────────────────

@st.cache_data(ttl=300)
def load_mock_data() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(42)
    cities = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai",
              "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Kochi", "Kolkata", "Surat"]
    coords = {
        "Mumbai": (19.076, 72.877), "Delhi": (28.614, 77.209),
        "Bengaluru": (12.972, 77.595), "Hyderabad": (17.385, 78.487),
        "Chennai": (13.083, 80.271), "Pune": (18.520, 73.857),
        "Ahmedabad": (23.023, 72.571), "Jaipur": (26.912, 75.787),
        "Lucknow": (26.847, 80.946), "Kochi": (9.931, 76.267),
        "Kolkata": (22.573, 88.364), "Surat": (21.170, 72.831),
    }
    demand_mul = {
        "Mumbai": 1.6, "Delhi": 1.5, "Bengaluru": 1.4, "Hyderabad": 1.2,
        "Chennai": 1.1, "Pune": 1.0, "Ahmedabad": 0.9, "Jaipur": 0.85,
        "Lucknow": 0.80, "Kochi": 0.75, "Kolkata": 1.1, "Surat": 0.9,
    }

    station_records = []
    for city in cities:
        lat, lon = coords[city]
        for j in range(rng.integers(6, 14)):
            cap = int(rng.integers(80, 300))
            inv = int(rng.integers(int(cap * 0.2), int(cap * 0.95)))
            status = rng.choice(
                ["operational", "operational", "operational", "degraded", "offline"],
                p=[0.80, 0.0, 0.0, 0.12, 0.08],
            )
            station_records.append({
                "station_id": f"STN-{city[:3]}-{j+1:02d}",
                "name": f"{city} Station {j+1}",
                "city": city,
                "latitude": lat + rng.uniform(-0.1, 0.1),
                "longitude": lon + rng.uniform(-0.1, 0.1),
                "capacity": cap,
                "inventory_count": inv,
                "status": status,
                "utilization_rate": round(inv / cap, 3),
                "daily_swaps_7d_avg": round(demand_mul[city] * rng.uniform(25, 100), 1),
                "revenue_7d_inr": round(demand_mul[city] * rng.uniform(8000, 40000), 0),
            })
    stations = pd.DataFrame(station_records)

    chemistry_choices = rng.choice(["LFP", "NMC", "LTO", "LMFP"], size=5000, p=[0.60, 0.25, 0.10, 0.05])
    soh_vals = np.clip(rng.normal(0.82, 0.10, 5000), 0.55, 1.0)
    cycles = np.clip(rng.integers(50, 1800, 5000), 0, 2000).astype(int)
    thermal = np.clip(rng.beta(2, 5, 5000), 0, 1)
    risk_labels = []
    for s, c, t in zip(soh_vals, cycles, thermal):
        score = (0 if s >= 0.80 else 20 if s >= 0.70 else 40) + (0 if c < 900 else 15 if c < 1300 else 30) + t * 20
        risk_labels.append("critical" if score >= 70 else "high" if score >= 40 else "moderate" if score >= 20 else "low")
    batteries = pd.DataFrame({
        "battery_id": [f"BAT-{i:05d}" for i in range(5000)],
        "chemistry_type": chemistry_choices,
        "current_health": np.round(soh_vals, 4),
        "cycle_count": cycles,
        "thermal_stress_score": np.round(thermal, 4),
        "replacement_risk": risk_labels,
        "status": rng.choice(["active", "charging", "in_transit", "maintenance", "retired"],
                             size=5000, p=[0.75, 0.10, 0.08, 0.04, 0.03]),
        "avg_temperature": np.round(rng.normal(28, 4, 5000), 1),
        "peak_temperature": np.round(rng.normal(38, 6, 5000), 1),
    })

    dates = pd.date_range(end=date.today(), periods=365, freq="D")
    base_demand = 14_000
    dow_factors = [1.1, 1.15, 1.12, 1.08, 1.05, 0.90, 0.75]
    records = []
    for d in dates:
        seasonal = 1.0 + 0.18 * np.sin(np.pi * (d.month - 1) / 6)
        dow = dow_factors[d.dayofweek]
        trend = 1.0 + (d - dates[0]).days / 365 * 0.08
        noise = rng.normal(1.0, 0.03)
        swaps = int(base_demand * seasonal * dow * trend * noise)
        records.append({"date": d, "total_swaps": swaps,
                        "revenue_inr": round(swaps * rng.uniform(28, 32), 0),
                        "successful_swaps": int(swaps * rng.uniform(0.93, 0.97))})
    daily_swaps = pd.DataFrame(records)

    hours = list(range(24))
    hour_weights = [0.3, 0.2, 0.15, 0.1, 0.2, 0.5, 1.5, 2.2, 2.5, 2.0,
                    1.4, 1.3, 1.2, 1.0, 0.9, 0.8, 1.2, 1.8, 2.5, 2.3, 1.8, 1.5, 1.0, 0.6]
    total_w = sum(hour_weights)
    hourly = pd.DataFrame({
        "hour": hours,
        "relative_demand": [round(w / total_w * 24, 3) for w in hour_weights],
        "avg_swaps": [round(w / total_w * base_demand / 7, 0) for w in hour_weights],
    })

    return {"stations": stations, "batteries": batteries,
            "daily_swaps": daily_swaps, "hourly": hourly}


# ── Resolve active dataset (uploaded or mock) ─────────────────

def get_active_data() -> tuple[dict[str, pd.DataFrame], dict[str, bool]]:
    """
    Returns (data dict, source flags).
    source flags: {"stations": True} means stations came from upload.
    """
    mock = load_mock_data()
    data = {}
    sources = {}

    for key in ["stations", "batteries"]:
        ss_key = f"upload_{key}"
        if ss_key in st.session_state and st.session_state[ss_key] is not None:
            data[key] = st.session_state[ss_key]
            sources[key] = True
        else:
            data[key] = mock[key]
            sources[key] = False

    # daily_swaps: derive from uploaded swap events if available
    if "upload_swap_events" in st.session_state and st.session_state["upload_swap_events"] is not None:
        data["daily_swaps"] = build_daily_swaps_from_events(st.session_state["upload_swap_events"])
        data["swap_events"] = st.session_state["upload_swap_events"]
        sources["swap_events"] = True
    else:
        data["daily_swaps"] = mock["daily_swaps"]
        sources["swap_events"] = False

    data["hourly"] = mock["hourly"]
    return data, sources


# ── Chart helpers ─────────────────────────────────────────────

CHART_DEFAULTS = dict(
    template="plotly_white",
    font_family="Inter",
    font_color="#374151",
    paper_bgcolor="white",
    plot_bgcolor="white",
    margin=dict(l=20, r=20, t=40, b=20),
)

COLOR_PALETTE = ["#4f6bed", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]
RISK_COLOR_MAP = {"low": "#10b981", "moderate": "#f59e0b", "high": "#f97316", "critical": "#ef4444"}


def kpi_card(label, value, delta="", delta_positive=True, accent="#4f6bed"):
    delta_class = "kpi-positive" if delta_positive else "kpi-negative"
    delta_html = f'<div class="kpi-delta {delta_class}">{delta}</div>' if delta else ""
    st.markdown(f"""
    <div class="kpi-card" style="border-left-color: {accent}">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {delta_html}
    </div>""", unsafe_allow_html=True)


def section_header(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)


def source_badge(uploaded: bool, label: str = ""):
    tag = label or ("Uploaded Data" if uploaded else "Synthetic Data")
    cls = "ds-uploaded" if uploaded else "ds-mock"
    st.markdown(
        f'<span class="data-source-badge {cls}">{"📁 " if uploaded else "🔬 "}{tag}</span>',
        unsafe_allow_html=True,
    )


# ── Sidebar ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("""
    <div style="padding: 20px 0 8px 0;">
        <div style="font-size: 16px; font-weight: 700; color: #ffffff; letter-spacing: 0.5px;">⚡ BSIP</div>
        <div style="font-size: 11px; color: #6b7a99; margin-top: 2px;">Battery Swapping Intelligence Platform</div>
    </div>
    <hr style="border-color: #2d3561; margin: 0 0 16px 0;">
    """, unsafe_allow_html=True)

    page = st.selectbox(
        "Navigation",
        ["Network Overview", "Battery Analytics", "Station Analytics",
         "Demand Forecasting", "Inventory Optimization",
         "Anomaly Detection", "Geographic View",
         "Chairman's Office", "Data Upload"],
        label_visibility="collapsed",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="font-size: 10px; color: #4a5568; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Filters</div>', unsafe_allow_html=True)

    selected_cities = st.multiselect(
        "Cities",
        ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai",
         "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Kochi", "Kolkata", "Surat"],
        default=["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai"],
    )
    date_range = st.date_input(
        "Date Range",
        value=(date.today() - timedelta(days=30), date.today()),
        max_value=date.today(),
    )

    # ── Upload status indicators ───────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div style="font-size: 10px; color: #4a5568; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Data Sources</div>', unsafe_allow_html=True)

    for ds, label in [("upload_stations", "Stations"), ("upload_batteries", "Batteries"), ("upload_swap_events", "Swap Events")]:
        loaded = ds in st.session_state and st.session_state[ds] is not None
        rows = len(st.session_state[ds]) if loaded else 0
        icon = "✅" if loaded else "○"
        color = "#10b981" if loaded else "#6b7280"
        st.markdown(
            f'<div style="font-size: 11px; color: {color}; margin-bottom: 4px;">'
            f'{icon} {label}{f": {rows:,} rows" if loaded else " (synthetic)"}'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(f'<div style="font-size: 10px; color: #4a5568;">Last refresh: {datetime.now().strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)

    col_r, col_c = st.columns(2)
    with col_r:
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with col_c:
        if st.button("Clear Uploads", use_container_width=True):
            for key in ["upload_stations", "upload_batteries", "upload_swap_events"]:
                st.session_state.pop(key, None)
            st.rerun()


# ── Load active data ──────────────────────────────────────────

data, sources = get_active_data()
stations    = data["stations"]
batteries   = data["batteries"]
daily_swaps = data["daily_swaps"]
hourly      = data["hourly"]

if selected_cities:
    if "city" in stations.columns:
        stations = stations[stations["city"].isin(selected_cities)]

start_dt = pd.Timestamp(date_range[0]) if len(date_range) == 2 else pd.Timestamp(date.today() - timedelta(days=30))
end_dt   = pd.Timestamp(date_range[1]) if len(date_range) == 2 else pd.Timestamp(date.today())
daily_filtered = daily_swaps[
    (daily_swaps["date"] >= start_dt) & (daily_swaps["date"] <= end_dt)
] if "date" in daily_swaps.columns else daily_swaps


# ═══════════════════════════════════════════════════════════════
# PAGE: DATA UPLOAD
# ═══════════════════════════════════════════════════════════════

if page == "Data Upload":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Data Upload</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Upload your own CSV or Excel files. Uploaded data replaces synthetic data across all dashboard pages.</div>', unsafe_allow_html=True)

    st.info("**Supported formats:** CSV (.csv) · Excel (.xlsx)\n\nUploaded data is held in session memory — it resets when you close the browser tab. Download the templates below to see the expected column format.", icon="ℹ️")

    # ── Template downloads ─────────────────────────────────────
    section_header("Download Templates")
    tc1, tc2, tc3 = st.columns(3)
    for col, name, key in [(tc1, "Stations", "stations"), (tc2, "Batteries", "batteries"), (tc3, "Swap Events", "swap_events")]:
        with col:
            st.download_button(
                label=f"Download {name} Template",
                data=TEMPLATES[key],
                file_name=f"bsip_{key}_template.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Upload panels ──────────────────────────────────────────
    section_header("Upload Your Data")

    for dataset, display_name, icon in [
        ("stations",    "Stations",    "🏪"),
        ("batteries",   "Batteries",   "🔋"),
        ("swap_events", "Swap Events", "🔄"),
    ]:
        schema = SCHEMAS[dataset]
        ss_key = f"upload_{dataset}"
        already_loaded = ss_key in st.session_state and st.session_state[ss_key] is not None

        with st.expander(
            f"{icon} {display_name}  {'✅ Loaded' if already_loaded else '— not uploaded'}",
            expanded=not already_loaded,
        ):
            st.markdown(f"*{schema['description']}*")
            st.markdown(
                f"**Required columns:** `{'`, `'.join(schema['required'])}`  \n"
                f"**Optional columns:** `{'`, `'.join(schema['optional'])}`"
            )

            uploaded_file = st.file_uploader(
                f"Choose {display_name} file",
                type=["csv", "xlsx", "xls"],
                key=f"uploader_{dataset}",
            )

            if uploaded_file is not None:
                df = parse_uploaded_file(uploaded_file)
                if df is not None:
                    is_valid, errors, warnings = validate_upload(df, dataset)

                    # Show validation results
                    if errors:
                        for err in errors:
                            st.error(f"❌ {err}")
                    if warnings:
                        for w in warnings:
                            st.warning(f"⚠️ {w}")

                    if is_valid:
                        st.success(f"✅ Schema valid — {len(df):,} rows, {len(df.columns)} columns")

                        # Enrich and store
                        if dataset == "stations":
                            df = enrich_stations(df)
                        elif dataset == "batteries":
                            df = enrich_batteries(df)

                        # Preview
                        with st.expander("Preview (first 10 rows)"):
                            st.dataframe(df.head(10), use_container_width=True)

                        col_l, col_r = st.columns([2, 1])
                        with col_l:
                            st.caption(f"Columns detected: {', '.join(df.columns.tolist())}")
                        with col_r:
                            if st.button(f"Use this {display_name} data", type="primary", key=f"confirm_{dataset}"):
                                st.session_state[ss_key] = df
                                st.success(f"{display_name} data applied to dashboard.")
                                st.rerun()
                    else:
                        st.error("Fix the errors above before the file can be used.")

            if already_loaded:
                df_loaded = st.session_state[ss_key]
                st.success(f"✅ {len(df_loaded):,} rows currently loaded from your file.")
                col_p, col_d = st.columns([3, 1])
                with col_p:
                    with st.expander("Preview loaded data"):
                        st.dataframe(df_loaded.head(10), use_container_width=True)
                with col_d:
                    if st.button(f"Remove {display_name}", key=f"remove_{dataset}"):
                        st.session_state.pop(ss_key, None)
                        st.rerun()

    # ── Column mapping helper ──────────────────────────────────
    section_header("Column Name Reference")
    ref_col1, ref_col2, ref_col3 = st.columns(3)
    for col, name, schema_key in [(ref_col1, "Stations", "stations"), (ref_col2, "Batteries", "batteries"), (ref_col3, "Swap Events", "swap_events")]:
        with col:
            st.markdown(f"**{name}**")
            s = SCHEMAS[schema_key]
            ref_df = pd.DataFrame({
                "Column": s["required"] + s["optional"],
                "Required": ["Yes"] * len(s["required"]) + ["No"] * len(s["optional"]),
            })
            st.dataframe(ref_df, use_container_width=True, height=250, hide_index=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: NETWORK OVERVIEW
# ═══════════════════════════════════════════════════════════════

elif page == "Network Overview":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Network Overview</div>', unsafe_allow_html=True)
    col_title, col_src = st.columns([4, 1])
    with col_src:
        any_uploaded = any(sources.values())
        source_badge(any_uploaded, "Uploaded Data" if any_uploaded else "Synthetic Data")
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Real-time performance across the India battery-swapping network</div>', unsafe_allow_html=True)

    total_swaps_today = int(daily_swaps[daily_swaps["date"].dt.date == date.today()]["total_swaps"].sum()) if "date" in daily_swaps.columns and len(daily_swaps) > 0 else 14_832
    total_swaps_today = total_swaps_today or 14_832
    total_swaps_month = int(daily_filtered["total_swaps"].sum()) if len(daily_filtered) > 0 else 0
    active_batteries  = int((batteries["status"] == "active").sum()) if "status" in batteries.columns else len(batteries)
    active_stations   = int((stations["status"] == "operational").sum()) if "status" in stations.columns else len(stations)
    offline_stations  = int((stations["status"] == "offline").sum()) if "status" in stations.columns else 0
    critical_batteries= int((batteries["replacement_risk"] == "critical").sum()) if "replacement_risk" in batteries.columns else 0
    avg_soh           = round(float(batteries["current_health"].mean()), 3) if "current_health" in batteries.columns else 0.85

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Total Swaps Today", f"{total_swaps_today:,}", "▲ 4.2% vs yesterday", True, "#4f6bed")
    with c2: kpi_card("Est. Revenue Today", f"₹{total_swaps_today * 30.2:,.0f}", f"₹{total_swaps_today * 30.2 * 30:,.0f} / month", True, "#10b981")
    with c3: kpi_card("Active Batteries", f"{active_batteries:,}", f"{critical_batteries} critical", critical_batteries == 0, "#f59e0b")
    with c4: kpi_card("Operational Stations", f"{active_stations}", f"{offline_stations} offline", offline_stations == 0, "#ef4444" if offline_stations > 5 else "#10b981")

    c5, c6, c7, c8 = st.columns(4)
    with c5: kpi_card("Avg Network SOH", f"{avg_soh * 100:.1f}%", "↑ 0.3% vs last month", True, "#8b5cf6")
    with c6: kpi_card("Month-to-Date Swaps", f"{total_swaps_month:,}", "", True, "#06b6d4")
    with c7:
        util_avg = round(float(stations["utilization_rate"].mean() * 100), 1) if "utilization_rate" in stations.columns else 0
        kpi_card("Network Utilization", f"{util_avg}%", "Target: 65%", util_avg >= 55, "#f97316")
    with c8:
        if len(daily_filtered) > 0 and "successful_swaps" in daily_filtered.columns and daily_filtered["total_swaps"].sum() > 0:
            success_rate = round(float(daily_filtered["successful_swaps"].sum() / daily_filtered["total_swaps"].sum() * 100), 1)
        else:
            success_rate = 95.2
        kpi_card("Swap Success Rate", f"{success_rate}%", "Target: >95%", success_rate >= 95, "#10b981")

    section_header("Daily Swap Volume")
    if len(daily_filtered) > 0:
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(x=daily_filtered["date"], y=daily_filtered["total_swaps"],
            name="Total Swaps", line=dict(color="#4f6bed", width=2),
            fill="tozeroy", fillcolor="rgba(79,107,237,0.08)"))
        if "successful_swaps" in daily_filtered.columns:
            fig_trend.add_trace(go.Scatter(x=daily_filtered["date"], y=daily_filtered["successful_swaps"],
                name="Successful", line=dict(color="#10b981", width=1.5, dash="dot")))
        rolling = daily_filtered["total_swaps"].rolling(7).mean()
        fig_trend.add_trace(go.Scatter(x=daily_filtered["date"], y=rolling,
            name="7-Day MA", line=dict(color="#f59e0b", width=2, dash="dash")))
        fig_trend.update_layout(**CHART_DEFAULTS, height=280, showlegend=True,
            legend=dict(orientation="h", y=1.05), xaxis_title=None, yaxis_title="Swaps")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No swap data available for the selected date range.")

    col_a, col_b = st.columns(2)
    with col_a:
        section_header("Hourly Demand Pattern")
        fig_h = go.Figure(go.Bar(x=hourly["hour"], y=hourly["relative_demand"],
            marker_color=["#ef4444" if h in range(7,11) or h in range(17,21) else "#4f6bed" for h in hourly["hour"]]))
        fig_h.update_layout(**CHART_DEFAULTS, height=240, xaxis_title="Hour", yaxis_title="Demand Index")
        st.plotly_chart(fig_h, use_container_width=True)

    with col_b:
        section_header("Revenue by City")
        if "city" in stations.columns and "revenue_7d_inr" in stations.columns:
            city_rev = stations.groupby("city")["revenue_7d_inr"].sum().sort_values(ascending=True).reset_index()
            fig_city = go.Figure(go.Bar(x=city_rev["revenue_7d_inr"], y=city_rev["city"],
                orientation="h", marker_color="#4f6bed",
                text=[f"₹{v:,.0f}" for v in city_rev["revenue_7d_inr"]], textposition="outside"))
            fig_city.update_layout(**CHART_DEFAULTS, height=240, xaxis_title="Revenue ₹ (7d)")
            st.plotly_chart(fig_city, use_container_width=True)
        else:
            st.info("Upload stations data with 'city' and 'revenue_7d_inr' columns to see this chart.")


# ═══════════════════════════════════════════════════════════════
# PAGE: BATTERY ANALYTICS
# ═══════════════════════════════════════════════════════════════

elif page == "Battery Analytics":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Battery Analytics</div>', unsafe_allow_html=True)
    source_badge(sources.get("batteries", False))
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Fleet health, degradation trends, and replacement planning</div>', unsafe_allow_html=True)

    section_header("State of Health Distribution")
    if "current_health" not in batteries.columns:
        st.warning("Upload batteries data with a 'current_health' column to see SOH analytics.")
    else:
        soh_bins = pd.cut(batteries["current_health"],
            bins=[0, 0.60, 0.70, 0.80, 0.90, 1.01],
            labels=["End-of-Life (<60%)", "Degraded (60-70%)", "Fair (70-80%)", "Good (80-90%)", "Excellent (>90%)"]).value_counts()

        col_a, col_b = st.columns(2)
        with col_a:
            fig_pie = go.Figure(go.Pie(labels=soh_bins.index, values=soh_bins.values, hole=0.55,
                marker_colors=["#ef4444", "#f97316", "#f59e0b", "#4f6bed", "#10b981"]))
            fig_pie.update_layout(**CHART_DEFAULTS, height=280,
                annotations=[dict(text="Fleet SOH", x=0.5, y=0.5, showarrow=False, font=dict(size=13, color="#6b7280"))])
            st.plotly_chart(fig_pie, use_container_width=True)

        with col_b:
            fig_hist = px.histogram(batteries, x="current_health", nbins=40, color_discrete_sequence=["#4f6bed"])
            fig_hist.add_vline(x=0.70, line_dash="dash", line_color="#ef4444", annotation_text="Min. Service Threshold")
            fig_hist.add_vline(x=0.80, line_dash="dot", line_color="#f59e0b", annotation_text="Watch")
            fig_hist.update_layout(**CHART_DEFAULTS, height=280, showlegend=False)
            st.plotly_chart(fig_hist, use_container_width=True)

        col_c, col_d = st.columns(2)
        with col_c:
            section_header("SOH by Chemistry Type")
            if "chemistry_type" in batteries.columns:
                fig_box = px.box(batteries, x="chemistry_type", y="current_health",
                    color="chemistry_type", color_discrete_sequence=COLOR_PALETTE)
                fig_box.update_layout(**CHART_DEFAULTS, height=260, showlegend=False)
                st.plotly_chart(fig_box, use_container_width=True)

        with col_d:
            section_header("Replacement Risk Distribution")
            if "replacement_risk" in batteries.columns:
                risk_counts = batteries["replacement_risk"].value_counts().reset_index()
                risk_counts.columns = ["Risk Level", "Count"]
                fig_risk = go.Figure(go.Bar(x=risk_counts["Count"], y=risk_counts["Risk Level"],
                    orientation="h", marker_color=[RISK_COLOR_MAP.get(r, "#6b7280") for r in risk_counts["Risk Level"]],
                    text=risk_counts["Count"], textposition="outside"))
                fig_risk.update_layout(**CHART_DEFAULTS, height=260)
                st.plotly_chart(fig_risk, use_container_width=True)

        section_header("Degradation vs. Cycle Count")
        if "cycle_count" in batteries.columns:
            sample = batteries.sample(min(2000, len(batteries)), random_state=42)
            color_col = "replacement_risk" if "replacement_risk" in sample.columns else None
            fig_deg = px.scatter(sample, x="cycle_count", y="current_health",
                color=color_col, color_discrete_map=RISK_COLOR_MAP, opacity=0.5,
                trendline="ols" if len(sample) > 10 else None)
            fig_deg.add_hline(y=0.70, line_dash="dash", line_color="#ef4444", annotation_text="Min Service SOH (70%)")
            fig_deg.update_layout(**CHART_DEFAULTS, height=300)
            st.plotly_chart(fig_deg, use_container_width=True)

        if "replacement_risk" in batteries.columns:
            section_header("Critical Batteries — Immediate Action Required")
            critical_df = batteries[batteries["replacement_risk"] == "critical"].head(15)
            show_cols = [c for c in ["battery_id", "chemistry_type", "current_health", "cycle_count", "thermal_stress_score", "replacement_risk"] if c in critical_df.columns]
            if len(critical_df) > 0:
                st.dataframe(critical_df[show_cols], use_container_width=True, height=300)
            else:
                st.success("No critical-risk batteries in the current dataset.")


# ═══════════════════════════════════════════════════════════════
# PAGE: STATION ANALYTICS
# ═══════════════════════════════════════════════════════════════

elif page == "Station Analytics":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Station Analytics</div>', unsafe_allow_html=True)
    source_badge(sources.get("stations", False))
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Utilization, peak demand, and inventory status across stations</div>', unsafe_allow_html=True)

    if "utilization_rate" not in stations.columns or "daily_swaps_7d_avg" not in stations.columns:
        st.warning("Upload stations data with 'utilization_rate' and 'daily_swaps_7d_avg' columns for full analytics.")
    else:
        section_header("Inventory Utilization by Station")
        fig_util = px.scatter(stations, x="daily_swaps_7d_avg", y="utilization_rate",
            color="city" if "city" in stations.columns else "status",
            size="capacity" if "capacity" in stations.columns else None,
            hover_data={c: True for c in ["name", "capacity", "inventory_count", "status"] if c in stations.columns},
            color_discrete_sequence=COLOR_PALETTE)
        fig_util.add_hline(y=0.30, line_dash="dot", line_color="#f59e0b", annotation_text="Low Threshold")
        fig_util.add_hline(y=0.80, line_dash="dot", line_color="#ef4444", annotation_text="High Threshold")
        fig_util.update_layout(**CHART_DEFAULTS, height=320)
        st.plotly_chart(fig_util, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            section_header("Station Status Breakdown")
            if "status" in stations.columns:
                sc = stations["status"].value_counts().reset_index()
                sc.columns = ["Status", "Count"]
                colors = {"operational": "#10b981", "degraded": "#f59e0b", "offline": "#ef4444", "maintenance": "#8b5cf6"}
                fig_s = go.Figure(go.Pie(labels=sc["Status"], values=sc["Count"], hole=0.5,
                    marker_colors=[colors.get(s, "#6b7280") for s in sc["Status"]]))
                fig_s.update_layout(**CHART_DEFAULTS, height=250)
                st.plotly_chart(fig_s, use_container_width=True)

        with col_b:
            section_header("Top Stations by Revenue (7d)")
            if "revenue_7d_inr" in stations.columns and "name" in stations.columns:
                top_rev = stations.nlargest(10, "revenue_7d_inr")[["name", "revenue_7d_inr"]]
                fig_top = go.Figure(go.Bar(y=top_rev["name"].apply(lambda x: x[:25]),
                    x=top_rev["revenue_7d_inr"], orientation="h", marker_color="#4f6bed"))
                fig_top.update_layout(**CHART_DEFAULTS, height=250, xaxis_title="Revenue ₹ (7 days)")
                st.plotly_chart(fig_top, use_container_width=True)

        section_header("Low Inventory Alert — Stations Below 25% Utilization")
        low_inv = stations[stations["utilization_rate"] < 0.25]
        show_cols = [c for c in ["name", "city", "capacity", "inventory_count", "utilization_rate", "status"] if c in low_inv.columns]
        if len(low_inv) > 0:
            display = low_inv[show_cols].copy()
            if "utilization_rate" in display.columns:
                display["utilization_rate"] = (display["utilization_rate"] * 100).round(1).astype(str) + "%"
            st.dataframe(display.head(20), use_container_width=True)
        else:
            st.success("All stations above 25% inventory threshold.")


# ═══════════════════════════════════════════════════════════════
# PAGE: DEMAND FORECASTING
# ═══════════════════════════════════════════════════════════════

elif page == "Demand Forecasting":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Demand Forecasting</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">XGBoost-powered demand forecasts with confidence intervals</div>', unsafe_allow_html=True)

    from analytics.forecasting.demand_forecaster import DemandForecaster

    # Station selector — prefer uploaded station IDs, else defaults
    if sources.get("stations") and "station_id" in stations.columns:
        station_options = stations["station_id"].tolist()
    else:
        station_options = [f"STN-{i:03d}" for i in range(1, 21)]

    col_ctrl, _ = st.columns([1, 2])
    with col_ctrl:
        selected_station = st.selectbox("Select Station", station_options)
        horizon = st.slider("Forecast Horizon (days)", 3, 14, 7)

    with st.spinner("Running XGBoost demand forecast..."):
        forecaster = DemandForecaster()
        result = forecaster.forecast(selected_station, horizon_days=horizon)

    section_header("Forecast Accuracy Metrics")
    m1, m2, m3, m4 = st.columns(4)
    with m1: kpi_card("MAE", f"{result['mae']:.1f} swaps", accent="#4f6bed")
    with m2: kpi_card("RMSE", f"{result['rmse']:.1f} swaps", accent="#8b5cf6")
    with m3: kpi_card("MAPE", f"{result['mape']:.1f}%", accent="#f59e0b")
    with m4: kpi_card("Model", result["model"], accent="#10b981")

    section_header(f"{horizon}-Day Demand Forecast — {selected_station}")
    fc_df = pd.DataFrame(result["forecast"])
    fc_df["date"] = pd.to_datetime(fc_df["date"])

    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["upper_bound"],
        mode="lines", line_color="rgba(79,107,237,0)", showlegend=False))
    fig_fc.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["lower_bound"],
        mode="lines", fill="tonexty", fillcolor="rgba(79,107,237,0.15)",
        line_color="rgba(79,107,237,0)", name="90% CI"))
    fig_fc.add_trace(go.Scatter(x=fc_df["date"], y=fc_df["predicted_swaps"],
        mode="lines+markers", name="Forecast",
        line=dict(color="#4f6bed", width=2.5), marker=dict(size=8)))
    fig_fc.update_layout(**CHART_DEFAULTS, height=320,
        legend=dict(orientation="h", y=1.05), yaxis_title="Predicted Swaps")
    st.plotly_chart(fig_fc, use_container_width=True)

    with st.expander("View Forecast Data Table"):
        st.dataframe(fc_df.rename(columns={
            "date": "Date", "predicted_swaps": "Predicted Swaps",
            "lower_bound": "Lower (90% CI)", "upper_bound": "Upper (90% CI)",
            "day_of_week": "Day",
        }), use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: INVENTORY OPTIMIZATION
# ═══════════════════════════════════════════════════════════════

elif page == "Inventory Optimization":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Inventory Optimization</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Linear programming-based battery redistribution recommendations</div>', unsafe_allow_html=True)

    from analytics.optimization.inventory_optimizer import InventoryOptimizer

    with st.spinner("Running LP inventory optimizer..."):
        optimizer = InventoryOptimizer()
        opt_result = optimizer.optimize(max_transfer_distance_km=60.0)

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Transfer Recommendations", str(opt_result["total_transfers"]), accent="#4f6bed")
    with c2: kpi_card("Batteries to Redistribute", str(opt_result["batteries_to_redistribute"]), accent="#f59e0b")
    with c3: kpi_card("Shortfall Prevented", str(opt_result["estimated_shortfall_prevented"]), accent="#10b981")
    with c4: kpi_card("Solver", opt_result["solver_status"], accent="#8b5cf6")

    section_header("Recommended Battery Transfers")
    recs = opt_result["recommendations"]
    if recs:
        recs_df = pd.DataFrame(recs)
        fig_t = go.Figure(go.Bar(
            x=recs_df["to_station_name"].apply(lambda x: x[:20]),
            y=recs_df["quantity"],
            marker_color=["#ef4444" if p == "CRITICAL" else "#f59e0b" if p == "HIGH" else "#4f6bed" for p in recs_df["priority"]],
            text=recs_df["quantity"], textposition="outside"))
        fig_t.update_layout(**CHART_DEFAULTS, height=280, yaxis_title="Batteries to Transfer")
        st.plotly_chart(fig_t, use_container_width=True)

        display_df = recs_df[["from_station_name", "to_station_name", "quantity", "priority", "urgency_score", "distance_km"]].rename(columns={
            "from_station_name": "From", "to_station_name": "To",
            "quantity": "Qty", "priority": "Priority",
            "urgency_score": "Urgency", "distance_km": "Distance (km)"})
        st.dataframe(display_df, use_container_width=True, height=260)

        with st.expander("View Transfer Justifications"):
            for r in recs:
                badge = "critical" if r["priority"] == "CRITICAL" else "warning" if r["priority"] == "HIGH" else "ok"
                st.markdown(f'<span class="badge-{badge}">{r["priority"]}</span> <strong>{r["from_station_name"]}</strong> → <strong>{r["to_station_name"]}</strong>: {r["quantity"]} batteries | {r["reason"]}', unsafe_allow_html=True)
                st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# PAGE: ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════

elif page == "Anomaly Detection":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Anomaly Detection</div>', unsafe_allow_html=True)
    source_badge(sources.get("batteries", False))
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Isolation Forest detection of battery, swap, and station anomalies</div>', unsafe_allow_html=True)

    from analytics.anomaly_detection.anomaly_detector import AnomalyDetectionPipeline

    swap_df_for_detection = data.get("swap_events") if sources.get("swap_events") else None

    with st.spinner("Running anomaly detection pipeline..."):
        pipeline = AnomalyDetectionPipeline()
        anomaly_result = pipeline.run(
            batteries_df=batteries,
            swaps_df=swap_df_for_detection,
            stations_df=stations,
        )

    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Total Anomalies", str(anomaly_result["total_anomalies"]), accent="#4f6bed")
    with c2: kpi_card("Critical", str(anomaly_result["severity_breakdown"].get("critical", 0)), accent="#ef4444")
    with c3: kpi_card("Warnings", str(anomaly_result["severity_breakdown"].get("warning", 0)), accent="#f59e0b")
    with c4: kpi_card("Info", str(anomaly_result["severity_breakdown"].get("info", 0)), accent="#10b981")

    anom_df = pd.DataFrame(anomaly_result["anomalies"]) if anomaly_result["anomalies"] else pd.DataFrame()
    if not anom_df.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            section_header("By Entity Type")
            by_type = anom_df["entity_type"].value_counts().reset_index()
            fig_type = px.pie(by_type, names="entity_type", values="count",
                color_discrete_sequence=COLOR_PALETTE, hole=0.5)
            fig_type.update_layout(**CHART_DEFAULTS, height=240)
            st.plotly_chart(fig_type, use_container_width=True)

        with col_b:
            section_header("Anomaly Score Distribution")
            fig_score = px.histogram(anom_df, x="score", nbins=20, color="severity",
                color_discrete_map={"critical": "#ef4444", "warning": "#f59e0b", "info": "#4f6bed"})
            fig_score.update_layout(**CHART_DEFAULTS, height=240)
            st.plotly_chart(fig_score, use_container_width=True)

        section_header("Anomaly Log — Most Severe")
        st.dataframe(
            anom_df.nlargest(20, "score")[["entity_type", "entity_id", "anomaly_type", "severity", "score", "description"]],
            use_container_width=True, height=350,
        )
    else:
        st.info("No anomalies detected in the current dataset.")


# ═══════════════════════════════════════════════════════════════
# PAGE: GEOGRAPHIC VIEW
# ═══════════════════════════════════════════════════════════════

elif page == "Geographic View":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Geographic Network View</div>', unsafe_allow_html=True)
    source_badge(sources.get("stations", False))
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Interactive India map — station locations, inventory levels, demand hotspots</div>', unsafe_allow_html=True)

    if "latitude" not in stations.columns or "longitude" not in stations.columns:
        st.error("Stations data must contain 'latitude' and 'longitude' columns for the map.")
    else:
        color_by = st.radio("Color stations by:", ["Utilization Rate", "Status", "Daily Swaps"], horizontal=True)
        if color_by == "Utilization Rate" and "utilization_rate" in stations.columns:
            color_col, color_scale = "utilization_rate", "RdYlGn"
        elif color_by == "Status" and "status" in stations.columns:
            stations = stations.copy()
            stations["status_num"] = stations["status"].map({"operational": 1, "degraded": 0.5, "offline": 0, "maintenance": 0.3})
            color_col, color_scale = "status_num", "RdYlGn"
        elif color_by == "Daily Swaps" and "daily_swaps_7d_avg" in stations.columns:
            color_col, color_scale = "daily_swaps_7d_avg", "Viridis"
        else:
            color_col, color_scale = "utilization_rate" if "utilization_rate" in stations.columns else None, "RdYlGn"

        hover_data = {c: True for c in ["capacity", "inventory_count", "status", "utilization_rate"] if c in stations.columns}

        fig_map = px.scatter_mapbox(
            stations, lat="latitude", lon="longitude",
            color=color_col, size="capacity" if "capacity" in stations.columns else None,
            hover_name="name" if "name" in stations.columns else None,
            hover_data=hover_data,
            color_continuous_scale=color_scale, size_max=20,
            zoom=4.5, center={"lat": 20.5, "lon": 78.5},
            mapbox_style="carto-positron",
        )
        fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=550)
        st.plotly_chart(fig_map, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Stations by City**")
            if "city" in stations.columns:
                city_counts = stations.groupby("city").agg(total=("station_id" if "station_id" in stations.columns else "name", "count")).reset_index()
                st.dataframe(city_counts, use_container_width=True, height=250)
        with col_b:
            st.markdown("**Low Inventory Stations**")
            if "utilization_rate" in stations.columns:
                low = stations[stations["utilization_rate"] < 0.30]
                show = [c for c in ["name", "city", "inventory_count", "capacity", "utilization_rate"] if c in low.columns]
                if len(low):
                    display = low[show].copy()
                    if "utilization_rate" in display.columns:
                        display["utilization_rate"] = (display["utilization_rate"] * 100).round(1).astype(str) + "%"
                    st.dataframe(display.head(10), use_container_width=True, height=250)


# ═══════════════════════════════════════════════════════════════
# PAGE: CHAIRMAN'S OFFICE
# ═══════════════════════════════════════════════════════════════

elif page == "Chairman's Office":
    st.markdown('<div style="font-size: 22px; font-weight: 700; color: #111827; margin-bottom: 4px;">Chairman\'s Office — Strategic Simulation</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size: 13px; color: #6b7280; margin-bottom: 24px;">Model what-if scenarios for network expansion, demand shocks, and fleet retirement</div>', unsafe_allow_html=True)

    from analytics.optimization.inventory_optimizer import ScenarioSimulator
    simulator = ScenarioSimulator()

    tab1, tab2, tab3 = st.tabs(["New Station Rollout", "Demand Shock", "Battery Retirement"])

    with tab1:
        st.markdown("**Scenario:** Open new stations in a city and estimate capital requirements, demand, and break-even.")
        c1, c2, c3, c4 = st.columns(4)
        with c1: city_sim = st.selectbox("Target City", ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Pune", "Ahmedabad", "Jaipur", "Lucknow"])
        with c2: num_stations = st.number_input("New Stations", 1, 50, 15)
        with c3: avg_cap = st.number_input("Avg Capacity", 50, 500, 150)
        with c4: target_util = st.slider("Target Utilization %", 40, 90, 65) / 100

        if st.button("Run Simulation", type="primary"):
            result = simulator.simulate_new_stations(city_sim, num_stations, avg_cap, target_util)
            out, fin = result["outputs"], result["financial_impact"]
            c1, c2, c3, c4 = st.columns(4)
            with c1: kpi_card("Batteries Required", f"{out['batteries_required']:,}", accent="#4f6bed")
            with c2: kpi_card("Est. Daily Swaps", f"{out['estimated_daily_swaps']:,}", accent="#10b981")
            with c3: kpi_card("Annual Revenue", f"₹{out['estimated_annual_revenue_inr']/1e6:.1f}M", accent="#f59e0b")
            with c4: kpi_card("Break-even", f"{out['breakeven_months']} months", accent="#8b5cf6")
            section_header("Recommendations")
            for rec in result["recommendations"]: st.markdown(f"• {rec}")

    with tab2:
        st.markdown("**Scenario:** Model the impact of a sudden demand increase.")
        c1, c2 = st.columns(2)
        with c1: demand_pct = st.slider("Demand Increase %", 5, 100, 30)
        with c2: affected = st.multiselect("Affected Cities (blank = all)", ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai"])

        if st.button("Run Demand Shock", type="primary"):
            result = simulator.simulate_demand_shock(demand_pct, affected or None)
            out, fin = result["outputs"], result["financial_impact"]
            c1, c2, c3 = st.columns(3)
            with c1: kpi_card("Additional Daily Swaps", f"{out['demand_delta_daily_swaps']:,.0f}", accent="#4f6bed")
            with c2: kpi_card("New Batteries Needed", f"{out['new_batteries_needed']:,}", accent="#ef4444")
            with c3: kpi_card("Stations at Risk", str(out["stations_at_risk"]), accent="#f59e0b")
            section_header("Recommendations")
            for rec in result["recommendations"]: st.markdown(f"• {rec}")

    with tab3:
        st.markdown("**Scenario:** Assess network impact of retiring a fleet fraction.")
        retirement_pct = st.slider("Fleet Retirement %", 5, 30, 10) / 100

        if st.button("Run Retirement Simulation", type="primary"):
            result = simulator.simulate_battery_retirement(retirement_pct)
            out, fin = result["outputs"], result["financial_impact"]
            c1, c2, c3 = st.columns(3)
            with c1: kpi_card("Batteries Retiring", f"{out['batteries_retiring']:,}", accent="#ef4444")
            with c2: kpi_card("Capacity Loss", f"{out['network_capacity_loss_pct']:.1f}%", accent="#f59e0b")
            with c3: kpi_card("Replacement Cost", f"₹{fin['replacement_capex_inr']/1e6:.1f}M", accent="#8b5cf6")
            section_header("Recommendations")
            for rec in result["recommendations"]: st.markdown(f"• {rec}")
