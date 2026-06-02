# Battery Swapping Intelligence Platform (BSIP)

> **Production-grade analytics system for India-wide EV battery-swapping network operations.**

---

## What This Project Does

BSIP is an analytics backend and executive dashboard for managing a large EV battery-swapping network across Indian cities (Mumbai, Delhi, Bengaluru, Hyderabad, Chennai, and more). At a swap station, a driver pulls up, hands over a depleted battery, and drives away with a fully-charged one in under two minutes. Running hundreds of these stations efficiently requires knowing which batteries are degrading, which stations are running low on inventory, and where to move batteries before a shortage happens.

This platform does five things: it tracks the health of every battery in the fleet using a multi-factor degradation model; it forecasts how many swaps each station will need over the next 1–7 days using an XGBoost model trained on time-series history; it computes an optimal battery transfer plan across stations using linear programming so overloaded stations get topped up from stations with surplus; it flags anomalous swap patterns and battery behaviour using Isolation Forest; and it gives an executive "what-if" simulation mode that estimates the financial and inventory impact of decisions like opening new stations or retiring degraded batteries.

The system exposes all of this through a FastAPI REST API and a Streamlit dashboard. The dashboard works with either a live PostgreSQL database or with uploaded CSV/Excel files — which means it can be demoed without any database setup.

---

## Tech Stack

| Technology | Version | Layer | Role |
|---|---|---|---|
| **Python** | 3.11+ | All | Runtime |
| **FastAPI** | 0.111 | API | HTTP server and request routing |
| **Uvicorn** | 0.29 | API | ASGI server |
| **Pydantic v2** | 2.7 | API / Domain | Request/response validation and settings |
| **SQLAlchemy** | 2.0 | Infrastructure | ORM (async + sync sessions) |
| **asyncpg** | 0.29 | Infrastructure | Async PostgreSQL driver |
| **psycopg2** | 2.9 | Infrastructure | Sync PostgreSQL driver (used by analytics queries) |
| **PostgreSQL** | 16 | Data | Primary relational database |
| **Alembic** | 1.13 | Infrastructure | Database migration tool |
| **XGBoost** | 2.0 | Analytics | Demand forecasting model |
| **scikit-learn** | 1.4 | Analytics | Isolation Forest (anomaly detection), time-series CV |
| **PuLP** | 2.8 | Analytics | Linear programming solver (inventory optimization) |
| **pandas / numpy** | 2.2 / 1.26 | Analytics | Data wrangling and feature engineering |
| **Streamlit** | 1.33 | Frontend | Interactive dashboard |
| **Plotly** | 5.21 | Frontend | Charts and visualizations |
| **Folium + streamlit-folium** | 0.16 / 0.20 | Frontend | Geographic map view |
| **python-jose** | 3.3 | API | JWT token creation and verification |
| **passlib[bcrypt]** | 1.7 | API | Password hashing |
| **pytest + pytest-asyncio** | 8.2 | Testing | Test runner |
| **pytest-cov** | 5.0 | Testing | Coverage reporting |
| **Docker / docker-compose** | — | Infra | Container orchestration |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTS                              │
│   Browser (Streamlit Dashboard)   /   API Consumers         │
└───────────────────┬────────────────────────┬────────────────┘
                    │ HTTP :8501             │ HTTP :8000
                    ▼                        ▼
