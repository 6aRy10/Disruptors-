# HERMES / Disruptors — working notes for agents

## Environment
- Python 3.12, `pip install -e .` (or `PYTHONPATH=src` when several worktrees share one venv).
- Database selection is explicit: `DEPENDENCY_DATABASE_TARGET=local|aiven` plus `DATABASE_URL`
  or `AIVEN_DATABASE_URL`. The Aiven PostgreSQL is the populated production twin:
  never run `load_seed_data.py`, `reset_demo.py` or migrations against it without approval.
- `.env`, `certs/`, `*.pem|*.cert|*.key` are git- and docker-ignored. Never print their contents.

## Ownership (parallel engineers)
- Migrations (`sql/`), USGS/GDACS collectors (`src/dependency/ingest/*`), live ingestion
  scripts (`scripts/run_live_stack.py`, `scripts/watch_*.py`) belong to Engineer 1.
- Kafka transport (`src/dependency/events/*`), health endpoints, Docker/Runtime deployment
  belong to Engineer 2 (branch `feat/hermes-aiven`).

## Verification
- Network-free Kafka suite:
  `python -m unittest tests.test_kafka_settings tests.test_kafka_transport tests.test_kafka_health tests.test_kafka_roundtrip tests.test_kafka_free_routing tests.test_aiven_preflight tests.test_aiven_network_probe tests.test_transport_consistency`
- DB-backed Kafka contract (needs a PostgreSQL target): `python -m unittest tests.test_kafka_contract tests.test_event_bus`
- Real brokers: `python scripts/verify_kafka_roundtrip.py [--publish]`
- Full CI list: `.github/workflows/test.yml`.
