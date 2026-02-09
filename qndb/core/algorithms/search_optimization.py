"""
Search & Optimization Algorithms
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Quantum algorithms for search and combinatorial optimization in
database workloads:

* **QuantumWalkSpatialSearch** — √N-advantage spatial search on structured graphs
* **QAOASolver** — QAOA for constraint-satisfaction queries
* **VQESolver** — VQE for optimization problems expressed as queries
* **QuantumAnnealingInterface** — interface to quantum/simulated annealing
* **AdaptiveGrover** — Grover's with unknown number of solutions
"""

import cirq
import math
import logging
import numpy as np
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Quantum Walk Spatial Search
# ======================================================================

class QuantumWalkSpatialSearch:
    """√N-advantage spatial search on user-defined graphs.

    Generalises the hypercube walk in ``QuantumSearch.quantum_walk_search``
    to arbitrary adjacency structures (grids, complete graphs, Erdős-Rényi,
    etc.).  The walker's Hilbert space is *position ⊗ coin*, where the
    coin dimension equals the maximum vertex degree.

    Args:
        num_vertices: Number of vertices in the search graph.
        adjacency: Adjacency list ``{vertex: [neighbours]}``.
                   If *None*, defaults to a hypercube.
    """

    def __init__(
        self,
        num_vertices: int,
        adjacency: Optional[Dict[int, List[int]]] = None,
    ) -> None:
        self.num_vertices = num_vertices
        self.pos_qubits_n = max(1, int(math.ceil(math.log2(num_vertices))))
        if adjacency is None:
            adjacency = self._hypercube_adj(self.pos_qubits_n)
        self.adjacency = adjacency
        self.max_degree = max((len(v) for v in adjacency.values()), default=1)
        self.coin_qubits_n = max(1, int(math.ceil(math.log2(self.max_degree))))

    # -- public API --------------------------------------------------------

    def build_circuit(
        self,
        marked: List[int],
        num_steps: Optional[int] = None,
    ) -> cirq.Circuit:
        """Build the quantum-walk search circuit.

        Args:
            marked: Indices of marked vertices.
            num_steps: Walk steps (defaults to ⌈√N⌉).

        Returns:
            Measurement-ready ``cirq.Circuit``.
        """
        if num_steps is None:
            num_steps = max(1, int(math.ceil(math.sqrt(self.num_vertices))))

        pos = [cirq.LineQubit(i) for i in range(self.pos_qubits_n)]
        coin = [cirq.LineQubit(self.pos_qubits_n + i) for i in range(self.coin_qubits_n)]

        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*pos))
        circuit.append(cirq.H.on_each(*coin))

        oracle = self._build_oracle(pos, marked)

        for _ in range(num_steps):
            circuit += oracle
            circuit += self._coin_operator(coin)
            circuit += self._shift_operator(pos, coin)

        circuit.append(cirq.measure(*pos, key="result"))
        return circuit

    # -- internal helpers --------------------------------------------------

    def _build_oracle(self, pos: List[cirq.LineQubit], marked: List[int]) -> cirq.Circuit:
        c = cirq.Circuit()
        for item in marked:
            bits = format(item, f"0{self.pos_qubits_n}b")
            flips = [cirq.X(pos[i]) for i, b in enumerate(bits) if b == "0"]
            c.append(flips)
            if len(pos) > 1:
                c.append(cirq.Z(pos[-1]).controlled_by(*pos[:-1]))
            else:
                c.append(cirq.Z(pos[0]))
            c.append(flips)
        return c

    @staticmethod
    def _coin_operator(coin: List[cirq.LineQubit]) -> cirq.Circuit:
        c = cirq.Circuit()
        c.append(cirq.H.on_each(*coin))
        c.append(cirq.X.on_each(*coin))
        if len(coin) > 1:
            c.append(cirq.Z(coin[-1]).controlled_by(*coin[:-1]))
        else:
            c.append(cirq.Z(coin[0]))
        c.append(cirq.X.on_each(*coin))
        c.append(cirq.H.on_each(*coin))
        return c

    def _shift_operator(
        self, pos: List[cirq.LineQubit], coin: List[cirq.LineQubit],
    ) -> cirq.Circuit:
        c = cirq.Circuit()
        for idx in range(min(self.coin_qubits_n, self.pos_qubits_n)):
            c.append(cirq.CNOT(coin[idx], pos[idx]))
        return c

    @staticmethod
    def _hypercube_adj(dim: int) -> Dict[int, List[int]]:
        n = 2 ** dim
        adj: Dict[int, List[int]] = {}
        for v in range(n):
            adj[v] = [v ^ (1 << d) for d in range(dim)]
        return adj


