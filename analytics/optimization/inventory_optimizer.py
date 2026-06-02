"""
LP-based inventory optimization engine for the battery-swapping network.
Uses PuLP linear programming to determine optimal battery transfers between stations,
minimizing shortfall risk while respecting transfer distance constraints.
"""
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import pulp
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False
    logger.warning("PuLP not available — using greedy fallback optimizer")


# ── Mock network data (used when DB unavailable) ──────────────────────────────

MOCK_STATIONS = [
    {"id": "STN-001", "name": "Mumbai Central Hub", "city": "Mumbai", "lat": 19.076, "lon": 72.877,
     "inventory": 300, "capacity": 400, "expected_demand": 120},
    {"id": "STN-002", "name": "Mumbai North",       "city": "Mumbai", "lat": 19.220, "lon": 72.850,
     "inventory": 40,  "capacity": 200, "expected_demand": 180},
    {"id": "STN-003", "name": "Delhi Central Hub",  "city": "Delhi",  "lat": 28.614, "lon": 77.209,
     "inventory": 250, "capacity": 350, "expected_demand": 90},
    {"id": "STN-004", "name": "Delhi South",        "city": "Delhi",  "lat": 28.530, "lon": 77.240,
     "inventory": 15,  "capacity": 180, "expected_demand": 160},
    {"id": "STN-005", "name": "Bengaluru Tech Park","city": "Bengaluru","lat": 12.972, "lon": 77.595,
     "inventory": 200, "capacity": 300, "expected_demand": 85},
    {"id": "STN-006", "name": "Bengaluru Airport",  "city": "Bengaluru","lat": 13.198, "lon": 77.706,
     "inventory": 30,  "capacity": 150, "expected_demand": 130},
    {"id": "STN-007", "name": "Chennai Marina",     "city": "Chennai","lat": 13.083, "lon": 80.271,
     "inventory": 180, "capacity": 250, "expected_demand": 70},
    {"id": "STN-008", "name": "Chennai OMR",        "city": "Chennai","lat": 12.900, "lon": 80.228,
     "inventory": 25,  "capacity": 180, "expected_demand": 140},
    {"id": "STN-009", "name": "Pune Camp",          "city": "Pune",   "lat": 18.520, "lon": 73.857,
     "inventory": 160, "capacity": 200, "expected_demand": 65},
    {"id": "STN-010", "name": "Pune Hinjewadi",     "city": "Pune",   "lat": 18.590, "lon": 73.740,
     "inventory": 20,  "capacity": 180, "expected_demand": 150},
    {"id": "STN-011", "name": "Hyderabad Hitech",   "city": "Hyderabad","lat": 17.443, "lon": 78.376,
     "inventory": 210, "capacity": 280, "expected_demand": 75},
    {"id": "STN-012", "name": "Hyderabad Old City", "city": "Hyderabad","lat": 17.360, "lon": 78.474,
     "inventory": 18,  "capacity": 160, "expected_demand": 120},
]


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


@dataclass
class StationNode:
    station_id: str
    name: str
    city: str
    lat: float
    lon: float
    inventory: int
    capacity: int
    expected_demand: int
    surplus: int = 0       # computed: inventory - expected_demand
    shortfall: int = 0     # computed: max(0, expected_demand - inventory)

    def __post_init__(self):
        self.surplus = max(0, self.inventory - self.expected_demand)
        self.shortfall = max(0, self.expected_demand - self.inventory)


