from __future__ import annotations

import csv
import json
from pathlib import Path

from dependency.data.enterprise_scale import (
    GENERATED,
    generate_enterprise_scale,
    write_enterprise_scale,
)


ROOT = Path(__file__).resolve().parents[1]
NETWORK = ROOT / "data" / "normalized" / "adidas_2026_network_facilities.csv"


def main() -> None:
    with NETWORK.open(newline="", encoding="utf-8-sig") as handle:
        network_rows = list(csv.DictReader(handle))

    data = generate_enterprise_scale(network_rows)
    manifest = write_enterprise_scale(data)

    print(f"Generated enterprise private twin at: {GENERATED}")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
