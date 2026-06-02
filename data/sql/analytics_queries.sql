-- ============================================================
-- BSIP Advanced Analytics Queries
-- Demonstrates: CTEs, Window Functions, Index Optimization
-- ============================================================

-- ── 1. Battery Fleet Ranking by Revenue Contribution ─────────
-- Uses CTE + RANK() window function

WITH battery_swap_stats AS (
    SELECT
        se.battery_out_id                               AS battery_id,
        b.chemistry_type,
        b.current_health,
        b.cycle_count,
        b.replacement_risk,
        COUNT(se.event_id)                              AS total_swaps,
        SUM(se.revenue_inr)                             AS total_revenue_inr,
        AVG(se.energy_delivered_kwh)                    AS avg_energy_kwh,
        MIN(se.timestamp)                               AS first_swap_at,
        MAX(se.timestamp)                               AS last_swap_at
    FROM swap_events se
    INNER JOIN batteries b ON se.battery_out_id = b.battery_id
    WHERE se.outcome = 'success'
      AND se.timestamp >= CURRENT_DATE - INTERVAL '90 days'
    GROUP BY se.battery_out_id, b.chemistry_type, b.current_health,
             b.cycle_count, b.replacement_risk
),
ranked_batteries AS (
    SELECT
        *,
        RANK() OVER (ORDER BY total_revenue_inr DESC)       AS revenue_rank,
        RANK() OVER (ORDER BY total_swaps DESC)             AS swaps_rank,
        NTILE(5)  OVER (ORDER BY total_revenue_inr DESC)   AS revenue_quintile,
        SUM(total_revenue_inr) OVER ()                     AS network_total_revenue,
        total_revenue_inr / SUM(total_revenue_inr) OVER () AS revenue_share
    FROM battery_swap_stats
)
SELECT
    battery_id,
    chemistry_type,
    ROUND(current_health::numeric * 100, 1)            AS soh_pct,
    cycle_count,
    replacement_risk,
    total_swaps,
    ROUND(total_revenue_inr::numeric, 0)               AS revenue_inr,
    ROUND((revenue_share * 100)::numeric, 3)           AS revenue_share_pct,
    revenue_rank,
    revenue_quintile
FROM ranked_batteries
ORDER BY revenue_rank
LIMIT 50;


-- ── 2. Station Demand vs. Inventory — Rolling Trend ──────────
-- Uses CTEs + multiple window functions

WITH daily_demand AS (
    SELECT
        se.station_id,
        st.name,
        st.city,
        DATE(se.timestamp)                              AS swap_date,
        COUNT(*)  FILTER (WHERE se.outcome = 'success') AS successful_swaps,
        SUM(se.revenue_inr)                             AS daily_revenue
    FROM swap_events se
    INNER JOIN stations st ON se.station_id = st.station_id
    WHERE se.timestamp >= CURRENT_DATE - INTERVAL '60 days'
    GROUP BY se.station_id, st.name, st.city, DATE(se.timestamp)
),
windowed AS (
    SELECT
        station_id,
        name,
        city,
        swap_date,
        successful_swaps,
        daily_revenue,
        AVG(successful_swaps) OVER (
            PARTITION BY station_id
            ORDER BY swap_date
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                                               AS rolling_7d_avg_swaps,
        AVG(successful_swaps) OVER (
            PARTITION BY station_id
            ORDER BY swap_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                               AS rolling_30d_avg_swaps,
        SUM(daily_revenue) OVER (
            PARTITION BY station_id
            ORDER BY swap_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                               AS rolling_30d_revenue,
        RANK() OVER (PARTITION BY swap_date ORDER BY successful_swaps DESC)
                                                        AS daily_demand_rank
    FROM daily_demand
)
SELECT *
FROM windowed
WHERE swap_date = CURRENT_DATE - 1
ORDER BY successful_swaps DESC;


-- ── 3. Battery Degradation by Chemistry Cohort ──────────────
-- Percentile analysis per chemistry type and manufacture quarter

WITH battery_cohorts AS (
    SELECT
        b.battery_id,
        b.chemistry_type,
        DATE_TRUNC('quarter', b.manufacturing_date)::date   AS manufacture_quarter,
        b.cycle_count,
        b.current_health,
        b.thermal_stress_score,
        b.replacement_risk,
        (CURRENT_DATE - b.manufacturing_date)               AS age_days,
        CASE WHEN b.cycle_count > 0
             THEN (1.0 - b.current_health) / b.cycle_count * 100
             ELSE 0 END                                     AS degradation_per_100_cycles
    FROM batteries b
    WHERE b.status IN ('active', 'charging')
)
SELECT
    chemistry_type,
    manufacture_quarter,
    COUNT(*)                                            AS cohort_size,
    ROUND(AVG(current_health)::numeric, 4)             AS avg_soh,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP
          (ORDER BY current_health)::numeric, 4)       AS median_soh,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP
          (ORDER BY current_health)::numeric, 4)       AS p25_soh,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP
          (ORDER BY current_health)::numeric, 4)       AS p75_soh,
    ROUND(AVG(degradation_per_100_cycles)::numeric, 5) AS avg_deg_rate,
    COUNT(*) FILTER (WHERE replacement_risk = 'critical') AS critical_count,
    ROUND(AVG(age_days)::numeric, 0)                   AS avg_age_days
