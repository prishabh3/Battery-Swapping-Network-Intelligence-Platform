from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/optimization", tags=["Optimization"])


class OptimizationRequest(BaseModel):
    horizon_days: int = 1
    max_transfer_distance_km: float = 50.0


class TransferRecommendation(BaseModel):
    transfer_id: str
    from_station_id: str
    from_station_name: str
    to_station_id: str
    to_station_name: str
    quantity: int
    priority: str
    urgency_score: float
    reason: str
    distance_km: float


class OptimizationResult(BaseModel):
    run_id: str
    total_transfers: int
    batteries_to_redistribute: int
    estimated_shortfall_prevented: int
    recommendations: list[TransferRecommendation]
    solver_status: str


@router.post("/inventory", response_model=OptimizationResult)
async def optimize_inventory(request: OptimizationRequest):
    """Run LP-based inventory optimization across the network."""
    try:
        from analytics.optimization.inventory_optimizer import InventoryOptimizer
        optimizer = InventoryOptimizer()
        result = optimizer.optimize(
            horizon_days=request.horizon_days,
            max_transfer_distance_km=request.max_transfer_distance_km,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Optimization failed: {str(e)}")


@router.get("/transfer-plan")
async def get_transfer_plan():
    """Return the most recent inventory transfer plan."""
    try:
        from analytics.optimization.inventory_optimizer import InventoryOptimizer
        optimizer = InventoryOptimizer()
        return optimizer.get_latest_plan()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
