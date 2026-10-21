from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[3]
GENERATED = ROOT / "data" / "generated" / "private_twin"

PRODUCT_COUNT = 2500
MATERIAL_VARIANTS = 24
ASSEMBLY_FACILITY_TARGET = 150
SOURCE_FACILITY_TARGET = 90

EXCLUDED_FLAGSHIP_COUNTRIES = {"Indonesia", "China", "Vietnam"}

MARKETS = (
    "Europe",
    "North America",
    "Greater China",
    "Japan",
    "Latin America",
    "Middle East",
)

WAREHOUSES = ("WH-EU", "WH-NA", "WH-GC")

CATEGORY_PATTERN = (
    "Footwear",
    "Footwear",
    "Footwear",
    "Apparel",
    "Apparel",
    "Accessories",
)

CATEGORY_ECONOMICS = {
    "Footwear": (135.0, 54.0),
    "Apparel": (72.0, 29.0),
    "Accessories": (58.0, 23.0),
}

FAMILIES = {
    "Footwear": (
        ("UPPER-MESH", "Performance mesh upper", "kit", "critical", 1.0),
        ("UPPER-OVERLAY", "Synthetic reinforcement overlay", "set", "medium", 1.0),
        ("LINING", "Textile lining", "kit", "medium", 1.0),
        ("LACES", "Performance lace pair", "pair", "low", 1.0),
        ("THREAD", "Industrial sewing thread", "meter", "medium", 15.0),
        ("ADHESIVE", "Footwear assembly adhesive", "kg", "critical", 0.09),
        ("MIDSOLE", "Performance foam midsole", "pair", "critical", 1.0),
        ("OUTSOLE", "Rubber outsole", "pair", "critical", 1.0),
        ("SOCKLINER", "Molded sockliner", "pair", "medium", 1.0),
        ("SHANK", "Stability shank / torsion component", "unit", "medium", 1.0),
        ("LABEL", "Product and compliance label set", "set", "low", 1.0),
        ("PACKAGING", "Footwear packaging set", "set", "low", 1.0),
    ),
    "Apparel": (
        ("MAIN-FABRIC", "Performance apparel main fabric", "meter", "critical", 1.55),
        ("LINING-FABRIC", "Apparel lining fabric", "meter", "medium", 0.55),
        ("THREAD", "Industrial sewing thread", "meter", "medium", 18.0),
        ("ZIPPER", "Garment zipper", "set", "medium", 1.0),
        ("RIB", "Rib trim", "set", "medium", 1.0),
        ("ELASTIC", "Garment elastic", "meter", "low", 0.65),
        ("DRAWCORD", "Drawcord", "set", "low", 1.0),
        ("LABEL", "Product and compliance label set", "set", "low", 1.0),
        ("HANGTAG", "Retail hangtag", "set", "low", 1.0),
        ("PACKAGING", "Apparel packaging set", "set", "low", 1.0),
        ("CARTON", "Distribution carton allocation", "unit", "low", 0.08),
    ),
    "Accessories": (
        ("SHELL-FABRIC", "Accessory shell fabric", "meter", "critical", 1.15),
        ("LINING-FABRIC", "Accessory lining fabric", "meter", "medium", 0.75),
        ("ZIPPER", "Accessory zipper set", "set", "critical", 2.0),
        ("WEBBING", "Load-bearing webbing", "meter", "medium", 2.4),
        ("BUCKLE", "Buckle and hardware set", "set", "medium", 1.0),
        ("FOAM", "Protective foam sheet allocation", "sheet", "medium", 0.4),
        ("THREAD", "Industrial sewing thread", "meter", "medium", 22.0),
        ("LABEL", "Product and compliance label set", "set", "low", 1.0),
        ("PACKAGING", "Accessory packaging set", "set", "low", 1.0),
        ("CARTON", "Distribution carton allocation", "unit", "low", 0.1),
    ),
}

