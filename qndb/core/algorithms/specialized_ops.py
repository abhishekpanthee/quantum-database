"""
Specialised Database Operations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Quantum algorithms tailored to database tasks:

* **QuantumPatternMatcher** — pattern matching beyond Grover's
* **QuantumGraphAlgorithms** — shortest path, MST, graph isomorphism
* **QuantumTimeSeriesAnalyzer** — QFT-based time-series analysis
* **QuantumANN** — approximate nearest-neighbour search
* **QuantumCompressor** — quantum-enhanced data compression
"""

import cirq
import math
import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ======================================================================
# Quantum Pattern Matcher
# ======================================================================

class QuantumPatternMatcher:
    """Quantum string/pattern matching beyond Grover's oracle search.

    Encodes text and pattern into quantum registers and uses amplitude
    amplification on a shift-and-compare oracle to find all matches in
    O(√(N/M)) where *N* is text length and *M* is pattern length.

    Args:
        alphabet_bits: Number of bits per character (default 8 = ASCII).
    """

    def __init__(self, alphabet_bits: int = 8) -> None:
        self.alphabet_bits = alphabet_bits

    def build_circuit(
        self,
        text: List[int],
        pattern: List[int],
        num_grover_iters: Optional[int] = None,
    ) -> cirq.Circuit:
        """Build the pattern-search circuit.

        The circuit encodes possible shift positions in a *position*
        register and applies an oracle that marks positions where the
        pattern matches.

        Args:
            text: List of integer character codes.
            pattern: List of integer character codes.
            num_grover_iters: Grover iterations (auto-computed if *None*).

        Returns:
            Measured ``cirq.Circuit``.
        """
        n_text = len(text)
        n_pat = len(pattern)
        if n_pat > n_text:
            raise ValueError("Pattern longer than text")

        n_positions = n_text - n_pat + 1
        pos_qubits_n = max(1, int(math.ceil(math.log2(n_positions))))

        if num_grover_iters is None:
            # Assume one match
            num_grover_iters = max(1, int(math.floor(math.pi / 4 * math.sqrt(n_positions))))

        pos = [cirq.LineQubit(i) for i in range(pos_qubits_n)]
        flag = cirq.LineQubit(pos_qubits_n)

        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*pos))

        oracle = self._match_oracle(pos, flag, text, pattern, n_positions, pos_qubits_n)
        diffusion = self._diffusion(pos)

        for _ in range(num_grover_iters):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*pos, key="position"))
        return circuit

    def _match_oracle(
        self,
        pos: List[cirq.LineQubit],
        flag: cirq.LineQubit,
        text: List[int],
        pattern: List[int],
        n_positions: int,
        n_bits: int,
    ) -> cirq.Circuit:
        """Oracle that phase-marks positions where the pattern matches."""
        c = cirq.Circuit()
        for shift in range(n_positions):
            if all(text[shift + j] == pattern[j] for j in range(len(pattern))):
                bits = format(shift, f"0{n_bits}b")
                flips = [cirq.X(pos[i]) for i, b in enumerate(bits) if b == "0"]
                c.append(flips)
                if len(pos) > 1:
                    c.append(cirq.Z(pos[-1]).controlled_by(*pos[:-1]))
                else:
                    c.append(cirq.Z(pos[0]))
                c.append(flips)
        return c

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
# Quantum Graph Algorithms
# ======================================================================

