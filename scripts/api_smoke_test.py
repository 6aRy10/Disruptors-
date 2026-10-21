from dependency.api.main import event_exposure, health, scenario_recovery


def main() -> None:
    print("HEALTH")
    print(health())

    print("\nEXPOSURE")
    exposure = event_exposure(
        "IDN-CIANJUR-2022-USGS-us7000ir9t",
        radius_km=100,
    )
    print({
        "event_id": exposure["event_id"],
        "facility_count": len(exposure["facilities"]),
        "status": exposure["exposure_status"],
    })

    print("\nRECOVERY")
    plan = scenario_recovery(
        "SCN-CIANJUR-REPLAY-01",
        "JI2993",
        release_safety_stock=False,
    )
    print({
        "state_version": plan["state_version"],
        "plan_status": plan["plan_status"],
        "shortage_units": plan["shortage_units"],
        "requires_supplier_confirmation": plan["requires_supplier_confirmation"],
    })


if __name__ == "__main__":
    main()