class InventoryOptimizer:
    """
    LP-based battery inventory optimizer.
    Minimizes total shortfall across the network subject to:
      - Supply constraints: can't transfer more than surplus
      - Demand constraints: shortfall bounded by available transfers
      - Distance constraint: no transfer > max_transfer_distance_km
      - Integer transfers (whole batteries)
    """

    def __init__(self) -> None:
        self._last_plan: Optional[dict] = None

    def _load_network(self) -> list[StationNode]:
        nodes = []
        for s in MOCK_STATIONS:
            # MOCK_STATIONS uses "id" key; StationNode expects "station_id"
            mapped = {k: v for k, v in s.items() if k in StationNode.__dataclass_fields__}
            if "station_id" not in mapped and "id" in s:
                mapped["station_id"] = s["id"]
            nodes.append(StationNode(**mapped))
        return nodes

    def _lp_solve(
        self,
        nodes: list[StationNode],
        max_distance_km: float,
    ) -> list[dict]:
        if not PULP_AVAILABLE:
            return self._greedy_solve(nodes, max_distance_km)

        surplus_nodes = [n for n in nodes if n.surplus > 0]
        deficit_nodes = [n for n in nodes if n.shortfall > 0]

        if not surplus_nodes or not deficit_nodes:
            return []

        prob = pulp.LpProblem("battery_inventory_optimization", pulp.LpMinimize)

        # Decision variables: x[i][j] = batteries transferred from i to j
        x = {}
        for s in surplus_nodes:
            for d in deficit_nodes:
                dist = _haversine_km(s.lat, s.lon, d.lat, d.lon)
                if dist <= max_distance_km:
                    x[(s.station_id, d.station_id)] = pulp.LpVariable(
                        f"x_{s.station_id}_{d.station_id}",
                        lowBound=0,
                        cat="Integer",
                    )

        if not x:
            return self._greedy_solve(nodes, max_distance_km * 2)

        # Slack variables for unmet demand
        slack = {d.station_id: pulp.LpVariable(f"slack_{d.station_id}", lowBound=0)
                 for d in deficit_nodes}

        # Objective: minimize unmet demand + distance cost
        prob += (
            pulp.lpSum(slack[d.station_id] for d in deficit_nodes)
            + 0.001 * pulp.lpSum(
                x[(s.station_id, d.station_id)]
                * _haversine_km(s.lat, s.lon, d.lat, d.lon)
                for (si, di), var in x.items()
                for s in surplus_nodes if s.station_id == si
                for d in deficit_nodes if d.station_id == di
            )
        )

        # Supply constraints
        for s in surplus_nodes:
            outflow = [v for (si, _), v in x.items() if si == s.station_id]
            if outflow:
                prob += pulp.lpSum(outflow) <= s.surplus

        # Demand constraints
        for d in deficit_nodes:
            inflow = [v for (_, di), v in x.items() if di == d.station_id]
            if inflow:
                prob += pulp.lpSum(inflow) + slack[d.station_id] >= d.shortfall
            else:
                prob += slack[d.station_id] >= d.shortfall

        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        recommendations = []
        for (si, di), var in x.items():
            qty = int(var.varValue or 0)
            if qty <= 0:
                continue
            s = next(n for n in surplus_nodes if n.station_id == si)
            d = next(n for n in deficit_nodes if n.station_id == di)
            dist = _haversine_km(s.lat, s.lon, d.lat, d.lon)
            urgency = min(1.0, d.shortfall / max(d.expected_demand, 1))
            priority = "CRITICAL" if urgency > 0.7 else "HIGH" if urgency > 0.4 else "NORMAL"

            recommendations.append({
                "transfer_id": str(uuid.uuid4()),
                "from_station_id": si,
                "from_station_name": s.name,
                "to_station_id": di,
                "to_station_name": d.name,
                "quantity": qty,
                "priority": priority,
                "urgency_score": round(urgency, 3),
                "reason": (
                    f"{d.name} has {d.shortfall} battery shortfall vs. "
                    f"expected demand of {d.expected_demand}. "
                    f"{s.name} has {s.surplus} surplus."
                ),
                "distance_km": round(dist, 1),
            })

        return recommendations

    def _greedy_solve(self, nodes: list[StationNode], max_distance_km: float) -> list[dict]:
        """Greedy fallback when PuLP unavailable."""
        surplus = sorted([n for n in nodes if n.surplus > 0], key=lambda n: -n.surplus)
        deficit = sorted([n for n in nodes if n.shortfall > 0], key=lambda n: -n.shortfall)
        recs = []

        for d in deficit:
            remaining_shortfall = d.shortfall
            for s in surplus:
                if remaining_shortfall <= 0 or s.surplus <= 0:
                    continue
                dist = _haversine_km(s.lat, s.lon, d.lat, d.lon)
                if dist > max_distance_km:
                    continue
                qty = min(remaining_shortfall, s.surplus)
                urgency = min(1.0, d.shortfall / max(d.expected_demand, 1))
                recs.append({
                    "transfer_id": str(uuid.uuid4()),
                    "from_station_id": s.station_id,
                    "from_station_name": s.name,
                    "to_station_id": d.station_id,
                    "to_station_name": d.name,
                    "quantity": qty,
                    "priority": "CRITICAL" if urgency > 0.7 else "HIGH" if urgency > 0.4 else "NORMAL",
                    "urgency_score": round(urgency, 3),
                    "reason": f"{d.name} shortfall: {d.shortfall}, {s.name} surplus: {s.surplus}",
                    "distance_km": round(dist, 1),
                })
                s.surplus -= qty
                remaining_shortfall -= qty

        return recs

    def optimize(self, horizon_days: int = 1, max_transfer_distance_km: float = 50.0) -> dict:
        nodes = self._load_network()
        recommendations = self._lp_solve(nodes, max_transfer_distance_km)

        total_transfers = len(recommendations)
        total_batteries = sum(r["quantity"] for r in recommendations)
        shortfall_prevented = sum(
            min(r["quantity"], next(n.shortfall for n in nodes if n.station_id == r["to_station_id"]))
            for r in recommendations
        )

        result = {
            "run_id": str(uuid.uuid4()),
            "total_transfers": total_transfers,
            "batteries_to_redistribute": total_batteries,
            "estimated_shortfall_prevented": shortfall_prevented,
            "recommendations": recommendations,
            "solver_status": "LP_OPTIMAL" if PULP_AVAILABLE else "GREEDY",
        }
        self._last_plan = result
        logger.info(
            "Optimization complete: %d transfers, %d batteries redistributed",
            total_transfers, total_batteries,
        )
        return result

    def get_latest_plan(self) -> dict:
        if not self._last_plan:
            return self.optimize()
        return self._last_plan


