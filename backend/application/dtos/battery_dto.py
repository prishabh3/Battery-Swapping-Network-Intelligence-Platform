from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class BatteryResponse(BaseModel):
    battery_id: str
    manufacturing_date: date
    chemistry_type: str
    cycle_count: int
    current_health: float
    nominal_capacity_kwh: float
    current_station_id: Optional[str]
    status: str
    thermal_stress_score: float
    replacement_risk: str
    avg_temperature: float
    peak_temperature: float
    last_swap_at: Optional[datetime]
    age_days: int
    soh_category: str
    is_eligible_for_swap: bool

    model_config = {"from_attributes": True}


class BatteryHealthReport(BaseModel):
    battery_id: str
    current_health: float
    soh_category: str
    cycle_count: int
    thermal_stress_score: float
    replacement_risk: str
    degradation_rate_per_100_cycles: float
    estimated_remaining_cycles: int
    estimated_end_of_life_date: Optional[date]
    recommendations: list[str]


class BatteryListResponse(BaseModel):
    total: int
    batteries: list[BatteryResponse]
    page: int
    page_size: int


class StationResponse(BaseModel):
    station_id: str
    name: str
    city: str
    state: str
    latitude: float
    longitude: float
    capacity: int
    inventory_count: int
    charging_slots: int
    status: str
    operator_name: str
    pincode: str
    utilization_rate: float
    utilization_tier: str
    can_fulfill_swap: bool

    model_config = {"from_attributes": True}


class SwapEventResponse(BaseModel):
    event_id: str
    timestamp: datetime
    station_id: str
    battery_in_id: str
    battery_out_id: str
    vehicle_id: str
    duration_seconds: int
    energy_delivered_kwh: float
    outcome: str
    revenue_inr: float
    soh_at_swap: float
    is_anomalous: bool
    anomaly_score: float


class NetworkKPIResponse(BaseModel):
    total_swaps_today: int
    total_swaps_week: int
    total_swaps_month: int
    active_batteries: int
    batteries_in_service: int
    active_stations: int
    offline_stations: int
    critical_batteries: int
    avg_soh_network: float
    total_inventory: int
    network_utilization_rate: float
    estimated_revenue_today_inr: float
    estimated_revenue_month_inr: float
    swaps_change_vs_yesterday_pct: float
