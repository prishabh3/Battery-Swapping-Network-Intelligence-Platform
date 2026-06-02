-- ============================================================
-- Battery Swapping Intelligence Platform — Core Schema
-- PostgreSQL 16
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Enum types ───────────────────────────────────────────────

DO $$ BEGIN
    CREATE TYPE chemistry_type_enum AS ENUM ('LFP', 'NMC', 'LTO', 'LMFP');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE battery_status_enum AS ENUM ('active', 'in_transit', 'charging', 'retired', 'maintenance');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE replacement_risk_enum AS ENUM ('low', 'moderate', 'high', 'critical');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE station_status_enum AS ENUM ('operational', 'degraded', 'offline', 'maintenance');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE fleet_type_enum AS ENUM ('2W', '3W', 'LCV');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE vehicle_status_enum AS ENUM ('active', 'inactive', 'maintenance');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE swap_outcome_enum AS ENUM (
        'success', 'failed_inventory', 'failed_station_offline',
        'failed_battery_health', 'cancelled'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ── Stations ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stations (
    station_id          VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name                VARCHAR(200)            NOT NULL,
    city                VARCHAR(100)            NOT NULL,
    state               VARCHAR(100)            NOT NULL,
    latitude            DOUBLE PRECISION        NOT NULL,
    longitude           DOUBLE PRECISION        NOT NULL,
    capacity            INTEGER                 NOT NULL CHECK (capacity > 0),
    inventory_count     INTEGER                 NOT NULL DEFAULT 0 CHECK (inventory_count >= 0),
    charging_slots      INTEGER                 NOT NULL,
    status              station_status_enum     NOT NULL DEFAULT 'operational',
    operator_name       VARCHAR(200)            NOT NULL,
    pincode             VARCHAR(10)             NOT NULL,
    created_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    last_outage_at      TIMESTAMPTZ,
    CONSTRAINT chk_inventory_le_capacity CHECK (inventory_count <= capacity)
);

CREATE INDEX IF NOT EXISTS ix_stations_city_status ON stations (city, status);
CREATE INDEX IF NOT EXISTS ix_stations_status ON stations (status);

-- ── Batteries ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS batteries (
    battery_id              VARCHAR(36) PRIMARY KEY,
    manufacturing_date      DATE                    NOT NULL,
    chemistry_type          chemistry_type_enum     NOT NULL,
    cycle_count             INTEGER                 NOT NULL DEFAULT 0 CHECK (cycle_count >= 0),
    current_health          DOUBLE PRECISION        NOT NULL CHECK (current_health BETWEEN 0 AND 1),
    nominal_capacity_kwh    DOUBLE PRECISION        NOT NULL,
    current_station_id      VARCHAR(36)             REFERENCES stations(station_id),
    status                  battery_status_enum     NOT NULL DEFAULT 'active',
    thermal_stress_score    DOUBLE PRECISION        DEFAULT 0.0,
    replacement_risk        replacement_risk_enum   DEFAULT 'low',
    avg_temperature         DOUBLE PRECISION        DEFAULT 25.0,
    peak_temperature        DOUBLE PRECISION        DEFAULT 35.0,
    last_swap_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ             NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_batteries_station ON batteries (current_station_id);
CREATE INDEX IF NOT EXISTS ix_batteries_status_health ON batteries (status, current_health);
CREATE INDEX IF NOT EXISTS ix_batteries_risk ON batteries (replacement_risk);
CREATE INDEX IF NOT EXISTS ix_batteries_chemistry ON batteries (chemistry_type);

-- ── Vehicles ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id              VARCHAR(36) PRIMARY KEY,
    fleet_type              fleet_type_enum         NOT NULL,
    region                  VARCHAR(100)            NOT NULL,
    city                    VARCHAR(100)            NOT NULL,
    operator_id             VARCHAR(36)             NOT NULL,
    registration_number     VARCHAR(20)             UNIQUE NOT NULL,
    status                  vehicle_status_enum     NOT NULL DEFAULT 'active',
    total_swaps             INTEGER                 DEFAULT 0,
    total_distance_km       DOUBLE PRECISION        DEFAULT 0.0,
    avg_daily_swaps         DOUBLE PRECISION        DEFAULT 0.0,
    last_swap_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ             NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_vehicles_city ON vehicles (city);
CREATE INDEX IF NOT EXISTS ix_vehicles_fleet ON vehicles (fleet_type, status);

-- ── Swap Events ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS swap_events (
    event_id                VARCHAR(36) PRIMARY KEY,
    timestamp               TIMESTAMPTZ             NOT NULL,
    station_id              VARCHAR(36)             NOT NULL REFERENCES stations(station_id),
    battery_in_id           VARCHAR(36)             NOT NULL REFERENCES batteries(battery_id),
    battery_out_id          VARCHAR(36)             NOT NULL REFERENCES batteries(battery_id),
    vehicle_id              VARCHAR(36)             NOT NULL REFERENCES vehicles(vehicle_id),
    duration_seconds        INTEGER                 NOT NULL CHECK (duration_seconds > 0),
    energy_delivered_kwh    DOUBLE PRECISION        NOT NULL CHECK (energy_delivered_kwh >= 0),
    outcome                 swap_outcome_enum       NOT NULL,
    revenue_inr             DOUBLE PRECISION        NOT NULL DEFAULT 0.0,
    soh_at_swap             DOUBLE PRECISION        NOT NULL,
    is_anomalous            BOOLEAN                 NOT NULL DEFAULT FALSE,
    anomaly_score           DOUBLE PRECISION        DEFAULT 0.0,
    created_at              TIMESTAMPTZ             NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_swap_events_timestamp ON swap_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_swap_events_station_ts ON swap_events (station_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS ix_swap_events_vehicle ON swap_events (vehicle_id);
CREATE INDEX IF NOT EXISTS ix_swap_events_outcome ON swap_events (outcome);
CREATE INDEX IF NOT EXISTS ix_swap_events_anomalous ON swap_events (is_anomalous) WHERE is_anomalous = TRUE;

-- ── Forecasts ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS daily_demand_forecasts (
    forecast_id         VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    station_id          VARCHAR(36)             NOT NULL REFERENCES stations(station_id),
    forecast_date       DATE                    NOT NULL,
    predicted_swaps     DOUBLE PRECISION        NOT NULL,
    confidence_lower    DOUBLE PRECISION        NOT NULL,
    confidence_upper    DOUBLE PRECISION        NOT NULL,
    model_version       VARCHAR(50)             NOT NULL,
    created_at          TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    UNIQUE (station_id, forecast_date, model_version)
);

-- ── Inventory Transfers ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS inventory_transfers (
    transfer_id         VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    from_station_id     VARCHAR(36)             NOT NULL REFERENCES stations(station_id),
    to_station_id       VARCHAR(36)             NOT NULL REFERENCES stations(station_id),
    quantity            INTEGER                 NOT NULL CHECK (quantity > 0),
    priority            VARCHAR(20)             NOT NULL,
    status              VARCHAR(20)             NOT NULL DEFAULT 'pending',
    recommended_at      TIMESTAMPTZ             NOT NULL DEFAULT NOW(),
    executed_at         TIMESTAMPTZ,
    reason              TEXT
);

-- ── Anomaly Records ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS anomaly_records (
    anomaly_id      VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    entity_type     VARCHAR(20)     NOT NULL,
    entity_id       VARCHAR(36)     NOT NULL,
    anomaly_type    VARCHAR(100)    NOT NULL,
    severity        VARCHAR(20)     NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    description     TEXT            NOT NULL,
    detected_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    is_resolved     BOOLEAN         NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_anomalies_entity ON anomaly_records (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS ix_anomalies_severity ON anomaly_records (severity) WHERE NOT is_resolved;
