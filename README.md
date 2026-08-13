# AI Auto Trading System

AI-driven auto-trading system for Vietnamese stocks (HOSE/HNX/UPCOM) using the
SSI FastConnect API. Streams real-time ticks, aggregates 5-minute bars, runs an
SMA-cross strategy, and executes paper trades (real order placement exists in
code but is gated off by default — see `config/config.yaml`'s
`real_trading_enabled`).

## Architecture

SSI stream → Collector → PostgreSQL/TimescaleDB + NATS → Engine → PaperBroker

- `trading/collector/` — SSI feed (real-time stream), REST backfill, parser, 5m bar aggregator
- `trading/engine/` — main loop, strategy (SMA cross), risk management, real order placement
- `trading/broker` — PaperBroker (simulated fills with VN fees + slippage)
- `trading/storage/` — PostgreSQL + TimescaleDB (bars, orders, positions, PnL)
- `trading/bus/` — NATS JetStream publisher (bars → engine subscription)
- `trading/alerts/` — structured logging + Telegram alerts (WARN/CRITICAL)
- `grafana/` — dashboards (price, PnL, positions, heartbeat)

See `CLAUDE.md` for full project conventions.

## Prerequisites

- Docker + Docker Compose (for the full stack)
- SSI FastConnect credentials (consumer id/secret, API key/secret, private key)
- Python 3.11+ and [uv](https://docs.astral.sh/uv/) (for running tests/scripts locally without Docker)

## Setup

1. Copy `.env.example` to `.env` and fill in real SSI credentials (and Telegram
   token/chat id if you want alerts). `.env` is gitignored — never commit it.
2. Review `config/config.yaml` — symbols, indices, holidays, watchdog thresholds,
   and `real_trading_enabled` (leave `false` unless you have completed the real
   order verification runbook, see `docs/plans-legacy/PLAN_REAL_ORDER_PLACEMENT.md`).
3. Start the stack:
   ```bash
   docker compose up -d --build
   ```
4. Check logs:
   ```bash
   docker compose logs -f collector
   docker compose logs -f engine
   ```
5. Grafana dashboards: http://localhost:3000 (default admin/admin — change this
   before exposing the port beyond localhost; see `DEPLOYMENT.md`).

## Local development (without Docker)

```bash
uv sync
uv run pytest -m "not integration" -v      # unit tests — KHÔNG cần Docker
uv run pytest tests/test_parser.py -v       # single file
uv run ruff check trading tests             # lint
```

Suite đầy đủ (gồm integration) cần Postgres đang chạy **và** NATS riêng cho
test:

```bash
docker compose --profile test up -d nats-test   # NATS 4223 — riêng, không đụng stack thật
uv run pytest -q                                 # full suite
```

Vì sao có `nats-test`: test chạy trên DB `trading_test` + NATS 4223 để **không
bao giờ đụng hệ thống thật** (stream BARS / durable consumer / engine_state).
Chi tiết: `docs/superpowers/plans/2026-08-13-test-isolation.md`.

## Production deployment

See `DEPLOYMENT.md` for VPS/Ubuntu deployment guidance (secrets, network
exposure, backups, resource limits).

## Status

Active development — see `CLAUDE.md` "Project status" for what's done vs. in
progress, and `GO_LIVE_AUDIT.md` for what is still blocking go-live.
