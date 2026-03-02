"""Scheduler enumerations."""

from enum import Enum, auto


class JobStatus(Enum):
    QUEUED = auto()
    SCHEDULED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()
    PREEMPTED = auto()


class JobPriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class ScheduleStrategy(Enum):
    FIFO = auto()
    PRIORITY = auto()
    FAIR = auto()
    DEADLINE = auto()
