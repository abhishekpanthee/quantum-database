"""
Audit Logging Module

This module implements comprehensive audit logging for
security-sensitive operations in the quantum database system.
"""

import time
import json
import uuid
import logging
import socket
import os
import hashlib
from typing import Dict, Any, List, Optional, Union, Tuple
from enum import Enum, auto
from datetime import datetime
import threading
import queue


class AuditEventType(Enum):
    """Types of events that can be audited."""
    LOGIN = auto()
    LOGOUT = auto()
    AUTHENTICATION_FAILURE = auto()
    AUTHORIZATION_FAILURE = auto()
    USER_CREATED = auto()
    USER_MODIFIED = auto()
    USER_DELETED = auto()
    ROLE_CREATED = auto()
    ROLE_MODIFIED = auto()
    ROLE_DELETED = auto()
    PERMISSION_GRANTED = auto()
    PERMISSION_REVOKED = auto()
    RESOURCE_CREATED = auto()
    RESOURCE_MODIFIED = auto()
    RESOURCE_DELETED = auto()
    QUERY_EXECUTED = auto()
    DATABASE_CREATED = auto()
    DATABASE_MODIFIED = auto()
    DATABASE_DELETED = auto()
    TABLE_CREATED = auto()
    TABLE_MODIFIED = auto()
    TABLE_DELETED = auto()
    DATA_ACCESS = auto()
    DATA_MODIFICATION = auto()
    CONFIGURATION_CHANGE = auto()
    ENCRYPTION_KEY_ROTATION = auto()
    BACKUP_CREATED = auto()
    BACKUP_RESTORED = auto()
    SYSTEM_ERROR = auto()
    SYSTEM_STARTUP = auto()
    SYSTEM_SHUTDOWN = auto()
    QUANTUM_CIRCUIT_EXECUTION = auto()
    DISTRIBUTED_CONSENSUS = auto()
    
    @classmethod
    def from_string(cls, event_str: str) -> 'AuditEventType':
        """Convert string to event type enum."""
        return cls[event_str.upper()]


class AuditEvent:
    """Represents an audit event."""
    
    def __init__(self, event_type: AuditEventType, user_id: str, 
                resource_id: Optional[str] = None):
        """
        Initialize an audit event.
        
        Args:
            event_type: Type of event
            user_id: ID of the user who performed the action
            resource_id: Optional ID of the affected resource
        """
        self.event_id = str(uuid.uuid4())
        self.event_type = event_type
        self.timestamp = time.time()
        self.user_id = user_id
        self.resource_id = resource_id
        self.details: Dict[str, Any] = {}
        self.source_ip = None
        self.source_hostname = None
        self.success = True
        self.process_id = os.getpid()
        self.thread_id = threading.get_ident()
    
    def add_detail(self, key: str, value: Any) -> None:
        """Add a detail to the event."""
        self.details[key] = value
    
    def set_source(self, ip: str, hostname: Optional[str] = None) -> None:
        """Set source information."""
        self.source_ip = ip
        self.source_hostname = hostname
    
    def set_success(self, success: bool) -> None:
        """Set whether the operation was successful."""
        self.success = success
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary representation."""
        return {
            'event_id': self.event_id,
            'event_type': self.event_type.name,
            'timestamp': self.timestamp,
            'datetime': datetime.fromtimestamp(self.timestamp).isoformat(),
            'user_id': self.user_id,
            'resource_id': self.resource_id,
            'details': self.details,
            'source_ip': self.source_ip,
            'source_hostname': self.source_hostname,
            'success': self.success,
            'process_id': self.process_id,
            'thread_id': self.thread_id
        }
    
    def to_json(self) -> str:
        """Convert event to JSON representation."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEvent':
        """Create an event from dictionary representation."""
        event = cls(
            AuditEventType.from_string(data['event_type']), 
            data['user_id'],
            data.get('resource_id')
        )
        event.event_id = data['event_id']
        event.timestamp = data['timestamp']
        event.details = data.get('details', {})
        event.source_ip = data.get('source_ip')
        event.source_hostname = data.get('source_hostname')
        event.success = data.get('success', True)
        event.process_id = data.get('process_id', 0)
        event.thread_id = data.get('thread_id', 0)
        return event


class AuditEventSink:
    """Base class for audit event sinks."""
    
    def write_event(self, event: AuditEvent) -> bool:
        """
        Write an event to the sink.
        
        Args:
            event: Audit event to write
            
        Returns:
            True if the write was successful
        """
        raise NotImplementedError("Subclasses must implement write_event")
    
    def flush(self) -> None:
        """Flush any buffered events."""
        pass
    
    def close(self) -> None:
        """Close the sink and release resources."""
        pass


