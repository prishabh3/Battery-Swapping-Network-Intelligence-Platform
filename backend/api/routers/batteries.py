from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.api.dependencies import get_battery_service, CurrentUser
from backend.application.services.battery_service import BatteryService
from backend.application.dtos.battery_dto import BatteryResponse, BatteryHealthReport, BatteryListResponse

router = APIRouter(prefix="/batteries", tags=["Batteries"])


def _battery_to_response(b) -> BatteryResponse:
    return BatteryResponse(
        battery_id=b.battery_id,
        manufacturing_date=b.manufacturing_date,
        chemistry_type=b.chemistry_type.value,
        cycle_count=b.cycle_count,
        current_health=b.current_health,
        nominal_capacity_kwh=b.nominal_capacity_kwh,
        current_station_id=b.current_station_id,
        status=b.status.value,
        thermal_stress_score=b.thermal_stress_score,
        replacement_risk=b.replacement_risk.value,
        avg_temperature=b.avg_temperature,
        peak_temperature=b.peak_temperature,
        last_swap_at=b.last_swap_at,
        age_days=b.age_days,
        soh_category=b.soh_category,
        is_eligible_for_swap=b.is_eligible_for_swap,
    )


@router.get("/", response_model=BatteryListResponse)
async def list_batteries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    service: BatteryService = Depends(get_battery_service),
):
    offset = (page - 1) * page_size
    batteries = await service.list_batteries(limit=page_size, offset=offset)
    return BatteryListResponse(
        total=len(batteries),
        batteries=[_battery_to_response(b) for b in batteries],
        page=page,
        page_size=page_size,
    )


@router.get("/critical", response_model=list[BatteryResponse])
async def list_critical_batteries(
    service: BatteryService = Depends(get_battery_service),
):
    batteries = await service.get_critical_batteries()
    return [_battery_to_response(b) for b in batteries]


@router.get("/degradation-candidates", response_model=list[BatteryResponse])
async def list_degradation_candidates(
    soh_threshold: float = Query(default=0.75, ge=0.5, le=1.0),
    service: BatteryService = Depends(get_battery_service),
):
    batteries = await service.get_degradation_candidates(soh_threshold)
    return [_battery_to_response(b) for b in batteries]


@router.get("/{battery_id}", response_model=BatteryResponse)
async def get_battery(
    battery_id: str,
    service: BatteryService = Depends(get_battery_service),
):
    battery = await service.get_battery(battery_id)
    if not battery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Battery not found")
    return _battery_to_response(battery)


@router.get("/{battery_id}/health-report", response_model=BatteryHealthReport)
async def get_health_report(
    battery_id: str,
    service: BatteryService = Depends(get_battery_service),
):
    report = await service.generate_health_report(battery_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Battery not found")
    return report
