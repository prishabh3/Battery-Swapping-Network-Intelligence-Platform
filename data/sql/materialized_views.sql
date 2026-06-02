-- ============================================================
-- Battery Swapping Intelligence Platform — Materialized Views
-- Advanced SQL: CTEs, Window Functions, Materialized Views
-- ============================================================

-- ── 1. Station Daily Performance ──────────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_station_daily_performance AS
WITH daily_station_swaps AS (
    SELECT
        DATE(se.timestamp)  AS swap_date,
        se.station_id,
        st.name             AS station_name,
        st.city,
        COUNT(*)            AS total_swaps,
        COUNT(*) FILTER (WHERE se.outcome = 'success')  AS successful_swaps,
        COUNT(*) FILTER (WHERE se.is_anomalous = TRUE)  AS anomalous_swaps,
        SUM(se.revenue_inr) AS daily_revenue_inr,
        AVG(se.duration_seconds) AS avg_swap_duration_s,
        SUM(se.energy_delivered_kwh) AS total_energy_kwh,
        st.capacity,
        st.inventory_count
    FROM swap_events se
    JOIN stations st ON se.station_id = st.station_id
    GROUP BY DATE(se.timestamp), se.station_id, st.name, st.city, st.capacity, st.inventory_count
),
ranked AS (
    SELECT
        *,
        successful_swaps::float / NULLIF(total_swaps, 0) AS success_rate,
        RANK() OVER (PARTITION BY swap_date ORDER BY total_swaps DESC) AS demand_rank_day,
        SUM(total_swaps) OVER (
            PARTITION BY station_id
            ORDER BY swap_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ) AS rolling_7d_swaps,
        AVG(daily_revenue_inr) OVER (
            PARTITION BY station_id
            ORDER BY swap_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS rolling_30d_avg_revenue
    FROM daily_station_swaps
)
SELECT * FROM ranked;

CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_station_perf_pk ON mv_station_daily_performance (swap_date, station_id);
CREATE INDEX IF NOT EXISTS ix_mv_station_perf_date ON mv_station_daily_performance (swap_date DESC);


-- ── 2. Battery Degradation Cohort Analysis ────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_battery_degradation_cohort AS
WITH battery_cohorts AS (
    SELECT
        b.battery_id,
        b.chemistry_type,
        EXTRACT(YEAR FROM b.manufacturing_date)::int AS manufacture_year,
        EXTRACT(QUARTER FROM b.manufacturing_date)::int AS manufacture_quarter,
        b.cycle_count,
        b.current_health,
        b.replacement_risk,
        b.thermal_stress_score,
        (CURRENT_DATE - b.manufacturing_date) AS age_days,
        (1.0 - b.current_health) / NULLIF(b.cycle_count, 0) * 100 AS degradation_per_100_cycles
    FROM batteries b
    WHERE b.status != 'retired'
),
cohort_stats AS (
    SELECT
        chemistry_type,
        manufacture_year,
        manufacture_quarter,
        COUNT(*)                                   AS cohort_size,
        AVG(current_health)                        AS avg_soh,
        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY current_health) AS median_soh,
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY current_health) AS p25_soh,
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY current_health) AS p75_soh,
        AVG(degradation_per_100_cycles)            AS avg_degradation_rate,
        AVG(thermal_stress_score)                  AS avg_thermal_stress,
        COUNT(*) FILTER (WHERE replacement_risk IN ('high', 'critical')) AS high_risk_count,
        AVG(age_days)                              AS avg_age_days
    FROM battery_cohorts
    GROUP BY chemistry_type, manufacture_year, manufacture_quarter
)
SELECT
    *,
    high_risk_count::float / NULLIF(cohort_size, 0) AS high_risk_fraction,
    RANK() OVER (PARTITION BY chemistry_type ORDER BY avg_soh DESC) AS soh_rank_within_chemistry
FROM cohort_stats;

CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_cohort_pk
    ON mv_battery_degradation_cohort (chemistry_type, manufacture_year, manufacture_quarter);


-- ── 3. Network Hourly Demand Pattern ─────────────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_hourly_demand_pattern AS
SELECT
    st.city,
    se.station_id,
    EXTRACT(DOW FROM se.timestamp)::int     AS day_of_week,
    EXTRACT(HOUR FROM se.timestamp)::int    AS hour_of_day,
    COUNT(*)                                AS avg_swaps,
    AVG(se.revenue_inr)                     AS avg_revenue_per_swap,
    AVG(se.duration_seconds)                AS avg_duration_s,
    COUNT(*) FILTER (WHERE se.outcome = 'success')::float
        / NULLIF(COUNT(*), 0)               AS success_rate
FROM swap_events se
JOIN stations st ON se.station_id = st.station_id
WHERE se.timestamp >= NOW() - INTERVAL '90 days'
GROUP BY st.city, se.station_id, EXTRACT(DOW FROM se.timestamp), EXTRACT(HOUR FROM se.timestamp);

CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_hourly_pk
    ON mv_hourly_demand_pattern (station_id, day_of_week, hour_of_day);


-- ── 4. Top Batteries by Revenue Contribution ─────────────────

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_battery_revenue_ranking AS
WITH battery_revenue AS (
    SELECT
        se.battery_out_id                       AS battery_id,
        b.chemistry_type,
        b.current_health,
        b.cycle_count,
        COUNT(se.event_id)                      AS total_swaps,
        SUM(se.revenue_inr)                     AS total_revenue_inr,
        AVG(se.energy_delivered_kwh)            AS avg_energy_per_swap,
        MAX(se.timestamp)                       AS last_active_at
    FROM swap_events se
    JOIN batteries b ON se.battery_out_id = b.battery_id
    WHERE se.outcome = 'success'
      AND se.timestamp >= NOW() - INTERVAL '180 days'
    GROUP BY se.battery_out_id, b.chemistry_type, b.current_health, b.cycle_count
)
SELECT
    battery_id,
    chemistry_type,
    current_health,
    cycle_count,
    total_swaps,
    total_revenue_inr,
    avg_energy_per_swap,
    last_active_at,
    RANK() OVER (ORDER BY total_revenue_inr DESC)   AS revenue_rank,
    RANK() OVER (ORDER BY total_swaps DESC)          AS swaps_rank,
    NTILE(10) OVER (ORDER BY total_revenue_inr DESC) AS revenue_decile
FROM battery_revenue;

CREATE UNIQUE INDEX IF NOT EXISTS ix_mv_battery_revenue_pk ON mv_battery_revenue_ranking (battery_id);


-- ── 5. Refresh helper function ────────────────────────────────

CREATE OR REPLACE FUNCTION refresh_all_materialized_views()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_station_daily_performance;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_battery_degradation_cohort;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_hourly_demand_pattern;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_battery_revenue_ranking;
END;
$$;
