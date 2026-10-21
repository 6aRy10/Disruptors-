from __future__ import annotations


def tariff_impact(*, customs_value_per_unit: float, additional_rate: float, units: int, baseline_unit_margin: float) -> dict:
    if customs_value_per_unit < 0 or additional_rate < 0 or units < 0:
        raise ValueError("tariff inputs must be non-negative")
    additional_cost_per_unit = round(customs_value_per_unit * additional_rate, 2)
    total_additional_cost = round(additional_cost_per_unit * units, 2)
    new_unit_margin = round(baseline_unit_margin - additional_cost_per_unit, 2)
    return {
        "additional_cost_per_unit": additional_cost_per_unit,
        "total_additional_cost": total_additional_cost,
        "baseline_unit_margin": baseline_unit_margin,
        "new_unit_margin": new_unit_margin,
        "margin_change_per_unit": round(-additional_cost_per_unit, 2),
    }