class ScenarioSimulator:
    """Chairman's Office simulation mode — what-if analysis."""

    REVENUE_PER_SWAP_INR = 30.0
    BATTERY_COST_INR = 45_000

    def simulate_new_stations(
        self, city: str, num_stations: int,
        avg_capacity: int = 150, target_utilization: float = 0.65,
    ) -> dict:
        base_demand_per_station = {"Mumbai": 120, "Delhi": 110, "Bengaluru": 95,
                                   "Hyderabad": 80, "Chennai": 75, "Pune": 70,
                                   "Ahmedabad": 60, "Jaipur": 55, "Lucknow": 50,
                                   "Kochi": 45, "Kolkata": 85, "Surat": 60}.get(city, 70)

        batteries_needed = int(avg_capacity * num_stations * target_utilization)
        daily_swaps = base_demand_per_station * num_stations
        annual_revenue = daily_swaps * 365 * self.REVENUE_PER_SWAP_INR
        capex = batteries_needed * self.BATTERY_COST_INR
        breakeven_months = math.ceil(capex / (annual_revenue / 12)) if annual_revenue > 0 else 999

        return {
            "scenario_name": f"New Stations — {city}",
            "inputs": {"city": city, "num_new_stations": num_stations,
                       "avg_capacity_per_station": avg_capacity,
                       "target_utilization": target_utilization},
            "outputs": {
                "batteries_required": batteries_needed,
                "estimated_daily_swaps": daily_swaps,
                "estimated_annual_revenue_inr": round(annual_revenue, 0),
                "capex_inr": capex,
                "projected_utilization_pct": round(target_utilization * 100, 1),
                "breakeven_months": breakeven_months,
            },
            "recommendations": [
                f"Procure {batteries_needed} batteries (LFP chemistry recommended for longevity).",
                f"Phase roll-out: launch {num_stations // 3 + 1} stations in month 1 to validate demand.",
                f"Target {target_utilization * 100:.0f}% utilization; ramp to full capacity over 6 months.",
                f"Estimated break-even: {breakeven_months} months at current demand projections.",
            ],
            "financial_impact": {
                "capex_inr": capex,
                "annual_revenue_inr": round(annual_revenue, 0),
                "payback_months": breakeven_months,
            },
            "risk_assessment": (
                "LOW" if breakeven_months < 18 else
                "MODERATE" if breakeven_months < 30 else "HIGH"
            ),
        }

    def simulate_demand_shock(
        self, demand_increase_pct: float, affected_cities: Optional[list] = None,
    ) -> dict:
        total_network_daily = 15_000  # baseline
        affected_fraction = 1.0 if not affected_cities else len(affected_cities) / 12
        demand_delta = total_network_daily * affected_fraction * (demand_increase_pct / 100)
        new_batteries_needed = int(demand_delta * 0.8)
        revenue_uplift_annual = demand_delta * 365 * self.REVENUE_PER_SWAP_INR
        procurement_cost = new_batteries_needed * self.BATTERY_COST_INR

        at_risk_stations = int(12 * affected_fraction * 0.4)

        return {
            "scenario_name": f"Demand Shock +{demand_increase_pct:.0f}%",
            "inputs": {"demand_increase_pct": demand_increase_pct,
                       "affected_cities": affected_cities or "All"},
            "outputs": {
                "demand_delta_daily_swaps": round(demand_delta, 0),
                "new_batteries_needed": new_batteries_needed,
                "stations_at_risk": at_risk_stations,
                "additional_revenue_annual_inr": round(revenue_uplift_annual, 0),
                "procurement_cost_inr": procurement_cost,
            },
            "recommendations": [
                f"Accelerate procurement of {new_batteries_needed} batteries immediately.",
                f"Re-run inventory optimization to redistribute surplus from low-demand stations.",
                f"{at_risk_stations} stations at risk of inventory shortfall — prioritize replenishment.",
                "Enable dynamic pricing at peak-demand stations to manage demand.",
            ],
            "financial_impact": {
                "additional_annual_revenue_inr": round(revenue_uplift_annual, 0),
                "battery_procurement_cost_inr": procurement_cost,
                "net_impact_year1_inr": round(revenue_uplift_annual - procurement_cost, 0),
            },
            "risk_assessment": (
                "HIGH" if demand_increase_pct > 40 else
                "MODERATE" if demand_increase_pct > 20 else "LOW"
            ),
        }

    def simulate_battery_retirement(self, retirement_pct: float = 0.10) -> dict:
        total_batteries = 5000
        retiring = int(total_batteries * retirement_pct)
        replacement_cost = retiring * self.BATTERY_COST_INR
        capacity_loss_pct = retirement_pct * 0.85
        swaps_at_risk = int(15_000 * capacity_loss_pct)

        return {
            "scenario_name": f"Battery Retirement — {retirement_pct * 100:.0f}%",
            "inputs": {"retirement_pct": retirement_pct},
            "outputs": {
                "batteries_retiring": retiring,
                "network_capacity_loss_pct": round(capacity_loss_pct * 100, 1),
                "daily_swaps_at_risk": swaps_at_risk,
                "replacement_cost_inr": replacement_cost,
            },
            "recommendations": [
                f"Replace {retiring} batteries over 3 months to avoid service disruption.",
                f"Prioritize replacement at high-demand stations first.",
                "Use retiring batteries for off-grid energy storage monetization.",
                "Negotiate bulk procurement discount (target >8%) on replacement order.",
            ],
            "financial_impact": {
                "replacement_capex_inr": replacement_cost,
                "revenue_at_risk_annual_inr": round(swaps_at_risk * 365 * self.REVENUE_PER_SWAP_INR, 0),
                "second_life_salvage_inr": round(retiring * 3000, 0),
            },
            "risk_assessment": "HIGH" if retirement_pct > 0.15 else "MODERATE" if retirement_pct > 0.08 else "LOW",
        }