class FileAuditEventSink(AuditEventSink):
    """Audit event sink that writes to a file."""
    
    def __init__(self, filename: str, rotate_size_mb: int = 10, 
                max_files: int = 5):
        """
        Initialize a file audit event sink.
        
        Args:
            filename: Path to the audit log file
            rotate_size_mb: Size in MB at which to rotate the file
            max_files: Maximum number of rotated files to keep
        """
        self.filename = filename
        self.rotate_size_bytes = rotate_size_mb * 1024 * 1024
        self.max_files = max_files
        self.file = None
        self.current_size = 0
        self._open_file()
    
    def _open_file(self) -> None:
        """Open the audit log file."""
        if os.path.exists(self.filename):
            self.current_size = os.path.getsize(self.filename)
        else:
            self.current_size = 0
        
        self.file = open(self.filename, 'a', encoding='utf-8')
    
    def _rotate_file(self) -> None:
        """Rotate the audit log file if needed."""
        if self.file:
            self.file.close()
        
        # Remove oldest file if we've reached max_files
        for i in range(self.max_files - 1, 0, -1):
            old_file = f"{self.filename}.{i}"
            new_file = f"{self.filename}.{i+1}"
            
            if os.path.exists(old_file):
                if i == self.max_files - 1:
                    # Remove oldest file
                    os.remove(old_file)
                else:
                    # Rename file to next number
                    os.rename(old_file, new_file)
        
        # Rename current file to .1
        if os.path.exists(self.filename):
            os.rename(self.filename, f"{self.filename}.1")
        
        self._open_file()
    
    def write_event(self, event: AuditEvent) -> bool:
        """Write an event to the file."""
        if not self.file:
            try:
                self._open_file()
            except Exception:
                return False
        
        try:
            event_json = event.to_json()
            self.file.write(event_json + '\n')
            self.file.flush()
            self.current_size += len(event_json) + 1
            
            if self.current_size >= self.rotate_size_bytes:
                self._rotate_file()
            
            return True
        except Exception:
            return False
    
    def flush(self) -> None:
        """Flush the file."""
        if self.file:
            self.file.flush()
    
    def close(self) -> None:
        """Close the file."""
        if self.file:
            self.file.close()
            self.file = None


class AuditLogger:
    """
    Central audit logger for the quantum database system.
    """
    
    def __init__(self):
        """Initialize the audit logger."""
        self.sinks: List[AuditEventSink] = []
        self.logs: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger(__name__)
    
    def add_sink(self, sink: AuditEventSink) -> None:
        """
        Add an audit event sink.
        
        Args:
            sink: The event sink to add
        """
        self.sinks.append(sink)
    
    def log_event(self, user_id: str, action: str, resource: str = None, 
                status: str = "success", details: Dict[str, Any] = None) -> str:
        """
        Log an audit event.
        
        Args:
            user_id: ID of the user who performed the action
            action: Description of the action
            resource: Optional resource that was affected
            status: Status of the action (success, failure, etc.)
            details: Additional details about the event
            
        Returns:
            ID of the logged event
        """
        # Create a simple event record
        event_id = str(uuid.uuid4())
        event = {
            "user_id": user_id,
            "action": action,
            "resource": resource,
            "status": status,
            "timestamp": time.time(),
            "details": details or {}
        }
        
        # Store in memory
        self.logs[event_id] = event
        
        # Log to all sinks if we have an AuditEvent class
        if 'AuditEvent' in globals():
            try:
                # Create a proper AuditEvent object if possible
                event_type = None
                # Try to map the action to an event type
                for et in AuditEventType:
                    if et.name.lower() == action.lower():
                        event_type = et
                        break
                
                # Use DATA_ACCESS as default if no matching type found
                if event_type is None:
                    event_type = AuditEventType.DATA_ACCESS
                
                audit_event = AuditEvent(
                    event_type=event_type,
                    user_id=user_id,
                    resource_id=resource
                )
                
                # Add details
                if details:
                    for key, value in details.items():
                        audit_event.add_detail(key, value)
                
                # Set success based on status
                audit_event.set_success(status.lower() == "success")
                
                # Try to get client information
                try:
                    hostname = socket.gethostname()
                    ip = socket.gethostbyname(hostname)
                    audit_event.set_source(ip, hostname)
                except:
                    # Don't fail if we can't get network info
                    pass
                
                # Write to all sinks
                for sink in self.sinks:
                    try:
                        sink.write_event(audit_event)
                    except Exception as e:
                        self.logger.error(f"Failed to write to sink: {e}")
            except Exception as e:
                self.logger.error(f"Failed to create audit event: {e}")
        
        return event_id
    
    def get_user_events(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all events for a specific user.
        
        Args:
            user_id: ID of the user
            
        Returns:
            List of events for the user
        """
        user_events = []
        for event_id, event in self.logs.items():
            if event["user_id"] == user_id:
                user_events.append(event)
        return user_events
    
    def get_resource_events(self, resource: str) -> List[Dict[str, Any]]:
        """
        Get all events for a specific resource.
        
        Args:
            resource: Resource identifier
            
        Returns:
            List of events for the resource
        """
        resource_events = []
        for event_id, event in self.logs.items():
            if event["resource"] == resource:
                resource_events.append(event)
        return resource_events
    
    def get_events_by_timerange(self, start_time: float, end_time: float) -> List[Dict[str, Any]]:
        """
        Get events within a specific time range.
        
        Args:
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            List of events within the time range
        """
        time_events = []
        for event_id, event in self.logs.items():
            if start_time <= event["timestamp"] <= end_time:
                time_events.append(event)
        return time_events
    
    def search_events(self, **filters) -> List[Dict[str, Any]]:
        """
        Search for events matching the given filters.
        
        Args:
            **filters: Keyword arguments for filtering events
            
        Returns:
            List of matching events
        """
        matching_events = []
        for event_id, event in self.logs.items():
            matches = True
            for key, value in filters.items():
                if key not in event or event[key] != value:
                    matches = False
                    break
            
            if matches:
                matching_events.append(event)
        
        return matching_events
    
    def clear_logs(self) -> None:
        """Clear all stored logs."""
        self.logs.clear()
        
    def flush_all_sinks(self) -> None:
        """Flush all sinks."""
        for sink in self.sinks:
            try:
                sink.flush()
            except Exception as e:
                self.logger.error(f"Failed to flush sink: {e}")