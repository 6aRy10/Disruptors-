"""Make a complete, verified PostgreSQL custom archive for a trusted teammate.

This file contains ALL tables and potentially sensitive contacts, events,
evidence, permissions, approvals and modeled commercial information.
Share only with an explicitly authorized teammate through a private channel.
This is a read-only pg_dump, never a database reset, migration or restore.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict

# This script runs under the repository venv from its root or absolute path.
from dependency.db.connection import database_target, database_url


def find_bin(name: str) -> str:
    """Find PostgreSQL CLI tools installed on Windows or already on PATH."""
    found = shutil.which(name)
    if found:
        return found
    if sys.platform == "win32":
        roots = [Path(os.getenv("ProgramFiles", "C:/Program Files")) / "PostgreSQL",
                 Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "PostgreSQL"]
        choices = []
        for root in roots:
            if root.is_dir():
                choices.extend(root.glob("*/bin/" + name + ".exe"))
        if choices:
            return str(sorted(choices, key=lambda p: tuple(
                int(s) if s.isdigit() else 0 for s in p.parts
            ), reverse=True)[0])
    raise FileNotFoundError(name + " is not installed or is not on PATH.")


# Never place a password-containing libpq URL on a process command line.
PG_ENV_KEYS = {
    "host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT",
    "dbname": "PGDATABASE", "user": "PGUSER", "password": "PGPASSWORD",
    "sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "channel_binding": "PGCHANNELBINDING",
    "options": "PGOPTIONS",
}


def pg_connection_environment(conninfo: str) -> tuple[dict, str]:
    settings = conninfo_to_dict(conninfo)
    database_name = settings.get("dbname")
    if not database_name:
        raise ValueError("Database name missing in configured connection.")
    env = os.environ.copy()
    for key, target in PG_ENV_KEYS.items():
        value = settings.get(key)
        if value is not None:
            env[target] = str(value)
    return env, str(database_name)


def sha256_file(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_full_database(output: Path, *, expected_target="local",
                         dump_path: str | None = None,
                         restore_path: str | None = None) -> dict:
    output = output.expanduser().resolve()
    if output.suffix.lower() != ".dump":
        raise ValueError("Use a .dump output filename.")
    if output.exists() or output.with_suffix(".dump.partial").exists():
        raise FileExistsError("The requested archive already exists.")
    if not output.parent.is_dir():
        raise ValueError("The output parent folder must exist.")

    target = database_target()
    if target != expected_target:
        raise ValueError("Wrong database target; export refused.")
    pg_env, database_name = pg_connection_environment(database_url())

    pg_dump = dump_path or find_bin("pg_dump")
    pg_restore = restore_path or find_bin("pg_restore")
    partial = output.with_suffix(".dump.partial")
    try:
        command = [
            pg_dump, "--format=custom", "--compress=6",
            "--no-owner", "--no-acl", "--file", str(partial),
        ]
        completed = subprocess.run(
            command, env=pg_env, capture_output=True, timeout=3600,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "pg_dump failed. Verify pg_dump version, database connection, "
                "read privileges and free disk space. Exit code "
                + str(completed.returncode)
            )
        if not partial.is_file() or partial.stat().st_size < 100:
            raise RuntimeError("pg_dump output was missing or unexpectedly small.")
        listing = subprocess.run(
            [pg_restore, "--list", str(partial)],
            env=pg_env, capture_output=True, timeout=120, check=False,
        )
        if listing.returncode != 0:
            raise RuntimeError("pg_restore could not read the archive; export refused.")
        contents = listing.stdout.decode("utf-8", errors="replace")
        # Validate this is not just a single empty table dump.
        expected = (" TABLE DATA public products ", " TABLE DATA public bom ",
                    " TABLE DATA public material_allocations ",
                    " TABLE DATA public fulfilment_commitments ",
                    " TABLE DATA public external_events ")
        missing = [name.strip() for name in expected if name not in contents]
        if missing:
            raise RuntimeError(
                "Archive is missing required HERMES data sections: "
                + ", ".join(missing)
            )
        size = partial.stat().st_size
        checksum = sha256_file(partial)
        partial.replace(output)
        return {
            "status": "COMPLETE_ARCHIVE_VERIFIED",
            "source_target": target,
            "database_name": database_name,
            "file": str(output),
            "size_mb": round(size / 1048576, 2),
            "sha256": checksum,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only_source": True,
            "contents": "ALL_CURRENT_TABLES_SCHEMA_AND_DATA",
            "sensitive": True,
            "warning": (
                "Contains full operational and potentially personal data. "
                "Send privately only to an authorized teammate; never commit "
                "or upload publicly."
            ),
        }
    finally:
        partial.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", choices=("local", "aiven"), default="local",
                        help="Explicit source DB; use local for owner's populated DB.")
    parser.add_argument("--acknowledge-sensitive-full-export",
                        action="store_true", required=True)
    args = parser.parse_args()
    load_dotenv()
    os.environ["DEPENDENCY_DATABASE_TARGET"] = args.target
    try:
        result = export_full_database(args.output, expected_target=args.target)
    except Exception as exc:
        # Never log database or subprocess exception text: a URL or credential
        # could be embedded in the underlying exception.
        raise SystemExit(
            "Backup was not created: " + type(exc).__name__
            + ". Check database target, pg_dump, pg_restore, privileges and disk space."
        ) from None
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