# ======================================================================
# QAOA — Quantum Approximate Optimization Algorithm
# ======================================================================

class QAOASolver:
    """QAOA for constraint-satisfaction queries.

    Encodes a cost function into a problem Hamiltonian and alternates
    cost and mixer layers.  Classical parameter optimisation is
    performed via Nelder-Mead on the simulated expectation value.

    Args:
        num_qubits: Problem size (number of binary variables).
        depth: Number of QAOA layers (*p*).
    """

    def __init__(self, num_qubits: int, depth: int = 1) -> None:
        self.num_qubits = num_qubits
        self.depth = depth
        self._optimal_params: Optional[np.ndarray] = None

    # -- circuit construction ----------------------------------------------

    def build_circuit(
        self,
        gammas: List[float],
        betas: List[float],
        cost_edges: List[Tuple[int, int]],
        cost_weights: Optional[List[float]] = None,
    ) -> cirq.Circuit:
        """Build a QAOA circuit.

        Args:
            gammas: Cost-layer angles (length = *depth*).
            betas: Mixer-layer angles (length = *depth*).
            cost_edges: Pairs of qubit indices coupled in the cost
                Hamiltonian (e.g. edges of a MaxCut graph).
            cost_weights: Optional per-edge weights (default 1.0).

        Returns:
            Parameterised ``cirq.Circuit`` (without measurement).
        """
        if len(gammas) != self.depth or len(betas) != self.depth:
            raise ValueError("gammas and betas must each have length = depth")

        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        weights = cost_weights or [1.0] * len(cost_edges)

        circuit = cirq.Circuit()
        # Initial superposition
        circuit.append(cirq.H.on_each(*qubits))

        for layer in range(self.depth):
            # Cost layer: exp(-i * gamma * C)
            for (i, j), w in zip(cost_edges, weights):
                circuit.append(cirq.ZZPowGate(exponent=gammas[layer] * w / math.pi).on(
                    qubits[i], qubits[j],
                ))
            # Mixer layer: exp(-i * beta * B)  where B = Σ X_i
            for q in qubits:
                circuit.append(cirq.rx(2 * betas[layer]).on(q))

        return circuit

    def build_measured_circuit(
        self,
        gammas: List[float],
        betas: List[float],
        cost_edges: List[Tuple[int, int]],
        cost_weights: Optional[List[float]] = None,
    ) -> cirq.Circuit:
        """Build the QAOA circuit with measurement appended."""
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = self.build_circuit(gammas, betas, cost_edges, cost_weights)
        circuit.append(cirq.measure(*qubits, key="result"))
        return circuit

    # -- classical optimisation loop ---------------------------------------

    def optimize(
        self,
        cost_edges: List[Tuple[int, int]],
        cost_weights: Optional[List[float]] = None,
        repetitions: int = 1000,
        max_iterations: int = 200,
    ) -> Dict[str, Any]:
        """Run the full QAOA optimisation loop.

        Uses a local Cirq simulator and Nelder-Mead to find optimal
        (gamma, beta).

        Returns:
            Dict with keys ``best_bitstring``, ``best_cost``,
            ``optimal_gammas``, ``optimal_betas``.
        """
        from scipy.optimize import minimize as sp_minimize

        weights = cost_weights or [1.0] * len(cost_edges)
        simulator = cirq.Simulator()

        def _cost_fn(params: np.ndarray) -> float:
            gs = params[: self.depth].tolist()
            bs = params[self.depth :].tolist()
            circ = self.build_measured_circuit(gs, bs, cost_edges, weights)
            result = simulator.run(circ, repetitions=repetitions)
            bits = result.measurements["result"]
            total = 0.0
            for sample in bits:
                for (i, j), w in zip(cost_edges, weights):
                    if sample[i] != sample[j]:
                        total += w
            return -total / len(bits)  # minimise negative cost

        x0 = np.random.uniform(0, math.pi, 2 * self.depth)
        opt = sp_minimize(_cost_fn, x0, method="Nelder-Mead",
                          options={"maxiter": max_iterations})

        best_gs = opt.x[: self.depth].tolist()
        best_bs = opt.x[self.depth :].tolist()
        self._optimal_params = opt.x

        # Sample the best circuit
        circ = self.build_measured_circuit(best_gs, best_bs, cost_edges, weights)
        result = simulator.run(circ, repetitions=repetitions)
        bits = result.measurements["result"]
        best_cost = -float("inf")
        best_bs_str = ""
        for sample in bits:
            c = sum(w for (i, j), w in zip(cost_edges, weights) if sample[i] != sample[j])
            if c > best_cost:
                best_cost = c
                best_bs_str = "".join(str(int(b)) for b in sample)

        logger.info("QAOA optimised: best_cost=%.4f", best_cost)
        return {
            "best_bitstring": best_bs_str,
            "best_cost": best_cost,
            "optimal_gammas": best_gs,
            "optimal_betas": best_bs,
        }


