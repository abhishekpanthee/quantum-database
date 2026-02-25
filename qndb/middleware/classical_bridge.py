"""
Classical-Quantum Integration Bridge

Bridge between classical database operations and quantum processing.

Features:
 - QuantumDataType enum (INT, FLOAT, VARCHAR, BOOL, TIMESTAMP, BLOB)
 - Automatic encoding selection based on data + query type
 - Configurable ConfidenceConfig with thresholds
 - batch_encode() for bulk operations
 - StreamingBridge for real-time data ingestion
"""

import logging
import math
import time
from enum import Enum, auto
from typing import Dict, Any, List, Tuple, Optional, Iterator
from collections import deque

from ..core.quantum_engine import QuantumEngine
from ..core.encoding import amplitude_encoder, basis_encoder
from ..interface.query_language import QueryParser

logger = logging.getLogger(__name__)


# ======================================================================
# Data type system
# ======================================================================

class QuantumDataType(Enum):
    """Supported quantum data types with encode/decode methods."""
    INT = auto()
    FLOAT = auto()
    VARCHAR = auto()
    BOOL = auto()
    TIMESTAMP = auto()
    BLOB = auto()

    @staticmethod
    def infer(value: Any) -> "QuantumDataType":
        if isinstance(value, bool):
            return QuantumDataType.BOOL
        if isinstance(value, int):
            return QuantumDataType.INT
        if isinstance(value, float):
            return QuantumDataType.FLOAT
        if isinstance(value, bytes):
            return QuantumDataType.BLOB
        if isinstance(value, str):
            # naive timestamp detection
            if len(value) >= 10 and value[4:5] == '-':
                return QuantumDataType.TIMESTAMP
            return QuantumDataType.VARCHAR
        return QuantumDataType.VARCHAR

    def encode_value(self, value: Any) -> float:
        """Encode a classical value into a float suitable for quantum encoding."""
        if value is None:
            return 0.0
        if self == QuantumDataType.BOOL:
            return 1.0 if value else 0.0
        if self in (QuantumDataType.INT, QuantumDataType.FLOAT):
            return float(value)
        if self == QuantumDataType.TIMESTAMP:
            import datetime as _dt
            if isinstance(value, str):
                try:
                    return _dt.datetime.fromisoformat(value).timestamp()
                except Exception:
                    return 0.0
            if isinstance(value, _dt.datetime):
                return value.timestamp()
            return float(value)
        if self == QuantumDataType.BLOB:
            return float(int.from_bytes(value[:8] if len(value) > 8 else value, 'big'))
        # VARCHAR – hash into [0,1)
        return (hash(value) % (2**32)) / (2**32)

    def decode_value(self, encoded: float, original_type_hint: Any = None) -> Any:
        """Best-effort decode from float back to classical domain."""
        if self == QuantumDataType.BOOL:
            return encoded > 0.5
        if self == QuantumDataType.INT:
            return int(round(encoded))
        if self == QuantumDataType.FLOAT:
            return encoded
        return encoded


# ======================================================================
# Confidence configuration
# ======================================================================

class ConfidenceConfig:
    """Configurable confidence thresholds for measurement interpretation."""

    def __init__(self, significance_threshold: float = 0.05,
                 high_confidence: float = 0.95,
                 medium_confidence: float = 0.80,
                 max_prob_weight: float = 0.7,
                 entropy_weight: float = 0.3):
        self.significance_threshold = significance_threshold
        self.high_confidence = high_confidence
        self.medium_confidence = medium_confidence
        self.max_prob_weight = max_prob_weight
        self.entropy_weight = entropy_weight


# ======================================================================
# Encoding selector
# ======================================================================

class EncodingSelector:
    """Choose encoding strategy based on data characteristics AND query type."""

    @staticmethod
    def select(data: Dict[str, Any], query_type: Optional[str] = None) -> str:
        continuous = 0
        discrete = 0
        for value in data.values():
            if isinstance(value, (list, tuple)):
                if all(isinstance(v, (int, float)) for v in value):
                    continuous += 1
                else:
                    discrete += 1
            elif isinstance(value, (int, float)):
                continuous += 1
            else:
                discrete += 1

        # Query-type overrides
        if query_type in ('QSEARCH', 'QUANTUM_SEARCH'):
            return 'amplitude'
        if query_type in ('QJOIN',):
            return 'basis'

        return 'amplitude' if continuous > discrete else 'basis'