┌──────────────────────────┐   ┌─────────────────────────────┐
│   FRONTEND               │   │   BACKEND (FastAPI)          │
│   frontend/dashboard/    │   │   backend/api/               │
│   app.py                 │   │                              │
│                          │   │  Routers:                    │
│  Pages:                  │   │  /api/v1/auth                │
│  • Network Overview      │   │  /api/v1/batteries           │
│  • Battery Analytics     │   │  /api/v1/analytics           │
│  • Station Analytics     │   │  /api/v1/forecasting         │
│  • Demand Forecasting    │◄──│  /api/v1/optimization        │
│  • Inventory Optim.      │   │  /api/v1/simulation          │
│  • Anomaly Detection     │   │                              │
│  • Geographic View       │   │  Middleware:                 │
│  • Chairman's Office     │   │  • CORS                      │
│  • Data Upload           │   │  • Request logging           │
└──────────────────────────┘   └───────────┬─────────────────┘
                                           │ depends on
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    ▼                      ▼                      ▼
       ┌────────────────────┐  ┌───────────────────┐  ┌─────────────────────┐
       │  APPLICATION LAYER │  │   DOMAIN LAYER    │  │  ANALYTICS LAYER    │
       │  backend/          │  │   backend/        │  │  analytics/         │
       │  application/      │  │   domain/         │  │                     │
       │                    │  │                   │  │  • DemandForecaster │
       │  • BatteryService  │  │  Entities:        │  │    (XGBoost)        │
       │  • AnalyticsService│  │  • Battery        │  │  • InventoryOptim.  │
       │  • DTOs            │  │  • Station        │  │    (PuLP LP solver) │
       │  • Use Cases       │  │  • SwapEvent      │  │  • AnomalyDetect.   │
       │                    │  │  • Vehicle        │  │    (Isolation Forest│
       │                    │  │                   │  │  • BatteryHealth    │
       └────────────────────┘  │  Repositories     │  │    Engine           │
                    │          │  (interfaces)     │  └─────────────────────┘
                    │          └───────────────────┘
                    ▼
       ┌────────────────────────────────┐
       │       INFRASTRUCTURE LAYER     │
       │       backend/infrastructure/  │
       │                                │
       │  • SQLAlchemy ORM models       │
       │  • Async DB session factory    │
       │  • Repository implementations  │
       └──────────────┬─────────────────┘
                      │
                      ▼
          ┌─────────────────────┐
          │    PostgreSQL 16    │
          │  database:          │
          │  battery_swapping   │
          │                     │
          │  Tables:            │
          │  batteries          │
          │  stations           │
          │  vehicles           │
          │  swap_events        │
          │  daily_demand_      │
          │    forecasts        │
          │  inventory_transfers│
          │  anomaly_records    │
          └─────────────────────┘
```

**The codebase follows Clean Architecture**: the Domain layer defines core business entities (Battery, Station, SwapEvent) with no framework dependencies. The Application layer contains services and use-cases that orchestrate domain objects. The Infrastructure layer is the only place that touches the database. The API layer wires it all together via FastAPI dependency injection. The Analytics layer (`analytics/`) is a separate Python package imported lazily by the API routers — it can run standalone without the web framework.

---

## How the Pieces Fit Together

**A battery lookup request** arrives at `GET /api/v1/batteries/{battery_id}`. FastAPI calls `get_battery_service()` in `dependencies.py`, which opens an async SQLAlchemy session and constructs a `BatteryService` backed by a `SQLAlchemyBatteryRepository`. The repository fetches the `BatteryModel` ORM row from PostgreSQL, maps it to a `Battery` domain dataclass (a pure Python object), and returns it up through the service to the router, where it gets serialized into a `BatteryResponse` Pydantic model and sent as JSON. Nothing in the domain entity knows anything about HTTP or the database.

**A demand forecast request** arrives at `POST /api/v1/forecasting/demand`. The router lazily imports `DemandForecaster` from `analytics/forecasting/`. If no trained model exists for the requested station, the forecaster generates 365 days of synthetic swap history (seeded deterministically from the station ID), builds 31 time-series features (lags at 1/7/14/21/28 days, rolling means and std at 7/14/30 days, cyclical day-of-week encoding, seasonal index), trains an XGBoost regressor with 5-fold time-series cross-validation, then predicts the next N days with a 90% confidence interval (mean ± 1.645 × std). The mock history guarantees the endpoint works without a live database.

**An inventory optimization run** at `POST /api/v1/optimization/inventory` instantiates `InventoryOptimizer`, loads the network (12 mock stations covering major Indian cities), classifies each station as surplus or deficit relative to its expected demand, then formulates a PuLP integer linear program: the decision variables are the number of batteries to transfer between each feasible source→destination pair (pairs beyond `max_transfer_distance_km` via Haversine are excluded), the objective minimizes total unmet demand plus a small distance cost coefficient (0.001), and the constraints keep each source within its surplus and each destination's shortfall covered by inflow plus slack. If PuLP is unavailable it falls back to a greedy biggest-surplus-to-biggest-deficit algorithm.

**An anomaly detection scan** runs three Isolation Forest models in sequence: one over battery features (SOH, cycle count, thermal stress, temperature), one over swap event features (duration, energy delivered, revenue, SOH-at-swap, time-of-day), and a rule-based checker for stations at >98% or <5% inventory. Each flagged item gets a normalized anomaly score (0–1) and a severity label (`info`/`warning`/`critical`).

**The Streamlit dashboard** does not call the FastAPI backend — it imports and calls the analytics modules directly in-process. When no uploaded file is present, it generates synthetic data in `load_mock_data()` (cached for 5 minutes via `@st.cache_data`) using the same city demand multipliers as the analytics layer. When a user uploads a CSV or Excel file through the Data Upload page, the file is validated against a defined schema (required columns, type checks, domain-specific sanity checks), enriched with derived columns (e.g., `utilization_rate = inventory_count / capacity`), and stored in Streamlit session state. Every other page reads from session state first, then falls back to mock data — so uploading stations data immediately updates the Network Overview map and KPIs.

---

## Quick Start

### Option A — Docker (recommended, no local Python setup needed)

```bash
# 1. Clone and enter the project
git clone https://github.com/prishabh3/Battery-Swapping-Network-Intelligence-Platform.git
cd Battery-Swapping-Network-Intelligence-Platform

# 2. Copy environment file
cp .env.example .env
# Edit .env if you want to change SECRET_KEY for production

# 3. Start all services (PostgreSQL + FastAPI backend + Streamlit frontend)
docker compose up --build

# Services will be available at:
#   Streamlit dashboard  → http://localhost:8501
#   FastAPI REST API     → http://localhost:8000
#   Interactive API docs → http://localhost:8000/api/docs
```

The `postgres` service initialises with `data/sql/schema.sql` (DDL) and `data/sql/materialized_views.sql` (views) on first startup. No separate seed step is needed — the dashboard and all analytics endpoints work with synthetic data when the database is empty.

---

### Option B — Local Python (no Docker)

**Prerequisites:** Python 3.11+, PostgreSQL 16

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create the database and user
psql -U postgres <<EOF
CREATE USER bsip WITH PASSWORD 'bsip_secret';
CREATE DATABASE battery_swapping OWNER bsip;
EOF

# 4. Apply the schema
psql -U bsip -d battery_swapping -f data/sql/schema.sql
psql -U bsip -d battery_swapping -f data/sql/materialized_views.sql

# 5. Copy and configure environment variables
cp .env.example .env
# Defaults in .env work out of the box for the local setup above

# 6. Start the FastAPI backend
PYTHONPATH=. uvicorn backend.api.main:app --reload --port 8000

# 7. In a separate terminal, start the Streamlit dashboard
PYTHONPATH=. streamlit run frontend/dashboard/app.py --server.port 8501
```

**Commonly forgotten steps:**
- `PYTHONPATH=.` must be set when running from the repo root, or Python won't find the `backend` and `analytics` packages.
- The database user must be named `bsip` and the database `battery_swapping` to match the default `DATABASE_URL` in `.env.example`. If you change them, update the `.env` file accordingly.
- `bcrypt` is pinned at 4.0.1 via passlib — do not upgrade it without checking passlib compatibility.
- The XGBoost `n_estimators` setting defaults to 500 in production. Set `BSIP_FAST_MODEL=1` to use 80 trees (6× faster training) in development or CI.

---

## Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://bsip:bsip_secret@localhost:5432/battery_swapping` | Yes | Async connection string for FastAPI |
| `SYNC_DATABASE_URL` | `postgresql+psycopg2://bsip:bsip_secret@localhost:5432/battery_swapping` | Yes | Sync connection string for analytics queries |
| `SECRET_KEY` | `dev-secret-key-change-in-prod-32ch` | Yes | JWT signing secret — change in production |
| `ALGORITHM` | `HS256` | No | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | No | Token lifetime (8 hours) |
| `LOG_LEVEL` | `INFO` | No | Python logging level |
| `ENVIRONMENT` | `development` | No | Environment tag in logs |
| `BSIP_FAST_MODEL` | `0` | No | Set to `1` to use 80-tree XGBoost (dev/test) |

---

## Feature Walkthrough

### 1. Log In

Navigate to `http://localhost:8501`. There is no login screen in the Streamlit dashboard — filters and navigation are open. The FastAPI API requires authentication.

**API login:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=analyst&password=analyst2024"
```
Returns a JWT `access_token`. Use it as `Authorization: Bearer <token>` in subsequent API calls. Token expires after 8 hours.

**Built-in demo accounts:**

| Username | Password | Role |
|---|---|---|
| `chairman` | `sunmobility2024` | `executive` |
| `analyst` | `analyst2024` | `analyst` |
| `ops` | `ops2024` | `operations` |

### 2. Explore the Network Overview

Open the Streamlit dashboard and select **Network Overview** from the sidebar. You will see 8 KPI cards: total swaps today, estimated revenue, active batteries (with critical count), operational stations, average SOH, month-to-date swaps, network utilization, and swap success rate.

Below the KPIs: a daily swap volume time-series chart with a 7-day moving average, an hourly demand pattern bar chart (peak hours 07:00–11:00 and 17:00–21:00 are highlighted red), and a revenue-by-city bar chart.

Use the **Cities** multiselect in the sidebar to filter all charts to specific cities. Use the **Date Range** picker to narrow the time window.

### 3. Inspect Battery Health

Select **Battery Analytics**. You'll see: a donut chart of fleet SOH distribution (Excellent / Good / Fair / Degraded / End-of-Life), a histogram with threshold lines at 70% and 80% SOH, a box-plot of SOH by chemistry type, a replacement risk bar chart, a scatter plot of degradation vs cycle count with an OLS trendline, and a table of critical-risk batteries requiring immediate action.

### 4. Run a Demand Forecast (API)

```bash
TOKEN="<your_token>"
curl -X POST http://localhost:8000/api/v1/forecasting/demand \
  -H "Content-Type: application/json" \
  -d '{"station_id": "STN-001", "horizon_days": 7}'
```

Returns day-by-day predicted swap counts with lower/upper bounds and cross-validation metrics (MAE, RMSE, MAPE). The dashboard's **Demand Forecasting** page calls this in-process and renders the output as a Plotly chart.

### 5. Run Inventory Optimization (API)

```bash
curl -X POST http://localhost:8000/api/v1/optimization/inventory \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"horizon_days": 1, "max_transfer_distance_km": 50}'
```

Returns a list of transfer recommendations (from station → to station, quantity, priority, urgency score, distance). The **Inventory Optimization** page in the dashboard renders these as a prioritized action table.

### 6. Upload Your Own Data

Go to **Data Upload** in the sidebar. Download the CSV templates for Stations, Batteries, or Swap Events. Fill in your real data and upload. The platform validates schema (required columns, types, domain-specific checks) and shows errors/warnings before applying. Once confirmed, every dashboard page switches to your uploaded data for that session.

### 7. Chairman's Office Simulation

Select **Chairman's Office**. This page exposes three what-if scenarios:
- **New Stations**: enter a city, number of stations, and capacity per station. Get back batteries required, projected daily swaps, annual revenue estimate, CAPEX, and break-even months.
- **Demand Shock**: simulate a sudden % increase in swaps. Get back how many extra batteries you need, how many stations are at risk, and the net financial impact.
- **Battery Retirement**: simulate retiring a fraction of the fleet. Get replacement cost, revenue at risk, and second-life salvage value.

---

## API Reference

Base URL: `http://localhost:8000/api/v1`  
Interactive docs: `http://localhost:8000/api/docs`

### Authentication

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/token` | None | Exchange username + password for a JWT |
| `GET` | `/auth/me` | Bearer | Return current user info |

**Example — login:**
```bash
curl -X POST /api/v1/auth/token \
  -d "username=analyst&password=analyst2024"
```
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 28800,
  "role": "analyst",
  "full_name": "Product Analytics"
}
```

---

### Batteries

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/batteries/` | Bearer | Paginated list of all batteries |
| `GET` | `/batteries/critical` | Bearer | Batteries with `replacement_risk = critical` |
| `GET` | `/batteries/degradation-candidates` | Bearer | Batteries below an SOH threshold (default 0.75) |
| `GET` | `/batteries/{battery_id}` | Bearer | Single battery by ID |
| `GET` | `/batteries/{battery_id}/health-report` | Bearer | Full health report with recommendations |

**Query parameters for `GET /batteries/`:**  
- `page` (int, default 1)  
- `page_size` (int, default 50, max 200)

**Query parameter for `GET /batteries/degradation-candidates`:**  
- `soh_threshold` (float, 0.5–1.0, default 0.75)

**Example response — health report:**
```json
{
  "battery_id": "BAT-00042",
  "current_health": 0.74,
  "soh_category": "Fair",
  "cycle_count": 1120,
  "thermal_stress_score": 0.42,
  "replacement_risk": "high",
  "degradation_rate_per_100_cycles": 0.0234,
  "estimated_remaining_cycles": 597,
  "estimated_end_of_life_date": "2026-03-15",
  "recommendations": [
    "Reduce peak-load operations to mitigate thermal stress.",
    "Prioritize for retirement in next maintenance cycle."
  ]
}
```

---

### Analytics

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/analytics/kpis` | None | Network-wide KPI snapshot (swaps, revenue, SOH, utilization) |
| `GET` | `/analytics/station-rankings` | None | Top 20 stations by swap volume over last 30 days |
| `GET` | `/analytics/demand-trends` | None | Rolling 7-day and 30-day demand averages per station (last 60 days) |

---

### Forecasting

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/forecasting/demand` | None | Per-station demand forecast for 1–N days |
| `GET` | `/forecasting/network-summary` | None | Aggregated 7-day forecast across the full network |

**Request body — `POST /forecasting/demand`:**
```json
{
  "station_id": "STN-001",
  "horizon_days": 7
}
```

**Response:**
```json
{
  "station_id": "STN-001",
  "model": "xgb_v1.0",
  "mae": 4.21,
  "rmse": 5.88,
  "mape": 6.3,
  "forecast": [
    {
      "date": "2025-06-03",
      "predicted_swaps": 98.4,
      "lower_bound": 73.5,
      "upper_bound": 123.3,
      "day_of_week": "Tuesday"
    }
  ]
}
```

---

### Optimization

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/optimization/inventory` | None | Run LP-based inventory optimization |
| `GET` | `/optimization/transfer-plan` | None | Return the most recently computed transfer plan |

**Request body — `POST /optimization/inventory`:**
```json
{
  "horizon_days": 1,
  "max_transfer_distance_km": 50.0
}
```

**Response:**
```json
{
  "run_id": "550e8400-e29b-...",
  "total_transfers": 4,
  "batteries_to_redistribute": 215,
  "estimated_shortfall_prevented": 190,
  "solver_status": "LP_OPTIMAL",
  "recommendations": [
    {
      "transfer_id": "...",
      "from_station_id": "STN-001",
      "from_station_name": "Mumbai Central Hub",
      "to_station_id": "STN-002",
      "to_station_name": "Mumbai North",
      "quantity": 80,
      "priority": "CRITICAL",
      "urgency_score": 0.78,
      "reason": "Mumbai North has 140 battery shortfall vs expected demand of 180. Mumbai Central Hub has 180 surplus.",
      "distance_km": 16.2
    }
  ]
}
```

---

### Simulation

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/simulation/new-stations` | None | Model financial impact of opening stations in a new city |
| `POST` | `/simulation/demand-shock` | None | Model impact of a sudden demand increase |
| `POST` | `/simulation/battery-retirement` | None | Model impact of retiring a % of the fleet |

**Request body — `POST /simulation/new-stations`:**
```json
{
  "city": "Mumbai",
  "num_new_stations": 10,
  "avg_capacity_per_station": 150,
  "target_utilization": 0.65
}
```

**Request body — `POST /simulation/demand-shock`:**
```json
{
  "demand_increase_pct": 30.0,
  "affected_cities": ["Mumbai", "Delhi"]
}
```

---

### Health Check

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | None | Returns `{"status": "healthy", "service": "BSIP API", "version": "1.0.0"}` |

---

## Database Layout

Database name: `battery_swapping`. All tables are in the default `public` schema.

### `batteries`
One row per physical battery unit.

| Column | Type | Description |
|---|---|---|
| `battery_id` | `VARCHAR(36)` PK | UUID string |
| `manufacturing_date` | `DATE` | Used to compute calendar aging |
| `chemistry_type` | ENUM | `LFP`, `NMC`, `LTO`, `LMFP` |
| `cycle_count` | `INTEGER` | Full charge-discharge cycles completed |
| `current_health` | `FLOAT` | State of Health (SOH), 0.0–1.0 |
| `nominal_capacity_kwh` | `FLOAT` | Rated capacity when new |
| `current_station_id` | `VARCHAR(36)` FK | Station where battery currently is |
| `status` | ENUM | `active`, `in_transit`, `charging`, `retired`, `maintenance` |
| `thermal_stress_score` | `FLOAT` | Composite thermal load, 0.0–1.0 |
| `replacement_risk` | ENUM | `low`, `moderate`, `high`, `critical` |
| `avg_temperature` | `FLOAT` | Average operating temperature (°C) |
| `peak_temperature` | `FLOAT` | Peak recorded temperature (°C) |
| `last_swap_at` | `DATETIME` | Timestamp of most recent swap |

Indexes: `(status, current_health)`, `(replacement_risk)`, FK on `current_station_id`.

---

### `stations`
One row per physical swap station.

| Column | Type | Description |
|---|---|---|
| `station_id` | `VARCHAR(36)` PK | UUID string |
| `name` | `VARCHAR(200)` | Human-readable name |
| `city` | `VARCHAR(100)` | City, indexed |
| `state` | `VARCHAR(100)` | State |
| `latitude` / `longitude` | `FLOAT` | Coordinates (used for Haversine distance in optimizer) |
| `capacity` | `INTEGER` | Maximum batteries the station can hold |
| `inventory_count` | `INTEGER` | Charged batteries currently on hand |
| `charging_slots` | `INTEGER` | Simultaneous charging positions |
| `status` | ENUM | `operational`, `degraded`, `offline`, `maintenance` |
| `operator_name` | `VARCHAR(200)` | Franchise operator |
| `pincode` | `VARCHAR(10)` | Postal code |
| `last_outage_at` | `DATETIME` | Nullable — last time station went offline |

Index: `(city, status)`.

---

### `vehicles`
One row per registered EV that uses the swap network.

| Column | Type | Description |
|---|---|---|
| `vehicle_id` | `VARCHAR(36)` PK | UUID string |
| `fleet_type` | ENUM | `2W` (two-wheeler), `3W` (three-wheeler), `LCV` (light commercial) |
| `registration_number` | `VARCHAR(20)` UNIQUE | Licence plate |
| `operator_id` | `VARCHAR(36)` | Fleet operator ID, indexed |
| `city` | `VARCHAR(100)` | Home city |
| `status` | ENUM | `active`, `inactive`, `maintenance` |
| `total_swaps` | `INTEGER` | Lifetime swap count |
| `avg_daily_swaps` | `FLOAT` | Rolling average |

---

### `swap_events`
One row per battery swap transaction. This is the most write-heavy table.

| Column | Type | Description |
|---|---|---|
| `event_id` | `VARCHAR(36)` PK | UUID string |
| `timestamp` | `DATETIME` | When the swap occurred, indexed |
| `station_id` | `VARCHAR(36)` FK | Where the swap happened |
| `battery_in_id` | `VARCHAR(36)` FK | Battery returned by the driver (going to charge) |
| `battery_out_id` | `VARCHAR(36)` FK | Battery given to the driver (charged) |
| `vehicle_id` | `VARCHAR(36)` FK | Vehicle that swapped |
| `duration_seconds` | `INTEGER` | Physical swap time (≤120s = fast swap) |
| `energy_delivered_kwh` | `FLOAT` | kWh delivered in the battery handed out |
| `outcome` | ENUM | `success`, `failed_inventory`, `failed_station_offline`, `failed_battery_health`, `cancelled` |
| `revenue_inr` | `FLOAT` | Revenue collected for this swap |
| `soh_at_swap` | `FLOAT` | SOH of the battery given out |
| `is_anomalous` | `BOOLEAN` | Set by anomaly detection pipeline |
| `anomaly_score` | `FLOAT` | 0–1, higher = more anomalous |

Indexes: `(timestamp, station_id)`, `(outcome)`, `(is_anomalous)`.

---

### `daily_demand_forecasts`
Stores forecasts produced by the demand forecasting engine.

| Column | Type | Description |
|---|---|---|
| `forecast_id` | `VARCHAR(36)` PK | UUID |
| `station_id` | `VARCHAR(36)` FK | Which station |
| `forecast_date` | `DATE` | Date being forecast |
| `predicted_swaps` | `FLOAT` | Point estimate |
| `confidence_lower` / `confidence_upper` | `FLOAT` | 90% confidence interval bounds |
| `model_version` | `VARCHAR(50)` | e.g. `xgb_v1.0` |

Unique constraint: `(station_id, forecast_date, model_version)` — prevents duplicate forecasts for the same model version run.

---

### `inventory_transfers`
Stores transfer recommendations from the optimizer.

| Column | Type | Description |
|---|---|---|
| `transfer_id` | `VARCHAR(36)` PK | UUID |
| `from_station_id` | `VARCHAR(36)` FK | Source station |
| `to_station_id` | `VARCHAR(36)` FK | Destination station |
| `quantity` | `INTEGER` | Batteries to move |
| `priority` | `VARCHAR(20)` | `CRITICAL`, `HIGH`, or `NORMAL` |
| `status` | `VARCHAR(20)` | `pending`, `in_progress`, `done` |
| `recommended_at` | `DATETIME` | When optimizer ran |
| `executed_at` | `DATETIME` | Nullable — when actually executed |
| `reason` | `TEXT` | Human-readable explanation |

---

### `anomaly_records`
Stores detected anomalies across all entity types.

| Column | Type | Description |
|---|---|---|
| `anomaly_id` | `VARCHAR(36)` PK | UUID |
| `entity_type` | `VARCHAR(20)` | `battery`, `station`, or `swap` |
| `entity_id` | `VARCHAR(36)` | ID of the flagged entity |
| `anomaly_type` | `VARCHAR(100)` | e.g. `degradation_anomaly`, `suspicious_swap`, `critical_low_inventory` |
| `severity` | `VARCHAR(20)` | `info`, `warning`, `critical` |
| `score` | `FLOAT` | 0–1 normalized anomaly score |
| `description` | `TEXT` | Human-readable description of why it was flagged |
| `detected_at` | `DATETIME` | Timestamp |
| `is_resolved` | `BOOLEAN` | Whether the issue has been addressed |
| `resolved_at` | `DATETIME` | Nullable |

Indexes: `(entity_type, entity_id)`, `(severity)`.

---

## Key Design Decisions

### 1. Replacement Risk as a Weighted Score (not a single threshold)

A battery is not just "bad" because its SOH drops below a number. The `compute_replacement_risk()` method in `Battery` accumulates a score from four independent signals: SOH below 80% (+20 points) or 70% (+40 points), cycle count over 1000 (+15) or 1500 (+30), thermal stress over 0.4 (+10) or 0.7 (+20), and age over 4 years (+10). A battery scoring ≥70 is `critical`, ≥40 is `high`, ≥20 is `moderate`. This catches cases like a thermally stressed battery that still has 80% SOH — it would score 0+10=10 (moderate) — which a pure SOH threshold would miss.

The `BatteryHealthEngine` in `analytics/battery_health/` uses a separate but similar model that also returns an explainability breakdown so each factor's contribution is visible.

### 2. Chemistry-Specific Degradation Parameters

SOH calculation in `SOHCalculator` uses published degradation coefficients per chemistry type rather than treating all batteries the same:

| Chemistry | Cycle degradation rate | Calendar degradation rate | Thermal sensitivity |
|---|---|---|---|
| LTO | 0.000015 | 0.00008 | 0.6 (lowest) |
| LFP | 0.000035 | 0.0001 | 0.8 |
| LMFP | 0.000040 | 0.0001 | 0.9 |
| NMC | 0.000050 | 0.0001 | 1.2 (highest) |

LTO degrades slowest and handles heat best; NMC degrades fastest. The SOH formula additionally applies an Arrhenius thermal acceleration factor (`exp(thermal_factor × (avg_temp - 25) / 300)`) to both cycle and calendar losses, so an NMC battery running at 35°C degrades measurably faster than the same battery at 25°C.

### 3. LP Optimization with Distance Constraint

The inventory optimizer does not simply match the largest surplus to the largest deficit. It uses integer linear programming (PuLP + CBC solver) which finds the globally optimal set of transfers subject to three hard constraints: sources can't give more than their surplus, the solver uses slack variables to allow partial deficit coverage when supply is insufficient, and pairs beyond `max_transfer_distance_km` are excluded entirely (Haversine distance). A small distance cost (0.001 × km) in the objective function breaks ties in favour of shorter moves. If PuLP is not installed, a greedy fallback sorts surplus nodes descending and greedily assigns them to deficit nodes.

### 4. XGBoost with Time-Series Cross-Validation

The demand forecaster never uses random k-fold CV — it uses `sklearn.model_selection.TimeSeriesSplit` with 5 folds, which always trains on past data and validates on future data. This prevents data leakage. The reported MAE, RMSE, and MAPE in the API response are the averages across those 5 out-of-sample folds, not train-set scores. The final model is then retrained on the full history before making predictions.

### 5. Dual Database Sessions (async + sync)

FastAPI runs on an async event loop. The backend API uses `asyncpg` via SQLAlchemy's `AsyncSession` for all API request handlers — nothing blocks the event loop. However, the analytics queries in `AnalyticsService` use raw SQL (`text()`) that also runs async. The `SYNC_DATABASE_URL` (psycopg2) is available for scripts and utilities that run outside the async context. Both connection strings are in `.env`.

### 6. Idempotent Forecast Storage

The `daily_demand_forecasts` table has a unique constraint on `(station_id, forecast_date, model_version)`. Re-running the forecaster for the same station on the same day with the same model version will conflict on insert rather than silently creating duplicate rows. This makes the forecasting pipeline safe to run repeatedly (e.g., in a nightly cron job) without accumulating stale duplicates.

### 7. Swap Eligibility is a Domain Rule, Not a Database Query

Whether a battery can be given to a driver is encoded as `Battery.is_eligible_for_swap` — a Python property on the domain entity that checks three conditions: status must be `active`, SOH must be ≥70%, and replacement risk must not be `critical`. This rule lives in the domain layer and is not a database view or API-level check. Any code that holds a `Battery` object can call this property without going back to the database.

### 8. Fast Test Mode

The production XGBoost model uses 500 estimators. `tests/conftest.py` sets `BSIP_FAST_MODEL=1` before any test runs, which switches the estimator count to 80. This reduces test runtime from ~3 minutes to ~30 seconds for the forecasting tests. The switch is done via an environment variable read at class definition time in `DemandForecaster._N_ESTIMATORS`, not inside a function — so it's evaluated once when the module loads.

---

## Testing

### Running the Test Suite

```bash
# Run all tests with coverage
pytest

# Run a specific test file
pytest tests/analytics/test_health_engine.py -v

# Run only fast tests (no DB required)
BSIP_FAST_MODEL=1 pytest tests/unit tests/analytics -v

# Run with coverage report in HTML
pytest --cov=backend --cov=analytics --cov-report=html
# Open htmlcov/index.html in a browser
```

`conftest.py` automatically sets `BSIP_FAST_MODEL=1` — you don't need to export it manually when running `pytest`.

### What the Tests Cover

**`tests/unit/`**

| File | What it tests |
|---|---|
| `test_battery_entity.py` | SOH category thresholds, `is_eligible_for_swap` logic, `compute_replacement_risk()` scoring including thermal stress escalation |
| `test_station_entity.py` | Utilization rate and tier calculation, `can_fulfill_swap()` conditions |
| `test_etl_pipeline.py` | Data pipeline transforms and validation |

**`tests/analytics/`**

| File | What it tests |
|---|---|
| `test_health_engine.py` | SOH formula (bounded 0.5–1.0, decreases with cycles), chemistry-specific degradation ordering (LFP > NMC), thermal stress formula, `DegradationTrendAnalyzer` linear regression and EOL projection, `BatteryHealthEngine.generate_lifecycle_report()` return type, risk classification, explainability keys |
| `test_demand_forecaster.py` | Forecast output structure, predicted values are non-negative, confidence interval direction (lower < upper), network summary shape |
| `test_anomaly_detector.py` | Isolation Forest output structure, severity labels, score bounds |
| `test_optimizer.py` | Haversine distance (same-point = 0, Mumbai–Delhi ≈ 1100–1500 km), `StationNode` surplus/shortfall calculation, optimizer output structure, quantity > 0, urgency_score ∈ [0,1], priority ∈ {CRITICAL, HIGH, NORMAL}, scenario simulator output keys |

**`tests/integration/`**

| File | What it tests |
|---|---|
| `test_api.py` | `/health` returns 200 with correct payload, valid login returns `access_token`, invalid credentials return 401, chairman login returns `executive` role, `/api/openapi.json` and `/api/docs` are reachable, simulation endpoints don't crash the server |

Integration tests use FastAPI's `TestClient` with `raise_server_exceptions=False` — the API is fully wired up against mocked or in-process service dependencies, not a real database.

---

## Project Structure

```
Battery Swapping Intelligence Platform/
│
├── backend/                        # FastAPI application
│   ├── api/
│   │   ├── main.py                 # App factory: registers routers, middleware, lifespan
│   │   ├── dependencies.py         # FastAPI Depends functions: DB session, JWT auth, services
│   │   ├── middleware/
│   │   │   └── logging_middleware.py
│   │   └── routers/
│   │       ├── auth.py             # POST /auth/token  (JWT login)
│   │       ├── batteries.py        # CRUD + health reports
│   │       ├── analytics.py        # KPIs, station rankings, demand trends
│   │       ├── forecasting.py      # Demand forecast (delegates to analytics/)
│   │       ├── optimization.py     # LP inventory optimization (delegates to analytics/)
│   │       └── simulation.py       # What-if scenarios (delegates to analytics/)
│   ├── application/
│   │   ├── services/
│   │   │   ├── battery_service.py  # Orchestrates BatteryRepository; health report logic
│   │   │   └── analytics_service.py# Raw SQL for KPIs, station rankings, demand trends
│   │   ├── dtos/
│   │   │   └── battery_dto.py      # Pydantic response models
│   │   └── use_cases/              # (placeholder for future command/query separation)
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── battery.py          # Battery dataclass: SOH properties, risk scoring
│   │   │   ├── station.py          # Station dataclass: utilization tier, swap eligibility
│   │   │   ├── swap_event.py       # SwapEvent dataclass: fast-swap flag, peak-hour flag
│   │   │   └── vehicle.py          # Vehicle dataclass
│   │   ├── repositories/           # Abstract repository interfaces (ABCs)
│   │   └── value_objects/          # (chemistry type, enums)
│   ├── infrastructure/
│   │   └── database/
│   │       ├── models.py           # SQLAlchemy ORM table definitions (7 tables)
│   │       ├── session.py          # Async engine + session factory
│   │       └── repositories/
│   │           └── battery_repository_impl.py  # SQLAlchemy implementation
│   └── config.py                   # Pydantic Settings (reads .env)
│
├── analytics/                      # Self-contained analytics package (no FastAPI dependency)
│   ├── forecasting/
│   │   └── demand_forecaster.py    # XGBoost demand forecasting with TSS-CV
│   ├── optimization/
│   │   └── inventory_optimizer.py  # PuLP LP solver + ScenarioSimulator
│   ├── anomaly_detection/
│   │   └── anomaly_detector.py     # Isolation Forest for batteries, swaps, and stations
│   ├── battery_health/
│   │   └── health_engine.py        # SOH calculator, degradation trend analyzer, lifecycle report
│   └── reporting/                  # (report generation utilities)
│
├── frontend/
│   └── dashboard/
│       └── app.py                  # 1087-line Streamlit app (9 pages, upload flow, charts)
│
├── tests/
│   ├── conftest.py                 # Sets BSIP_FAST_MODEL=1 for all tests
│   ├── unit/                       # Domain entity and ETL tests (no DB, no network)
│   ├── analytics/                  # Tests for forecasting, optimization, anomaly, health
│   └── integration/                # FastAPI TestClient tests against the full app
│
├── data/
│   └── sql/
│       ├── schema.sql              # DDL: CREATE TABLE statements with indexes
│       ├── materialized_views.sql  # Pre-aggregated views for dashboard queries
│       └── analytics_queries.sql   # Reference queries used by AnalyticsService
│
├── docker-compose.yml              # Starts postgres + backend + frontend
├── Dockerfile.backend              # python:3.11-slim, installs requirements, runs uvicorn
├── Dockerfile.frontend             # python:3.11-slim, installs requirements, runs streamlit
├── requirements.txt                # All Python dependencies with pinned versions
├── pyproject.toml                  # pytest config, ruff linter, mypy settings
└── .env.example                    # Template for all environment variables
```

---

## Common Issues

### `ModuleNotFoundError: No module named 'backend'`
**Cause:** Python can't find the `backend` or `analytics` packages.  
**Fix:** Run from the repo root with `PYTHONPATH=.` set:
```bash
PYTHONPATH=. uvicorn backend.api.main:app --reload
PYTHONPATH=. streamlit run frontend/dashboard/app.py
PYTHONPATH=. pytest
```

---

### `passlib[bcrypt]` startup warning: "error reading bcrypt version"
**Cause:** bcrypt ≥4.1 removed the `__about__` module that passlib reads.  
**Fix:** Requirements pin `bcrypt==4.0.1` via `passlib[bcrypt]==1.7.4`. If you see this warning after a `pip install --upgrade`, run:
```bash
pip install "bcrypt==4.0.1"
```

---

### `sqlalchemy.exc.OperationalError: connection refused` on port 5432
**Cause:** PostgreSQL isn't running, or the credentials in `.env` don't match.  
**Fix:** Verify PostgreSQL is running and the user/database exist:
```bash
pg_isready -h localhost -U bsip -d battery_swapping
```
If not, create them:
```bash
psql -U postgres -c "CREATE USER bsip WITH PASSWORD 'bsip_secret';"
psql -U postgres -c "CREATE DATABASE battery_swapping OWNER bsip;"
```

---

### Demand forecast returns a 500 error
**Cause:** Usually a Python path issue — the `analytics` package can't be imported inside the FastAPI process.  
**Fix:** Make sure `PYTHONPATH=.` is set (or `PYTHONPATH=/app` inside Docker). The forecasting router imports `DemandForecaster` lazily inside the route handler, so the import error only surfaces when the endpoint is called, not at startup.

---

### Tests are very slow (>3 minutes for analytics tests)
**Cause:** `BSIP_FAST_MODEL` is not set, so XGBoost trains 500-tree models.  
**Fix:** `tests/conftest.py` sets `BSIP_FAST_MODEL=1` automatically when you run `pytest`. If you are running a test file directly with `python`, set it manually:
```bash
BSIP_FAST_MODEL=1 python -m pytest tests/analytics/test_demand_forecaster.py
```

---

### PuLP solver not found: `No module named 'pulp'` or CBC not installed
**Cause:** PuLP is not installed, or the bundled CBC solver binary is missing.  
**Fix:**
```bash
pip install pulp==2.8.0
```
PuLP 2.x bundles the CBC solver binary — no separate install needed. If the binary is still not found, the optimizer automatically falls back to its greedy algorithm and returns `"solver_status": "GREEDY"` in the response.

---

### `asyncpg.exceptions.UndefinedTableError: relation "batteries" does not exist`
**Cause:** The schema was never applied to the database.  
**Fix:**
```bash
psql -U bsip -d battery_swapping -f data/sql/schema.sql
psql -U bsip -d battery_swapping -f data/sql/materialized_views.sql
```
When using Docker, this happens automatically on first startup via the `docker-entrypoint-initdb.d/` volume mount.

---

*Python 3.11+ required. All dependencies are pinned in `requirements.txt`.*
