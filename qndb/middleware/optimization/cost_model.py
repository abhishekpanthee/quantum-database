"""Quantum-aware cost model."""

import math
from typing import Dict, Any, Optional

from qndb.middleware.optimization.statistics import TableStatistics


class QuantumCostModel:
    """Cost model incorporating quantum resource estimates."""

    def __init__(self, error_rate: float = 0.001, available_qubits: int = 50):
        self.error_rate = error_rate
        self.available_qubits = available_qubits

    def cost(self, plan: Dict[str, Any], stats: Optional[TableStatistics] = None) -> Dict[str, Any]:
        cardinality = float(plan.get("estimated_rows", 100))
        if stats:
            cardinality = stats.estimate_cardinality(plan.get("conditions"))

        n = max(int(cardinality), 1)
        qubits = max(int(math.log2(n)) + 1, 2) if n > 0 else 2
        depth = int(math.pi / 4 * math.sqrt(n)) if n > 0 else 1
        gates = qubits * depth
        # error probability ~ 1 - (1-p)^gates
        error_prob = 1.0 - (1.0 - self.error_rate) ** gates

        return {
            "qubits": qubits,
            "depth": depth,
            "gates": gates,
            "error_probability": round(error_prob, 6),
            "classical_ops": int(cardinality),
            "estimated_rows": cardinality,
            "exceeds_capacity": qubits > self.available_qubits,
        }