PORTS_BY_COUNTRY = {
    "Bangladesh": ("BDCGP", "Chattogram"),
    "Cambodia": ("KHKOS", "Sihanoukville"),
    "India": ("INNSA", "Nhava Sheva"),
    "Pakistan": ("PKKHI", "Karachi"),
    "Turkey": ("TRMER", "Mersin"),
    "Türkiye": ("TRMER", "Mersin"),
    "Thailand": ("THLCH", "Laem Chabang"),
    "Taiwan": ("TWKHH", "Kaohsiung"),
    "Taiwan, China": ("TWKHH", "Kaohsiung"),
    "Korea": ("KRPUS", "Busan"),
    "South Korea": ("KRPUS", "Busan"),
    "Japan": ("JPYOK", "Yokohama"),
    "Italy": ("ITGOA", "Genoa"),
    "Germany": ("DEHAM", "Hamburg"),
    "Egypt": ("EGPSD", "Port Said"),
    "Morocco": ("MAPTM", "Tanger Med"),
    "Tunisia": ("TNRDS", "Rades"),
    "Jordan": ("JOAQJ", "Aqaba"),
}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _has_coordinates(row: dict) -> bool:
    return bool(_clean(row.get("lat")) and _clean(row.get("lng")))


def _category_match(row: dict, category: str) -> bool:
    return category.lower() in _clean(row.get("product_categories")).lower()


def _tier1(row: dict) -> bool:
    tiers = _clean(row.get("tiers")).lower()
    return "tier 1" in tiers or "t1" in tiers


def _tier2(row: dict) -> bool:
    tiers = _clean(row.get("tiers")).lower()
    return (
        "tier 2" in tiers
        or "t2" in tiers
        or "material" in tiers
        or "trim" in tiers
    )


def _network_candidates(network_rows: list[dict]) -> list[dict]:
    rows = [
        row
        for row in network_rows
        if _has_coordinates(row)
        and _clean(row.get("country")) not in EXCLUDED_FLAGSHIP_COUNTRIES
    ]
    return sorted(
        rows,
        key=lambda row: (
            _clean(row.get("country")),
            _clean(row.get("official_name") or row.get("name")),
            _clean(row.get("facility_id")),
        ),
    )


def _take_unique(rows: Iterable[dict], n: int, used: set[str]) -> list[dict]:
    selected: list[dict] = []
    for row in rows:
        network_id = _clean(row.get("facility_id"))
        if not network_id or network_id in used:
            continue
        used.add(network_id)
        selected.append(row)
        if len(selected) >= n:
            break
    return selected


