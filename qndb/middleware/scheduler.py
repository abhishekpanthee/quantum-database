"""
Job Scheduler — backward-compatibility shim.

New code should import from :mod:`qndb.middleware.scheduling` instead.
"""

from qndb.middleware.scheduling.enums import (      # noqa: F401
    JobStatus, JobPriority, ScheduleStrategy,
)
from qndb.middleware.scheduling.job import QuantumJob              # noqa: F401
from qndb.middleware.scheduling.quota import ResourceQuota         # noqa: F401
from qndb.middleware.scheduling.monitor import QueueMonitor        # noqa: F401
from qndb.middleware.scheduling.adapters import (   # noqa: F401
    ExternalSchedulerAdapter, KubernetesAdapter, SlurmAdapter,
)
from qndb.middleware.scheduling.resources import ResourceManager   # noqa: F401
from qndb.middleware.scheduling.job_scheduler import JobScheduler  # noqa: F401

__all__ = [
    "JobStatus", "JobPriority", "ScheduleStrategy",
    "QuantumJob", "ResourceQuota", "QueueMonitor",
    "ExternalSchedulerAdapter", "KubernetesAdapter", "SlurmAdapter",
    "ResourceManager", "JobScheduler",
]
