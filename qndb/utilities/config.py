# config.py
"""
Configuration management for quantum database.

This module provides utilities for loading, validating, and accessing 
configuration settings for the quantum database system.
"""

import os
import json
import yaml
import logging
import copy
from collections import ChainMap
import threading
from pathlib import Path

# Default configuration paths
DEFAULT_CONFIG_PATHS = [
    './config.yml',
    './config.yaml',
    './config.json',
    '~/.quantum_db/config.yml',
    '/etc/quantum_db/config.yml'
]

# Environment variable prefix
ENV_PREFIX = 'QUANTUM_DB_'

# Thread-local storage for scoped configuration
_thread_local = threading.local()

# Module logger
logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Exception raised for configuration errors."""
    pass


class Configuration:
    """Configuration management for quantum database."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        # Default configuration
        self._defaults = {
            'database': {
                'name': 'quantum_db',
                'circuit_optimization_level': 2,
                'max_qubits': 32,
                'simulator': 'statevector',
                'persistence_path': './data',
                'error_correction': {
                    'enabled': False,
                    'method': 'surface_code'
                }
            },
            'runtime': {
                'execution_mode': 'simulator',
                'max_circuit_depth': 1000,
                'max_shots': 10000,
                'timeout_seconds': 300,
                'parallel_circuits': 4
            },
            'storage': {
                'format': 'qasm',
                'compression': False,
                'max_cached_circuits': 100,
                'cache_size_mb': 1024
            },
            'security': {
                'encryption': {
                    'enabled': False,
                    'algorithm': 'AES256'
                },
                'access_control': {
                    'enabled': False,
                    'default_policy': 'deny'
                }
            },
            'logging': {
                'log_level': 'INFO',
                'log_to_console': True,
                'log_to_file': False,
                'log_dir': './logs',
                'log_filename': 'quantum_db.log'
            },
            'distributed': {
                'enabled': False,
                'node_discovery': 'manual',
                'known_nodes': [],
                'sync_interval_seconds': 60
            },
            'middleware': {
                'cache_results': True,
                'query_optimization_level': 2,
                'max_queue_size': 1000,
                'max_workers': 8
            },
            'interface': {
                'host': '127.0.0.1',
                'port': 8008,
                'max_connections': 100,
                'connection_timeout': 30
            }
        }
        
        # Current configuration (starts with defaults)
        self._config = copy.deepcopy(self._defaults)
        
        # Keep track of loaded config files
        self._loaded_files = []
    
    def reset(self):
        """Reset configuration to defaults."""
        self._config = copy.deepcopy(self._defaults)
        self._loaded_files = []
    
    def load_file(self, filepath):
        """
        Load configuration from file.
        
        Args:
            filepath (str): Path to configuration file
            
        Returns:
            bool: True if file was loaded successfully
            
        Raises:
            ConfigurationError: If file format is not supported or file is invalid
        """
        filepath = os.path.expanduser(filepath)
        
        if not os.path.exists(filepath):
            logger.warning(f"Configuration file not found: {filepath}")
            return False
        
        try:
            with open(filepath, 'r') as f:
                if filepath.endswith('.json'):
                    config_data = json.load(f)
                elif filepath.endswith(('.yml', '.yaml')):
                    config_data = yaml.safe_load(f)
                else:
                    raise ConfigurationError(
                        f"Unsupported configuration format: {filepath}"
                    )
            
            # Update configuration
            self._deep_update(self._config, config_data)
            
            # Add to loaded files
            self._loaded_files.append(filepath)
            logger.info(f"Loaded configuration from {filepath}")
            
            return True
        
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise ConfigurationError(f"Invalid configuration file {filepath}: {e}")
        except Exception as e:
            raise ConfigurationError(f"Error loading configuration from {filepath}: {e}")
    
    def load_default_files(self):
        """
        Load configuration from default file locations.
        
        Returns:
            int: Number of files successfully loaded
        """
        loaded_count = 0
        
        for path in DEFAULT_CONFIG_PATHS:
            expanded_path = os.path.expanduser(path)
            try:
                if self.load_file(expanded_path):
                    loaded_count += 1
            except ConfigurationError as e:
                logger.warning(f"Error loading default config file: {e}")
        
        return loaded_count
    
    def load_from_env(self):
        """
        Load configuration from environment variables.
        
        Environment variables should be prefixed with QUANTUM_DB_ and use __
        as separator for nested keys (e.g., QUANTUM_DB_DATABASE__NAME)
        
        Returns:
            int: Number of environment variables processed
        """
        count = 0
        
        for key, value in os.environ.items():
            if key.startswith(ENV_PREFIX):
                # Remove prefix and split by double underscore
                key_parts = key[len(ENV_PREFIX):].lower().split('__')
                
                # Try to parse value as JSON
                try:
                    parsed_value = json.loads(value)
                except json.JSONDecodeError:
                    # If not valid JSON, use as string
                    parsed_value = value
                
                # Update config with this value
                self._update_nested(self._config, key_parts, parsed_value)
                count += 1
        
        if count > 0:
            logger.info(f"Loaded {count} configuration values from environment variables")
        
        return count
    
    def load_dict(self, config_dict):
        """
        Load configuration from dictionary.
        
        Args:
            config_dict (dict): Configuration dictionary
            
        Returns:
            bool: True if loaded successfully
        """
        if not isinstance(config_dict, dict):
            raise ConfigurationError("Configuration must be a dictionary")
        
        # Update configuration
        self._deep_update(self._config, config_dict)
        return True
    
    def get(self, key_path, default=None):
        """
        Get configuration value by key path.
        
        Args:
            key_path (str): Dot-separated path to config value (e.g., 'database.name')
            default: Value to return if key not found
            
        Returns:
            Value at the specified key path, or default if not found
        """
        # Check thread-local override first
        if hasattr(_thread_local, 'config_overlay'):
            try:
                value = self._get_nested(_thread_local.config_overlay, key_path.split('.'))
                if value is not None:
                    return value
            except KeyError:
                pass
        
        # Fall back to main config
        try:
            return self._get_nested(self._config, key_path.split('.'))
        except KeyError:
            return default
    
    def set(self, key_path, value):
        """
        Set configuration value by key path.
        
        Args:
            key_path (str): Dot-separated path to config value (e.g., 'database.name')
            value: Value to set
        """
        self._update_nested(self._config, key_path.split('.'), value)
    
    def with_overlay(self, overlay_dict):
        """
        Create a context manager with overlaid configuration.
        
        Args:
            overlay_dict (dict): Configuration overlay
            
        Returns:
            ConfigOverlay: Context manager for scoped configuration
        """
        return ConfigOverlay(overlay_dict)
    
    def _deep_update(self, target, source):
        """Recursively update target dict with values from source dict."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    def _update_nested(self, config_dict, key_parts, value):
        """Update nested dictionary using key parts list."""
        current = config_dict
        
        # Navigate to the deepest level
        for part in key_parts[:-1]:
            if part not in current:
                current[part] = {}
            elif not isinstance(current[part], dict):
                current[part] = {}
            
            current = current[part]
        
        # Set the value at the deepest level
        current[key_parts[-1]] = value
    
    def _get_nested(self, config_dict, key_parts):
        """Get value from nested dictionary using key parts list."""
        current = config_dict
        
        for part in key_parts:
            current = current[part]
        
        return current
    
    def as_dict(self):
        """
        Get a copy of the complete configuration as a dictionary.
        
        Returns:
            dict: Complete configuration
        """
        return copy.deepcopy(self._config)
    
    def validate(self, schema=None):
        """
        Validate the configuration against a schema.
        
        Args:
            schema (dict, optional): Validation schema
            
        Returns:
            bool: True if valid
            
        Raises:
            ConfigurationError: If validation fails
        """
        if schema is None:
            # Default minimal validation
            required_sections = ['database', 'runtime', 'logging']
            for section in required_sections:
                if section not in self._config:
                    raise ConfigurationError(f"Missing required configuration section: {section}")
            return True
        
        # If jsonschema is available, use it for validation
        try:
            import jsonschema
            jsonschema.validate(instance=self._config, schema=schema)
            return True
        except ImportError:
            logger.warning("jsonschema package not available, performing basic validation")
            return self._basic_validate(schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ConfigurationError(f"Configuration validation failed: {e}")
    
    def _basic_validate(self, schema):
        """Basic schema validation for when jsonschema is not available."""
        if 'required' in schema:
            for key in schema['required']:
                if key not in self._config:
                    raise ConfigurationError(f"Missing required configuration key: {key}")
        
        if 'properties' in schema:
            for key, prop_schema in schema['properties'].items():
                if key in self._config:
                    value = self._config[key]
                    
                    # Type validation
                    if 'type' in prop_schema:
                        schema_type = prop_schema['type']
                        if schema_type == 'object' and not isinstance(value, dict):
                            raise ConfigurationError(f"Expected {key} to be an object")
                        elif schema_type == 'array' and not isinstance(value, list):
                            raise ConfigurationError(f"Expected {key} to be an array")
                        elif schema_type == 'string' and not isinstance(value, str):
                            raise ConfigurationError(f"Expected {key} to be a string")
                        elif schema_type == 'number' and not isinstance(value, (int, float)):
                            raise ConfigurationError(f"Expected {key} to be a number")
                        elif schema_type == 'boolean' and not isinstance(value, bool):
                            raise ConfigurationError(f"Expected {key} to be a boolean")
                    
                    # Recursive validation for objects
                    if isinstance(value, dict) and 'properties' in prop_schema:
                        for subkey, subvalue in value.items():
                            if subkey in prop_schema['properties']:
                                # Here we would ideally recurse, but for basic validation
                                # we'll just check presence
                                pass
        
        return True


class ConfigOverlay:
    """Context manager for temporary configuration overlay."""
    
    def __init__(self, overlay_dict):
        """
        Initialize configuration overlay.
        
        Args:
            overlay_dict (dict): Configuration overlay
        """
        self.overlay_dict = overlay_dict
        self.previous_overlay = None
    
    def __enter__(self):
        """Apply overlay when entering context."""
        # Save previous overlay if it exists
        if hasattr(_thread_local, 'config_overlay'):
            self.previous_overlay = _thread_local.config_overlay
        
        # Set new overlay
        _thread_local.config_overlay = self.overlay_dict
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Remove overlay when exiting context."""
        if self.previous_overlay is not None:
            # Restore previous overlay
            _thread_local.config_overlay = self.previous_overlay
        else:
            # Remove overlay completely
            if hasattr(_thread_local, 'config_overlay'):
                delattr(_thread_local, 'config_overlay')


