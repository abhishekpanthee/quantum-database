import unittest
import os
import numpy as np
import json
import datetime
import cirq
import sys
from qndb.core.storage.circuit_compiler import CircuitCompiler
from qndb.core.storage.error_correction import QuantumErrorCorrection
from qndb.core.storage.persistent_storage import PersistentStorage
from qndb.utilities.logging import get_logger, configure_logging

# Configure logging to ensure output is visible
configure_logging({
    'console_level': 'INFO',
    'log_to_console': True,
    'log_to_file': True,
    'log_filename': 'storage_tests.log'
})

logger = get_logger("storage_tests")

# Add this at the top of the file
print("==== QUANTUM DATABASE STORAGE TESTS ====")

class TestCircuitCompiler(unittest.TestCase):
    def setUp(self):
        self.compiler = CircuitCompiler()
        logger.info("Setting up CircuitCompiler test")
        
    def test_optimize_circuit(self):
        """Test circuit optimization reduces gate count."""
        from qndb.core.quantum_engine import QuantumEngine
        
        logger.info("Creating circuit with redundant gates")
        # Create a circuit with redundant gates
        engine = QuantumEngine(num_qubits=2)
        engine.apply_operation("X", [0])
        engine.apply_operation("X", [0])  # This should cancel out
        
        # Print details for debugging
        original_ops = list(engine.circuit.all_operations())
        original_count = len(original_ops)
        logger.info(f"Original circuit has {original_count} operations")
        
        # Optimize the circuit
        logger.info("Optimizing circuit")
        optimized_circuit = self.compiler.optimize_circuit(engine.circuit)
        
        # Print optimized circuit details
        optimized_ops = list(optimized_circuit.all_operations())
        optimized_count = len(optimized_ops)
        logger.info(f"Optimized circuit has {optimized_count} operations")
        
        # Check if optimization actually reduced gate count
        self.assertLess(optimized_count, original_count, 
                         f"Expected fewer operations after optimization, but got {optimized_count} (was {original_count})")
        
    def test_serialize_circuit(self):
        """Test circuit serialization to storable format."""
        from qndb.core.quantum_engine import QuantumEngine
        
        logger.info("Creating test circuit for serialization")
        engine = QuantumEngine(num_qubits=2)
        engine.apply_operation("H", [0])
        engine.apply_operation("X", [0, 1])  # controlled-x gate
        
        # Serialize the circuit
        logger.info("Serializing circuit")
        serialized = self.compiler.serialize_circuit(engine.circuit)
        
        # Detailed assertions and debugging
        self.assertIsInstance(serialized, str, "Serialized circuit should be a string")
        self.assertGreater(len(serialized), 0, "Serialized circuit string should not be empty")
        
        # Try to parse as JSON for more validation
        try:
            parsed = json.loads(serialized)
            logger.info(f"Serialized circuit structure: {list(parsed.keys())}")
            self.assertIn("operations", parsed, "Serialized circuit should contain operations")
            self.assertIn("qubits", parsed, "Serialized circuit should contain qubits")
        except json.JSONDecodeError:
            self.fail("Serialized circuit is not valid JSON")
        
        logger.info(f"Serialized circuit (excerpt): {serialized[:100]}...")
        
    def test_deserialize_circuit(self):
        """Test circuit deserialization from stored format."""
        from qndb.core.quantum_engine import QuantumEngine
        
        logger.info("Creating test circuit for serialization/deserialization")
        engine = QuantumEngine(num_qubits=2)
        engine.apply_operation("H", [0])
        engine.apply_operation("X", [0, 1])  # controlled-x gate
        
        # Serialize
        logger.info("Serializing circuit")
        serialized = self.compiler.serialize_circuit(engine.circuit)
        
        # Deserialize
        logger.info("Deserializing circuit")
        deserialized = self.compiler.deserialize_circuit(serialized)
        
        # Check that operations match in detail
        original_ops = list(engine.circuit.all_operations())
        deserialized_ops = list(deserialized.all_operations())
        
        logger.info(f"Original circuit has {len(original_ops)} operations")
        logger.info(f"Deserialized circuit has {len(deserialized_ops)} operations")
        
        # Detailed comparison of operations
        self.assertEqual(len(original_ops), len(deserialized_ops), 
                         "Number of operations should match after deserialization")
        
        # Compare gates and qubits involved
        for i, (orig_op, deser_op) in enumerate(zip(original_ops, deserialized_ops)):
            logger.info(f"Comparing operation {i+1}:")
            # Check gate type
            orig_gate_type = type(orig_op.gate).__name__
            deser_gate_type = type(deser_op.gate).__name__
            logger.info(f"  Original gate: {orig_gate_type}, Deserialized gate: {deser_gate_type}")
            self.assertEqual(orig_gate_type, deser_gate_type, 
                             f"Gate type mismatch at operation {i+1}")
            
            # Check qubits
            orig_qubits = [str(q) for q in orig_op.qubits]
            deser_qubits = [str(q) for q in deser_op.qubits]
            logger.info(f"  Original qubits: {orig_qubits}, Deserialized qubits: {deser_qubits}")
            self.assertEqual(len(orig_qubits), len(deser_qubits), 
                            f"Qubit count mismatch at operation {i+1}")

    def test_circuit_compression(self):
        """Test that circuit compression reduces storage size."""
        from qndb.core.quantum_engine import QuantumEngine
        
        logger.info("Creating large test circuit for compression test")
        # Create a larger circuit
        engine = QuantumEngine(num_qubits=5)
        for i in range(5):
            engine.apply_operation("H", [i])
        for i in range(4):
            engine.apply_operation("X", [i, i+1])
        
        # Serialize without compression
        logger.info("Serializing without compression")
        uncompressed = self.compiler.serialize_circuit(engine.circuit, compress=False)
        uncompressed_size = len(uncompressed)
        
        # Serialize with compression
        logger.info("Serializing with compression")
        compressed = self.compiler.serialize_circuit(engine.circuit, compress=True)
        compressed_size = len(compressed)
        
        logger.info(f"Uncompressed size: {uncompressed_size} bytes")
        logger.info(f"Compressed size: {compressed_size} bytes")
        
        # Check compression effectiveness
        self.assertLess(compressed_size, uncompressed_size, 
                        "Compressed size should be less than uncompressed size")
        
        # Ensure we can still deserialize the compressed circuit
        logger.info("Verifying compressed circuit can be deserialized")
        deserialized = self.compiler.deserialize_circuit(compressed)
        self.assertEqual(len(list(engine.circuit.all_operations())), 
                         len(list(deserialized.all_operations())),
                         "Operations count should match after compression/decompression")


