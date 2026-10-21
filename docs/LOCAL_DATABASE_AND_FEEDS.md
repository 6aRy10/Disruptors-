# Local PostgreSQL and live feeds: verify before demo

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
When AIVEN_DATABASE_URL and DATABASE_URL are both set, AIVEN_DATABASE_URL
takes precedence.

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