def _select_facilities(network_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    candidates = _network_candidates(network_rows)
    used: set[str] = set()

    assembly_pool = [row for row in candidates if _tier1(row)]
    source_pool = [row for row in candidates if _tier2(row)]

    assembly = _take_unique(
        assembly_pool,
        ASSEMBLY_FACILITY_TARGET,
        used,
    )
    if len(assembly) < ASSEMBLY_FACILITY_TARGET:
        assembly.extend(
            _take_unique(
                candidates,
                ASSEMBLY_FACILITY_TARGET - len(assembly),
                used,
            )
        )

    sources = _take_unique(
        source_pool,
        SOURCE_FACILITY_TARGET,
        used,
    )
    if len(sources) < SOURCE_FACILITY_TARGET:
        sources.extend(
            _take_unique(
                candidates,
                SOURCE_FACILITY_TARGET - len(sources),
                used,
            )
        )

    if len(assembly) < 40 or len(sources) < 20:
        raise ValueError(
            "Public network does not contain enough geocoded non-flagship "
            "facilities to generate the enterprise-scale twin."
        )

    return assembly, sources


def _operational_facility(
    row: dict,
    facility_id: str,
    role: str,
) -> dict:
    return {
        "facility_id": facility_id,
        "network_facility_id": row["facility_id"],
        "name": row.get("official_name") or row.get("name") or facility_id,
        "country": row.get("country") or "",
        "city": row.get("city") or "",
        "province": row.get("province") or "",
        "tier": row.get("tiers") or role,
        "product_categories": row.get("product_categories") or "",
        "parent_organization": row.get("parent_organizations") or "",
        "lat": row.get("lat") or "",
        "lng": row.get("lng") or "",
        "source_url": row.get("source_url") or "",
        "identity_provenance_class": "VERIFIED_PUBLIC",
        "operational_role": role,
        "operational_provenance_class": "SIMULATED_PRIVATE",
    }


def _material_rows() -> tuple[list[dict], dict[str, list[str]], dict[str, dict]]:
    rows: list[dict] = []
    by_category: dict[str, list[str]] = defaultdict(list)
    lookup: dict[str, dict] = {}

    for category, families in FAMILIES.items():
        for family_index, (family, label, uom, criticality, _) in enumerate(families):
            for variant in range(1, MATERIAL_VARIANTS + 1):
                material_id = (
                    f"DTMAT-{category[:3].upper()}-"
                    f"{family.replace('-', '')[:8]}-{variant:02d}"
                )
                row = {
                    "material_id": material_id,
                    "name": f"{label} variant {variant:02d}",
                    "uom": uom,
                    "category": category,
                    "criticality": criticality,
                    "family": family,
                    "family_index": family_index,
                    "variant": variant,
                    "provenance_class": "SIMULATED_PRIVATE",
                }
                rows.append(row)
                by_category[category].append(material_id)
                lookup[material_id] = row

    return rows, by_category, lookup


def _category_facilities(
    facilities: list[dict],
    category: str,
) -> list[dict]:
    matched = [
        row
        for row in facilities
        if category.lower() in row["product_categories"].lower()
    ]
    return matched or facilities


def generate_enterprise_scale(
    network_rows: list[dict],
    *,
    product_count: int = PRODUCT_COUNT,
) -> dict[str, list[dict]]:
    assembly_network, source_network = _select_facilities(network_rows)

    assembly = [
        _operational_facility(row, f"DTF-A-{index:04d}", "assembly")
        for index, row in enumerate(assembly_network, start=1)
    ]
    sources = [
        _operational_facility(row, f"DTF-S-{index:04d}", "material_source")
        for index, row in enumerate(source_network, start=1)
    ]
    facilities = assembly + sources

    materials, _, material_lookup = _material_rows()

    source_by_material: dict[str, list[dict]] = {}
    material_sources: list[dict] = []
    for index, material in enumerate(materials):
        first = sources[index % len(sources)]
        second = sources[(index * 7 + 17) % len(sources)]
        if first["facility_id"] == second["facility_id"]:
            second = sources[(index + 1) % len(sources)]
        selected = [first, second]
        source_by_material[material["material_id"]] = selected
        for source_rank, source in enumerate(selected, start=1):
            material_sources.append(
                {
                    "material_id": material["material_id"],
                    "facility_id": source["facility_id"],
                    "role": "primary" if source_rank == 1 else "alternate",
                    "approved": True,
                    "lead_time_days": 5 + ((index + source_rank * 3) % 18),
                    "weekly_capacity_units": 30000 + ((index * 1733) % 85000),
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

    products: list[dict] = []
    bom: list[dict] = []
    product_facilities: list[dict] = []
    material_allocations: list[dict] = []
    supplier_capacity: list[dict] = []
    production_orders: list[dict] = []
    commitments: list[dict] = []
    purchase_orders: list[dict] = []
    inventory: list[dict] = []
    substitutions: list[dict] = []
    transport_lanes: list[dict] = []

    assembly_by_category = {
        category: _category_facilities(assembly, category)
        for category in FAMILIES
    }

    # Material substitution catalogue.
    family_materials: dict[tuple[str, str], list[str]] = defaultdict(list)
    for material in materials:
        family_materials[(material["category"], material["family"])].append(
            material["material_id"]
        )
    for (category, family), ids in sorted(family_materials.items()):
        for index, material_id in enumerate(ids):
            substitute_id = ids[(index + 1) % len(ids)]
            substitutions.append(
                {
                    "material_id": material_id,
                    "substitute_material_id": substitute_id,
                    "approved": (index % 3 != 0),
                    "max_ratio": 1.0 if index % 4 else 0.5,
                    "engineering_status": (
                        "APPROVED" if index % 3 != 0 else "REVIEW_REQUIRED"
                    ),
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

    # Transport lanes are facility/market master data. Create once per
    # assembly facility and market instead of duplicating per SKU.
    for facility_index, facility in enumerate(assembly, start=1):
        port_code, port_name = PORTS_BY_COUNTRY.get(
            facility["country"],
            ("", f"Modeled export gateway - {facility['country']}"),
        )
        for market_index, market in enumerate(MARKETS):
            mode = "ocean" if market_index < 4 else "air"
            base_days = 18 + ((facility_index * 3 + market_index * 5) % 24)
            if mode == "air":
                base_days = 4 + ((facility_index + market_index) % 5)
            transport_lanes.append(
                {
                    "lane_id": f"DTLANE-{facility['facility_id']}-{market_index + 1}",
                    "origin_facility_id": facility["facility_id"],
                    "port_unlocode": port_code,
                    "port_name": port_name,
                    "destination_market": market,
                    "mode": mode,
                    "transit_days": base_days,
                    "cost_eur_per_unit": round(
                        (2.2 + ((facility_index + market_index) % 9) * 0.45)
                        if mode == "ocean"
                        else (9.5 + ((facility_index + market_index) % 8) * 1.2),
                        2,
                    ),
                    "status": "open",
                    "policy_tag": "",
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

    today = date(2026, 10, 21)
    week_start = date(2026, 10, 19)
    now_iso = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc).isoformat()

    for product_index in range(1, product_count + 1):
        category = CATEGORY_PATTERN[(product_index - 1) % len(CATEGORY_PATTERN)]
        sku = f"DTSKU-{product_index:05d}"
        revenue_base, margin_base = CATEGORY_ECONOMICS[category]
        unit_revenue = revenue_base + ((product_index * 7) % 36)
        unit_margin = margin_base + ((product_index * 5) % 17)

        products.append(
            {
                "sku": sku,
                "name": f"Digital Twin {category} Style {product_index:05d}",
                "category": category,
                "public_material_basis": (
                    "Category-level material families are modeled from public "
                    "product/material disclosures; exact SKU BOM is private."
                ),
                "standard_unit_revenue_eur": unit_revenue,
                "standard_unit_margin_eur": unit_margin,
                "provenance_class": "SIMULATED_PRIVATE",
                "source_url": "",
            }
        )

        facility_pool = assembly_by_category[category]
        primary = facility_pool[(product_index * 5) % len(facility_pool)]
        backup1 = facility_pool[(product_index * 11 + 3) % len(facility_pool)]
        backup2 = facility_pool[(product_index * 17 + 7) % len(facility_pool)]
        selected_facilities: list[dict] = []
        for candidate in (primary, backup1, backup2):
            if candidate["facility_id"] not in {
                row["facility_id"] for row in selected_facilities
            }:
                selected_facilities.append(candidate)
        while len(selected_facilities) < 3:
            candidate = facility_pool[
                (product_index + len(selected_facilities) * 13)
                % len(facility_pool)
            ]
            if candidate["facility_id"] not in {
                row["facility_id"] for row in selected_facilities
            }:
                selected_facilities.append(candidate)

        roles = ("primary_assembly", "approved_backup", "approved_backup")
        setup_days = (0, 3 + product_index % 3, 6 + product_index % 4)
        demand_units = 6000 + ((product_index * 379) % 11000)

        for rank, facility in enumerate(selected_facilities):
            product_facilities.append(
                {
                    "sku": sku,
                    "facility_id": facility["facility_id"],
                    "role": roles[rank],
                    "approved": True,
                    "setup_lead_days": setup_days[rank],
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )
            capacity_units = int(
                demand_units
                * (1.25 if rank == 0 else 0.8 + rank * 0.18)
            )
            committed_units = int(capacity_units * (0.38 + 0.08 * rank))
            supplier_capacity.append(
                {
                    "facility_id": facility["facility_id"],
                    "sku": sku,
                    "week_start": week_start.isoformat(),
                    "capacity_units": capacity_units,
                    "committed_units": committed_units,
                    "status": "available",
                    "evidence_age_hours": 8 + ((product_index + rank * 17) % 85),
                    "source": "ERP digital-twin supplier master",
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

        families = FAMILIES[category]
        sku_materials: list[str] = []
        sku_qty_by_material: dict[str, float] = {}
        for family_index, (family, _, _, _, base_qty) in enumerate(families):
            variant = ((product_index + family_index * 3) % MATERIAL_VARIANTS) + 1
            material_id = (
                f"DTMAT-{category[:3].upper()}-"
                f"{family.replace('-', '')[:8]}-{variant:02d}"
            )
            sku_materials.append(material_id)
            qty = base_qty * (1.0 + ((product_index + family_index) % 4) * 0.04)
            sku_qty_by_material[material_id] = round(qty, 4)
            bom.append(
                {
                    "sku": sku,
                    "material_id": material_id,
                    "qty_per_unit": round(qty, 4),
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

            allocated_sources = source_by_material[material_id]
            for destination in selected_facilities:
                for source_rank, source in enumerate(allocated_sources):
                    material_allocations.append(
                        {
                            "material_id": material_id,
                            "source_facility_id": source["facility_id"],
                            "destination_facility_id": destination["facility_id"],
                            "sku": sku,
                            "approved": True,
                            "allocation_share": 0.65 if source_rank == 0 else 0.35,
                            "provenance_class": "SIMULATED_PRIVATE",
                        }
                    )

        # Production plan: primary plus one smaller contingency order.
        production_orders.append(
            {
                "prod_id": f"DTPROD-{product_index:05d}-A",
                "sku": sku,
                "facility_id": selected_facilities[0]["facility_id"],
                "qty": demand_units,
                "start_date": (today + timedelta(days=1 + product_index % 5)).isoformat(),
                "due_date": (today + timedelta(days=10 + product_index % 11)).isoformat(),
                "status": "planned",
                "provenance_class": "SIMULATED_PRIVATE",
            }
        )
        production_orders.append(
            {
                "prod_id": f"DTPROD-{product_index:05d}-B",
                "sku": sku,
                "facility_id": selected_facilities[1]["facility_id"],
                "qty": int(demand_units * 0.18),
                "start_date": (today + timedelta(days=5 + product_index % 6)).isoformat(),
                "due_date": (today + timedelta(days=18 + product_index % 12)).isoformat(),
                "status": "tentative",
                "provenance_class": "SIMULATED_PRIVATE",
            }
        )

        # Eight customer commitments create a real allocation problem.
        remaining = demand_units
        for order_index in range(1, 9):
            market = MARKETS[(product_index + order_index) % len(MARKETS)]
            if order_index == 8:
                qty = remaining
            else:
                qty = max(
                    100,
                    int(demand_units * (0.08 + ((order_index * 7) % 9) / 100)),
                )
                qty = min(qty, remaining)
            remaining -= qty
            revenue = qty * unit_revenue
            margin = qty * (unit_margin - (order_index % 3) * 1.5)
            commitments.append(
                {
                    "commitment_id": f"DTCMT-{product_index:05d}-{order_index:02d}",
                    "customer_or_market": f"{market} wholesale commitment {order_index}",
                    "market": market,
                    "sku": sku,
                    "qty": qty,
                    "due_date": (
                        today + timedelta(days=8 + order_index * 2 + product_index % 7)
                    ).isoformat(),
                    "unit_revenue_eur": unit_revenue,
                    "revenue_eur": round(revenue, 2),
                    "unit_margin_eur": round(
                        unit_margin - (order_index % 3) * 1.5,
                        2,
                    ),
                    "gross_margin_eur": round(margin, 2),
                    "priority": 1 + ((order_index - 1) % 3),
                    "partial_allowed": True,
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

        # Finished-goods inventory across three regional warehouses.
        for wh_index, warehouse in enumerate(WAREHOUSES):
            on_hand = int(demand_units * (0.05 + 0.025 * wh_index))
            inventory.append(
                {
                    "site_id": warehouse,
                    "item_type": "finished_good",
                    "item_id": sku,
                    "qty_on_hand": on_hand,
                    "qty_reserved": int(on_hand * 0.18),
                    "safety_stock": int(on_hand * 0.22),
                    "updated_at": now_iso,
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

        # Five inbound component POs per SKU.
        critical_materials = [
            material_id
            for material_id in sku_materials
            if material_lookup[material_id]["criticality"] == "critical"
        ]
        po_materials = (critical_materials + sku_materials)[:5]
        for po_index, material_id in enumerate(po_materials, start=1):
            source = source_by_material[material_id][(product_index + po_index) % 2]
            qty_per_unit = sku_qty_by_material[material_id]
            purchase_orders.append(
                {
                    "po_id": f"DTPO-{product_index:05d}-{po_index:02d}",
                    "material_id": material_id,
                    "supplier_facility_id": source["facility_id"],
                    "qty": round(demand_units * qty_per_unit * 0.72, 2),
                    "eta": (
                        datetime(2026, 10, 24, 9, 0, tzinfo=timezone.utc)
                        + timedelta(days=(product_index + po_index * 2) % 18)
                    ).isoformat(),
                    "status": "confirmed" if po_index < 4 else "released",
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

    # Material inventory is a shared cross-product resource. This intentionally
    # creates correlated dependencies and competition for the same materials.
    for index, material in enumerate(materials, start=1):
        for site_index, site in enumerate(("MAT-HUB-APAC", "MAT-HUB-EMEA")):
            base = 15000 + ((index * 311 + site_index * 7001) % 90000)
            inventory.append(
                {
                    "site_id": site,
                    "item_type": "material",
                    "item_id": material["material_id"],
                    "qty_on_hand": base,
                    "qty_reserved": int(base * 0.31),
                    "safety_stock": int(base * 0.12),
                    "updated_at": now_iso,
                    "provenance_class": "SIMULATED_PRIVATE",
                }
            )

    return {
        "facilities": facilities,
        "products": products,
        "materials": materials,
        "product_facilities": product_facilities,
        "bom": bom,
        "material_sources": material_sources,
        "material_allocations": material_allocations,
        "substitutions": substitutions,
        "inventory": inventory,
        "supplier_capacity": supplier_capacity,
        "production_orders": production_orders,
        "customer_orders": commitments,
        "purchase_orders": purchase_orders,
        "transport_lanes": transport_lanes,
    }


CSV_FIELDS = {
    "facilities": (
        "facility_id",
        "network_facility_id",
        "name",
        "country",
        "city",
        "province",
        "tier",
        "product_categories",
        "parent_organization",
        "lat",
        "lng",
        "source_url",
        "identity_provenance_class",
        "operational_role",
        "operational_provenance_class",
    ),
    "products": (
        "sku",
        "name",
        "category",
        "public_material_basis",
        "standard_unit_revenue_eur",
        "standard_unit_margin_eur",
        "provenance_class",
        "source_url",
    ),
    "materials": (
        "material_id",
        "name",
        "uom",
        "category",
        "criticality",
        "family",
        "family_index",
        "variant",
        "provenance_class",
    ),
    "product_facilities": (
        "sku",
        "facility_id",
        "role",
        "approved",
        "setup_lead_days",
        "provenance_class",
    ),
    "bom": ("sku", "material_id", "qty_per_unit", "provenance_class"),
    "material_sources": (
        "material_id",
        "facility_id",
        "role",
        "approved",
        "lead_time_days",
        "weekly_capacity_units",
        "provenance_class",
    ),
    "material_allocations": (
        "material_id",
        "source_facility_id",
        "destination_facility_id",
        "sku",
        "approved",
        "allocation_share",
        "provenance_class",
    ),
    "substitutions": (
        "material_id",
        "substitute_material_id",
        "approved",
        "max_ratio",
        "engineering_status",
        "provenance_class",
    ),
    "inventory": (
        "site_id",
        "item_type",
        "item_id",
        "qty_on_hand",
        "qty_reserved",
        "safety_stock",
        "updated_at",
        "provenance_class",
    ),
    "supplier_capacity": (
        "facility_id",
        "sku",
        "week_start",
        "capacity_units",
        "committed_units",
        "status",
        "evidence_age_hours",
        "source",
        "provenance_class",
    ),
    "production_orders": (
        "prod_id",
        "sku",
        "facility_id",
        "qty",
        "start_date",
        "due_date",
        "status",
        "provenance_class",
    ),
    "customer_orders": (
        "commitment_id",
        "customer_or_market",
        "market",
        "sku",
        "qty",
        "due_date",
        "unit_revenue_eur",
        "revenue_eur",
        "unit_margin_eur",
        "gross_margin_eur",
        "priority",
        "partial_allowed",
        "provenance_class",
    ),
    "purchase_orders": (
        "po_id",
        "material_id",
        "supplier_facility_id",
        "qty",
        "eta",
        "status",
        "provenance_class",
    ),
    "transport_lanes": (
        "lane_id",
        "origin_facility_id",
        "port_unlocode",
        "port_name",
        "destination_market",
        "mode",
        "transit_days",
        "cost_eur_per_unit",
        "status",
        "policy_tag",
        "provenance_class",
    ),
}


def write_enterprise_scale(data: dict[str, list[dict]]) -> dict:
    GENERATED.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    total = 0

    for dataset, fields in CSV_FIELDS.items():
        rows = data[dataset]
        path = GENERATED / f"{dataset}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        counts[dataset] = len(rows)
        total += len(rows)

    manifest = {
        "schema_version": 1,
        "generator": "dependency.data.enterprise_scale",
        "deterministic": True,
        "private_data_provenance": "SIMULATED_PRIVATE",
        "public_identity_provenance": "VERIFIED_PUBLIC",
        "excluded_flagship_countries": sorted(EXCLUDED_FLAGSHIP_COUNTRIES),
        "counts": counts,
        "total_generated_rows": total,
        "note": (
            "Facility identities come from the loaded public adidas network. "
            "All SKU/BOM/order/capacity/route/source relationships generated "
            "here are synthetic private-enterprise data."
        ),
    }
    (GENERATED / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest


def _executemany(conn, sql: str, rows: list[tuple]) -> None:
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows)


def _delete_previous_scale(conn) -> None:
    conn.execute("DELETE FROM material_allocations WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM supplier_capacity WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM production_orders WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM fulfilment_commitments WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM purchase_orders WHERE po_id LIKE 'DTPO-%'")
    conn.execute("DELETE FROM transport_lanes WHERE lane_id LIKE 'DTLANE-%'")
    conn.execute("DELETE FROM inventory WHERE item_id LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM inventory WHERE item_id LIKE 'DTMAT-%'")
    conn.execute("DELETE FROM product_facilities WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM bom WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM substitutions WHERE material_id LIKE 'DTMAT-%'")
    conn.execute("DELETE FROM material_sources WHERE material_id LIKE 'DTMAT-%'")
    conn.execute("DELETE FROM products WHERE sku LIKE 'DTSKU-%'")
    conn.execute("DELETE FROM materials WHERE material_id LIKE 'DTMAT-%'")
    conn.execute("DELETE FROM facility_network_links WHERE facility_id LIKE 'DTF-%'")
    conn.execute("DELETE FROM facilities WHERE facility_id LIKE 'DTF-%'")


def load_enterprise_scale(
    conn,
    network_rows: list[dict],
    *,
    product_count: int = PRODUCT_COUNT,
) -> dict:
    data = generate_enterprise_scale(
        network_rows,
        product_count=product_count,
    )
    manifest = write_enterprise_scale(data)
    _delete_previous_scale(conn)

    _executemany(
        conn,
        """
        INSERT INTO facilities(
          facility_id,name,country,city,province,tier,product_categories,
          parent_organization,geom,provenance_class,source_url
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,
          ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s,%s
        )
        """,
        [
            (
                row["facility_id"],
                row["name"],
                row["country"],
                row["city"],
                row["province"],
                row["tier"],
                row["product_categories"],
                row["parent_organization"],
                float(row["lng"]),
                float(row["lat"]),
                row["identity_provenance_class"],
                row["source_url"],
            )
            for row in data["facilities"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO facility_network_links(
          facility_id,network_facility_id,match_method,match_confidence,
          provenance_class
        ) VALUES (%s,%s,'ENTERPRISE_SCALE_EXACT_SOURCE_ROW',1.0,'PUBLIC_DERIVED')
        """,
        [
            (row["facility_id"], row["network_facility_id"])
            for row in data["facilities"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO products(
          sku,name,category,public_material_basis,standard_unit_revenue_eur,
          standard_unit_margin_eur,provenance_class,source_url
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["sku"],
                row["name"],
                row["category"],
                row["public_material_basis"],
                row["standard_unit_revenue_eur"],
                row["standard_unit_margin_eur"],
                row["provenance_class"],
                row["source_url"],
            )
            for row in data["products"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO materials(
          material_id,name,uom,category,criticality,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["material_id"],
                row["name"],
                row["uom"],
                row["category"],
                row["criticality"],
                row["provenance_class"],
            )
            for row in data["materials"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO product_facilities(
          sku,facility_id,role,approved,setup_lead_days,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["sku"],
                row["facility_id"],
                row["role"],
                row["approved"],
                row["setup_lead_days"],
                row["provenance_class"],
            )
            for row in data["product_facilities"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO bom(sku,material_id,qty_per_unit,provenance_class)
        VALUES (%s,%s,%s,%s)
        """,
        [
            (
                row["sku"],
                row["material_id"],
                row["qty_per_unit"],
                row["provenance_class"],
            )
            for row in data["bom"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO material_sources(
          material_id,facility_id,role,approved,lead_time_days,
          weekly_capacity_units,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["material_id"],
                row["facility_id"],
                row["role"],
                row["approved"],
                row["lead_time_days"],
                row["weekly_capacity_units"],
                row["provenance_class"],
            )
            for row in data["material_sources"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO material_allocations(
          material_id,source_facility_id,destination_facility_id,sku,
          approved,allocation_share,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["material_id"],
                row["source_facility_id"],
                row["destination_facility_id"],
                row["sku"],
                row["approved"],
                row["allocation_share"],
                row["provenance_class"],
            )
            for row in data["material_allocations"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO substitutions(
          material_id,substitute_material_id,approved,max_ratio,
          engineering_status,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["material_id"],
                row["substitute_material_id"],
                row["approved"],
                row["max_ratio"],
                row["engineering_status"],
                row["provenance_class"],
            )
            for row in data["substitutions"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO inventory(
          site_id,item_type,item_id,qty_on_hand,qty_reserved,safety_stock,
          updated_at,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["site_id"],
                row["item_type"],
                row["item_id"],
                row["qty_on_hand"],
                row["qty_reserved"],
                row["safety_stock"],
                row["updated_at"],
                row["provenance_class"],
            )
            for row in data["inventory"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO supplier_capacity(
          facility_id,sku,week_start,capacity_units,committed_units,status,
          evidence_age_hours,source,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["facility_id"],
                row["sku"],
                row["week_start"],
                row["capacity_units"],
                row["committed_units"],
                row["status"],
                row["evidence_age_hours"],
                row["source"],
                row["provenance_class"],
            )
            for row in data["supplier_capacity"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO production_orders(
          prod_id,sku,facility_id,qty,start_date,due_date,status,
          provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["prod_id"],
                row["sku"],
                row["facility_id"],
                row["qty"],
                row["start_date"],
                row["due_date"],
                row["status"],
                row["provenance_class"],
            )
            for row in data["production_orders"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO fulfilment_commitments(
          commitment_id,customer_or_market,market,sku,qty,due_date,
          unit_revenue_eur,revenue_eur,unit_margin_eur,gross_margin_eur,
          priority,partial_allowed,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["commitment_id"],
                row["customer_or_market"],
                row["market"],
                row["sku"],
                row["qty"],
                row["due_date"],
                row["unit_revenue_eur"],
                row["revenue_eur"],
                row["unit_margin_eur"],
                row["gross_margin_eur"],
                row["priority"],
                row["partial_allowed"],
                row["provenance_class"],
            )
            for row in data["customer_orders"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO purchase_orders(
          po_id,material_id,supplier_facility_id,qty,eta,status,
          provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["po_id"],
                row["material_id"],
                row["supplier_facility_id"],
                row["qty"],
                row["eta"],
                row["status"],
                row["provenance_class"],
            )
            for row in data["purchase_orders"]
        ],
    )
    _executemany(
        conn,
        """
        INSERT INTO transport_lanes(
          lane_id,origin_facility_id,port_unlocode,port_name,
          destination_market,mode,transit_days,cost_eur_per_unit,status,
          policy_tag,provenance_class
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        [
            (
                row["lane_id"],
                row["origin_facility_id"],
                row["port_unlocode"],
                row["port_name"],
                row["destination_market"],
                row["mode"],
                row["transit_days"],
                row["cost_eur_per_unit"],
                row["status"],
                row["policy_tag"],
                row["provenance_class"],
            )
            for row in data["transport_lanes"]
        ],
    )

    return manifest