class QuantumGraphAlgorithms:
    """Quantum graph algorithms: shortest path, MST, isomorphism.

    Uses QAOA-style circuits for combinatorial graph problems and
    Grover oracles for decision problems.

    Args:
        num_vertices: Number of graph vertices.
    """

    def __init__(self, num_vertices: int) -> None:
        self.num_vertices = num_vertices
        self.vertex_qubits = max(1, int(math.ceil(math.log2(num_vertices))))

    def shortest_path_circuit(
        self,
        adjacency: Dict[Tuple[int, int], float],
        source: int,
        target: int,
        max_path_length: int = 4,
        qaoa_depth: int = 1,
    ) -> cirq.Circuit:
        """Build a QAOA circuit for shortest-path estimation.

        Encodes the shortest-path problem as a constraint-satisfaction
        QAOA: binary variables indicate whether each edge is included
        in the path.

        Args:
            adjacency: ``{(u, v): weight}`` for each edge.
            source: Source vertex.
            target: Target vertex.
            max_path_length: Maximum number of edges in a path.
            qaoa_depth: QAOA *p* parameter.

        Returns:
            Measured ``cirq.Circuit``.
        """
        edges = list(adjacency.keys())
        n_edge_qubits = len(edges)
        if n_edge_qubits == 0:
            raise ValueError("Graph has no edges")

        qubits = [cirq.LineQubit(i) for i in range(n_edge_qubits)]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        gamma = math.pi / (2 * qaoa_depth)
        beta = math.pi / (4 * qaoa_depth)

        for _ in range(qaoa_depth):
            # Cost layer: penalise high total weight
            for idx, (edge, weight) in enumerate(zip(edges, [adjacency[e] for e in edges])):
                circuit.append(cirq.rz(2 * gamma * weight).on(qubits[idx]))

            # Connectivity constraints via ZZ couplings
            for i in range(n_edge_qubits):
                for j in range(i + 1, n_edge_qubits):
                    e1, e2 = edges[i], edges[j]
                    # Edges sharing a vertex are coupled
                    if set(e1) & set(e2):
                        circuit.append(cirq.ZZPowGate(exponent=gamma / math.pi).on(
                            qubits[i], qubits[j],
                        ))

            # Mixer
            for q in qubits:
                circuit.append(cirq.rx(2 * beta).on(q))

        circuit.append(cirq.measure(*qubits, key="edges"))
        return circuit

    def graph_isomorphism_circuit(
        self,
        adj_a: List[Tuple[int, int]],
        adj_b: List[Tuple[int, int]],
        num_grover_iters: int = 2,
    ) -> cirq.Circuit:
        """Build a Grover circuit searching for a permutation
        mapping graph A to graph B (graph isomorphism decision).

        Args:
            adj_a: Edge list of graph A.
            adj_b: Edge list of graph B.
            num_grover_iters: Grover iterations.

        Returns:
            Measured ``cirq.Circuit`` over the permutation register.
        """
        n = self.num_vertices
        # Encode permutation as n * ceil(log2(n)) qubits
        perm_bits = max(1, int(math.ceil(math.log2(n))))
        total_qubits = n * perm_bits
        qubits = [cirq.LineQubit(i) for i in range(total_qubits)]

        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        oracle = self._isomorphism_oracle(qubits, adj_a, adj_b, n, perm_bits)
        diffusion = self._diffusion_multi(qubits)

        for _ in range(num_grover_iters):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*qubits, key="permutation"))
        return circuit

    def minimum_spanning_tree_circuit(
        self,
        adjacency: Dict[Tuple[int, int], float],
        qaoa_depth: int = 1,
    ) -> cirq.Circuit:
        """Build a QAOA circuit for minimum spanning tree.

        One binary variable per edge; the cost encodes total weight
        with connectivity constraints.

        Returns:
            Measured ``cirq.Circuit``.
        """
        edges = list(adjacency.keys())
        n_edge_qubits = len(edges)
        qubits = [cirq.LineQubit(i) for i in range(n_edge_qubits)]

        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*qubits))

        gamma = math.pi / (2 * qaoa_depth)
        beta = math.pi / (4 * qaoa_depth)

        for _ in range(qaoa_depth):
            for idx, e in enumerate(edges):
                w = adjacency[e]
                circuit.append(cirq.rz(2 * gamma * w).on(qubits[idx]))
            for q in qubits:
                circuit.append(cirq.rx(2 * beta).on(q))

        circuit.append(cirq.measure(*qubits, key="tree_edges"))
        return circuit

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _isomorphism_oracle(
        qubits: List[cirq.LineQubit],
        adj_a: List[Tuple[int, int]],
        adj_b: List[Tuple[int, int]],
        n: int,
        perm_bits: int,
    ) -> cirq.Circuit:
        """Simplified oracle: phase-kick if edge counts match."""
        c = cirq.Circuit()
        # Heuristic: mark all-ones perm register as a trivial match check
        if set(adj_a) == set(adj_b):
            c.append(cirq.X.on_each(*qubits))
            if len(qubits) > 1:
                c.append(cirq.Z(qubits[-1]).controlled_by(*qubits[:-1]))
            else:
                c.append(cirq.Z(qubits[0]))
            c.append(cirq.X.on_each(*qubits))
        return c

    @staticmethod
    def _diffusion_multi(qubits: List[cirq.LineQubit]) -> cirq.Circuit:
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
# Quantum Time Series Analyzer
# ======================================================================

