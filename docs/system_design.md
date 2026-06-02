# System Design Document
## Battery Swapping Network Intelligence Platform

---

## 1. System Overview

The platform is a multi-layer analytics system designed to handle:
- **500,000+ swap transactions/year** across a 120-station, 12-city network
- **5,000+ batteries** with real-time health monitoring
- **Sub-second API responses** for dashboard KPIs via materialized views
- **XGBoost forecasting** trained on 365+ days of historical demand

---

## 2. Architecture Decisions

### 2.1 Clean Architecture

**Decision**: Domain → Application → Infrastructure → API layering.

**Why**: The analytics layer (XGBoost, PuLP, Isolation Forest) must be testable without a database. Clean architecture enforces this via repository interfaces — the application service layer depends only on abstractions.

**Tradeoff**: More boilerplate (DTOs, repository interfaces, mapper functions) vs. a simpler service-per-file approach. Justified at this scale because the analytics models and the API are independently deployable.

### 2.2 PostgreSQL over NoSQL

**Decision**: PostgreSQL 16 with materialized views.

**Why**: Swap events have a natural relational structure (station → battery → vehicle). Time-series analytics (rolling demand, cohort degradation) are cleanest in SQL with window functions. Materialized views pre-aggregate expensive joins for dashboard latency.

**Tradeoff**: Less horizontally scalable than Cassandra or ClickHouse for pure time-series. At 500K events/year (~1,400/day), PostgreSQL easily handles this with proper indexing.

### 2.3 XGBoost for Demand Forecasting

**Decision**: XGBoost + hand-crafted time-series features over Prophet/LSTM.

**Why**: 
- Faster training (seconds vs. minutes) — critical for per-station models (120 stations)
- Interpretable feature importances (DOW, lag, rolling mean)
- Better than Prophet on short-horizon tasks with clear periodic patterns
- LSTM would overfit on 365-day histories

**Tradeoff**: XGBoost doesn't natively model seasonality — mitigated with cyclical encoding (sin/cos transforms) and explicit seasonal index features.

### 2.4 Linear Programming for Inventory Optimization

**Decision**: PuLP LP solver over heuristics or ML-based optimization.

**Why**: LP provides provably optimal solutions with hard constraints (can't ship more than available surplus, distance limit). The problem structure is well-suited to LP: linear objective (minimize shortfall), linear constraints (supply/demand balance).

**Tradeoff**: LP doesn't model stochastic demand. The deterministic demand input is the XGBoost point forecast — combining probabilistic forecasting with stochastic LP is a future improvement.

### 2.5 Isolation Forest for Anomaly Detection

**Decision**: Isolation Forest over DBSCAN or Autoencoders.

**Why**: 
- No labeled anomaly data available for supervised learning
- Isolation Forest scales well to 5,000 batteries and 500K swap events
- Interpretable contamination parameter
- Works on tabular features without temporal structure requirements

**Tradeoff**: No temporal anomaly detection (e.g., sudden SOH drops within a single battery's history). A future improvement would add CUSUM or LSTM-based sequential anomaly detection.

### 2.6 Streamlit over React

**Decision**: Streamlit for the frontend dashboard.

**Why**: Internal analytics tool with a Python-first team. Streamlit allows the same team to build both analytics and UI without a separate frontend stack. Plotly provides production-quality charts.

**Tradeoff**: Limited layout control vs. React. Mitigated with custom CSS injection. Not suitable for public-facing consumer dashboards.

---

## 3. Data Pipeline Design

```
Synthetic Generator (Python)
        ↓
  Parquet Files (data/raw/)
        ↓
  ETL Pipeline (4 stages)
  ├── Load Raw
  ├── Validate (schema, ranges, duplicates)
  ├── Feature Engineering (lag, rolling, cyclical)
  └── Load to PostgreSQL
        ↓
  PostgreSQL Tables
        ↓
  Materialized Views (refreshed hourly in production)
        ↓
  FastAPI → Streamlit
```

**ETL Metrics**: Each stage tracks `rows_in`, `rows_out`, `rows_dropped`, `errors`, `duration_seconds`.

---

## 4. Scaling Strategy

### Current (MVP)
- Single PostgreSQL instance with read replicas for the dashboard
- Streamlit deployed as a single process
- FastAPI with uvicorn workers (4 workers × 2 cores)

### Phase 2 (10× traffic)
- **TimescaleDB** extension on PostgreSQL for automatic time-series partitioning
- **Redis cache** for materialized view results (15-minute TTL)
- FastAPI behind **NGINX** load balancer
- Streamlit → **Grafana** for read-only dashboards

### Phase 3 (100× traffic — 50+ cities)
- **Apache Kafka** for real-time swap event streaming
- **Apache Spark** for distributed feature engineering (swap events → 500M+/year)
- **MLflow** for model registry and A/B testing of forecasting models
- Sharded PostgreSQL or migrate to **ClickHouse** for OLAP queries
- **Kubernetes** orchestration of all services

---

## 5. Database Query Patterns

### High-frequency (cached via materialized views)
- Network KPI aggregates (called every 30s by dashboard)
- Station utilization rates
- Rolling 7-day demand trends

### Medium-frequency (direct query with indexes)
- Battery health reports (per-battery, on demand)
- Station anomaly checks
- Forecast retrieval

### Low-frequency (scheduled refresh)
- Cohort degradation analysis
- Revenue attribution
- Battery revenue rankings

---

## 6. Security Considerations

- **JWT authentication** with role-based access (executive / analyst / operations)
- **bcrypt password hashing** (cost factor 12)
- **CORS** restricted to known frontend origins in production
- **SQL injection prevention**: all queries via SQLAlchemy ORM or `text()` with bound parameters
- **Secrets management**: all credentials via environment variables, never hardcoded

---

## 7. Observability

- **Structured logging** via Python `logging` with request ID correlation
- **Request timing** via `X-Response-Time` response header
- **ETL metrics** written to a `pipeline_runs` table (future)
- **Alerting hooks** (future): PagerDuty integration for critical battery anomalies

---

## 8. Known Limitations & Future Improvements

| Limitation | Future Improvement |
|-----------|-------------------|
| Deterministic LP uses point forecast as demand input | Stochastic LP with forecast confidence intervals |
| XGBoost trained fresh per request (slow for 120 stations) | Pre-train and persist models to disk/MLflow |
| Anomaly detection has no temporal sequential model | Add CUSUM or LSTM sequential anomaly detection |
| No real-time data — ETL is batch | Kafka streaming pipeline for sub-minute latency |
| PDF report uses static layout | Parameterized Jinja2 templates with charts embedded |
| Single-region deployment | Multi-region active-passive with pglogical replication |
| No CI/CD deployment step | ArgoCD GitOps deployment to Kubernetes |
