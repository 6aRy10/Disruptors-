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

### Consumer identity safety

The local outbox worker and Aiven Kafka consumer now use the same
`incident-orchestrator` idempotency identity and PostgreSQL records.
The consumer subscribes to executed-action events as well. During Kafka
cutover, **run only one active event consumer**: this prevents overlapping
handlers from racing before idempotency commits. Sequential redelivery is
safe; concurrent exactly-once delivery is not guaranteed yet.

## Free tier versus trial (checked 2026-10-21)

Aiven's **always-free** tier currently provides PostgreSQL (1 GB disk,
1 GB RAM), and managed Kafka (up to 250 KB/s ingress/egress and up to
3 days of retention). The **30-day trial** allows credits for paid plans.
Free PostgreSQL supports extensions in principle, and Aiven lists PostGIS
among its supported PostgreSQL extensions. Exact extension availability,
permissions, service plan and disk use must be tested on **the provisioned
service** before migrating the 266,737-row graph. The trial is not a reason
to risk the only working database.

Official references:
- https://aiven.io/free-tier
- https://aiven.io/docs/products/postgresql/concepts/pg-free-tier
- https://aiven.io/docs/products/postgresql/reference/list-of-extensions
- https://aiven.io/docs/platform/concepts/service-pricing

**Current engineering choice:** use a free Kafka service as the first managed
infrastructure target. Keep PostgreSQL/PostGIS local until a managed database
passes read-only PostGIS/size checks. If the local database requires more than
1 GB, evaluate the trial paid PostgreSQL instead of truncating the twin.
The user must create the services in their own Aiven console; this repo cannot
and must not provision using credentials stored in GitHub.

## Free Kafka topic ceiling — addressed in transport

Official Aiven Free Kafka limit: **five physical topics**, two partitions per
topic. Dependency defines eleven logical topics. All logical event types now
travel through one physical Kafka topic, `dependency.events` (default).
The original logical topic, event key, outbox ID and payload remain in the
message envelope. Idempotency and action logic remain unchanged.

Create ONE topic named `dependency.events` in the Aiven Console.
`AIVEN_KAFKA_ROUTING_MODE=single` and
`AIVEN_KAFKA_PHYSICAL_TOPIC=dependency.events` are the defaults.
Only paid Kafka clusters with enough topic quota should use optional
`AIVEN_KAFKA_ROUTING_MODE=logical` compatibility mode.

https://aiven.io/docs/products/kafka/free-tier/kafka-free-tier

## Containers, health checks and Aiven Runtime

See `docs/AIVEN_KAFKA_RUNTIME_DEPLOYMENT.md` for the Docker image
(`Dockerfile`, `compose.yaml`, `compose.aiven.yaml`), the publisher/consumer
worker roles, `/health/live`, `/health/ready`, `/health/kafka`, and the
end-to-end `scripts/verify_kafka_roundtrip.py --publish` broker check.

## Read-only live Kafka readiness check

After configuring TLS privately and creating the `dependency.events` topic
in the Aiven Console, run:

```powershell
python -m scripts.aiven_preflight --probe-kafka
```

Only `READY_TO_STREAM` confirms broker reachability and topic metadata
access. Other results are `NOT_READY`, `MISSING_TOPICS`,
`TOPIC_ACCESS_ERROR` or `CONNECTION_FAILED`. The probe cannot create topics
or publish events; it never changes the current local PostgreSQL target.
