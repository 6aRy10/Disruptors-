# Aiven free-tier plan — safe switch only after verification

The hackathon's data requirements benefit from Aiven managed PostgreSQL and
Aiven Kafka. The existing PostgreSQL outbox and Kafka producer/consumer
contracts already use the same event envelope; we do not need a second event
processing implementation.

**Aiven free tiers are sandbox-sized**, so validate the chosen service's
current storage, memory, Kafka limits and PostGIS extension support. Do not
assume that a free PostgreSQL instance has PostGIS enabled, or that it fits
the full 266,737-row private twin. If the free plan lacks these, keep the
complete PostGIS graph locally and use managed Kafka as the stream layer.
Neither a new feed nor a dashboard screenshot proves infrastructure use.

## First check — no changes made

1. Create the desired services through Aiven, if available to you.
2. Set credentials only in your local environment, never GitHub.
3. Keep your local `DATABASE_URL` intact. Note that if you set
   `AIVEN_DATABASE_URL`, the application **automatically prefers Aiven**.
   To test Aiven without switching the running system, run this diagnostic
   in a separate PowerShell session with only the appropriate variables.
4. Execute:

```powershell
python -m scripts.aiven_preflight
```

This is read-only. It checks extension availability, table presence, target
identity and approximate database storage size. It never prints credentials
or modifies records. For Kafka it only checks auth configuration, not live
connectivity. `CONFIGURED_NOT_CONNECTED` is **not** deployment proof.

## Production event path

USGS / GDACS / PortWatch -> event normalization -> PostgreSQL operational
record plus transactional outbox -> (optional) Aiven Kafka publisher ->
Kafka consumer -> same idempotent incident orchestrator -> live investigation
tasks -> operator-confirmed private evidence -> versioned joint replan ->
approval -> execution -> memory.

For a **local**, safe smoke test:
```powershell
python -m scripts.run_live_stack
python -m scripts.inspect_event GDACS-WF-1032942
```

For Aiven Kafka, configure TLS and create the required topics first. Then
start the publisher and consumer independently:
```powershell
python -m scripts.flush_event_bus --publish
python -m scripts.run_kafka_consumer
```

Do not run remote publishing until brokers, topic availability, TLS,
credentials and permissions are verified. Both consumers require access to
the same PostgreSQL operational database to preserve idempotency; using
different databases silently breaks the shared memory and state contract.

## Data movement

Never reset local PostgreSQL to test a remote service. Before migration,
record row counts, PostgreSQL/PostGIS versions and database size. Verify
extension support and quotas on the target. Migrate only with an explicitly
reviewed backup and restore plan. Run the doctor and replay suite on the new
database, then switch environment variables. **No automatic migration** is
performed by this repo preflight.

The fallback demo uses the known-good local PostGIS and transactional
outbox; Kafka and all external services must be optional for that demo.
