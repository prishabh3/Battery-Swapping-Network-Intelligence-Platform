"""
XGBoost-based demand forecasting for battery swap stations.
Forecasts daily and hourly swap demand with confidence intervals.
"""
import logging
import os
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    logger.warning("XGBoost not available — falling back to gradient boosting")


CITY_DEMAND_MULTIPLIERS = {
    "Mumbai": 1.6, "Delhi": 1.5, "Bengaluru": 1.4, "Hyderabad": 1.2,
    "Chennai": 1.1, "Pune": 1.0, "Ahmedabad": 0.9, "Jaipur": 0.85,
    "Lucknow": 0.80, "Kochi": 0.75, "Kolkata": 1.1, "Surat": 0.9,
}


class FeatureEngineering:
    """Generate time-series features for demand forecasting."""

    @staticmethod
    def build_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df["day_of_week"] = df["date"].dt.dayofweek
        df["day_of_month"] = df["date"].dt.day
        df["month"] = df["date"].dt.month
        df["quarter"] = df["date"].dt.quarter
        df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
        df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
        df["is_month_start"] = df["date"].dt.is_month_start.astype(int)
        df["is_month_end"] = df["date"].dt.is_month_end.astype(int)

        # Indian public holiday proximity (approximate)
        holiday_months = [1, 8, 10, 11]
        df["near_holiday"] = df["month"].isin(holiday_months).astype(int)

        # Cyclical encoding
        df["dow_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["dow_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

        # Seasonal demand: peaks in summer
        df["seasonal_index"] = 1.0 + 0.2 * np.sin(np.pi * (df["month"] - 1) / 6)

        # Lag features
        for lag in [1, 7, 14, 21, 28]:
            df[f"lag_{lag}"] = df["daily_swaps"].shift(lag)

        # Rolling window features
        for window in [7, 14, 30]:
            df[f"roll_mean_{window}"] = df["daily_swaps"].shift(1).rolling(window).mean()
            df[f"roll_std_{window}"] = df["daily_swaps"].shift(1).rolling(window).std()
            df[f"roll_max_{window}"] = df["daily_swaps"].shift(1).rolling(window).max()

        df["ewm_7"] = df["daily_swaps"].shift(1).ewm(span=7).mean()
        df["ewm_30"] = df["daily_swaps"].shift(1).ewm(span=30).mean()

        return df.dropna()

    @staticmethod
    def feature_columns() -> list[str]:
        return [
            "day_of_week", "day_of_month", "month", "quarter", "week_of_year",
            "is_weekend", "is_month_start", "is_month_end", "near_holiday",
            "dow_sin", "dow_cos", "month_sin", "month_cos", "seasonal_index",
            "lag_1", "lag_7", "lag_14", "lag_21", "lag_28",
            "roll_mean_7", "roll_mean_14", "roll_mean_30",
            "roll_std_7", "roll_std_14", "roll_std_30",
            "roll_max_7", "roll_max_14", "roll_max_30",
            "ewm_7", "ewm_30",
        ]


class DemandForecaster:
    """Per-station XGBoost demand forecaster with time-series cross-validation."""

    # Reduced during tests via BSIP_FAST_MODEL=1 env var
    _N_ESTIMATORS = int(os.environ.get("BSIP_FAST_MODEL", "0")) and 80 or 500

    MODEL_PARAMS = {
        "n_estimators": _N_ESTIMATORS,
        "learning_rate": 0.05,
        "max_depth": 6,
        "min_child_weight": 3,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "n_jobs": -1,
    }

    def __init__(self, model_path: Optional[str] = None) -> None:
        self._models: dict[str, object] = {}
        self._station_stats: dict[str, dict] = {}
        self._trained = False
        self._model_version = "xgb_v1.0"

        if model_path and Path(model_path).exists():
            self._load_models(model_path)

    def _build_model(self):
        if XGB_AVAILABLE:
            return xgb.XGBRegressor(**self.MODEL_PARAMS)
        from sklearn.ensemble import GradientBoostingRegressor
        return GradientBoostingRegressor(
            n_estimators=300, learning_rate=0.05, max_depth=5,
            subsample=0.8, random_state=42,
        )

    def _generate_mock_history(self, station_id: str, n_days: int = 365) -> pd.DataFrame:
        """Generate plausible swap history when DB is unavailable."""
        rng = np.random.default_rng(seed=hash(station_id) % 2**31)
        dates = [date.today() - timedelta(days=n_days - i) for i in range(n_days)]
        base_demand = rng.integers(30, 120)
        records = []
        for d in dates:
            dow_factor = 1.2 if d.weekday() < 5 else 0.8
            month_factor = 1.0 + 0.2 * np.sin(np.pi * (d.month - 1) / 6)
            noise = rng.normal(0, base_demand * 0.1)
            swaps = max(5, int(base_demand * dow_factor * month_factor + noise))
            records.append({"date": pd.Timestamp(d), "daily_swaps": swaps, "station_id": station_id})
        return pd.DataFrame(records)

    def _train_station_model(self, station_id: str, history_df: pd.DataFrame):
        df = FeatureEngineering.build_features(history_df.sort_values("date"))
        features = FeatureEngineering.feature_columns()
        X = df[features]
        y = df["daily_swaps"]

        tscv = TimeSeriesSplit(n_splits=5)
        cv_maes, cv_rmses, cv_mapes = [], [], []

        for train_idx, val_idx in tscv.split(X):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

            m = self._build_model()
            m.fit(X_tr, y_tr)

            preds = m.predict(X_val)
            cv_maes.append(mean_absolute_error(y_val, preds))
            cv_rmses.append(np.sqrt(mean_squared_error(y_val, preds)))
            mape = np.mean(np.abs((y_val - preds) / y_val.clip(lower=1))) * 100
            cv_mapes.append(mape)

        # Final model on all data
        final_model = self._build_model()
        final_model.fit(X, y)

        self._models[station_id] = final_model
        self._station_stats[station_id] = {
            "mae": round(float(np.mean(cv_maes)), 3),
            "rmse": round(float(np.mean(cv_rmses)), 3),
            "mape": round(float(np.mean(cv_mapes)), 3),
            "mean_demand": float(y.mean()),
            "std_demand": float(y.std()),
        }

    def forecast(self, station_id: str, horizon_days: int = 7) -> dict:
        if station_id not in self._models:
            history = self._generate_mock_history(station_id)
            self._train_station_model(station_id, history)

        model = self._models[station_id]
        stats = self._station_stats[station_id]
        history = self._generate_mock_history(station_id)

        # Build future feature rows
        last_date = history["date"].max()
        future_dates = [last_date + timedelta(days=i + 1) for i in range(horizon_days)]

        # Extend history for lag computation
        extended = history.copy()
        for fd in future_dates:
            extended = pd.concat([
                extended,
                pd.DataFrame({"date": [pd.Timestamp(fd)], "daily_swaps": [stats["mean_demand"]],
                              "station_id": [station_id]})
            ], ignore_index=True)

        extended_feat = FeatureEngineering.build_features(extended)
        features = FeatureEngineering.feature_columns()

        forecast_rows = extended_feat[extended_feat["date"].isin([pd.Timestamp(d) for d in future_dates])]
        X_future = forecast_rows[features]
        predictions = model.predict(X_future)

        confidence_width = stats["std_demand"] * 1.645  # 90% CI
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        forecast_points = []
        for i, (fd, pred) in enumerate(zip(future_dates, predictions)):
            pred = max(0.0, float(pred))
            forecast_points.append({
                "date": str(fd),
                "predicted_swaps": round(pred, 1),
                "lower_bound": round(max(0.0, pred - confidence_width), 1),
                "upper_bound": round(pred + confidence_width, 1),
                "day_of_week": day_names[pd.Timestamp(fd).dayofweek],
            })

        return {
            "station_id": station_id,
            "model": self._model_version,
            "mae": stats["mae"],
            "rmse": stats["rmse"],
            "mape": stats["mape"],
            "forecast": forecast_points,
        }

    def network_summary_forecast(self) -> dict:
        """Aggregate 7-day demand forecast across all station archetypes."""
        sample_stations = [f"STN-{i:03d}" for i in range(1, 11)]
        total_by_day: dict[str, float] = {}

        for sid in sample_stations:
            result = self.forecast(sid, horizon_days=7)
            for pt in result["forecast"]:
                total_by_day[pt["date"]] = total_by_day.get(pt["date"], 0) + pt["predicted_swaps"]

        # Scale to network size (120 stations, 10 sampled)
        scale = 12
        return {
            "forecast_generated_at": datetime.utcnow().isoformat(),
            "total_network_stations": 120,
            "network_daily_forecast": [
                {
                    "date": d,
                    "predicted_swaps": round(v * scale, 0),
                    "predicted_revenue_inr": round(v * scale * 15 * 2.0, 0),  # ~₹15/kWh × 2kWh
                }
                for d, v in sorted(total_by_day.items())
            ],
        }
