from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from rapidfuzz.fuzz import token_set_ratio


SOURCE_URL = "https://www.adidas-group.com/en/sustainability/transparency/supplier-lists"

LISTS = {
    "PRIMARY": {
        "tag": "OSHub-Data-Template-adidas-Primary-Jul 2026",
        "source_date": "2026-07-01",
    },
    "LICENSEE": {
        "tag": "OSHub-Data-Template-adidas-Licensee-Jul 2026",
        "source_date": "2026-07-01",
    },
    "WET_PROCESS": {
        "tag": "OSHub-Data-Template-adidas-Wet Process Suppliers-Apr 2026",
        "source_date": "2026-04-01",
    },
}

COUNTRY_ALIASES = {
    "turkey": "turkiye",
    "türkiye": "turkiye",
    "united states of america": "united states",
    "usa": "united states",
    "u s a": "united states",
    "korea republic of south korea": "south korea",
    "korea republic of": "south korea",
    "korea": "south korea",
    "republic of korea": "south korea",
    "taiwan ": "taiwan",
    "viet nam": "vietnam",
    "lao peoples democratic republic": "laos",
}


def _clean(value) -> str:
    text = "" if value is None else str(value).strip()
    if text.lower() in {"", "24", "n/a", "na", "none", "null"}:
        return ""
    return text


