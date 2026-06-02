import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.api.middleware.logging_middleware import RequestLoggingMiddleware
from backend.api.routers import auth, batteries, analytics, forecasting, optimization, simulation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.getLogger("bsip").info("Battery Swapping Intelligence Platform starting up")
    yield
    logging.getLogger("bsip").info("Shutting down")


app = FastAPI(
    title="Battery Swapping Intelligence Platform",
    description=(
        "Enterprise analytics API for India-wide EV battery-swapping network operations. "
        "Covers demand forecasting, inventory optimization, battery health monitoring, "
        "anomaly detection, and executive decision-support simulation."
    ),
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(batteries.router, prefix=PREFIX)
app.include_router(analytics.router, prefix=PREFIX)
app.include_router(forecasting.router, prefix=PREFIX)
app.include_router(optimization.router, prefix=PREFIX)
app.include_router(simulation.router, prefix=PREFIX)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "BSIP API", "version": "1.0.0"}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logging.getLogger("bsip").error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please contact the platform team."},
    )