FROM battery_cohorts
GROUP BY chemistry_type, manufacture_quarter
ORDER BY chemistry_type, manufacture_quarter;


-- ── 4. Hourly Swap Pattern — Heatmap Data ────────────────────
-- DOW × Hour demand matrix for visualization

SELECT
    EXTRACT(DOW FROM timestamp)::int        AS day_of_week,
    EXTRACT(HOUR FROM timestamp)::int       AS hour_of_day,
    COUNT(*)                                AS total_swaps,
    COUNT(*) FILTER (WHERE outcome = 'success') AS successful_swaps,
    ROUND(AVG(revenue_inr)::numeric, 2)     AS avg_revenue,
    ROUND(AVG(duration_seconds)::numeric, 0) AS avg_duration_s
FROM swap_events
WHERE timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY EXTRACT(DOW FROM timestamp), EXTRACT(HOUR FROM timestamp)
ORDER BY day_of_week, hour_of_day;


-- ── 5. Network Anomaly Summary (last 7 days) ─────────────────

SELECT
    entity_type,
    anomaly_type,
    severity,
    COUNT(*)                                AS anomaly_count,
    ROUND(AVG(score)::numeric, 3)           AS avg_score,
    MAX(score)                              AS max_score,
    MIN(detected_at)                        AS first_detected,
    MAX(detected_at)                        AS last_detected,
    COUNT(*) FILTER (WHERE is_resolved)     AS resolved_count
FROM anomaly_records
WHERE detected_at >= NOW() - INTERVAL '7 days'
GROUP BY entity_type, anomaly_type, severity
ORDER BY severity DESC, anomaly_count DESC;


-- ── 6. Station Inventory Risk Score ──────────────────────────
-- Combines utilization, forecasted demand gap, and recent outage history

WITH station_metrics AS (
    SELECT
        st.station_id,
        st.name,
        st.city,
        st.capacity,
        st.inventory_count,
        st.status,
        st.inventory_count::float / NULLIF(st.capacity, 0) AS util_rate,
        COALESCE(fc.avg_forecast, 0)                        AS forecasted_demand,
        CASE WHEN st.last_outage_at >= NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END AS recent_outage
    FROM stations st
    LEFT JOIN (
        SELECT station_id, AVG(predicted_swaps) AS avg_forecast
        FROM daily_demand_forecasts
        WHERE forecast_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
        GROUP BY station_id
    ) fc ON st.station_id = fc.station_id
),
risk_scored AS (
    SELECT
        *,
        -- Composite risk: low inventory + high demand + recent outage
        (CASE WHEN util_rate < 0.20 THEN 40
              WHEN util_rate < 0.35 THEN 25
              WHEN util_rate < 0.50 THEN 10
              ELSE 0 END
         + CASE WHEN inventory_count < forecasted_demand * 0.5 THEN 30 ELSE 0 END
         + recent_outage * 20
         + CASE WHEN status = 'offline' THEN 30
                WHEN status = 'degraded' THEN 15
                ELSE 0 END
        )                                                   AS risk_score
    FROM station_metrics
)
SELECT
    station_id,
    name,
    city,
    status,
    inventory_count,
    capacity,
    ROUND(util_rate::numeric * 100, 1)                      AS util_pct,
    ROUND(forecasted_demand::numeric, 0)                    AS forecast_demand_7d,
    risk_score,
    CASE WHEN risk_score >= 60 THEN 'CRITICAL'
         WHEN risk_score >= 35 THEN 'HIGH'
         WHEN risk_score >= 15 THEN 'MODERATE'
         ELSE 'LOW' END                                     AS inventory_risk
FROM risk_scored
ORDER BY risk_score DESC
LIMIT 30;
