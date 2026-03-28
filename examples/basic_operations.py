"""
Basic Operations — qndb Core Engine
====================================

Demonstrates storing, retrieving, searching, and deleting data
using the core QuantumEngine, encoders, and measurement.
"""

from qndb.core.quantum_engine import QuantumEngine
from qndb.core.encoding.amplitude_encoder import AmplitudeEncoder
from qndb.core.encoding.basis_encoder import BasisEncoder
from qndb.core.operations.search import QuantumSearch
from qndb.core.measurement.readout import QuantumReadout


def main():
    # --- Initialize the engine ---
    engine = QuantumEngine(num_qubits=8)
    print(f"Engine initialized with {engine.num_qubits} qubits\n")

    # --- Store records ---
    records = {
        "user:1": {"name": "Alice", "role": "admin", "level": 5},
        "user:2": {"name": "Bob", "role": "analyst", "level": 3},
        "user:3": {"name": "Carol", "role": "engineer", "level": 4},
    }
    for key, value in records.items():
        engine.store_data(key, value)
        print(f"Stored {key}")

    # --- Retrieve ---
    print("\n--- Retrieve ---")
    for key in records:
        result = engine.retrieve_data(key)
        print(f"{key} -> {result}")

    # --- Search ---
    print("\n--- Search ---")
    results = engine.search({"role": "admin"})
    print(f"Search for role=admin: {results}")

    # --- Delete ---
    print("\n--- Delete ---")
    engine.delete_data("user:2")
    print("Deleted user:2")
    result = engine.retrieve_data("user:2")
    print(f"user:2 after delete: {result}")

    # --- Encoding ---
    print("\n--- Encoding ---")
    amp_enc = AmplitudeEncoder(num_qubits=4)
    circuit = amp_enc.encode([0.5, 0.5, 0.5, 0.5])
    print(f"Amplitude-encoded circuit:\n{circuit}\n")

    basis_enc = BasisEncoder(num_qubits=4)
    circuit = basis_enc.encode(5)  # binary 0101
    print(f"Basis-encoded 5:\n{circuit}\n")

    # --- Measurement ---
    print("\n--- Measurement ---")
    readout = QuantumReadout(num_qubits=4)
    stats = readout.measure(circuit, repetitions=100)
    print(f"Measurement results: {stats}")


if __name__ == "__main__":
    main()