# ======================================================================
# VQE — Variational Quantum Eigensolver
# ======================================================================

class VQESolver:
    """VQE for optimisation problems expressed as quantum queries.

    The ansatz uses a hardware-efficient *Ry-CNOT* ladder.

    Args:
        num_qubits: Number of qubits.
        ansatz_depth: Number of variational layers.
    """

    def __init__(self, num_qubits: int, ansatz_depth: int = 2) -> None:
        self.num_qubits = num_qubits
        self.ansatz_depth = ansatz_depth

    def build_ansatz(self, params: np.ndarray) -> cirq.Circuit:
        """Build the parameterised ansatz circuit.

        Args:
            params: Flat array of rotation angles.  Size must be
                ``num_qubits * ansatz_depth``.

        Returns:
            Ansatz ``cirq.Circuit``.
        """
        expected = self.num_qubits * self.ansatz_depth
        if len(params) != expected:
            raise ValueError(f"Expected {expected} params, got {len(params)}")

        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()
        idx = 0
        for _layer in range(self.ansatz_depth):
            for q in qubits:
                circuit.append(cirq.ry(params[idx]).on(q))
                idx += 1
            for i in range(self.num_qubits - 1):
                circuit.append(cirq.CNOT(qubits[i], qubits[i + 1]))
        return circuit

    def compute_expectation(
        self,
        hamiltonian_terms: List[Tuple[float, List[Tuple[int, str]]]],
        params: np.ndarray,
        repetitions: int = 1000,
    ) -> float:
        """Estimate ⟨ψ(θ)|H|ψ(θ)⟩ by sampling.

        Args:
            hamiltonian_terms: List of ``(coefficient, [(qubit, pauli), …])``
                where *pauli* is ``"X"``, ``"Y"``, or ``"Z"``.
            params: Variational parameters.
            repetitions: Shots per Pauli term.

        Returns:
            Estimated expectation value.
        """
        simulator = cirq.Simulator()
        total = 0.0

        for coeff, paulis in hamiltonian_terms:
            qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
            circuit = self.build_ansatz(params)

            # Rotate into measurement basis
            for q_idx, basis in paulis:
                if basis == "X":
                    circuit.append(cirq.H(qubits[q_idx]))
                elif basis == "Y":
                    circuit.append(cirq.rx(-math.pi / 2).on(qubits[q_idx]))
                # Z: no change

            meas_qubits = [qubits[q_idx] for q_idx, _ in paulis]
            circuit.append(cirq.measure(*meas_qubits, key="m"))

            result = simulator.run(circuit, repetitions=repetitions)
            bits = result.measurements["m"]
            # Eigenvalue is (-1)^(sum_of_bits)
            eigenvalues = np.array([(-1) ** int(np.sum(b)) for b in bits])
            total += coeff * float(np.mean(eigenvalues))

        return total

    def optimize(
        self,
        hamiltonian_terms: List[Tuple[float, List[Tuple[int, str]]]],
        repetitions: int = 1000,
        max_iterations: int = 200,
    ) -> Dict[str, Any]:
        """Run the full VQE optimisation loop.

        Returns:
            Dict with ``optimal_params``, ``ground_energy``.
        """
        from scipy.optimize import minimize as sp_minimize

        n_params = self.num_qubits * self.ansatz_depth
        x0 = np.random.uniform(0, 2 * math.pi, n_params)

        def _obj(p: np.ndarray) -> float:
            return self.compute_expectation(hamiltonian_terms, p, repetitions)

        opt = sp_minimize(_obj, x0, method="COBYLA",
                          options={"maxiter": max_iterations})
        logger.info("VQE converged: energy=%.6f", opt.fun)
        return {"optimal_params": opt.x.tolist(), "ground_energy": float(opt.fun)}


