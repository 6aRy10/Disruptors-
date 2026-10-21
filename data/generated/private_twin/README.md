# Generated enterprise private twin

This directory is created by:

```powershell
python scripts/generate_enterprise_scale_data.py
```

It is also regenerated automatically by `python scripts/load_seed_data.py`.

The generated files are intentionally large enough to exercise the same graph,
SQL, recovery and agent tools on enterprise-scale private data.

Important truth rule:

- facility identities and coordinates are selected from the loaded public Adidas
  supplier network;
- SKU assignments, BOMs, material sources, allocations, orders, inventory,
  capacities, substitutions and transport routes are `SIMULATED_PRIVATE`;
- the generator excludes Indonesia, China and Vietnam from the scale expansion
  so the flagship Cianjur demo and the two secondary scenario ground-truth
  fixtures do not get silently changed by synthetic scale rows.

The committed source of truth is the deterministic generator. The generated CSV
files can be deleted and rebuilt at any time.
