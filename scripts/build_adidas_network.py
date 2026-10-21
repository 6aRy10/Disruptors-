from __future__ import annotations

import argparse
import json

from dependency.data.adidas_network import build_network

parser = argparse.ArgumentParser(
    description="Rebuild the canonical adidas 2026 public network from source CSVs."
)
parser.add_argument("--primary", required=True)
parser.add_argument("--licensees", required=True)
parser.add_argument("--wet-process", required=True)
parser.add_argument("--facilities", required=True)
parser.add_argument("--output-dir", default="data/normalized")
parser.add_argument("--demo-facilities", default="config/facilities_demo.csv")
args = parser.parse_args()

stats = build_network(
    primary_csv=args.primary,
    licensee_csv=args.licensees,
    wet_process_csv=args.wet_process,
    facilities_csv=args.facilities,
    output_dir=args.output_dir,
    demo_facilities_csv=args.demo_facilities,
)

print(json.dumps(stats, indent=2))
