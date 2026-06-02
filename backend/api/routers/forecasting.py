from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

router = APIRouter(prefix="/forecasting", tags=["Forecasting"])


class ForecastRequest(BaseModel):
    station_id: str
    horizon_days: int = 7


class ForecastPoint(BaseModel):
    date: str
    predicted_swaps: float
    lower_bound: float
    upper_bound: float
    day_of_week: str


class ForecastResponse(BaseModel):
    station_id: str
    model: str
    mae: float
    rmse: float
    mape: float
    forecast: list[ForecastPoint]


@router.post("/demand", response_model=ForecastResponse)
async def forecast_demand(request: ForecastRequest):
    """Generate demand forecast for a station."""
    try:
        from analytics.forecasting.demand_forecaster import DemandForecaster
        forecaster = DemandForecaster()
        result = forecaster.forecast(
            station_id=request.station_id,
            horizon_days=request.horizon_days,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecasting failed: {str(e)}")


@router.get("/network-summary")
async def get_network_forecast_summary():
    """Return aggregate demand forecast across the network."""
    try:
        from analytics.forecasting.demand_forecaster import DemandForecaster
        forecaster = DemandForecaster()
        return forecaster.network_summary_forecast()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
