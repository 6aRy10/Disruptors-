from __future__ import annotations


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


def band(score: float) -> str:
    s = _clamp(score)
    if s < 30:
        return "LOW"
    if s < 50:
        return "MODERATE"
    if s < 70:
        return "HIGH"
    return "CRITICAL"


def event_business_risk(
    disruption_severity: float,
    dependency_criticality: float,
    time_urgency: float,
    commercial_exposure: float,
    recovery_difficulty: float,
) -> float:
    score = (
        0.20 * _clamp(disruption_severity)
        + 0.25 * _clamp(dependency_criticality)
        + 0.20 * _clamp(time_urgency)
        + 0.20 * _clamp(commercial_exposure)
        + 0.15 * _clamp(recovery_difficulty)
    )
    return round(score, 1)


def facility_risk(event_severity, exposure_confidence, operational_criticality, recovery_difficulty):
    score = (
        0.35 * _clamp(event_severity)
        + 0.25 * _clamp(exposure_confidence)
        + 0.20 * _clamp(operational_criticality)
        + 0.20 * _clamp(recovery_difficulty)
    )
    return round(score, 1)


def material_risk(upstream_facility_risk, source_concentration, inventory_urgency, lead_time_risk):
    score = (
        0.35 * _clamp(upstream_facility_risk)
        + 0.25 * _clamp(source_concentration)
        + 0.20 * _clamp(inventory_urgency)
        + 0.20 * _clamp(lead_time_risk)
    )
    return round(score, 1)


def product_risk(upstream_disruption, assembly_capacity_risk, inventory_coverage_risk, commercial_impact):
    score = (
        0.30 * _clamp(upstream_disruption)
        + 0.30 * _clamp(assembly_capacity_risk)
        + 0.20 * _clamp(inventory_coverage_risk)
        + 0.20 * _clamp(commercial_impact)
    )
    return round(score, 1)


def commitment_risk(product_risk_score, shortage_ratio, due_date_urgency, priority_value):
    score = (
        0.35 * _clamp(product_risk_score)
        + 0.30 * _clamp(shortage_ratio)
        + 0.20 * _clamp(due_date_urgency)
        + 0.15 * _clamp(priority_value)
    )
    return round(score, 1)
