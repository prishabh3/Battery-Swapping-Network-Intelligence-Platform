from fastapi import APIRouter, Depends

from backend.api.dependencies import get_analytics_service
from backend.application.services.analytics_service import AnalyticsService
from backend.application.dtos.battery_dto import NetworkKPIResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/kpis", response_model=NetworkKPIResponse)
async def get_network_kpis(service: AnalyticsService = Depends(get_analytics_service)):
    data = await service.get_network_kpis()
    return NetworkKPIResponse(**data) if data else NetworkKPIResponse(
        total_swaps_today=0, total_swaps_week=0, total_swaps_month=0,
        active_batteries=0, batteries_in_service=0, active_stations=0,
        offline_stations=0, critical_batteries=0, avg_soh_network=0.0,
        total_inventory=0, network_utilization_rate=0.0,
        estimated_revenue_today_inr=0.0, estimated_revenue_month_inr=0.0,
        swaps_change_vs_yesterday_pct=0.0,
    )


@router.get("/station-rankings")
async def get_station_rankings(service: AnalyticsService = Depends(get_analytics_service)):
    return await service.get_station_rankings()


@router.get("/demand-trends")
async def get_rolling_demand_trends(service: AnalyticsService = Depends(get_analytics_service)):
    return await service.get_rolling_demand_trends()
