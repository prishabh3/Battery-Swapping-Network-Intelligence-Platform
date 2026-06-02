import pytest
import numpy as np

from analytics.forecasting.demand_forecaster import FeatureEngineering, DemandForecaster


class TestFeatureEngineering:
    def test_feature_columns_correct_count(self):
        cols = FeatureEngineering.feature_columns()
        assert len(cols) > 20

    def test_build_features_returns_dataframe(self):
        import pandas as pd
        from datetime import date, timedelta

        dates = pd.date_range(end=date.today(), periods=100, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "daily_swaps": np.random.default_rng(42).integers(30, 120, 100),
            "station_id": "STN-001",
        })
        result = FeatureEngineering.build_features(df)
        assert len(result) > 0
        for col in ["lag_1", "lag_7", "roll_mean_7", "dow_sin", "seasonal_index"]:
            assert col in result.columns

    def test_features_no_nan(self):
        import pandas as pd
        from datetime import date, timedelta

        dates = pd.date_range(end=date.today(), periods=90, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "daily_swaps": np.random.default_rng(1).integers(20, 100, 90),
            "station_id": "STN-002",
        })
        result = FeatureEngineering.build_features(df)
        feature_cols = [c for c in FeatureEngineering.feature_columns() if c in result.columns]
        assert result[feature_cols].isna().sum().sum() == 0


class TestDemandForecaster:
    def test_forecast_returns_correct_horizon(self):
        forecaster = DemandForecaster()
        result = forecaster.forecast("STN-TEST-001", horizon_days=7)
        assert len(result["forecast"]) == 7

    def test_forecast_positive_predictions(self):
        forecaster = DemandForecaster()
        result = forecaster.forecast("STN-TEST-002", horizon_days=5)
        for pt in result["forecast"]:
            assert pt["predicted_swaps"] >= 0

    def test_forecast_confidence_interval_ordered(self):
        forecaster = DemandForecaster()
        result = forecaster.forecast("STN-TEST-003", horizon_days=7)
        for pt in result["forecast"]:
            assert pt["lower_bound"] <= pt["predicted_swaps"] <= pt["upper_bound"]

    def test_forecast_metrics_present(self):
        forecaster = DemandForecaster()
        result = forecaster.forecast("STN-TEST-004", horizon_days=3)
        for key in ["mae", "rmse", "mape", "model"]:
            assert key in result
        assert result["mae"] >= 0
        assert result["rmse"] >= 0
        assert result["mape"] >= 0

    def test_network_summary_returns_7_days(self):
        forecaster = DemandForecaster()
        summary = forecaster.network_summary_forecast()
        assert len(summary["network_daily_forecast"]) == 7
        for d in summary["network_daily_forecast"]:
            assert d["predicted_swaps"] > 0
