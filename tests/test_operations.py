import unittest
import numpy as np
import logging
import sys
import cirq
from collections import Counter

from qndb.core.operations.search import QuantumSearch
from qndb.core.operations.join import QuantumJoin
from qndb.core.operations.indexing import QuantumIndex
from qndb.core.operations.quantum_gates import DatabaseGates

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class TestQuantumSearch(unittest.TestCase):
    def setUp(self):
        logger.debug("Setting up QuantumSearch test")
        # Initialize with the required num_qubits parameter
        self.search = QuantumSearch(num_qubits=4)
        
    def test_create_oracle(self):
        """Test creating a quantum oracle for search."""
        logger.debug("Testing create_oracle")
        # Create a simple oracle that marks item 3 (binary 11)
        oracle_circuit = self.search.create_oracle(marked_items=[3])
        
        logger.debug(f"Oracle circuit: {oracle_circuit}")
        
        # Verify circuit has operations
        operations = list(oracle_circuit.all_operations())
        logger.debug(f"Oracle operations: {operations}")
        self.assertGreater(len(operations), 0)
        
    def test_create_diffusion_operator(self):
        """Test creating the diffusion operator."""
        logger.debug("Testing create_diffusion_operator")
        diffusion_circuit = self.search.create_diffusion_operator()
        
        logger.debug(f"Diffusion circuit: {diffusion_circuit}")
        
        # Verify circuit has operations
        operations = list(diffusion_circuit.all_operations())
        logger.debug(f"Diffusion operations: {operations}")
        self.assertGreater(len(operations), 0)
        
    def test_grovers_algorithm(self):
        """Test Grover's search algorithm implementation."""
        logger.debug("Testing grovers_algorithm")
        # Search for item 2 (binary 10) in a 4-qubit space
        circuit = self.search.grovers_algorithm(
            marked_items=[2],
            num_iterations=1
        )
        
        logger.debug(f"Grover's circuit: {circuit}")
        
        # Verify circuit was created
        self.assertIsNotNone(circuit)
        operations = list(circuit.all_operations())
        logger.debug(f"Grover's operations count: {len(operations)}")
        self.assertGreater(len(operations), 0)
        
        # Since we can't easily simulate the result here,
        # just check the circuit structure
        measurements = [op for op in operations if isinstance(op.gate, cirq.MeasurementGate)]
        self.assertTrue(measurements, "Circuit should include measurements")
        

class TestQuantumJoin(unittest.TestCase):
    def setUp(self):
        logger.debug("Setting up QuantumJoin test")
        self.join = QuantumJoin()
        
    def test_inner_join(self):
        """Test inner join quantum circuit."""
        logger.debug("Testing inner_join")
        # Create test qubits
        key_qubits_a = [cirq.LineQubit(i) for i in range(2)]
        value_qubits_a = [cirq.LineQubit(i+10) for i in range(2)]
        key_qubits_b = [cirq.LineQubit(i+20) for i in range(2)]
        value_qubits_b = [cirq.LineQubit(i+30) for i in range(2)]
        output_key_qubits = [cirq.LineQubit(i+40) for i in range(2)]
        output_value_qubits_a = [cirq.LineQubit(i+50) for i in range(2)]
        output_value_qubits_b = [cirq.LineQubit(i+60) for i in range(2)]
        flag_qubit = cirq.LineQubit(70)
        
        # Create inner join circuit
        try:
            join_circuit = self.join.inner_join(
                key_qubits_a, value_qubits_a,
                key_qubits_b, value_qubits_b,
                output_key_qubits,
                output_value_qubits_a,
                output_value_qubits_b,
                flag_qubit
            )
            
            logger.debug(f"Inner join circuit: {join_circuit}")
            
            # Verify circuit was created
            self.assertIsNotNone(join_circuit)
            operations = list(join_circuit.all_operations())
            logger.debug(f"Join operations count: {len(operations)}")
            self.assertGreater(len(operations), 0)
        except Exception as e:
            logger.error(f"Error in inner_join: {e}")
            self.fail(f"inner_join raised exception: {e}")
    
    def test_left_join(self):
        """Test left join quantum circuit."""
        logger.debug("Testing left_join")
        # Create test qubits
        key_qubits_a = [cirq.LineQubit(i) for i in range(2)]
        value_qubits_a = [cirq.LineQubit(i+10) for i in range(2)]
        key_qubits_b = [cirq.LineQubit(i+20) for i in range(2)]
        value_qubits_b = [cirq.LineQubit(i+30) for i in range(2)]
        output_key_qubits = [cirq.LineQubit(i+40) for i in range(2)]
        output_value_qubits_a = [cirq.LineQubit(i+50) for i in range(2)]
        output_value_qubits_b = [cirq.LineQubit(i+60) for i in range(2)]
        match_flag_qubit = cirq.LineQubit(70)
        
        # Create left join circuit
        try:
            join_circuit = self.join.left_join(
                key_qubits_a, value_qubits_a,
                key_qubits_b, value_qubits_b,
                output_key_qubits,
                output_value_qubits_a,
                output_value_qubits_b,
                match_flag_qubit
            )
            
            logger.debug(f"Left join circuit: {join_circuit}")
            
            # Verify circuit was created
            self.assertIsNotNone(join_circuit)
            operations = list(join_circuit.all_operations())
            logger.debug(f"Join operations count: {len(operations)}")
            self.assertGreater(len(operations), 0)
        except Exception as e:
            logger.error(f"Error in left_join: {e}")
            self.fail(f"left_join raised exception: {e}")