class TestErrorCorrection(unittest.TestCase):
    def setUp(self):
        self.corrector = QuantumErrorCorrection()
        logger.info("Setting up QuantumErrorCorrection test")
        
    def test_apply_bit_flip_code(self):
        """Test bit-flip error correction code application."""
        from qndb.core.quantum_engine import QuantumEngine
        
        print("\n=== Testing Bit Flip Code ===")
        logger.info("Creating single-qubit circuit for bit-flip protection")
        # Create simple circuit
        engine = QuantumEngine(num_qubits=1)
        engine.apply_operation("X", [0])  # Set to |1⟩
        
        print("Initial circuit state: |1⟩")
        logger.info("Initial circuit state: |1⟩")
        
        # Apply bit-flip code (should create redundancy)
        print("Applying bit-flip error correction code...")
        logger.info("Applying bit-flip error correction code")
        protected_circuit, protected_qubits = self.corrector.apply_bit_flip_code(
            engine.circuit, engine.qubits
        )
        
        # Detailed debugging
        print(f"Protected circuit has {len(protected_qubits)} qubits")
        print(f"Protected circuit operations: {len(list(protected_circuit.all_operations()))}")
        logger.info(f"Protected circuit has {len(protected_qubits)} qubits")
        logger.info(f"Protected circuit operations: {len(list(protected_circuit.all_operations()))}")
        
    def test_apply_phase_flip_code(self):
        """Test phase-flip error correction code application."""
        from qndb.core.quantum_engine import QuantumEngine
        
        logger.info("Creating single-qubit circuit with phase for phase-flip protection")
        # Create simple circuit with phase
        engine = QuantumEngine(num_qubits=1)
        engine.apply_operation("H", [0])  # Set to |+⟩
        
        logger.info("Initial circuit state: |+⟩")
        
        # Apply phase-flip code
        logger.info("Applying phase-flip error correction code")
        protected_circuit, protected_qubits = self.corrector.apply_phase_flip_code(
            engine.circuit, engine.qubits
        )
        
        # Detailed debugging
        logger.info(f"Protected circuit has {len(protected_qubits)} qubits")
        logger.info(f"Protected circuit operations: {len(list(protected_circuit.all_operations()))}")
        
        # Should now have 3 qubits for the phase-flip code
        self.assertEqual(len(protected_qubits), 3, 
                        "Phase-flip code should expand to 3 physical qubits")
        
        # Verify the encoding operations exist (should have Hadamards for phase encoding)
        op_types = [str(op.gate) for op in protected_circuit.all_operations()]
        logger.info(f"Operation types in protected circuit: {op_types}")
        
        # The encoding should include Hadamard gates
        self.assertTrue(any('H' in str(gate) for gate in op_types),
                       "Phase-flip code should contain Hadamard operations")
        
    def test_detect_and_correct_errors(self):
        """Test error detection and correction in a noisy circuit."""
        from qndb.core.quantum_engine import QuantumEngine
        import cirq
        
        logger.info("Creating circuit for error correction test")
        # Create a circuit protected with error correction
        engine = QuantumEngine(num_qubits=1)
        engine.apply_operation("X", [0])  # Set to |1⟩
        
        logger.info("Applying bit-flip protection")
        protected_circuit, protected_qubits = self.corrector.apply_bit_flip_code(
            engine.circuit, engine.qubits
        )
        
        # Simulate an error on the first qubit
        logger.info("Introducing a bit-flip error on the first protected qubit")
        error_circuit = protected_circuit.copy()
        error_circuit.append(cirq.X(protected_qubits[0]))
        
        logger.info("Circuit operations after error:")
        for i, op in enumerate(error_circuit.all_operations()):
            logger.info(f"  Operation {i+1}: {op}")
        
        # Attempt to correct the error
        logger.info("Detecting and correcting the error")
        corrected_circuit = self.corrector.detect_and_correct_errors(
            error_circuit, protected_qubits, "bit_flip"
        )
        
        logger.info("Circuit operations after correction:")
        for i, op in enumerate(corrected_circuit.all_operations()):
            logger.info(f"  Operation {i+1}: {op}")
        
        # Validate - need to verify through simulation results
        # This is a simplified test - real validation would need quantum simulation
        self.assertIsNotNone(corrected_circuit, "Corrected circuit should not be None")
        self.assertGreater(len(list(corrected_circuit.all_operations())), 
                          len(list(error_circuit.all_operations())),
                          "Corrected circuit should have additional correction operations")

    def test_syndrome_measurement(self):
        """Test syndrome measurement for error detection."""
        from qndb.core.quantum_engine import QuantumEngine
        import cirq
        
        logger.info("Creating circuit for syndrome measurement test")
        # Create a circuit protected with error correction
        engine = QuantumEngine(num_qubits=1)
        engine.apply_operation("X", [0])  # Set to |1⟩
        
        # Apply protection
        logger.info("Applying bit-flip protection")
        protected_circuit, protected_qubits = self.corrector.apply_bit_flip_code(
            engine.circuit, engine.qubits
        )
        
        # Introduce an error
        logger.info("Introducing a bit-flip error on the second protected qubit")
        error_circuit = protected_circuit.copy()
        error_circuit.append(cirq.X(protected_qubits[1]))  # Error on second qubit
        
        # Get syndrome measurement circuit
        logger.info("Creating syndrome measurement circuit")
        syndrome_circuit = self.corrector.create_syndrome_circuit(
            error_circuit, protected_qubits, "bit_flip"
        )
        
        # Verify syndrome measurement components
        logger.info(f"Syndrome circuit operations: {len(list(syndrome_circuit.all_operations()))}")
        
        # Should have ancilla qubits for syndrome measurement
        all_qubits = list(syndrome_circuit.all_qubits())
        logger.info(f"Total qubits in syndrome circuit: {len(all_qubits)}")
        
        # There should be more qubits in the syndrome circuit (added ancillas)
        self.assertGreater(len(all_qubits), len(protected_qubits),
                          "Syndrome circuit should include ancilla qubits")