# ======================================================================
# Adaptive Grover's Search
# ======================================================================

class AdaptiveGrover:
    """Grover's search with unknown number of solutions.

    Uses the *exponential search* strategy: run Grover with
    geometrically increasing iteration counts until a marked item
    is found.

    Args:
        num_qubits: Search-space qubits.
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.database_size = 2 ** num_qubits

    def build_circuit(
        self,
        oracle: cirq.Circuit,
        num_iterations: int,
    ) -> cirq.Circuit:
        """Build a Grover circuit with a given iteration count.

        Args:
            oracle: Phase-oracle circuit.
            num_iterations: Grover iterations.

        Returns:
            Measured ``cirq.Circuit``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        diffusion = self._diffusion(qubits)
        for _ in range(num_iterations):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*qubits, key="result"))
        return circuit

    def run_adaptive(
        self,
        oracle: cirq.Circuit,
        verify: Callable[[int], bool],
        max_rounds: int = 20,
        repetitions: int = 1,
    ) -> Optional[int]:
        """Run adaptive search with exponentially growing iterations.

        Args:
            oracle: Phase-oracle.
            verify: Classical function that returns ``True`` if a
                candidate is a valid solution.
            max_rounds: Maximum number of doubling rounds.
            repetitions: Shots per round.

        Returns:
            The found solution index, or ``None``.
        """
        simulator = cirq.Simulator()
        lam = 6 / 5  # growth factor (per Boyer-Brassard-Høyer-Tapp)
        m = 1
        for _round in range(max_rounds):
            k = np.random.randint(0, int(m) + 1)
            k = max(k, 1)
            circ = self.build_circuit(oracle, k)
            result = simulator.run(circ, repetitions=repetitions)
            bits = result.measurements["result"]
            for sample in bits:
                candidate = int("".join(str(int(b)) for b in sample), 2)
                if verify(candidate):
                    logger.info("AdaptiveGrover found solution %d at round %d (k=%d)",
                                candidate, _round, k)
                    return candidate
            m *= lam
            if m > self.database_size:
                m = self.database_size
        return None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _diffusion(qubits: List[cirq.LineQubit]) -> cirq.Circuit:
        c = cirq.Circuit()
        c.append(cirq.H.on_each(*qubits))
        c.append(cirq.X.on_each(*qubits))
        if len(qubits) > 1:
            c.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
        else:
            c.append(cirq.Z(qubits[0]))
        c.append(cirq.X.on_each(*qubits))
        c.append(cirq.H.on_each(*qubits))
        return c