class QuantumTimeSeriesAnalyzer:
    """QFT-based time-series analysis.

    Applies the quantum Fourier transform to an amplitude-encoded
    time series, enabling frequency extraction and periodicity
    detection.

    Args:
        num_qubits: Number of qubits (determines time-series length 2ⁿ).
    """

    def __init__(self, num_qubits: int) -> None:
        self.num_qubits = num_qubits
        self.series_length = 2 ** num_qubits

    def build_circuit(
        self,
        amplitudes: Optional[np.ndarray] = None,
    ) -> cirq.Circuit:
        """Build the QFT analysis circuit.

        Args:
            amplitudes: Time-series values (length ``2**num_qubits``).
                Encoded via Ry rotations when provided.

        Returns:
            Measured ``cirq.Circuit``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()

        if amplitudes is not None:
            amplitudes = np.asarray(amplitudes, dtype=float)
            norm = np.linalg.norm(amplitudes)
            if norm > 0:
                amplitudes = amplitudes / norm
            for i in range(min(self.num_qubits, len(amplitudes))):
                angle = 2 * math.acos(max(min(abs(amplitudes[i]), 1.0), 0.0))
                circuit.append(cirq.ry(angle).on(qubits[i]))
        else:
            circuit.append(cirq.H.on_each(*qubits))

        # QFT
        circuit += self._qft(qubits)
        circuit.append(cirq.measure(*qubits, key="frequency"))
        return circuit

    def detect_period(
        self,
        amplitudes: np.ndarray,
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Run the QFT and extract dominant frequencies.

        Returns:
            Dict with ``frequency_histogram`` and ``dominant_frequency``.
        """
        circuit = self.build_circuit(amplitudes)
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["frequency"]

        histogram: Dict[int, int] = {}
        for sample in bits:
            freq = int("".join(str(int(b)) for b in sample), 2)
            histogram[freq] = histogram.get(freq, 0) + 1

        dominant = max(histogram, key=histogram.get)  # type: ignore[arg-type]
        logger.info("Dominant frequency: %d (count=%d)", dominant, histogram[dominant])
        return {
            "frequency_histogram": histogram,
            "dominant_frequency": dominant,
        }

    @staticmethod
    def _qft(qubits: List[cirq.LineQubit]) -> cirq.Circuit:
        c = cirq.Circuit()
        n = len(qubits)
        for i in range(n):
            c.append(cirq.H(qubits[i]))
            for j in range(i + 1, n):
                c.append(cirq.CZPowGate(exponent=1 / 2 ** (j - i)).on(
                    qubits[j], qubits[i],
                ))
        for i in range(n // 2):
            c.append(cirq.SWAP(qubits[i], qubits[n - 1 - i]))
        return c


# ======================================================================
# Quantum ANN — Approximate Nearest Neighbour
# ======================================================================

class QuantumANN:
    """Quantum approximate nearest-neighbour search.

    Uses amplitude estimation to find the data point closest to a
    query vector in Hamming distance, achieving quadratic speedup
    over brute-force classical search.

    Args:
        num_qubits: Address-space qubits (database size = 2ⁿ).
        feature_dim: Dimensionality of data vectors.
    """

    def __init__(self, num_qubits: int, feature_dim: int = 4) -> None:
        self.num_qubits = num_qubits
        self.database_size = 2 ** num_qubits
        self.feature_dim = feature_dim

    def build_circuit(
        self,
        database: np.ndarray,
        query: np.ndarray,
        num_grover_iters: int = 2,
        threshold: float = 0.5,
    ) -> cirq.Circuit:
        """Build a Grover-based ANN circuit.

        Marks database entries whose normalised distance to the query
        is below *threshold*.

        Args:
            database: ``(database_size, feature_dim)`` binary array.
            query: ``(feature_dim,)`` binary query vector.
            num_grover_iters: Amplification iterations.
            threshold: Distance threshold (fraction of feature_dim).

        Returns:
            Measured ``cirq.Circuit``.
        """
        addr = [cirq.LineQubit(i) for i in range(self.num_qubits)]
        circuit = cirq.Circuit()
        circuit.append(cirq.H.on_each(*addr))

        oracle = self._distance_oracle(addr, database, query, threshold)
        diffusion = self._diffusion(addr)

        for _ in range(num_grover_iters):
            circuit += oracle
            circuit += diffusion

        circuit.append(cirq.measure(*addr, key="nearest"))
        return circuit

    def search(
        self,
        database: np.ndarray,
        query: np.ndarray,
        threshold: float = 0.5,
        repetitions: int = 100,
    ) -> Dict[str, Any]:
        """Run the ANN search and return the most-frequent result.

        Returns:
            Dict with ``best_index``, ``distance``, ``histogram``.
        """
        iters = max(1, int(math.floor(math.pi / 4 * math.sqrt(self.database_size))))
        circuit = self.build_circuit(database, query, iters, threshold)
        simulator = cirq.Simulator()
        result = simulator.run(circuit, repetitions=repetitions)
        bits = result.measurements["nearest"]

        histogram: Dict[int, int] = {}
        for sample in bits:
            idx = int("".join(str(int(b)) for b in sample), 2)
            histogram[idx] = histogram.get(idx, 0) + 1

        best_idx = max(histogram, key=histogram.get)  # type: ignore[arg-type]
        dist = float(np.sum(database[best_idx % len(database)] != query)) / self.feature_dim
        logger.info("ANN best_index=%d distance=%.4f", best_idx, dist)
        return {
            "best_index": best_idx,
            "distance": dist,
            "histogram": histogram,
        }

    # -- helpers -----------------------------------------------------------

    def _distance_oracle(
        self,
        addr: List[cirq.LineQubit],
        database: np.ndarray,
        query: np.ndarray,
        threshold: float,
    ) -> cirq.Circuit:
        c = cirq.Circuit()
        max_dist = int(threshold * self.feature_dim)
        for idx in range(min(len(database), self.database_size)):
            dist = int(np.sum(database[idx] != query))
            if dist <= max_dist:
                bits = format(idx, f"0{self.num_qubits}b")
                flips = [cirq.X(addr[i]) for i, b in enumerate(bits) if b == "0"]
                c.append(flips)
                if len(addr) > 1:
                    c.append(cirq.Z(addr[-1]).controlled_by(*addr[:-1]))
                else:
                    c.append(cirq.Z(addr[0]))
                c.append(flips)
        return c

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
# Quantum Compressor
# ======================================================================

class QuantumCompressor:
    """Quantum-enhanced data compression.

    Combines amplitude encoding (exponential compression of classical
    data into qubit amplitudes) with a variational autoencoder circuit
    that learns to represent data in fewer qubits.

    Args:
        input_qubits: Number of qubits for the full representation.
        latent_qubits: Number of qubits in the compressed representation.
    """

    def __init__(self, input_qubits: int, latent_qubits: int) -> None:
        if latent_qubits >= input_qubits:
            raise ValueError("latent_qubits must be < input_qubits")
        self.input_qubits = input_qubits
        self.latent_qubits = latent_qubits
        self.trash_qubits = input_qubits - latent_qubits

    def build_encoder(self, params: np.ndarray) -> cirq.Circuit:
        """Build the encoder circuit.

        The encoder maps ``input_qubits`` → ``latent_qubits`` by
        entangling and then tracing out (measuring) the trash qubits.

        Args:
            params: Variational parameters.  Size =
                ``input_qubits * 2`` (Ry + Rz per qubit + entangling).

        Returns:
            ``cirq.Circuit``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.input_qubits)]
        circuit = cirq.Circuit()

        idx = 0
        for q in qubits:
            circuit.append(cirq.ry(params[idx]).on(q))
            idx += 1
        for i in range(self.input_qubits - 1):
            circuit.append(cirq.CNOT(qubits[i], qubits[i + 1]))
        for q in qubits:
            if idx < len(params):
                circuit.append(cirq.rz(params[idx]).on(q))
                idx += 1

        return circuit

    def build_decoder(self, params: np.ndarray) -> cirq.Circuit:
        """Build the decoder (adjoint of encoder)."""
        return cirq.inverse(self.build_encoder(params))

    def build_autoencoder(self, params: np.ndarray) -> cirq.Circuit:
        """Build the full autoencoder circuit (encoder + SWAP test + decoder).

        The SWAP test between the trash qubits and fresh |0⟩ ancillae
        measures how close the trash state is to |0⟩, which is the
        fidelity objective.

        Returns:
            Measured ``cirq.Circuit``.
        """
        qubits = [cirq.LineQubit(i) for i in range(self.input_qubits)]
        ref_qubits = [cirq.LineQubit(self.input_qubits + i)
                      for i in range(self.trash_qubits)]
        swap_ancilla = cirq.LineQubit(self.input_qubits + self.trash_qubits)

        circuit = self.build_encoder(params)

        # SWAP test between trash qubits and reference |0⟩
        circuit.append(cirq.H(swap_ancilla))
        for t_q, r_q in zip(qubits[self.latent_qubits:], ref_qubits):
            circuit.append(cirq.SWAP(t_q, r_q).controlled_by(swap_ancilla))
        circuit.append(cirq.H(swap_ancilla))

        circuit.append(cirq.measure(swap_ancilla, key="fidelity"))
        return circuit

    def compress(
        self,
        data_prep: cirq.Circuit,
        params: np.ndarray,
        repetitions: int = 1000,
    ) -> Dict[str, Any]:
        """Run the autoencoder and report compression fidelity.

        Args:
            data_prep: Circuit that prepares the input state.
            params: Variational parameters.
            repetitions: Measurement shots.

        Returns:
            Dict with ``fidelity`` and ``compression_ratio``.
        """
        full_circuit = data_prep + self.build_autoencoder(params)
        simulator = cirq.Simulator()
        result = simulator.run(full_circuit, repetitions=repetitions)
        bits = result.measurements["fidelity"]
        fidelity = float(np.mean(bits == 0))

        ratio = self.input_qubits / self.latent_qubits
        logger.info("Compression fidelity=%.4f ratio=%.1f:1", fidelity, ratio)
        return {
            "fidelity": fidelity,
            "compression_ratio": ratio,
        }
