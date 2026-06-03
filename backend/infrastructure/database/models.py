from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum as SAEnum, Float, ForeignKey,
    Integer, String, Text, Index, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class BatteryModel(Base):
    __tablename__ = "batteries"

    battery_id = Column(String(36), primary_key=True)
    manufacturing_date = Column(Date, nullable=False)
    chemistry_type = Column(SAEnum("LFP", "NMC", "LTO", "LMFP", name="chemistry_type_enum"), nullable=False)
    cycle_count = Column(Integer, default=0, nullable=False)
    current_health = Column(Float, nullable=False)
    nominal_capacity_kwh = Column(Float, nullable=False)
    current_station_id = Column(String(36), ForeignKey("stations.station_id"), nullable=True, index=True)
    status = Column(SAEnum("active", "in_transit", "charging", "retired", "maintenance", name="battery_status_enum"), nullable=False)
    thermal_stress_score = Column(Float, default=0.0)
    replacement_risk = Column(SAEnum("low", "moderate", "high", "critical", name="replacement_risk_enum"), default="low")
    avg_temperature = Column(Float, default=25.0)
    peak_temperature = Column(Float, default=35.0)
    last_swap_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    station = relationship("StationModel", back_populates="batteries", foreign_keys=[current_station_id])
    swap_events_in = relationship("SwapEventModel", back_populates="battery_in", foreign_keys="SwapEventModel.battery_in_id")
    swap_events_out = relationship("SwapEventModel", back_populates="battery_out", foreign_keys="SwapEventModel.battery_out_id")

    __table_args__ = (
        Index("ix_batteries_status_health", "status", "current_health"),
        Index("ix_batteries_risk", "replacement_risk"),
    )


class StationModel(Base):
    __tablename__ = "stations"

    station_id = Column(String(36), primary_key=True)
    name = Column(String(200), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    state = Column(String(100), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    capacity = Column(Integer, nullable=False)
    inventory_count = Column(Integer, default=0, nullable=False)
    charging_slots = Column(Integer, nullable=False)
    status = Column(SAEnum("operational", "degraded", "offline", "maintenance", name="station_status_enum"), nullable=False)
    operator_name = Column(String(200), nullable=False)
    pincode = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    last_outage_at = Column(DateTime, nullable=True)

    batteries = relationship("BatteryModel", back_populates="station", foreign_keys="BatteryModel.current_station_id")
    swap_events = relationship("SwapEventModel", back_populates="station")

    __table_args__ = (
        Index("ix_stations_city_status", "city", "status"),
    )


class VehicleModel(Base):
    __tablename__ = "vehicles"

    vehicle_id = Column(String(36), primary_key=True)
    fleet_type = Column(SAEnum("2W", "3W", "LCV", name="fleet_type_enum"), nullable=False)
    region = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    operator_id = Column(String(36), nullable=False, index=True)
    registration_number = Column(String(20), unique=True, nullable=False)
    status = Column(SAEnum("active", "inactive", "maintenance", name="vehicle_status_enum"), nullable=False)
    total_swaps = Column(Integer, default=0)
    total_distance_km = Column(Float, default=0.0)
    avg_daily_swaps = Column(Float, default=0.0)
    last_swap_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    swap_events = relationship("SwapEventModel", back_populates="vehicle")


class SwapEventModel(Base):
    __tablename__ = "swap_events"

    event_id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    station_id = Column(String(36), ForeignKey("stations.station_id"), nullable=False, index=True)
    battery_in_id = Column(String(36), ForeignKey("batteries.battery_id"), nullable=False)
    battery_out_id = Column(String(36), ForeignKey("batteries.battery_id"), nullable=False)
    vehicle_id = Column(String(36), ForeignKey("vehicles.vehicle_id"), nullable=False, index=True)
    duration_seconds = Column(Integer, nullable=False)
    energy_delivered_kwh = Column(Float, nullable=False)
    outcome = Column(SAEnum("success", "failed_inventory", "failed_station_offline", "failed_battery_health", "cancelled", name="swap_outcome_enum"), nullable=False)
    revenue_inr = Column(Float, nullable=False)
    soh_at_swap = Column(Float, nullable=False)
    is_anomalous = Column(Boolean, default=False)
    anomaly_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    station = relationship("StationModel", back_populates="swap_events")
    battery_in = relationship("BatteryModel", back_populates="swap_events_in", foreign_keys=[battery_in_id])
    battery_out = relationship("BatteryModel", back_populates="swap_events_out", foreign_keys=[battery_out_id])
    vehicle = relationship("VehicleModel", back_populates="swap_events")

    __table_args__ = (
        Index("ix_swap_events_timestamp_station", "timestamp", "station_id"),
        Index("ix_swap_events_outcome", "outcome"),
        Index("ix_swap_events_anomalous", "is_anomalous"),
    )


class DailyDemandForecastModel(Base):
    __tablename__ = "daily_demand_forecasts"

    forecast_id = Column(String(36), primary_key=True)
    station_id = Column(String(36), ForeignKey("stations.station_id"), nullable=False, index=True)
    forecast_date = Column(Date, nullable=False)
    predicted_swaps = Column(Float, nullable=False)
    confidence_lower = Column(Float, nullable=False)
    confidence_upper = Column(Float, nullable=False)
    model_version = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("station_id", "forecast_date", "model_version", name="uq_forecast_station_date"),
    )


class InventoryTransferModel(Base):
    __tablename__ = "inventory_transfers"

    transfer_id = Column(String(36), primary_key=True)
    from_station_id = Column(String(36), ForeignKey("stations.station_id"), nullable=False)
    to_station_id = Column(String(36), ForeignKey("stations.station_id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    priority = Column(String(20), nullable=False)
    status = Column(String(20), default="pending")
    recommended_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    executed_at = Column(DateTime, nullable=True)
    reason = Column(Text, nullable=True)


class AnomalyRecordModel(Base):
    __tablename__ = "anomaly_records"

    anomaly_id = Column(String(36), primary_key=True)
    entity_type = Column(String(20), nullable=False)    # battery | station | swap
    entity_id = Column(String(36), nullable=False)
    anomaly_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)
    score = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    is_resolved = Column(Boolean, default=False)

    __table_args__ = (
        Index("ix_anomalies_entity", "entity_type", "entity_id"),
        Index("ix_anomalies_severity", "severity"),
    )
