"""
Persistent Storage - Mechanisms for storing quantum data persistently.
"""
import cirq
import numpy as np
import json
import os
import pickle
import datetime
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
    
    def save_circuit(self, circuit: cirq.Circuit, name: str, metadata: Dict = None) -> str:
        """
        Save a quantum circuit to disk.
        
        Args:
            circuit: Cirq circuit to save
            name: Name to save the circuit under
            metadata: Optional metadata dictionary
            
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
        
        # Save metadata if provided
        if metadata is None:
            metadata = {}
        
        # Ensure metadata has created_at
        if "created_at" not in metadata:
            metadata["created_at"] = datetime.datetime.now().isoformat()
        
        # Store metadata in a separate file
        metadata_path = os.path.join(self.storage_dir, f"{name}_metadata.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        return circuit_path
    
    def load_circuit(self, name: str) -> cirq.Circuit:
        """
        Load a quantum circuit from disk.
        
        Args:
            name: Name or path of the circuit to load
            
        Returns:
            Loaded Cirq circuit
        """
        # Handle if full path is provided
        if name.endswith("_circuit.pickle"):
            circuit_path = name
        elif os.path.join(self.storage_dir) in name:
            # Extract basename from full path
            basename = os.path.basename(name.rstrip("/"))
            if not basename.endswith("_circuit.pickle"):
                basename += "_circuit.pickle"
            circuit_path = os.path.join(self.storage_dir, basename)
        else:
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
    
    def save_database_schema(self, schema: Dict[str, Any], name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Save a database schema to disk.
        
        Args:
            schema: Dictionary containing database schema
            name: Name to save the schema under
            metadata: Optional metadata to store with the schema
            
        Returns:
            Path to the saved schema
        """
        schema_path = os.path.join(self.storage_dir, f"{name}_schema.json")
        
        # Add metadata to the schema if provided
        if metadata:
            schema_with_metadata = schema.copy()
            schema_with_metadata["__metadata__"] = metadata
        else:
            schema_with_metadata = schema
        
        with open(schema_path, 'w') as f:
            json.dump(schema_with_metadata, f, indent=2)
        
        # Store metadata separately as well for consistency
        if metadata is None:
            metadata = {}
        
        # Ensure metadata has created_at
        if "created_at" not in metadata:
            metadata["created_at"] = datetime.datetime.now().isoformat()
            
        # Store metadata in a separate file
        metadata_path = os.path.join(self.storage_dir, f"{name}_metadata.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        return schema_path
    
    def load_database_schema(self, name: str) -> Dict[str, Any]:
        """
        Load a database schema from storage.
        
        Args:
            name: Name or ID of the schema to load
            
        Returns:
            The loaded schema as a dictionary
            
        Raises:
            KeyError: If the schema is not found
        """
        # Handle full paths with schema extension
        schema_path = name
        if not schema_path.endswith('_schema.json'):
            schema_path = os.path.join(self.storage_dir, f"{name}_schema.json")
        
        # Check if the file exists
        if not os.path.exists(schema_path):
            # Raise KeyError for consistency with the test expectation
            raise KeyError(f"Schema '{name}' not found")
        
        # Load the schema from the file
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
    
    def list_stored_items(self) -> List[Dict[str, Any]]:
        """
        List all stored items with metadata.
        
        Returns:
            List of dictionaries containing item information
        """
        items = []
        
        for filename in os.listdir(self.storage_dir):
            item_name = None
            item_type = None
            metadata = {}
            created_at = datetime.datetime.now().isoformat()
            
            if filename.endswith("_circuit.pickle"):
                item_name = filename.replace("_circuit.pickle", "")
                item_type = "circuit"
                
            elif filename.endswith("_state.npy"):
                item_name = filename.replace("_state.npy", "")
                item_type = "state"
                
            elif filename.endswith("_schema.json"):
                item_name = filename.replace("_schema.json", "")
                item_type = "data"
                
            elif filename.endswith("_results.pickle"):
                item_name = filename.replace("_results.pickle", "")
                item_type = "results"
            
            # Skip if not a valid item or we already processed this item
            if item_name is None or any(i["name"] == item_name for i in items):
                continue
                
            # Try to load metadata if it exists
            metadata_path = os.path.join(self.storage_dir, f"{item_name}_metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    # Extract created_at from metadata if available
                    if "created_at" in metadata:
                        created_at = metadata["created_at"]
                except:
                    pass
            
            # Add item info with properly formatted ID
            # The test expects the ID to match the full file path for deletion/metadata operations
            items.append({
                "id": f"{self.storage_dir}/{item_name}_schema.json" if item_type == "data" else f"{self.storage_dir}/{item_name}",
                "name": item_name,
                "type": item_type,
                "created_at": created_at,
                "metadata": metadata
            })
                    
        return items
    
    def delete_data(self, name: str) -> bool:
        """
        Delete a stored item.
        
        Args:
            name: Name or ID of the item to delete
            
        Returns:
            True if deletion was successful
        """
        # Extract base name from the name/ID
        base_name = name
        
        # If it contains the storage directory, extract just the item name
        if name.startswith(self.storage_dir):
            # Check for direct file path first
            if os.path.exists(name):
                os.remove(name)
                
                # Also remove associated metadata file if it exists
                base_without_ext = name.rsplit('.', 1)[0]  # Remove extension
                metadata_path = f"{base_without_ext.replace('_schema', '')}_metadata.json"
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                return True
                
            # Extract basename for processing
            base_name = name[len(self.storage_dir) + 1:]
        
        # Further clean up the name by removing extensions
        for ext in ["_schema.json", "_circuit.pickle", "_state.npy", "_results.pickle"]:
            if base_name.endswith(ext):
                base_name = base_name[:-len(ext)]
                break
            
        # Check and delete all possible file types for this item
        files_to_delete = [
            f"{base_name}_circuit.pickle",
            f"{base_name}_circuit.txt",
            f"{base_name}_schema.json",
            f"{base_name}_state.npy",
            f"{base_name}_results.pickle",
            f"{base_name}_metadata.json"
        ]
        
        deleted_any = False
        for file_name in files_to_delete:
            file_path = os.path.join(self.storage_dir, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
                deleted_any = True
                
        return deleted_any
    
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
    
    def clear_all(self) -> None:
        """
        Clear all stored items from the storage.
        
        Returns:
            None
        """
        if not os.path.exists(self.storage_dir):
            return
            
        for filename in os.listdir(self.storage_dir):
            file_path = os.path.join(self.storage_dir, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")
    
    def update_metadata(self, item_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update metadata for a stored item.
        
        Args:
            item_id: ID of the item to update
            metadata: New metadata to set
            
        Returns:
            True if update was successful
        """
        # Extract base name from the ID
        base_name = item_id
        
        # If it contains the storage directory, extract just the item name
        if item_id.startswith(self.storage_dir):
            # Remove storage_dir prefix
            base_name = item_id[len(self.storage_dir) + 1:]
        
        # Further clean up the name by removing extensions
        for ext in ["_schema.json", "_circuit.pickle", "_state.npy", "_results.pickle"]:
            if base_name.endswith(ext):
                base_name = base_name[:-len(ext)]
                break
            
        # Check if item exists by checking for any of its possible files
        found = False
        for ext in ["_circuit.pickle", "_schema.json", "_state.npy", "_results.pickle"]:
            if os.path.exists(os.path.join(self.storage_dir, f"{base_name}{ext}")):
                found = True
                break
                
        if not found:
            raise KeyError(f"Item with ID {item_id} not found")
            
        # Get existing metadata
        metadata_path = os.path.join(self.storage_dir, f"{base_name}_metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as f:
                existing_metadata = json.load(f)
        else:
            existing_metadata = {}
            
        # Update metadata
        existing_metadata.update(metadata)
        
        # Ensure created_at exists
        if "created_at" not in existing_metadata:
            existing_metadata["created_at"] = datetime.datetime.now().isoformat()
            
        # Add updated_at timestamp
        existing_metadata["updated_at"] = datetime.datetime.now().isoformat()
            
        # Save updated metadata
        with open(metadata_path, 'w') as f:
            json.dump(existing_metadata, f, indent=2)
            
        # If it's a schema, also update the embedded metadata
        schema_path = os.path.join(self.storage_dir, f"{base_name}_schema.json")
        if os.path.exists(schema_path):
            try:
                with open(schema_path, 'r') as f:
                    schema = json.load(f)
                    
                # Update metadata in schema
                if "__metadata__" in schema:
                    schema["__metadata__"].update(metadata)
                else:
                    schema["__metadata__"] = existing_metadata
                    
                with open(schema_path, 'w') as f:
                    json.dump(schema, f, indent=2)
            except:
                pass
                
        return True