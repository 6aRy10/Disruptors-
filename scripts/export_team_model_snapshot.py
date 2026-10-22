"""Export an approved, read-only team data snapshot.

This intentionally excludes supplier contacts, event payloads, evidence replies,
operator identities, approvals, credentials and operational audit history.
It is NOT a PostgreSQL backup and must not be restored to the owner's DB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile
from datetime import datetime, timezone

from dependency.db.connection import connect, database_target

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Exact database table and optional column allowlist; never accept table names
# from CLI. The relationship projection excludes labor/union information.
MODEL_TABLES = {
    "legal_entities": "*",
    "facilities": "*",
    "network_facilities": "*",
    "network_facility_relationships": (
        "relationship_id,network_facility_id,list_type,source_row,country,"
        "account_name,city,province,tier,product_categories,workers_count,"
        "parent_organization,os_id,match_method,match_score,provenance_class,source_url"
    ),
    "network_parent_groups": "*",
    "network_parent_edges": "*",
    "facility_network_links": "*",
    "products": "*",
    "materials": "*",
    "product_facilities": "*",
    "bom": "*",
    "material_sources": "*",
    "material_allocations": "*",
    "substitutions": "*",
    "inventory": "*",
    "supplier_capacity": "*",
    "production_orders": "*",
    "fulfilment_commitments": "*",
    "purchase_orders": "*",
    "transport_lanes": "*",
}
EXCLUDED_CLASSES = [
    "operational_contacts", "external_events", "event_outbox",
    "event_consumptions", "incidents", "incident_investigation_tasks",
    "supplier_confirmation_requests", "supplier_confirmation_replies",
    "incident_evidence", "incident_plan_history", "approval_requests",
    "action_executions", "incident_decisions", "incident_outcomes",
    "agent_runs", "operational_state_version", "investigation_outreach_drafts",
    "confirmed_facility_capacity", "scenarios", "scenario_facility_state",
]


def export(destination: Path) -> dict:
    destination = destination.expanduser().resolve()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Output must be a .zip archive")
    if destination.is_relative_to(PROJECT_ROOT):
        raise ValueError("Write outside the Git repository to prevent accidental publication")
    if destination.exists():
        raise FileExistsError("Destination already exists; choose a new filename")
    if not destination.parent.is_dir():
        raise ValueError("Destination directory does not exist")

    # Do NOT switch a caller from local to Aiven as a side-effect.
    selected_target = database_target()
    fd, tmp_path = tempfile.mkstemp(
        prefix=".hermes-team-", suffix=".zip.tmp", dir=destination.parent
    )
    os.close(fd)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_target": selected_target,
        "classification": "VERIFIED_PUBLIC_OR_SIMULATED_PRIVATE",
        "purpose": "SHARE_READ_ONLY_DISPOSABLE_MODEL_FIXTURE",
        "not_a_full_db_backup": True,
        "not_supplier_confirmed": True,
        "omitted_tables": EXCLUDED_CLASSES,
        "tables": {},
    }
    try:
        with connect() as conn:
            # One coherent snapshot, no writes and no change to source state.
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as archive:
                for table, columns in MODEL_TABLES.items():
                    name = f"tables/{table}.csv"
                    cursor = conn.cursor()
                    row_count = int(cursor.execute(
                        f"SELECT COUNT(*) FROM public.{table}"
                    ).fetchone()[0])
                    digest = hashlib.sha256()
                    byte_count = 0
                    with archive.open(name, "w", force_zip64=True) as writer:
                        with cursor.copy(
                            f"COPY (SELECT {columns} FROM public.{table}) TO STDOUT WITH CSV HEADER"
                        ) as stream:
                            for chunk in stream:
                                if isinstance(chunk, str):
                                    chunk = chunk.encode("utf-8")
                                writer.write(chunk)
                                digest.update(chunk)
                                byte_count += len(chunk)
                    cursor.close()
                    manifest["tables"][table] = {
                        "rows": row_count, "csv_bytes": byte_count,
                        "sha256": digest.hexdigest(),
                    }
                archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2))
                archive.writestr("READ_ME_FIRST.txt", (
                    "HERMES MODEL SNAPSHOT (READ-ONLY).\n"
                    "Public identity data and simulated private planning data only.\n"
                    "Not original Adidas ERP. No authenticated supplier capacity.\n"
                    "No incident evidence, operator contacts, approvals or execution history.\n"
                    "Share privately with authorized teammates. Do not commit ZIP to GitHub.\n"
                    "Import ONLY into an empty, explicitly disposable development DB.\n"
                    "CSV files are for inspection and team test fixtures, not a full SQL restore.\n"
                ))
        os.replace(tmp_path, destination)
        return manifest
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New .zip path OUTSIDE the Git repo, e.g. ~/Downloads/hermes-team-model.zip")
    parser.add_argument("--acknowledge-team-export", action="store_true", required=True,
                        help="Confirm authorized distribution of public + simulated modeled data")
    args = parser.parse_args()
    try:
        result = export(args.output)
    except Exception as exc:
        # Never output a raw psycopg error, which might disclose a database URL.
        raise SystemExit("Export stopped safely: " + type(exc).__name__) from None
    print(json.dumps({
        "status": "EXPORTED_READ_ONLY",
        "tables": len(result["tables"]),
        "total_table_rows": sum(t["rows"] for t in result["tables"].values()),
        "excluded_private_or_operational_tables": len(EXCLUDED_CLASSES),
        "next_step": "Share privately; do not upload or commit the ZIP.",
    }, indent=2))


if __name__ == "__main__":
    main()
