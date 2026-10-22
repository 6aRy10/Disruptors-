# Aiven Kafka transport and Aiven Runtime deployment

Scope: the Kafka side of HERMES (outbox relay, consumer, health checks) and the
container deployment. PostgreSQL is already live on Aiven and is **never**
created, migrated or reset by anything in this document.

## 1. Architecture in one paragraph

Every state change is written to PostgreSQL together with a row in
`event_outbox` (same transaction). The **publisher** role relays unpublished
rows to Aiven Kafka and marks each row only after the broker acknowledges it
(`acks=all`, idempotent producer). The **consumer** role reads the single
physical topic `dependency.events`, decodes the envelope (which carries the
original logical topic and `outbox_id`), and calls the same idempotent
`process_event_envelope` as the local worker. Offsets are committed only after
the handler succeeds. Nothing is dropped; a failure leaves the row in the
outbox with `attempts` and `last_error` populated.

```
collectors/API --tx--> PostgreSQL(event_outbox) --publisher--> Kafka dependency.events
                                                                     |
PostgreSQL(event_consumptions) <------- consumer (group dependency-incident-orchestrator)
```

Free-tier limits respected: **one** physical topic (limit is five), one
consumer group, compression on, batches of 100.

## 2. Configuration

The code reads two variable families (`src/dependency/events/kafka_settings.py`):

| Purpose | Project variable (files) | Aiven Runtime variable (inline PEM, injected) |
|---|---|---|
| Brokers | `AIVEN_KAFKA_BROKERS` | `KAFKA_BOOTSTRAP_SERVERS` |
| Protocol | `AIVEN_KAFKA_SECURITY_PROTOCOL` (`SSL` default) | `KAFKA_SECURITY_PROTOCOL` (`SSL`) |
| CA | `AIVEN_KAFKA_CA_FILE` | `KAFKA_CA_CERT` |
| Client cert | `AIVEN_KAFKA_CERT_FILE` | `KAFKA_ACCESS_CERT` |
| Client key | `AIVEN_KAFKA_KEY_FILE` | `KAFKA_ACCESS_KEY` |
| SASL (optional) | `AIVEN_KAFKA_USERNAME/PASSWORD`, `AIVEN_KAFKA_SASL_MECHANISM` | — |

Rules enforced (fail closed, before any network call):
- Protocol must be `SSL` or `SASL_SSL`. `PLAINTEXT` only with
  `AIVEN_KAFKA_ALLOW_PLAINTEXT=true` for a throwaway local broker.
- TLS requires a CA (Aiven uses a private CA) and either mTLS pair or SASL pair.
- SASL requires `SASL_SSL` and Aiven's SASL port (differs from the SSL port).

Database: containers set `DEPENDENCY_DATABASE_TARGET=aiven` and expect
`AIVEN_DATABASE_URL`. Non-secret routing defaults are baked into the image:
`AIVEN_KAFKA_ROUTING_MODE=single`, `AIVEN_KAFKA_PHYSICAL_TOPIC=dependency.events`.

## 3. What you must do in the Aiven Console (manual, once)

1. Create (or select) an **Aiven for Apache Kafka** service in the same project
   as `hermes-db`. Free plan is sufficient.
2. Create topic **`dependency.events`** (partitions: 2, retention: default).
   Topic auto-creation is off on Aiven by default; the code never creates topics.
3. Keep the Kafka **ACL** default (`admin` user, all topics) or add an ACL for
   user `avnadmin` on topic `dependency.events` with `admin`/`readwrite`.
4. For the file-based path, download from the service *Overview* page:
   `ca.pem`, `service.cert`, `service.key` and note `Service URI` (host:port).
   For Aiven Runtime, skip the download; the integration injects the PEMs.

Give me: nothing. Put the three files in `./certs/` (git/docker-ignored) and
the URI in `.env` as `AIVEN_KAFKA_BROKERS=host:port`. Never paste them in chat.

## 4. Verify against the real brokers (no DB writes)

```powershell
# 1. configuration + read-only metadata probe (no message produced)
python scripts/verify_kafka_roundtrip.py
# 2. publish ONE probe envelope and consume it back with a throwaway group
python scripts/verify_kafka_roundtrip.py --publish
```

Expected final block: `"roundtrip": {"status": "VERIFIED", "published": true,
"consumed": true, "roundtrip_ms": ...}`. The probe uses logical topic
`hermes.transport.probe`; the production consumer skips and commits it, so it
cannot poison the orchestrator. Exit codes: 0 verified, 1 broker/roundtrip
failure, 2 configuration invalid. Also available: `python -m scripts.aiven_preflight --probe-kafka`.

Then drain the real outbox once, manually, and watch the consumer handle it:

```powershell
python -m scripts.flush_event_bus            # lists pending rows, publishes nothing
python -m scripts.flush_event_bus --publish  # relays pending rows once
python scripts/run_kafka_consumer.py --max-messages 5
```

## 5. Health checks

| Endpoint / command | Meaning |
|---|---|
| `GET /health/live` | Process alive. No dependency touched. |
| `GET /health/ready` | 200 when PostgreSQL answers and Kafka config is valid or absent; 503 otherwise. `?probe_kafka=true` adds a broker metadata probe. |
| `GET /health/kafka` | Secret-free settings summary, routing, outbox backlog (`pending`, oldest age, `published_last_hour`), consumer lag (`published_not_consumed`, `consumption_errors`). `?probe=true` -> `STREAMING_READY` / `BROKER_MISSING_TOPICS` / `BROKER_UNREACHABLE`. |
| `python scripts/healthcheck.py api\|publisher\|consumer` | Container `HEALTHCHECK`. Workers are healthy when their heartbeat file (`HERMES_HEARTBEAT_FILE`) is < 90 s old (`HERMES_HEARTBEAT_STALE_SECONDS`). |

