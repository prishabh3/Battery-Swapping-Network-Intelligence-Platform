"""
Shared pytest fixtures and test configuration.
Sets BSIP_FAST_MODEL=1 to use 80-tree XGBoost models during tests
instead of production 500-tree models, reducing test runtime ~6×.
"""
import os

os.environ.setdefault("BSIP_FAST_MODEL", "1")