# ======================================================================
# Streaming bridge
# ======================================================================

class StreamingBridge:
    """Real-time streaming ingestion bridge.

    Accepts chunks of rows and yields encoded batches.
    """

    def __init__(self, bridge: "ClassicalBridge", batch_size: int = 64):
        self._bridge = bridge
        self._batch_size = batch_size
        self._buffer: deque = deque()

    def push(self, row: Dict[str, Any]) -> Optional[Tuple]:
        """Push a row. Returns an encoded batch when buffer reaches batch_size."""
        self._buffer.append(row)
        if len(self._buffer) >= self._batch_size:
            return self._flush()
        return None

    def flush(self) -> Optional[Tuple]:
        if self._buffer:
            return self._flush()
        return None

    def _flush(self) -> Tuple:
        batch = list(self._buffer)
        self._buffer.clear()
        return self._bridge.batch_encode(batch)

    def __len__(self):
        return len(self._buffer)


# ======================================================================
# ClassicalBridge (main class)
# ======================================================================

class ClassicalBridge:
    """Bridge between classical data structures/operations and quantum counterparts."""

    def __init__(self, quantum_engine: QuantumEngine,
                 confidence_config: Optional[ConfidenceConfig] = None):
        self.quantum_engine = quantum_engine
        self.query_parser = QueryParser()
        self.confidence_config = confidence_config or ConfidenceConfig()
        self.encoding_selector = EncodingSelector()
        logger.info("Classical bridge initialized with quantum engine")

    # ------------------------------------------------------------------
    # Data translation
    # ------------------------------------------------------------------

    def translate_data(self, data: Dict[str, Any], encoding_type: str = "auto",
                       query_type: Optional[str] = None) -> Tuple:
        if encoding_type == "auto":
            encoding_type = self.encoding_selector.select(data, query_type)

        if encoding_type == "amplitude":
            return amplitude_encoder.encode(data)
        elif encoding_type == "basis":
            return basis_encoder.encode(data)
        else:
            raise ValueError(f"Unsupported encoding type: {encoding_type}")

    def batch_encode(self, rows: List[Dict[str, Any]],
                     encoding_type: str = "auto") -> Tuple[List, Dict[str, Any]]:
        """Encode a batch of rows, inferring per-column types."""
        if not rows:
            return [], {"count": 0}

        # Infer column types from first row
        col_types: Dict[str, QuantumDataType] = {}
        for col, val in rows[0].items():
            col_types[col] = QuantumDataType.infer(val)

        encoded_rows: List[List[float]] = []
        for row in rows:
            encoded = []
            for col, dtype in col_types.items():
                encoded.append(dtype.encode_value(row.get(col)))
            encoded_rows.append(encoded)

        meta = {
            "count": len(encoded_rows),
            "columns": {c: dt.name for c, dt in col_types.items()},
            "encoding": encoding_type,
        }
        return encoded_rows, meta

    # ------------------------------------------------------------------
    # Query translation
    # ------------------------------------------------------------------

    def translate_query(self, query: str) -> Dict:
        parsed_query = self.query_parser.parse(query)
        quantum_operations = self._map_to_quantum_operations(parsed_query)
        return {"parsed_query": parsed_query, "quantum_operations": quantum_operations}

    # ------------------------------------------------------------------
    # Result translation
    # ------------------------------------------------------------------

    def translate_results(self, quantum_results: Dict, measurement_count: int) -> Dict[str, Any]:
        probabilities = self._extract_probabilities(quantum_results, measurement_count)
        return self._probabilities_to_classical(probabilities)

    # ------------------------------------------------------------------
    # State conversion
    # ------------------------------------------------------------------

    def quantum_to_classical(self, quantum_state: Dict[str, Any]) -> Dict[str, Any]:
        state_vector = quantum_state.get("state_vector", [])
        num_qubits = quantum_state.get("num_qubits", self.quantum_engine.num_qubits)

        if isinstance(state_vector, list):
            amplitudes = []
            for amp in state_vector:
                if isinstance(amp, complex):
                    amplitudes.append([amp.real, amp.imag])
                else:
                    amplitudes.append(amp)
        else:
            amplitudes = []
            for amp in state_vector:
                if hasattr(amp, 'imag') and amp.imag != 0:
                    amplitudes.append([float(amp.real), float(amp.imag)])
                else:
                    amplitudes.append(float(amp.real))

        classical_representation = {
            "amplitudes": amplitudes,
            "metadata": {
                "qubits": num_qubits,
                "encoding": quantum_state.get("encoding", "amplitude"),
                "timestamp": quantum_state.get("timestamp", time.time()),
                "has_complex": any(isinstance(a, list) for a in amplitudes),
            },
        }
        if "metadata" in quantum_state:
            classical_representation["metadata"].update(quantum_state["metadata"])
        if "operations" in quantum_state:
            classical_representation["operations"] = quantum_state["operations"]
        return classical_representation

    def classical_to_quantum(self, classical_data: Dict[str, Any]) -> Dict[str, Any]:
        raw_amplitudes = classical_data.get("amplitudes", [1.0, 0.0])
        amplitudes = []
        for amp in raw_amplitudes:
            if isinstance(amp, list) and len(amp) == 2:
                amplitudes.append(complex(amp[0], amp[1]))
            else:
                amplitudes.append(amp)

        metadata = classical_data.get("metadata", {})
        num_qubits = metadata.get("qubits", self.quantum_engine.num_qubits)
        encoding = metadata.get("encoding", "amplitude")

        quantum_state: Dict[str, Any] = {
            "state_vector": amplitudes,
            "num_qubits": num_qubits,
            "encoding": encoding,
            "metadata": metadata,
        }
        if "operations" in classical_data:
            quantum_state["operations"] = classical_data["operations"]
        return quantum_state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_continuous_data(self, data: Dict[str, Any]) -> bool:
        continuous = 0
        discrete = 0
        for value in data.values():
            if isinstance(value, (list, tuple)):
                if all(isinstance(v, (int, float)) for v in value):
                    continuous += 1
                else:
                    discrete += 1
            elif isinstance(value, (int, float)):
                continuous += 1
            else:
                discrete += 1
        return continuous > discrete

    def _map_to_quantum_operations(self, parsed_query: Dict) -> Dict:
        operations: Dict[str, Any] = {}
        qt = parsed_query.get("type")
        if qt == "SELECT":
            operations["type"] = "search"
            operations["algorithm"] = "grover" if parsed_query.get("where") else "amplitude_estimation"
            operations["target_condition"] = parsed_query.get("where")
            operations["projection"] = parsed_query.get("select")
        elif qt == "JOIN":
            operations["type"] = "join"
            operations["algorithm"] = "quantum_join"
            operations["tables"] = parsed_query.get("tables")
            operations["conditions"] = parsed_query.get("on")
        return operations

    def _extract_probabilities(self, quantum_results: Dict, measurement_count: int) -> Dict[str, float]:
        return {state: count / measurement_count for state, count in quantum_results.items()}

    def _probabilities_to_classical(self, probabilities: Dict[str, float]) -> Dict[str, Any]:
        threshold = self.confidence_config.significance_threshold
        significant = {s: p for s, p in probabilities.items() if p > threshold}
        sorted_states = sorted(significant.items(), key=lambda x: x[1], reverse=True)
        return {
            "most_probable": sorted_states[0][0] if sorted_states else None,
            "probability": sorted_states[0][1] if sorted_states else 0,
            "all_results": sorted_states,
            "confidence": self._calculate_confidence(probabilities),
        }

    def _calculate_confidence(self, probabilities: Dict[str, float]) -> float:
        if not probabilities:
            return 0.0
        max_prob = max(probabilities.values())
        entropy = -sum(p * math.log2(p) for p in probabilities.values() if p > 0)
        n = len(probabilities)
        max_entropy = math.log2(n) if n > 1 else 1.0
        norm_entropy = entropy / max_entropy if max_entropy != 0 else 0
        w1 = self.confidence_config.max_prob_weight
        w2 = self.confidence_config.entropy_weight
        confidence = w1 * max_prob + w2 * (1 - norm_entropy)
        
        return min(1.0, max(0.0, confidence))