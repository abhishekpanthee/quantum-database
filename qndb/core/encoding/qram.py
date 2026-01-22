"""
Quantum Random Access Memory (QRAM) Implementation.

Implements a bucket-brigade QRAM architecture with proper routing qubits,
address decoding, and data loading (arXiv:0708.1879).
"""
import cirq
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

class QRAM:
    """
    Quantum Random Access Memory implementation for efficient data loading.
    """
    
    def __init__(self, num_address_qubits: int, num_data_qubits: int):
        """
        Initialize the QRAM.
        
        Args:
            num_address_qubits: Number of qubits used for addressing
            num_data_qubits: Number of qubits used for data storage
        """
        self.num_address_qubits = num_address_qubits
        self.num_data_qubits = num_data_qubits
        self.max_addresses = 2**num_address_qubits
        
    def _initialize_qubits(self) -> Tuple[List[cirq.Qid], List[cirq.Qid]]:
        """
        Initialize address and data qubits.
        
        Returns:
            Tuple of (address qubits, data qubits)
        """
        address_qubits = [cirq.LineQubit(i) for i in range(self.num_address_qubits)]
        data_qubits = [cirq.LineQubit(i + self.num_address_qubits) 
                      for i in range(self.num_data_qubits)]
        
        return address_qubits, data_qubits

    def _create_routing_qubits(self) -> List[cirq.Qid]:
        """Create routing (tree-node) qubits for the bucket-brigade.

        The binary tree has 2^n - 1 internal nodes where n is the number of
        address qubits.  Each internal node is a routing qubit that steers the
        signal left or right.
        """
        offset = self.num_address_qubits + self.num_data_qubits
        num_routing = 2 ** self.num_address_qubits - 1
        return [cirq.NamedQubit(f"_route_{i}") for i in range(num_routing)]

    def _route_address(self, address_qubits: List[cirq.Qid],
                       routing_qubits: List[cirq.Qid]) -> cirq.Circuit:
        """Build the routing stage: fan address bits into the binary tree.

        For each level *l* of the tree (root = level 0), the address qubit
        ``address_qubits[l]`` determines whether the signal goes left (0) or
        right (1).  We propagate this choice with controlled-SWAP on routing
        qubits.
        """
        circuit = cirq.Circuit()

        # Level 0: copy top address bit into the root routing qubit
        circuit.append(cirq.CNOT(address_qubits[0], routing_qubits[0]))

        # Subsequent levels: the parent routing qubit controls which child
        # receives the next address bit.
        for level in range(1, self.num_address_qubits):
            nodes_at_level = 2 ** level
            first_node = 2 ** level - 1  # index of first node at this level

            for node_offset in range(nodes_at_level):
                node_idx = first_node + node_offset
                if node_idx >= len(routing_qubits):
                    break
                parent_idx = (node_idx - 1) // 2
                is_right_child = node_idx % 2 == 0  # 0-indexed: even = right child

                # The parent being in state |1> means the signal went right;
                # if we are the matching child, copy the address bit.
                if is_right_child:
                    circuit.append(
                        cirq.CNOT(address_qubits[level], routing_qubits[node_idx])
                            .controlled_by(routing_qubits[parent_idx])
                    )
                else:
                    circuit.append(cirq.X(routing_qubits[parent_idx]))
                    circuit.append(
                        cirq.CNOT(address_qubits[level], routing_qubits[node_idx])
                            .controlled_by(routing_qubits[parent_idx])
                    )
                    circuit.append(cirq.X(routing_qubits[parent_idx]))

        return circuit

    def create_bucket_brigade_circuit(self, 
                                      data_map: Dict[int, List[int]]) -> cirq.Circuit:
        """
        Create a bucket brigade QRAM circuit for the given data.
        
        The bucket-brigade architecture uses a binary tree of routing qubits.
        Each address qubit controls a level of the tree, directing the query
        to the correct memory cell.  Data is loaded conditioned on the leaf
        routing qubits.
        
        Args:
            data_map: Dictionary mapping addresses to data values (as bit lists)
            
        Returns:
            Cirq circuit implementing the QRAM
        """
        address_qubits, data_qubits = self._initialize_qubits()
        routing_qubits = self._create_routing_qubits()

        circuit = cirq.Circuit()

        # --- 1. Route the address through the binary tree ---
        circuit += self._route_address(address_qubits, routing_qubits)

        # --- 2. Load data at each leaf conditioned on the routing state ---
        # The leaf routing qubits are the last 2^(n-1) entries.
        num_leaves = 2 ** (self.num_address_qubits - 1) if self.num_address_qubits > 0 else 1
        leaf_start = len(routing_qubits) - num_leaves

        for address, data_bits in data_map.items():
            if address >= self.max_addresses:
                continue
            # Determine the path from root to leaf for this address
            # and build controls from the routing qubits along that path.
            controls = self._path_controls(address, routing_qubits)

            for bit_idx, bit_val in enumerate(data_bits):
                if bit_val == 1 and bit_idx < self.num_data_qubits:
                    if controls:
                        circuit.append(
                            cirq.X(data_qubits[bit_idx]).controlled_by(*controls)
                        )
                    else:
                        circuit.append(cirq.X(data_qubits[bit_idx]))

        return circuit

    def _path_controls(self, address: int,
                       routing_qubits: List[cirq.Qid]) -> List[cirq.Qid]:
        """Return the routing qubits along the tree-path for *address*."""
        controls = []
        node_idx = 0  # start at root
        for level in range(self.num_address_qubits):
            if node_idx < len(routing_qubits):
                controls.append(routing_qubits[node_idx])
            bit = (address >> (self.num_address_qubits - 1 - level)) & 1
            if bit == 0:
                node_idx = 2 * node_idx + 1  # left child
            else:
                node_idx = 2 * node_idx + 2  # right child
        return controls

    def create_fanout_circuit(self, data_map: Dict[int, List[int]]) -> cirq.Circuit:
        """
        Create a fanout-based QRAM circuit for the given data.

        This is a direct select-style QRAM: for each address in *data_map*,
        a multi-controlled X conditioned on the address qubits loads the data.
        Simpler than bucket-brigade but uses O(2^n) multi-controlled gates.
        
        Args:
            data_map: Dictionary mapping addresses to data values (as bit lists)
            
        Returns:
            Cirq circuit implementing the QRAM
        """
        address_qubits, data_qubits = self._initialize_qubits()
        circuit = cirq.Circuit()

        for address, data_bits in data_map.items():
            if address >= self.max_addresses:
                continue

            address_bin = format(address, f'0{self.num_address_qubits}b')
            control_values = [int(b) for b in address_bin]

            for bit_idx, bit_val in enumerate(data_bits):
                if bit_val == 1 and bit_idx < self.num_data_qubits:
                    circuit.append(
                        cirq.X(data_qubits[bit_idx]).controlled_by(
                            *address_qubits, control_values=control_values
                        )
                    )

        return circuit

    def query(self, address_state: List[int],
              data_map: Optional[Dict[int, List[int]]] = None) -> cirq.Circuit:
        """
        Create a circuit to query the QRAM with a specific address.
        
        Args:
            address_state: Binary representation of the address to query
            data_map: Optional data to load (uses fanout circuit internally)
            
        Returns:
            Cirq circuit for the query
        """
        if len(address_state) != self.num_address_qubits:
            raise ValueError(f"Expected {self.num_address_qubits} address bits")
            
        address_qubits, data_qubits = self._initialize_qubits()
        circuit = cirq.Circuit()

        # Set the address qubits
        for i, bit in enumerate(address_state):
            if bit == 1:
                circuit.append(cirq.X(address_qubits[i]))

        # If data_map provided, build and append the QRAM load circuit
        if data_map is not None:
            circuit += self.create_fanout_circuit(data_map)

        # Measure the data qubits
        circuit.append(cirq.measure(*data_qubits, key='data'))
        
        return circuit