All outputs reduce exceptions to type names; hostnames, URLs and PEMs never appear.

## 6. Local / VM deployment with Docker

```powershell
Copy-Item .env.example .env       # fill AIVEN_DATABASE_URL, AIVEN_KAFKA_BROKERS, DEPENDENCY_WRITE_TOKEN
New-Item -ItemType Directory certs # put ca.pem, service.cert, service.key here
docker compose up --build -d
docker compose ps                  # STATUS shows (healthy) for api, publisher, consumer
Invoke-RestMethod "http://localhost:8000/health/kafka?probe=true"
docker compose logs -f consumer
```

`compose.yaml` mounts `./certs` read-only and sets the `AIVEN_KAFKA_*_FILE`
paths. Run exactly one `consumer` replica (idempotency is DB-backed but
sequential; see `AIVEN_FREE_TIER_DEPLOYMENT.md`). Stop with
`docker compose down` — SIGTERM is handled: the consumer finishes the in-flight
message and commits before exiting.

## 7. Aiven Runtime deployment

Manifest: `compose.aiven.yaml` (three applications: `hermes-api`,
`hermes-publisher`, `hermes-consumer`, all built from `Dockerfile`). It
deliberately declares **no** data services so Runtime does not provision a new
PostgreSQL; the existing services are attached afterwards.

1. Console -> project -> **Runtime** -> *Deploy application* -> connect GitHub ->
   repository `Disruptors-` -> branch `feat/hermes-aiven` -> manifest
   `compose.aiven.yaml` -> *Scan* -> *Deploy*. Repeat for each application or
   deploy them together if the scan lists all three.
2. Attach the existing services (CLI; replace names):

```bash
avn project switch PROJECT_NAME
for APP in hermes-api hermes-publisher hermes-consumer; do
  avn service integration-create --integration-type application_service_credential \
    --source-service hermes-db --dest-service "$APP" \
    --user-config-json '{"service_type":"pg","exposed_values":{"connection_string":{"environment_variable_key":"AIVEN_DATABASE_URL"}}}'
  avn service integration-create --integration-type application_service_credential \
    --source-service KAFKA_SERVICE_NAME --dest-service "$APP" \
    --user-config-json '{"service_type":"kafka","exposed_values":{
      "bootstrap_servers":{"environment_variable_key":"KAFKA_BOOTSTRAP_SERVERS"},
      "security_protocol":{"environment_variable_key":"KAFKA_SECURITY_PROTOCOL"},
      "access_key":{"environment_variable_key":"KAFKA_ACCESS_KEY"},
      "access_cert":{"environment_variable_key":"KAFKA_ACCESS_CERT"},
      "ca_cert":{"environment_variable_key":"KAFKA_CA_CERT"}}}'
done
```

   Console alternative: open each application -> *Connected services* ->
   *Connect service* -> pick `hermes-db` / the Kafka service; then rename the
   PostgreSQL variable to `AIVEN_DATABASE_URL`.

   The PostgreSQL integration uses the custom key `AIVEN_DATABASE_URL` so the
   application's explicit `DEPENDENCY_DATABASE_TARGET=aiven` selection works
   unchanged. The Kafka integration injects `KAFKA_BOOTSTRAP_SERVERS`,
   `KAFKA_SECURITY_PROTOCOL=SSL`, `KAFKA_CA_CERT`, `KAFKA_ACCESS_CERT`,
   `KAFKA_ACCESS_KEY`; no certificate files are needed.
3. Add secrets as Runtime environment variables on `hermes-api`:
   `DEPENDENCY_WRITE_TOKEN` (strong random), `OPENAI_API_KEY` if agents are
   used, `SLACK_*` if Slack is used. Mark them *secret*, not *variable*.
4. Redeploy, then check `https://<hermes-api-host>/health/ready?probe_kafka=true`
   and `/health/kafka?probe=true` -> `STREAMING_READY`.
5. Scale `hermes-consumer` to exactly one instance.

Deployments are not triggered by `git push`; redeploy from the console after
each merge.

## 8. Operations

- Backlog growing (`/health/kafka` -> `outbox.pending` rising,
  `pending_with_failed_attempts` > 0): publisher cannot reach brokers; check
  publisher logs (`last_error_type`) and `verify_kafka_roundtrip.py`.
- `consumer_lag.published_not_consumed` rising: consumer is down or stuck;
  its heartbeat healthcheck will restart it. A persistent `consumption_errors`
  count means a handler error on one event; inspect `event_consumptions.error_text`
  for that `outbox_id`. The consumer stops on handler errors on purpose so the
  offset is redelivered rather than skipped.
- `orphaned` count in consumer logs: the topic (3-day retention) still holds
  events whose `outbox_id` is not in the connected database, e.g. from before
  the 2026-10-22 reload. Default `AIVEN_KAFKA_ORPHAN_POLICY=skip` commits past
  them (they cannot be recorded idempotently without an outbox row). Set
  `fail` to stop instead when the publisher and consumer should always share
  one database. Verified live on 2026-10-22: 17 duplicates, 3 orphans, 0 errors.
- Switching to paid Kafka with per-type topics: set
  `AIVEN_KAFKA_ROUTING_MODE=logical`, create the 11 topics, redeploy
  publisher and consumer together.

## 9. Tests

```powershell
python -m unittest tests.test_kafka_settings tests.test_kafka_transport tests.test_kafka_health tests.test_kafka_roundtrip tests.test_kafka_free_routing tests.test_aiven_preflight tests.test_aiven_network_probe tests.test_transport_consistency
python -m unittest tests.test_kafka_contract tests.test_event_bus    # need a PostgreSQL target
```
