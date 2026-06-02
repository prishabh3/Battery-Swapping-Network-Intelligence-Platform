from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/simulation", tags=["Chairman's Office Simulation"])


class NewStationScenario(BaseModel):
    city: str
    num_new_stations: int
    avg_capacity_per_station: int = 150
    target_utilization: float = 0.65


class DemandShockScenario(BaseModel):
    demand_increase_pct: float
    affected_cities: Optional[list[str]] = None


class ScenarioResult(BaseModel):
    scenario_name: str
    inputs: dict
    outputs: dict
    recommendations: list[str]
    financial_impact: dict
    risk_assessment: str


@router.post("/new-stations", response_model=ScenarioResult)
async def simulate_new_stations(scenario: NewStationScenario):
    """Simulate impact of opening new stations in a city."""
    from analytics.optimization.inventory_optimizer import ScenarioSimulator

    sim = ScenarioSimulator()
    result = sim.simulate_new_stations(
        city=scenario.city,
        num_stations=scenario.num_new_stations,
        avg_capacity=scenario.avg_capacity_per_station,
        target_utilization=scenario.target_utilization,
    )
    return result


@router.post("/demand-shock", response_model=ScenarioResult)
async def simulate_demand_shock(scenario: DemandShockScenario):
    """Simulate impact of demand increase on battery inventory."""
    from analytics.optimization.inventory_optimizer import ScenarioSimulator

    sim = ScenarioSimulator()
    result = sim.simulate_demand_shock(
        demand_increase_pct=scenario.demand_increase_pct,
        affected_cities=scenario.affected_cities,
    )
    return result


@router.post("/battery-retirement", response_model=ScenarioResult)
async def simulate_battery_retirement(retirement_pct: float = 0.10):
    """Simulate retiring a fraction of the battery fleet and assess network impact."""
    from analytics.optimization.inventory_optimizer import ScenarioSimulator

    sim = ScenarioSimulator()
    return sim.simulate_battery_retirement(retirement_pct)
