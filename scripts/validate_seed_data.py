from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def read_csv(name: str) -> list[dict]:
    with (CONFIG / name).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def values(name: str, key: str) -> set[str]:
    return {r[key].strip() for r in read_csv(name) if r.get(key, "").strip()}


def main() -> int:
    facilities = values("facilities_demo.csv", "facility_id")
    products = values("products.csv", "sku")
    materials = values("materials.csv", "material_id")
    scenarios = values("scenarios.csv", "scenario_id")

    errors: list[str] = []

    checks = [
        ("product_facilities.csv", "facility_id", facilities, "facility"),
        ("supplier_capacity.csv", "facility_id", facilities, "facility"),
        ("production_orders.csv", "facility_id", facilities, "facility"),
        ("purchase_orders.csv", "supplier_facility_id", facilities, "facility"),
        ("material_sources.csv", "facility_id", facilities, "facility"),
        ("material_allocations.csv", "source_facility_id", facilities, "facility"),
        ("material_allocations.csv", "destination_facility_id", facilities, "facility"),
        ("transport_lanes.csv", "origin_facility_id", facilities, "facility"),
        ("scenario_facility_state.csv", "facility_id", facilities, "facility"),
        ("product_facilities.csv", "sku", products, "product"),
        ("supplier_capacity.csv", "sku", products, "product"),
        ("production_orders.csv", "sku", products, "product"),
        ("customer_orders.csv", "sku", products, "product"),
        ("bom.csv", "sku", products, "product"),
        ("material_allocations.csv", "sku", products, "product"),
        ("bom.csv", "material_id", materials, "material"),
        ("purchase_orders.csv", "material_id", materials, "material"),
        ("material_sources.csv", "material_id", materials, "material"),
        ("material_allocations.csv", "material_id", materials, "material"),
        ("scenario_facility_state.csv", "scenario_id", scenarios, "scenario"),
    ]

    for filename, column, master, label in checks:
        if not (CONFIG / filename).exists():
            continue
        for row in read_csv(filename):
            value = row.get(column, "").strip()
            if value and value not in master:
                errors.append(f"{filename}: unknown {label} {column}={value}")

    bom_pairs = {(r["sku"], r["material_id"]) for r in read_csv("bom.csv")}
    for row in read_csv("material_allocations.csv"):
        pair = (row["sku"], row["material_id"])
        if pair not in bom_pairs:
            errors.append(
                "material_allocations.csv: allocation material is not in BOM "
                f"sku={row['sku']} material_id={row['material_id']}"
            )

    approved_pairs = {
        (r["sku"], r["facility_id"])
        for r in read_csv("product_facilities.csv")
        if r.get("approved", "").strip().lower() in {"true", "1", "yes", "y"}
    }

    for row in read_csv("production_orders.csv"):
        pair = (row["sku"], row["facility_id"])
        if pair not in approved_pairs:
            errors.append(
                "production_orders.csv: production facility is not an approved product facility "
                f"sku={row['sku']} facility_id={row['facility_id']}"
            )

    for row in read_csv("supplier_capacity.csv"):
        pair = (row["sku"], row["facility_id"])
        if pair not in approved_pairs:
            errors.append(
                "supplier_capacity.csv: capacity exists for a facility not approved for the SKU "
                f"sku={row['sku']} facility_id={row['facility_id']}"
            )

    if errors:
        print("SEED DATA INVALID")
        for error in sorted(set(errors)):
            print(f" - {error}")
        print(f"\n{len(set(errors))} unique integrity errors found.")
        return 1

    print("SEED DATA VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
