"""Small reproducible benchmark scaffold.

The team can expand this to full graph/route/BOM perturbations. It exists now so the
repo has a clear evaluation path instead of relying only on a polished demo.
"""
from __future__ import annotations
import random
from dependency.solver.feasibility import check_plan


def run(seed: int = 42, n: int = 100) -> dict:
    rng = random.Random(seed)
    feasible_count = 0
    expected_feasible_count = 0
    correct = 0
    for _ in range(n):
        demand = rng.randint(1000, 10000)
        finished = rng.randint(0, 4000)
        capacity = rng.randint(0, 9000)
        materials_ok = rng.random() > 0.15
        route_ok = rng.random() > 0.15
        approved = rng.random() > 0.10
        expected = materials_ok and route_ok and approved and finished + capacity >= demand
        result = check_plan(
            required_units=demand,
            finished_units=finished,
            assembly_units=capacity,
            materials_available=materials_ok,
            route_on_time=route_ok,
            approved=approved,
        )
        if expected:
            expected_feasible_count += 1
        if result["feasible"]:
            feasible_count += 1
        if result["feasible"] == expected:
            correct += 1
    return {
        "seed": seed,
        "scenarios": n,
        "correct_feasibility": correct,
        "accuracy": round(correct / n, 4),
        "expected_feasible": expected_feasible_count,
        "solver_feasible": feasible_count,
    }


if __name__ == "__main__":
    print(run())
