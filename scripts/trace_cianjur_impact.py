from __future__ import annotations

import json

from dependency.graph.impact import trace_event_impact

EVENT_ID = "IDN-CIANJUR-2022-USGS-us7000ir9t"

impact = trace_event_impact(event_id=EVENT_ID, radius_km=100)

print("\nCIANJUR IMPACT TRACE")
print("=" * 72)
print(f"Event: {impact['event_id']}")
print(f"Rule: facilities within {impact['radius_km']} km")
print(f"Status: {impact['exposure_status']} (proximity is not proof of shutdown)")
print(f"Facilities potentially exposed: {len(impact['facilities'])}")

print("\nDEPENDENCY PATHS")
for path in impact["dependency_paths"]:
    if path["path_type"] == "ASSEMBLY":
        print(
            f"  ASSEMBLY: {path['facility_name']} ({path['distance_km']} km)"
            f" -> {path['sku']} {path['product_name']}"
        )
    else:
        print(
            f"  MATERIAL: {path['facility_name']} ({path['distance_km']} km)"
            f" -> {path['material_id']} {path['material_name']}"
            f" -> {path['sku']} {path['product_name']}"
        )

print("\nPRODUCT / COMMERCIAL EXPOSURE")
for product in impact["products"]:
    print(
        f"  {product['sku']} {product['name']}: "
        f"{product['commitment_units']:.0f} units committed, "
        f"EUR {product['revenue_eur']:,.0f} revenue, "
        f"EUR {product['gross_margin_eur']:,.0f} gross margin, "
        f"earliest due {product['earliest_due_date']}"
    )

print("\nTOTALS")
print(json.dumps(impact["totals"], indent=2))