# ======================================================================
# Quantum Annealing Interface
# ======================================================================

class QuantumAnnealingInterface:
    """Simulated quantum annealing for combinatorial optimisation.

    Encodes an Ising-model cost function and performs an annealing
    schedule using Trotterised time evolution.

    Args:
        num_qubits: Number of spin variables.
        total_time: Total annealing time (arb. units).
        num_trotter_steps: Trotter decomposition steps.
    """

    def __init__(
        self,
        num_qubits: int,
        total_time: float = 4.0,
        num_trotter_steps: int = 20,
    ) -> None:
        self.num_qubits = num_qubits
        self.total_time = total_time
        self.num_trotter_steps = num_trotter_steps

    def build_circuit(
        self,
        couplings: Dict[Tuple[int, int], float],
        fields: Optional[Dict[int, float]] = None,
    ) -> cirq.Circuit:
        """Build the annealing circuit.

        The schedule linearly interpolates between the transverse-field
        mixer and the problem Hamiltonian.

        Args:
            couplings: ``{(i,j): J_ij}`` Ising couplings.
            fields: ``{i: h_i}`` local fields (default 0).

        Returns:
            Measured ``cirq.Circuit``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        fields = fields or {}
        dt = self.total_time / self.num_trotter_steps
        circuit = cirq.Circuit()

        # Start in ground state of mixer (|+⟩^n)
        circuit.append(cirq.H.on_each(*qubits))

        for step in range(self.num_trotter_steps):
            s = (step + 1) / self.num_trotter_steps  # 0→1

            # Problem Hamiltonian: (s) * Σ J_ij Z_i Z_j + h_i Z_i
            for (i, j), jval in couplings.items():
                angle = 2 * s * jval * dt
                circuit.append(cirq.ZZPowGate(exponent=angle / math.pi).on(
                    qubits[i], qubits[j],
                ))
            for i, h in fields.items():
                angle = 2 * s * h * dt
                circuit.append(cirq.rz(angle).on(qubits[i]))

            # Mixer: (1 - s) * Σ X_i
            mixer_strength = (1 - s) * dt
            for q in qubits:
                circuit.append(cirq.rx(2 * mixer_strength).on(q))

        circuit.append(cirq.measure(*qubits, key="result"))
        return circuit

    def anneal(
        self,
        couplings: Dict[Tuple[int, int], float],
        fields: Optional[Dict[int, float]] = None,
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Run the annealing and return the best solution.

        Returns:
            Dict with ``best_bitstring``, ``best_energy``, ``histogram``.
        """
        circuit = self.build_circuit(couplings, fields)
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["result"]

        best_energy = float("inf")
        best_bs = ""
        histogram: Dict[str, int] = {}

        for sample in bits:
            bs = "".join(str(int(b)) for b in sample)
            histogram[bs] = histogram.get(bs, 0) + 1
            e = self._ising_energy(sample, couplings, fields or {})
            if e < best_energy:
                best_energy = e
                best_bs = bs

        logger.info("Annealing complete: best_energy=%.4f", best_energy)
        return {
            "best_bitstring": best_bs,
            "best_energy": best_energy,
            "histogram": histogram,
        }

    @staticmethod
    def _ising_energy(
        bits: np.ndarray,
        couplings: Dict[Tuple[int, int], float],
        fields: Dict[int, float],
    ) -> float:
        spins = 2 * bits.astype(float) - 1  # {0,1} → {-1,+1}
        e = sum(j * spins[i] * spins[k] for (i, k), j in couplings.items())
        e += sum(h * spins[i] for i, h in fields.items())
        return float(e)
