# Full HERMES database transfer — OWNER + TEAMMATE (Windows)
22 October 2026 — exact current PostgreSQL state, not a CSV subset.

## What this transfers
One PostgreSQL custom-format archive contains ALL schema, tables, indexes,
public supplier identities, simulated private product/BOM/allocations/orders,
event arrivals, incidents, evidence, scenario planning state, approvals and
operational history **from the database selected at backup time**.
It does not include environment passwords, global PostgreSQL user/role accounts,
private React/Vite frontend files or GitHub code. Send those separately using
approved private channels. This is a point-in-time DB snapshot: events arriving
after the backup are not present.

**Sensitivity**: a full backup may contain contact/personal fields and confidential
operational notes. Share only after authorizing this teammate. Use restricted
file sharing and preferably encrypted AES-256 archive; provide the encryption
password via another channel. Do not upload the dump into public GitHub.

## OWNER — export without any DB changes
Run from your existing backend checkout in PowerShell:

```powershell
cd "$HOME\Downloads\disruptors\Disruptors-"
git switch feat/db-foundation
git pull --ff-only origin feat/db-foundation
.\.venv\Scripts\Activate.ps1
python scripts/export_full_team_database.py --target local --acknowledge-sensitive-full-export --output "$HOME\Downloads\HERMES_FULL_TEAM_DB.dump"
```

This chooses `DATABASE_URL` explicitly even if `AIVEN_DATABASE_URL` also
exists. It uses `pg_dump`, preserves source rows, checks archive table sections
with `pg_restore --list`, and prints file size and SHA256. No
`load_seed_data`, `reset_demo_state`, migration, or database overwrite.

If output exists, exporter refuses overwrite. Choose a new filename only
if making a newer snapshot. If `pg_dump` is absent, install PostgreSQL
command-line tools (same or newer major version than server). Exporter can
find standard Windows PostgreSQL installation directories.

After export, share the one .dump file privately. Send the checksum separately.
With restricted Drive/OneDrive, confirm recipient has actually been given
access, not just received the message.

## TEAMMATE — restore to a DIFFERENT local PostgreSQL database
**Never run restore against the owner's active database, a company database,
or an existing populated database.** Install PostgreSQL and PostGIS locally.

1. Download the dump. Compare file checksum with owner's SHA256:

```powershell
Get-FileHash "$HOME\Downloads\HERMES_FULL_TEAM_DB.dump" -Algorithm SHA256
```

2. Open Valentina Studio or pgAdmin and create a **brand-new empty** database
named `hermes_team` on your own localhost PostgreSQL server (PostGIS available
on the server). Ensure your local role can create the PostGIS extension and
schema objects. Do NOT run HERMES seed/reset scripts after restoring.

3. In PowerShell, with PostgreSQL `bin` on PATH, run:

```powershell
pg_restore --host 127.0.0.1 --port 5432 --username postgres --dbname hermes_team --no-owner --no-acl --exit-on-error "$HOME\Downloads\HERMES_FULL_TEAM_DB.dump"
```

You may need to type your own **local PostgreSQL** password. Never use the
owner's database URL/password. The archive restores schema, extensions,
indexes and data into your teammate-owned database.

4. Confirm rows:

```powershell
psql --host 127.0.0.1 --port 5432 --username postgres --dbname hermes_team -c "SELECT (SELECT count(*) FROM network_facilities) AS public_sites, (SELECT count(*) FROM products) AS products, (SELECT count(*) FROM material_allocations) AS allocations, (SELECT count(*) FROM fulfilment_commitments) AS commitments, (SELECT count(*) FROM external_events) AS events;"
```

Source counts at the initial demo load were 770 public sites,
2,500 products, 170,018 allocations and 20,018 commitments; real current
DB counts may differ because source events and operational records change.

5. Configure the cloned HERMES backend in the teammate's own local `.env`
with a `DATABASE_URL` pointing **only** to their `hermes_team` local DB and
`DEPENDENCY_DATABASE_TARGET=local`. Do not share or commit credentials.
Run `python scripts/doctor.py` and start FastAPI.

**Troubleshooting**: If `pg_restore` is not recognized, locate
`C:\Program Files\PostgreSQL\<installed-version>\bin\pg_restore.exe` or add
the PostgreSQL bin directory to PATH. If PostGIS is missing, install the server
extension before restoring. If a restore reports that tables already exist,
stop; do not use `--clean` against a database with data. Recreate a new
**disposable** empty database with a distinct name. If a PostgreSQL CLI version
is older than the source server version, install a compatible newer client.

## What remains separate
- Backend & data generators: https://github.com/6aRy10/Disruptors-
- Current private frontend: owner-held HERMES v10 app / team launch package.
- Sensitive API keys, source credentials and environment files: **never** put
  them in the dump, GitHub, or chat.
- Aiven credentials and the actual Aiven service: an archive does not itself
  upload to Aiven. Restoring there needs target quota/PostGIS compatibility,
  explicit authorization and a separate backup/restore plan.

## Security and event processing note
A full operational snapshot includes existing outbox/consumer states.
Running two teams' watch workers independently on restored copies can create
different local event timelines; do not mistake restored snapshots for a
synchronized shared managed database. Do not enable Kafka publication,
supplier outbound messages or paid model calls on a copied dataset without
reviewing side effects and configured environment.