class TestQuantumIndex(unittest.TestCase):
    def setUp(self):
        logger.debug("Setting up QuantumIndex test")
        # Initialize with default parameters - no special handling needed now
        self.index = QuantumIndex()
        
    def test_create_hash_index(self):
        """Test creating a hash index circuit."""
        logger.debug("Testing create_hash_index")
        key_qubits = [cirq.LineQubit(i) for i in range(4)]
        hash_qubits = [cirq.LineQubit(i+10) for i in range(2)]
        
        # Create hash index
        hash_circuit = self.index.create_hash_index(key_qubits, hash_qubits)
        
        logger.debug(f"Hash index circuit: {hash_circuit}")
        
        # Verify circuit was created
        self.assertIsNotNone(hash_circuit)
        operations = list(hash_circuit.all_operations())
        logger.debug(f"Hash index operations count: {len(operations)}")
        self.assertGreater(len(operations), 0)
        
    def test_binary_tree_index(self):
        """Test creating a binary tree index circuit."""
        logger.debug("Testing binary_tree_index")
        key_qubits = [cirq.LineQubit(i) for i in range(4)]
        index_qubits = [cirq.LineQubit(i+10) for i in range(2)]
        
        # Create binary tree index
        tree_circuit = self.index.binary_tree_index(key_qubits, index_qubits)
        
        logger.debug(f"Binary tree index circuit: {tree_circuit}")
        
        # Verify circuit was created
        self.assertIsNotNone(tree_circuit)
        operations = list(tree_circuit.all_operations())
        logger.debug(f"Binary tree operations count: {len(operations)}")
        self.assertGreater(len(operations), 0)


class TestDatabaseGates(unittest.TestCase):
    def setUp(self):
        logger.debug("Setting up DatabaseGates test")
        self.gates = DatabaseGates()
        
    def test_create_oracle(self):
        """Test creating a pattern-matching oracle."""
        logger.debug("Testing create_oracle gate")
        qubits = [cirq.LineQubit(i) for i in range(2)]
        
        try:
            # Create oracle for pattern "01"
            oracle_circuit = self.gates.create_oracle("01", qubits)
            
            logger.debug(f"Oracle circuit: {oracle_circuit}")
            
            # Verify circuit was created
            self.assertIsNotNone(oracle_circuit)
            operations = list(oracle_circuit.all_operations())
            logger.debug(f"Oracle operations count: {len(operations)}")
            self.assertGreater(len(operations), 0)
        except Exception as e:
            logger.error(f"Error in create_oracle: {e}")
            self.fail(f"create_oracle raised exception: {e}")
    
    def test_create_equality_test(self):
        """Test creating an equality test circuit."""
        logger.debug("Testing create_equality_test")
        qubits1 = [cirq.LineQubit(i) for i in range(2)]
        qubits2 = [cirq.LineQubit(i+10) for i in range(2)]
        output_qubit = cirq.LineQubit(20)
        
        try:
            eq_circuit = self.gates.create_equality_test(qubits1, qubits2, output_qubit)
            
            logger.debug(f"Equality test circuit: {eq_circuit}")
            
            # Verify circuit was created
            self.assertIsNotNone(eq_circuit)
            operations = list(eq_circuit.all_operations())
            logger.debug(f"Equality test operations count: {len(operations)}")
            self.assertGreater(len(operations), 0)
        except Exception as e:
            logger.error(f"Error in create_equality_test: {e}")
            self.fail(f"create_equality_test raised exception: {e}")
    
    def test_create_amplitude_amplification(self):
        """Test creating an amplitude amplification circuit."""
        logger.debug("Testing create_amplitude_amplification")
        qubits = [cirq.LineQubit(i) for i in range(2)]
        
        # First create an oracle to use
        oracle_circuit = self.gates.create_oracle("01", qubits)
        
        try:
            amp_circuit = self.gates.create_amplitude_amplification(
                oracle_circuit, qubits, iterations=1
            )
            
            logger.debug(f"Amplitude amplification circuit: {amp_circuit}")
            
            # Verify circuit was created
            self.assertIsNotNone(amp_circuit)
            operations = list(amp_circuit.all_operations())
            logger.debug(f"Amplitude amplification operations count: {len(operations)}")
            self.assertGreater(len(operations), 0)
        except Exception as e:
            logger.error(f"Error in create_amplitude_amplification: {e}")
            self.fail(f"create_amplitude_amplification raised exception: {e}")


if __name__ == "__main__":
    logger.info("Starting quantum operations tests")
    unittest.main()