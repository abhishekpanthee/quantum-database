"""
Persistent Storage - Mechanisms for storing quantum data persistently.
"""
import cirq
import numpy as np
import json
import os
import pickle
from typing import List, Dict, Any, Optional, Tuple, Union

class PersistentStorage:
    """
    Handles persistent storage of quantum database states and circuits.
    """
    
    def __init__(self, storage_dir: str = "quantum_storage"):
        """
        Initialize the persistent storage.
        
        Args:
            storage_dir: Directory to store quantum database files
        """
        self.storage_dir = storage_dir
        self._ensure_directory_exists()
        
    def _ensure_directory_exists(self) -> None:
        """Create the storage directory if it doesn't exist."""
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
    
    def save_circuit(self, circuit: cirq.Circuit, name: str) -> str:
        """
        Save a quantum circuit to disk.
        
        Args:
            circuit: Cirq circuit to save
            name: Name to save the circuit under
            
        Returns:
            Path to the saved circuit
        """
        circuit_path = os.path.join(self.storage_dir, f"{name}_circuit.pickle")
        
        with open(circuit_path, 'wb') as f:
            pickle.dump(circuit, f)
            
        # Also save a text representation for human readability
        text_path = os.path.join(self.storage_dir, f"{name}_circuit.txt")
        with open(text_path, 'w') as f:
            f.write(str(circuit))
            
        return circuit_path
    
    def load_circuit(self, name: str) -> cirq.Circuit:
        """
        Load a quantum circuit from disk.
        
        Args:
            name: Name of the circuit to load
            
        Returns:
            Loaded Cirq circuit
        """
        circuit_path = os.path.join(self.storage_dir, f"{name}_circuit.pickle")
        
        if not os.path.exists(circuit_path):
            raise FileNotFoundError(f"Circuit '{name}' not found")
            
        with open(circuit_path, 'rb') as f:
            circuit = pickle.load(f)
            
        return circuit
    
    def save_state_vector(self, state_vector: np.ndarray, name: str) -> str:
        """
        Save a quantum state vector to disk.
        
        Args:
            state_vector: Numpy array representing quantum state
            name: Name to save the state under
            
        Returns:
            Path to the saved state
        """
        state_path = os.path.join(self.storage_dir, f"{name}_state.npy")
        np.save(state_path, state_vector)
        return state_path
    
    def load_state_vector(self, name: str) -> np.ndarray:
        """
        Load a quantum state vector from disk.
        
        Args:
            name: Name of the state to load
            
        Returns:
            Loaded state vector
        """
        state_path = os.path.join(self.storage_dir, f"{name}_state.npy")
        
        if not os.path.exists(state_path):
            raise FileNotFoundError(f"State '{name}' not found")
            
        return np.load(state_path)
    
    def save_database_schema(self, schema: Dict[str, Any], name: str) -> str:
        """
        Save a database schema to disk.
        
        Args:
            schema: Dictionary containing database schema
            name: Name to save the schema under
            
        Returns:
            Path to the saved schema
        """
        schema_path = os.path.join(self.storage_dir, f"{name}_schema.json")
        
        with open(schema_path, 'w') as f:
            json.dump(schema, f, indent=2)
            
        return schema_path
    
    def load_database_schema(self, name: str) -> Dict[str, Any]:
        """
        Load a database schema from disk.
        
        Args:
            name: Name of the schema to load
            
        Returns:
            Loaded database schema
        """
        schema_path = os.path.join(self.storage_dir, f"{name}_schema.json")
        
        if not os.path.exists(schema_path):
            raise FileNotFoundError(f"Schema '{name}' not found")
            
        with open(schema_path, 'r') as f:
            schema = json.load(f)
            
        return schema
    
    def save_measurement_results(self, results: Dict[str, np.ndarray], name: str) -> str:
        """
        Save measurement results to disk.
        
        Args:
            results: Dictionary of measurement results
            name: Name to save the results under
            
        Returns:
            Path to the saved results
        """
        results_path = os.path.join(self.storage_dir, f"{name}_results.pickle")
        
        with open(results_path, 'wb') as f:
            pickle.dump(results, f)
            
        return results_path
    
    def load_measurement_results(self, name: str) -> Dict[str, np.ndarray]:
        """
        Load measurement results from disk.
        
        Args:
            name: Name of the results to load
            
        Returns:
            Loaded measurement results
        """
        results_path = os.path.join(self.storage_dir, f"{name}_results.pickle")
        
        if not os.path.exists(results_path):
            raise FileNotFoundError(f"Results '{name}' not found")
            
        with open(results_path, 'rb') as f:
            results = pickle.load(f)
            
        return results
    
    def list_stored_items(self) -> Dict[str, List[str]]:
        """
        List all stored items by category.
        
        Returns:
            Dictionary of item types and names
        """
        items = {
            "circuits": [],
            "states": [],
            "schemas": [],
            "results": []
        }
        
        for filename in os.listdir(self.storage_dir):
            if filename.endswith("_circuit.pickle"):
                items["circuits"].append(filename.replace("_circuit.pickle", ""))
            elif filename.endswith("_state.npy"):
                items["states"].append(filename.replace("_state.npy", ""))
            elif filename.endswith("_schema.json"):
                items["schemas"].append(filename.replace("_schema.json", ""))
            elif filename.endswith("_results.pickle"):
                items["results"].append(filename.replace("_results.pickle", ""))
                
        return items
    
    def delete_item(self, name: str, item_type: str) -> bool:
        """
        Delete a stored item.
        
        Args:
            name: Name of the item to delete
            item_type: Type of item ("circuit", "state", "schema", "results")
            
        Returns:
            True if deletion was successful
        """
        if item_type == "circuit":
            path = os.path.join(self.storage_dir, f"{name}_circuit.pickle")
            text_path = os.path.join(self.storage_dir, f"{name}_circuit.txt")
            path = os.path.join(self.storage_dir, f"{name}_circuit.pickle")
            text_path = os.path.join(self.storage_dir, f"{name}_circuit.txt")
            if os.path.exists(path):
                os.remove(path)
            if os.path.exists(text_path):
                os.remove(text_path)
        elif item_type == "state":
            path = os.path.join(self.storage_dir, f"{name}_state.npy")
            if os.path.exists(path):
                os.remove(path)
        elif item_type == "schema":
            path = os.path.join(self.storage_dir, f"{name}_schema.json")
            if os.path.exists(path):
                os.remove(path)
        elif item_type == "results":
            path = os.path.join(self.storage_dir, f"{name}_results.pickle")
            if os.path.exists(path):
                os.remove(path)
        else:
            raise ValueError(f"Unknown item type: {item_type}")
            
        return True
    
    def backup_database(self, backup_path: Optional[str] = None) -> str:
        """
        Create a backup of the entire database.
        
        Args:
            backup_path: Path to save the backup to (defaults to timestamped file)
            
        Returns:
            Path to the backup file
        """
        import datetime
        import shutil
        
        if backup_path is None:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"quantum_db_backup_{timestamp}"
            
        # Create a zip archive of the storage directory
        shutil.make_archive(backup_path, 'zip', self.storage_dir)
        
        return f"{backup_path}.zip"
    
    def restore_from_backup(self, backup_path: str) -> bool:
        """
        Restore the database from a backup.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if restoration was successful
        """
        import shutil
        
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup file '{backup_path}' not found")
            
        # Clear the current storage directory
        if os.path.exists(self.storage_dir):
            shutil.rmtree(self.storage_dir)
            
        # Extract the backup
        shutil.unpack_archive(backup_path, self.storage_dir)
        
        return True