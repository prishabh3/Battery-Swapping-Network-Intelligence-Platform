import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

NETWORK_KPI_QUERY = text("""
WITH today_swaps AS (
    SELECT COUNT(*) AS cnt, COALESCE(SUM(revenue_inr), 0) AS rev
    FROM swap_events
    WHERE DATE(timestamp) = CURRENT_DATE AND outcome = 'success'
),
yesterday_swaps AS (
    SELECT COUNT(*) AS cnt
    FROM swap_events
    WHERE DATE(timestamp) = CURRENT_DATE - 1 AND outcome = 'success'
),
week_swaps AS (
    SELECT COUNT(*) AS cnt
    FROM swap_events
    WHERE timestamp >= NOW() - INTERVAL '7 days' AND outcome = 'success'
),
month_swaps AS (
    SELECT COUNT(*) AS cnt, COALESCE(SUM(revenue_inr), 0) AS rev
    FROM swap_events
    WHERE timestamp >= NOW() - INTERVAL '30 days' AND outcome = 'success'
),
battery_stats AS (
    SELECT
        COUNT(*) FILTER (WHERE status = 'active') AS active_cnt,
        COUNT(*) FILTER (WHERE status IN ('active','charging')) AS in_service,
        COUNT(*) FILTER (WHERE replacement_risk = 'critical') AS critical_cnt,
        AVG(current_health) FILTER (WHERE status = 'active') AS avg_soh
    FROM batteries
),
station_stats AS (
    SELECT
        COUNT(*) FILTER (WHERE status = 'operational') AS active_cnt,
        COUNT(*) FILTER (WHERE status = 'offline') AS offline_cnt,
        COALESCE(SUM(inventory_count), 0) AS total_inv,
        COALESCE(AVG(inventory_count::float / NULLIF(capacity, 0)), 0) AS avg_util
    FROM stations
)
SELECT
    t.cnt AS swaps_today,
    t.rev AS rev_today,
    y.cnt AS swaps_yesterday,
    w.cnt AS swaps_week,
    m.cnt AS swaps_month,
    m.rev AS rev_month,
    b.active_cnt, b.in_service, b.critical_cnt, b.avg_soh,
    s.active_cnt AS active_stations,
    s.offline_cnt,
    s.total_inv,
    s.avg_util
FROM today_swaps t, yesterday_swaps y, week_swaps w, month_swaps m, battery_stats b, station_stats s
""")

STATION_RANKING_QUERY = text("""
WITH station_metrics AS (
    SELECT
        st.station_id,
        st.name,
        st.city,
        st.capacity,
        st.inventory_count,
        st.status,
        COUNT(se.event_id) AS total_swaps_30d,
        COALESCE(SUM(se.revenue_inr), 0) AS revenue_30d,
        COALESCE(AVG(se.duration_seconds), 0) AS avg_swap_duration,
        st.inventory_count::float / NULLIF(st.capacity, 0) AS util_rate,
        RANK() OVER (ORDER BY COUNT(se.event_id) DESC) AS demand_rank
    FROM stations st
    LEFT JOIN swap_events se
        ON st.station_id = se.station_id
        AND se.timestamp >= NOW() - INTERVAL '30 days'
        AND se.outcome = 'success'
    GROUP BY st.station_id, st.name, st.city, st.capacity, st.inventory_count, st.status
)
SELECT * FROM station_metrics
ORDER BY total_swaps_30d DESC
LIMIT 20
""")

ROLLING_DEMAND_QUERY = text("""
SELECT
    DATE(timestamp) AS swap_date,
    station_id,
    COUNT(*) AS daily_swaps,
    AVG(COUNT(*)) OVER (
        PARTITION BY station_id
        ORDER BY DATE(timestamp)
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_avg,
    AVG(COUNT(*)) OVER (
        PARTITION BY station_id
        ORDER BY DATE(timestamp)
        ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ) AS rolling_30d_avg
FROM swap_events
WHERE outcome = 'success'
  AND timestamp >= NOW() - INTERVAL '60 days'
GROUP BY DATE(timestamp), station_id
ORDER BY swap_date DESC, station_id
""")


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_network_kpis(self) -> dict[str, Any]:
        result = await self._session.execute(NETWORK_KPI_QUERY)
        row = result.mappings().first()
        if not row:
            return {}

        swaps_today = row["swaps_today"] or 0
        swaps_yesterday = row["swaps_yesterday"] or 0
        pct_change = (
            ((swaps_today - swaps_yesterday) / swaps_yesterday * 100)
            if swaps_yesterday > 0 else 0.0
        )

        return {
            "total_swaps_today": swaps_today,
            "total_swaps_week": row["swaps_week"] or 0,
            "total_swaps_month": row["swaps_month"] or 0,
            "active_batteries": row["active_cnt"] or 0,
            "batteries_in_service": row["in_service"] or 0,
            "active_stations": row["active_stations"] or 0,
            "offline_stations": row["offline_cnt"] or 0,
            "critical_batteries": row["critical_cnt"] or 0,
            "avg_soh_network": round(float(row["avg_soh"] or 0.85), 4),
            "total_inventory": row["total_inv"] or 0,
            "network_utilization_rate": round(float(row["avg_util"] or 0), 4),
            "estimated_revenue_today_inr": float(row["rev_today"] or 0),
            "estimated_revenue_month_inr": float(row["rev_month"] or 0),
            "swaps_change_vs_yesterday_pct": round(pct_change, 2),
        }

    async def get_station_rankings(self) -> list[dict]:
        result = await self._session.execute(STATION_RANKING_QUERY)
        return [dict(r) for r in result.mappings().all()]

    async def get_rolling_demand_trends(self) -> list[dict]:
        result = await self._session.execute(ROLLING_DEMAND_QUERY)
        return [dict(r) for r in result.mappings().all()]
