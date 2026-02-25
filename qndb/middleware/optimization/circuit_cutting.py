"""Circuit cutting utilities for queries exceeding available qubits."""

from typing import Dict, List, Any


def circuit_cut_needed(cost: Dict[str, Any]) -> bool:
    return cost.get("exceeds_capacity", False)


def cut_plan_into_subplans(plan: Dict[str, Any], max_qubits: int) -> List[Dict[str, Any]]:
    """Split a large plan into independent sub-plans that each fit within
    *max_qubits*.  This is a simplified version that partitions by table."""
    subplans: List[Dict[str, Any]] = []
    # Each sub-plan gets a proportional share of qubits
    n_parts = max(1, plan.get("qubits", max_qubits) // max_qubits)
    rows = plan.get("estimated_rows", 100)
    per_part = max(int(rows / n_parts), 1)
    for i in range(n_parts):
        sp = dict(plan)
        sp["partition"] = i
        sp["estimated_rows"] = per_part
        sp["qubits"] = min(plan.get("qubits", max_qubits), max_qubits)
        subplans.append(sp)
    return subplans