def _ascii(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normalize_name(value: str) -> str:
    text = _ascii(_clean(value)).lower()
    text = re.sub(
        r"\b(ltd|limited|co|company|corp|corporation|inc|incorporated|llc|"
        r"sa|srl|spa|pte|plc|gmbh|bv|ag|factory|factories)\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_country(value: str) -> str:
    text = normalize_name(value)
    return COUNTRY_ALIASES.get(text, text)


def _slug_id(prefix: str, *parts: str) -> str:
    raw = "|".join(_clean(x) for x in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def read_csv(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _float(value):
    text = _clean(value)
    return float(text) if text else None


def _number(value):
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _official_address(row: dict) -> str:
    parts = [
        _clean(row.get("Address 1")),
        _clean(row.get("Address 2")),
        _clean(row.get("Address 3")),
        _clean(row.get("City")),
        _clean(row.get("Province")),
        _clean(row.get("Zip Code")),
    ]
    return ", ".join(x for x in parts if x)


def _candidate_score(row: dict, facility: dict) -> float:
    name_score = token_set_ratio(
        normalize_name(row.get("Account Name", "")),
        normalize_name(facility.get("name", "")),
    )
    city = normalize_name(row.get("City", ""))
    address = normalize_name(facility.get("address", ""))
    city_score = token_set_ratio(city, address) if city else 0.0
    official_address = normalize_name(_official_address(row))
    address_score = (
        token_set_ratio(official_address, address) if official_address else 0.0
    )
    return (0.78 * name_score) + (0.10 * city_score) + (0.12 * address_score)


def _match_official_row(
    row: dict,
    candidates: list[dict],
) -> tuple[dict | None, str, float]:
    country = normalize_country(row.get("Location", ""))
    same_country = [
        f
        for f in candidates
        if normalize_country(f.get("country_name", "")) == country
    ]
    if not same_country:
        return None, "UNMATCHED", 0.0

    name = normalize_name(row.get("Account Name", ""))
    exact = [f for f in same_country if normalize_name(f.get("name", "")) == name]
    if len(exact) == 1:
        return exact[0], "EXACT_NAME_COUNTRY", 100.0

    pool = exact if exact else same_country
    best = None
    best_score = -1.0
    for facility in pool:
        score = _candidate_score(row, facility)
        if score > best_score:
            best = facility
            best_score = score

    if best_score >= 86.0:
        return best, "FUZZY_HIGH_PRECISION", round(best_score, 2)

    return None, "UNMATCHED", round(max(0.0, best_score), 2)


def _preserved_demo_ids(path: str | Path | None) -> dict[tuple[str, str], str]:
    if not path:
        return {}
    result = {}
    for row in read_csv(path):
        result[
            (
                normalize_country(row.get("country", "")),
                normalize_name(row.get("account_name", row.get("name", ""))),
            )
        ] = row["facility_id"]
    return result


def build_network(
    *,
    primary_csv: str | Path,
    licensee_csv: str | Path,
    wet_process_csv: str | Path,
    facilities_csv: str | Path,
    output_dir: str | Path,
    demo_facilities_csv: str | Path | None = None,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    source_files = {
        "PRIMARY": Path(primary_csv),
        "LICENSEE": Path(licensee_csv),
        "WET_PROCESS": Path(wet_process_csv),
    }
    osh_rows = read_csv(facilities_csv)
    demo_ids = _preserved_demo_ids(demo_facilities_csv)

    list_candidates = {}
    all_adidas_osh: dict[str, dict] = {}
    for list_type, meta in LISTS.items():
        rows = [
            row
            for row in osh_rows
            if meta["tag"] in row.get("contributor (list)", "")
        ]
        list_candidates[list_type] = rows
        for row in rows:
            all_adidas_osh[row["os_id"]] = row

    canonical: dict[str, dict] = {}
    relationships: list[dict] = []
    matched = 0
    exact = 0
    fuzzy = 0
    unmatched = 0

    for list_type, source_path in source_files.items():
        official_rows = read_csv(source_path)
        for index, row in enumerate(official_rows, start=1):
            match, method, score = _match_official_row(
                row,
                list_candidates[list_type],
            )

            if match:
                matched += 1
                if method == "EXACT_NAME_COUNTRY":
                    exact += 1
                else:
                    fuzzy += 1

                demo_id = demo_ids.get(
                    (
                        normalize_country(row.get("Location", "")),
                        normalize_name(row.get("Account Name", "")),
                    )
                )
                network_id = demo_id or f"OSH-{match['os_id']}"
                lat = _float(match.get("lat"))
                lng = _float(match.get("lng"))
                coord_provenance = "PUBLIC_DERIVED"
                osh_url = f"https://opensupplyhub.org/facilities/{match['os_id']}"
                os_id = match["os_id"]
                canonical_name = match.get("name") or row.get("Account Name")
                address = match.get("address") or _official_address(row)
            else:
                unmatched += 1
                network_id = _slug_id(
                    "ADIDAS26",
                    list_type,
                    row.get("Location", ""),
                    row.get("Account Name", ""),
                    _official_address(row),
                )
                lat = None
                lng = None
                coord_provenance = "UNLOCATED"
                osh_url = ""
                os_id = ""
                canonical_name = row.get("Account Name")
                address = _official_address(row)

            rel_id = _slug_id(
                "REL",
                list_type,
                str(index),
                row.get("Location", ""),
                row.get("Account Name", ""),
            )

            relationship = {
                "relationship_id": rel_id,
                "network_facility_id": network_id,
                "list_type": list_type,
                "source_row": index,
                "country": _clean(row.get("Location")),
                "account_name": _clean(row.get("Account Name")),
                "address": _official_address(row),
                "city": _clean(row.get("City")),
                "province": _clean(row.get("Province")),
                "zip_code": _clean(row.get("Zip Code")),
                "tier": _clean(row.get("Tier")),
                "product_categories": _clean(row.get("Product Categories")),
                "workers_count": _number(row.get("Workers Count")),
                "female_workers": _number(row.get("Female Workers ")),
                "male_workers": _number(row.get("Male Workers")),
                "migrant_workers": _number(row.get("Migrant Workers")),
                "parent_organization": _clean(row.get("Parent Organization Name")),
                "trade_union": _clean(
                    row.get("Does the facility have a registered trade union(s) on-site?")
                ),
                "worker_representation": _clean(
                    row.get(
                        "Does the supplier have other means of democratically elected worker representation?"
                    )
                ),
                "cba": _clean(
                    row.get("Is there a Collective Bargaining Agreement (CBA) in place?")
                ),
                "os_id": os_id,
                "match_method": method,
                "match_score": score,
                "provenance_class": "VERIFIED_PUBLIC",
                "source_url": SOURCE_URL,
            }
            relationships.append(relationship)

            item = canonical.setdefault(
                network_id,
                {
                    "network_facility_id": network_id,
                    "os_id": os_id,
                    "name": _clean(canonical_name),
                    "official_name": _clean(row.get("Account Name")),
                    "country": _clean(row.get("Location")),
                    "city": _clean(row.get("City")),
                    "province": _clean(row.get("Province")),
                    "address": _clean(address),
                    "tiers": set(),
                    "product_categories": set(),
                    "list_types": set(),
                    "parent_organizations": set(),
                    "workers_count": None,
                    "relationship_count": 0,
                    "lat": lat,
                    "lng": lng,
                    "coordinate_provenance": coord_provenance,
                    "official_provenance": "VERIFIED_PUBLIC",
                    "match_methods": set(),
                    "source_url": SOURCE_URL,
                    "osh_url": osh_url,
                },
            )
            item["relationship_count"] += 1
            item["tiers"].add(_clean(row.get("Tier")))
            item["product_categories"].add(_clean(row.get("Product Categories")))
            item["list_types"].add(list_type)
            if _clean(row.get("Parent Organization Name")):
                item["parent_organizations"].add(
                    _clean(row.get("Parent Organization Name"))
                )
            if relationship["workers_count"] is not None:
                item["workers_count"] = relationship["workers_count"]
            item["match_methods"].add(method)

    # Add any adidas-tagged Open Supply Hub facility that did not match an
    # official row. This keeps the supplied public geospatial network complete.
    for os_id, row in all_adidas_osh.items():
        network_id = f"OSH-{os_id}"
        if network_id in canonical:
            continue
        canonical[network_id] = {
            "network_facility_id": network_id,
            "os_id": os_id,
            "name": _clean(row.get("name")),
            "official_name": "",
            "country": _clean(row.get("country_name")),
            "city": "",
            "province": "",
            "address": _clean(row.get("address")),
            "tiers": set(),
            "product_categories": set(),
            "list_types": set(),
            "parent_organizations": {
                x.strip()
                for x in (row.get("parent_company") or "").split("|")
                if x.strip()
            },
            "workers_count": None,
            "relationship_count": 0,
            "lat": _float(row.get("lat")),
            "lng": _float(row.get("lng")),
            "coordinate_provenance": "PUBLIC_DERIVED",
            "official_provenance": "PUBLIC_DERIVED",
            "match_methods": {"OSH_ADIDAS_CONTRIBUTOR"},
            "source_url": SOURCE_URL,
            "osh_url": f"https://opensupplyhub.org/facilities/{os_id}",
        }

    facility_rows = []
    for item in canonical.values():
        facility_rows.append(
            {
                **item,
                "tiers": "|".join(sorted(x for x in item["tiers"] if x)),
                "product_categories": "|".join(
                    sorted(x for x in item["product_categories"] if x)
                ),
                "list_types": "|".join(sorted(item["list_types"])),
                "parent_organizations": "|".join(
                    sorted(item["parent_organizations"])
                ),
                "match_methods": "|".join(sorted(item["match_methods"])),
            }
        )

    facility_rows.sort(
        key=lambda r: (
            normalize_country(r["country"]),
            normalize_name(r["name"]),
            r["network_facility_id"],
        )
    )

    parent_to_facilities: dict[str, set[str]] = defaultdict(set)
    parent_display = {}
    for row in facility_rows:
        for parent in (row["parent_organizations"] or "").split("|"):
            parent = parent.strip()
            if not parent:
                continue
            key = normalize_name(parent)
            if not key:
                continue
            parent_to_facilities[key].add(row["network_facility_id"])
            parent_display.setdefault(key, parent)

    parent_rows = [
        {
            "parent_id": _slug_id("PARENT", key),
            "parent_name": parent_display[key],
            "facility_count": len(facilities),
            "provenance_class": "VERIFIED_PUBLIC",
            "source_url": SOURCE_URL,
        }
        for key, facilities in parent_to_facilities.items()
    ]
    parent_rows.sort(key=lambda r: (-r["facility_count"], r["parent_name"]))

    parent_edges = []
    for row in facility_rows:
        for parent in (row["parent_organizations"] or "").split("|"):
            parent = parent.strip()
            if not parent:
                continue
            key = normalize_name(parent)
            if not key:
                continue
            parent_edges.append(
                {
                    "network_facility_id": row["network_facility_id"],
                    "parent_id": _slug_id("PARENT", key),
                    "relationship_type": "DISCLOSED_PARENT_ORGANIZATION",
                    "provenance_class": "VERIFIED_PUBLIC",
                    "source_url": SOURCE_URL,
                }
            )

    def write(name: str, rows: list[dict]):
        path = output / name
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write("adidas_2026_network_facilities.csv", facility_rows)
    write("adidas_2026_list_relationships.csv", relationships)
    write("adidas_2026_parent_groups.csv", parent_rows)
    write("adidas_2026_parent_edges.csv", parent_edges)

    stats = {
        "source_date": "2026-07-01",
        "official_rows": len(relationships),
        "primary_and_subcontractor_rows": sum(
            1 for r in relationships if r["list_type"] == "PRIMARY"
        ),
        "licensee_rows": sum(
            1 for r in relationships if r["list_type"] == "LICENSEE"
        ),
        "wet_process_rows": sum(
            1 for r in relationships if r["list_type"] == "WET_PROCESS"
        ),
        "open_supply_hub_adidas_facilities": len(all_adidas_osh),
        "network_facilities": len(facility_rows),
        "network_facilities_with_coordinates": sum(
            1 for r in facility_rows if r["lat"] is not None and r["lng"] is not None
        ),
        "official_rows_linked_to_network": matched,
        "exact_name_matches": exact,
        "fuzzy_matches": fuzzy,
        "unmatched_official_rows": unmatched,
        "countries": len({r["country"] for r in facility_rows if r["country"]}),
        "parent_groups": len(parent_rows),
        "provenance": {
            "official_list_rows": "VERIFIED_PUBLIC",
            "open_supply_hub_coordinates": "PUBLIC_DERIVED",
        },
    }
    (output / "adidas_2026_network_stats.json").write_text(
        json.dumps(stats, indent=2),
        encoding="utf-8",
    )

    return stats