class TestPersistentStorage(unittest.TestCase):
    def setUp(self):
        self.test_db_path = "test_db_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Setting up PersistentStorage test with database: {self.test_db_path}")
        self.storage = PersistentStorage(self.test_db_path)
        # Clear any existing data
        self.storage.clear_all()
        
    def tearDown(self):
        # Clean up after tests
        logger.info(f"Cleaning up test database: {self.test_db_path}")
        self.storage.clear_all()
        
        # Check if database files were properly cleaned up
        if os.path.exists(self.test_db_path):
            remaining_files = os.listdir(self.test_db_path)
            if remaining_files:
                logger.warning(f"Database directory not empty after clear_all(): {remaining_files}")
        
    def test_store_and_retrieve_circuit(self):
        """Test storing and retrieving a quantum circuit."""
        from qndb.core.quantum_engine import QuantumEngine
        
        logger.info("Creating test circuit for storage test")
        # Create a test circuit
        engine = QuantumEngine(num_qubits=3)
        engine.apply_operation("H", [0])
        engine.apply_operation("X", [0, 1])
        engine.apply_operation("Z", [2])
        
        # Count initial operations
        original_ops = list(engine.circuit.all_operations())
        logger.info(f"Original circuit has {len(original_ops)} operations")
        
        # Store the circuit
        logger.info("Storing circuit in persistent storage")
        circuit_name = "test_hadamard_cnot_circuit"
        circuit_id = self.storage.save_circuit(engine.circuit, circuit_name)
        
        logger.info(f"Circuit stored with ID: {circuit_id}")
        self.assertIsNotNone(circuit_id, "Storage should return a valid circuit ID")
        
        # Verify circuit was stored properly
        stored_items = self.storage.list_stored_items()
        logger.info(f"Storage contains {len(stored_items)} items after storing circuit")
        
        # Find our circuit in the stored items
        circuit_item = next((item for item in stored_items if item.get("name") == circuit_name), None)
        self.assertIsNotNone(circuit_item, f"Stored circuit with name '{circuit_name}' not found in storage")
        
        # Retrieve the circuit
        logger.info(f"Retrieving circuit with ID: {circuit_id}")
        retrieved_circuit = self.storage.load_circuit(circuit_id)
        
        # Check operations match in detail
        retrieved_ops = list(retrieved_circuit.all_operations())
        logger.info(f"Retrieved circuit has {len(retrieved_ops)} operations")
        
        # Compare gate counts
        self.assertEqual(len(original_ops), len(retrieved_ops), 
                         "Retrieved circuit should have same number of operations")
        
        # Compare each operation
        logger.info("Comparing original and retrieved operations:")
        for i, (orig_op, retr_op) in enumerate(zip(original_ops, retrieved_ops)):
            orig_desc = f"{type(orig_op.gate).__name__} on {[str(q) for q in orig_op.qubits]}"
            retr_desc = f"{type(retr_op.gate).__name__} on {[str(q) for q in retr_op.qubits]}"
            
            logger.info(f"  Op {i+1}: Original: {orig_desc}, Retrieved: {retr_desc}")
            
            # Check operation type
            self.assertEqual(type(orig_op.gate).__name__, type(retr_op.gate).__name__,
                           f"Gate type mismatch at operation {i+1}")
            
            # Check qubit count
            self.assertEqual(len(orig_op.qubits), len(retr_op.qubits),
                           f"Qubit count mismatch at operation {i+1}")
        
    def test_store_and_retrieve_data(self):
        """Test storing and retrieving classical data."""
        # Create complex test data
        test_data = {
            "vector": [1, 2, 3, 4], 
            "matrix": [[1, 2], [3, 4]],
            "nested": {
                "a": [5, 6, 7],
                "b": {"x": 10, "y": 20}
            },
            "metadata": {
                "timestamp": datetime.datetime.now().isoformat(),
                "description": "Test data for storage"
            }
        }
        
        logger.info("Storing complex test data")
        data_name = "complex_test_dataset"
        # Store data
        data_id = self.storage.save_database_schema(test_data, data_name)
        
        logger.info(f"Data stored with ID: {data_id}")
        self.assertIsNotNone(data_id, "Storage should return a valid data ID")
        
        # Verify data appears in storage list
        stored_items = self.storage.list_stored_items()
        data_item = next((item for item in stored_items if item.get("name") == data_name), None)
        self.assertIsNotNone(data_item, f"Stored data with name '{data_name}' not found in storage")
        
        # Retrieve data
        logger.info(f"Retrieving data with ID: {data_id}")
        retrieved_data = self.storage.load_database_schema(data_id)
        
        # Detailed comparison of complex data
        logger.info("Comparing original and retrieved data structures")
        
        # Check top-level keys
        self.assertEqual(set(test_data.keys()), set(retrieved_data.keys()),
                        "Retrieved data should have same top-level keys")
        
        # Check vector data
        self.assertEqual(test_data["vector"], retrieved_data["vector"],
                        "Vector data should match")
        
        # Check matrix data
        self.assertEqual(test_data["matrix"], retrieved_data["matrix"],
                        "Matrix data should match")
        
        # Check nested structure
        self.assertEqual(test_data["nested"]["a"], retrieved_data["nested"]["a"],
                        "Nested array data should match")
        self.assertEqual(test_data["nested"]["b"], retrieved_data["nested"]["b"],
                        "Nested object data should match")
        
        # Check metadata
        self.assertEqual(test_data["metadata"]["description"], 
                        retrieved_data["metadata"]["description"],
                        "Metadata description should match")
        
    def test_delete_data(self):
        """Test deleting stored data."""
        test_data = {"value": 42, "name": "meaning_of_life"}
        
        logger.info("Storing test data for deletion test")
        # Store and then delete
        data_id = self.storage.save_database_schema(test_data, "temp_data")
        
        # Verify data exists before deletion
        before_delete = self.storage.list_stored_items()
        logger.info(f"Storage has {len(before_delete)} items before deletion")
        self.assertTrue(any(item.get("id") == data_id for item in before_delete),
                      f"Data with ID {data_id} should exist before deletion")
        
        # Delete the data
        logger.info(f"Deleting data with ID: {data_id}")
        self.storage.delete_data(data_id)
        
        # Verify data was deleted
        after_delete = self.storage.list_stored_items()
        logger.info(f"Storage has {len(after_delete)} items after deletion")
        self.assertFalse(any(item.get("id") == data_id for item in after_delete),
                       f"Data with ID {data_id} should not exist after deletion")
        
        # Should raise exception when attempting to retrieve
        logger.info("Attempting to retrieve deleted data (should fail)")
        with self.assertRaises(KeyError):
            self.storage.load_database_schema(data_id)
            
    def test_list_stored_items(self):
        """Test listing all stored circuits and data."""
        # Store multiple items of different types
        logger.info("Storing multiple items for list test")
        from qndb.core.quantum_engine import QuantumEngine
        
        # Store classical data
        self.storage.save_database_schema({"a": 1}, "data1")
        self.storage.save_database_schema({"b": 2}, "data2")
        
        # Store a circuit
        engine = QuantumEngine(num_qubits=1)
        engine.apply_operation("H", [0])
        self.storage.save_circuit(engine.circuit, "circuit1")
        
        # List all items
        logger.info("Listing all stored items")
        items = self.storage.list_stored_items()
        
        # Detailed analysis of returned items
        logger.info(f"Storage contains {len(items)} items")
        for i, item in enumerate(items):
            logger.info(f"  Item {i+1}: ID={item.get('id')}, Name={item.get('name')}, Type={item.get('type')}")
        
        # Check item count
        self.assertEqual(len(items), 3, 
                        "Storage should contain exactly 3 items")
        
        # Check item names
        item_names = [item["name"] for item in items]
        logger.info(f"Item names: {item_names}")
        
        self.assertIn("data1", item_names, "Item 'data1' should be in the stored items list")
        self.assertIn("data2", item_names, "Item 'data2' should be in the stored items list")
        self.assertIn("circuit1", item_names, "Item 'circuit1' should be in the stored items list")
        
        # Check item types
        data_items = [item for item in items if item.get("type") == "data"]
        circuit_items = [item for item in items if item.get("type") == "circuit"]
        
        logger.info(f"Found {len(data_items)} data items and {len(circuit_items)} circuit items")
        
        self.assertEqual(len(data_items), 2, "Should have 2 data items")
        self.assertEqual(len(circuit_items), 1, "Should have 1 circuit item")
        
        # Verify each item has the required fields
        for item in items:
            self.assertIn("id", item, "Each item should have an 'id' field")
            self.assertIn("name", item, "Each item should have a 'name' field")
            self.assertIn("type", item, "Each item should have a 'type' field")
            self.assertIn("created_at", item, "Each item should have a 'created_at' field")
        
    def test_update_metadata(self):
        """Test updating metadata for stored items."""
        logger.info("Testing metadata update functionality")
        
        # Store an item with initial metadata
        data_id = self.storage.save_database_schema(
            {"value": 100}, 
            "updatable_data",
            metadata={"version": 1, "status": "draft"}
        )
        
        # Verify initial metadata
        items = self.storage.list_stored_items()
        data_item = next(item for item in items if item["id"] == data_id)
        
        logger.info(f"Initial metadata: {data_item.get('metadata', {})}")
        self.assertEqual(data_item.get("metadata", {}).get("version"), 1,
                        "Initial metadata version should be 1")
        
        # Update metadata
        logger.info("Updating item metadata")
        updated_metadata = {"version": 2, "status": "final", "updated_at": datetime.datetime.now().isoformat()}
        
        self.storage.update_metadata(data_id, updated_metadata)
        
        # Verify updated metadata
        updated_items = self.storage.list_stored_items()
        updated_item = next(item for item in updated_items if item["id"] == data_id)
        
        logger.info(f"Updated metadata: {updated_item.get('metadata', {})}")
        self.assertEqual(updated_item.get("metadata", {}).get("version"), 2,
                        "Updated metadata version should be 2")
        self.assertEqual(updated_item.get("metadata", {}).get("status"), "final",
                        "Updated metadata status should be 'final'")

# Add this at the end of the file
if __name__ == "__main__":
    print("\n==== STARTING TESTS ====")
    # Use TestLoader to control the order
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes in desired order
    suite.addTests(loader.loadTestsFromTestCase(TestCircuitCompiler))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorCorrection))
    suite.addTests(loader.loadTestsFromTestCase(TestPersistentStorage))
    
    # Run tests with higher verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n==== TEST SUMMARY ====")
    print(f"Ran {result.testsRun} tests")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    # Exit with appropriate code
    sys.exit(not result.wasSuccessful())