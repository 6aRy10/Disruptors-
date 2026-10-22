# Local PostgreSQL and live feeds: verify before demo

## If HERMES shows HTTP 500 in multiple workspaces

The frontend is receiving an internal error from the proxy or backend.
Do NOT run the seed loader. Pull the working branch, start Uvicorn, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_hermes_backend.ps1
```

The GET-only script checks FastAPI OpenAPI readiness, database selection,
schema tables and independent incident/activity/facility queries. The route
`/app-data/readiness` intentionally returns structured JSON even when the
database is unavailable. It does not reveal passwords, usernames, hostnames,
connection URLs or private source documents.

- If both database URLs exist and no target is selected, set
  `$env:DEPENDENCY_DATABASE_TARGET = "local"` in the backend terminal when
  the populated local PostgreSQL database is the intended target, then restart.
- If PostgreSQL cannot connect, inspect your existing PostgreSQL server/service
  and configured target. Do not load another database.
- If the schema is incomplete, verify the selected database. Do not reset it.
- If connection is ready but one query fails, inspect that endpoint's error type,
  SQLSTATE and the Uvicorn traceback. Do not infer that the entire source feed
  is down from one failed query.
- If the backend health is good but the Vite proxy fails, check
  `HERMES_BACKEND_URL` and the process on port 5173.


GitHub Actions creates a separate disposable PostgreSQL database for every run.
It **never** fills your Windows PostgreSQL installation.

In PowerShell inside the repository:

```powershell
git switch feat/db-foundation
git pull --ff-only origin feat/db-foundation
.\.venv\Scripts\Activate.ps1
python scripts/doctor.py
```

Doctor prints the effective database host and database name, but never the
password. Open **that exact host and database** in Valentina Studio or psql.
If AIVEN_DATABASE_URL and DATABASE_URL are both present, the backend now
**requires** DEPENDENCY_DATABASE_TARGET=local or =aiven. It does not silently
prefer one URL. For the owner's populated local PostgreSQL database, choose
local in the backend terminal. Never share the URL or credentials.

If doctor reports SCHEMA_NOT_LOADED or DATA_INCOMPLETE, confirm this is a
disposable project database first. The loader intentionally resets demo data.

```powershell
python scripts/validate_seed_data.py
python scripts/load_seed_data.py
python scripts/doctor.py
```

Expected after loading: at least 2,500 generated products, 770 public network
facilities, and 170,010 generated material-allocation edges. These are
SIMULATED_PRIVATE commercial relationships linked to public supplier identities.

Feed reachability does **not** mean automatic event monitoring is running.
Open independent PowerShell windows and run the workers:

```powershell
python scripts/watch_usgs.py --help
python scripts/watch_gdacs.py --help
python scripts/run_local_orchestrator.py --watch
```

Check each watch script's flags before starting. Do not run scripts with
unknown frequency or outbound side effects. Live events are separate from the
historical Cianjur replay. PostGIS proximity means POTENTIALLY_EXPOSED, not
confirmed facility disruption.

Troubleshooting: if doctor reports an unexpected database name or host,
inspect your local environment variables and .env privately. Never paste
credentials into chat or commit them to GitHub.