# Global configuration instance
_global_config = Configuration()


def get_config():
    """
    Get the global configuration instance.
    
    Returns:
        Configuration: Global configuration instance
    """
    return _global_config


def load_config(config_path=None):
    """
    Load configuration from specified path or default locations.
    
    Args:
        config_path (str, optional): Path to config file
        
    Returns:
        Configuration: Loaded configuration
    """
    # Reset to defaults
    _global_config.reset()
    
    # Try to load from specific path if provided
    if config_path:
        try:
            if not _global_config.load_file(config_path):
                logger.warning(f"Could not load configuration from {config_path}")
        except ConfigurationError as e:
            logger.error(f"Error loading configuration: {e}")
    else:
        # Load from default locations
        loaded = _global_config.load_default_files()
        if loaded == 0:
            logger.warning("No configuration files found in default locations")
    
    # Load from environment variables
    _global_config.load_from_env()
    
    return _global_config


def get(key, default=None):
    """
    Get configuration value by key path.
    
    Args:
        key (str): Dot-separated path to config value
        default: Value to return if key not found
        
    Returns:
        Value at the specified key path, or default if not found
    """
    return _global_config.get(key, default)


def set(key, value):
    """
    Set configuration value by key path.
    
    Args:
        key (str): Dot-separated path to config value
        value: Value to set
    """
    _global_config.set(key, value)


def with_overlay(overlay_dict):
    """
    Create a context manager with overlaid configuration.
    
    Args:
        overlay_dict (dict): Configuration overlay
        
    Returns:
        ConfigOverlay: Context manager for scoped configuration
    """
    return _global_config.with_overlay(overlay_dict)