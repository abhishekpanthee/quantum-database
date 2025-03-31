"""
Job Scheduler

This module handles the scheduling of quantum database jobs,
managing resource allocation, prioritization, and load balancing.
"""

import logging
import time
import heapq
import threading
from typing import Dict, List, Tuple, Callable, Any, Optional
from enum import Enum, auto
from queue import PriorityQueue
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    """Enumeration of possible job statuses."""
    QUEUED = auto()
    SCHEDULED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class JobPriority(Enum):
    """Enumeration of job priorities."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class ScheduleStrategy(Enum):
    """Enumeration of scheduling strategies."""
    FIFO = auto()  # First In First Out
    PRIORITY = auto()  # Priority-based
    FAIR = auto()  # Fair sharing
    DEADLINE = auto()  # Deadline-based


class QuantumJob:
    """
    Represents a quantum database job to be scheduled.
    """
    
    def __init__(self, job_id: str, query: Dict, priority: JobPriority = JobPriority.NORMAL, 
                 deadline: Optional[datetime] = None, user_id: Optional[str] = None,
                 estimated_runtime: float = 60.0):
        """
        Initialize a quantum job.

        Args:
            job_id: Unique identifier for the job
            query: The query to execute
            priority: Job priority level
            deadline: Deadline for job completion
            user_id: ID of the user who submitted the job
            estimated_runtime: Estimated runtime in seconds
        """
        self.job_id = job_id
        self.query = query
        self.priority = priority
        self.deadline = deadline
        self.user_id = user_id
        self.estimated_runtime = estimated_runtime
        
        self.status = JobStatus.QUEUED
        self.queued_time = datetime.now()
        self.start_time = None
        self.end_time = None
        self.result = None
        self.error = None
        
        # Resource requirements
        self.qubit_count = self._estimate_qubit_count()
        self.circuit_depth = self._estimate_circuit_depth()
        
        logger.debug(f"Created job {job_id} with priority {priority.name}")

    def _estimate_qubit_count(self) -> int:
        """
        Estimate the number of qubits required for this job.
        
        Returns:
            Estimated qubit count
        """
        # Placeholder implementation - would normally analyze the query
        # to determine resource requirements
        
        # Extract from query if available
        if 'qubit_allocation' in self.query and 'total_qubits' in self.query['qubit_allocation']:
            return self.query['qubit_allocation']['total_qubits']
        
        # Default estimate
        return 10

    def _estimate_circuit_depth(self) -> int:
        """
        Estimate the circuit depth for this job.
        
        Returns:
            Estimated circuit depth
        """
        # Extract from query if available
        if 'circuits' in self.query and self.query['circuits']:
            depths = [circuit.get('depth', 100) for circuit in self.query['circuits']]
            return max(depths)
        
        # Default estimate
        return 100

    def start(self) -> None:
        """Mark the job as running and record the start time."""
        self.status = JobStatus.RUNNING
        self.start_time = datetime.now()
        logger.info(f"Job {self.job_id} started at {self.start_time}")

    def complete(self, result: Any) -> None:
        """
        Mark the job as completed and store the result.
        
        Args:
            result: The result of the job
        """
        self.status = JobStatus.COMPLETED
        self.end_time = datetime.now()
        self.result = result
        logger.info(f"Job {self.job_id} completed at {self.end_time}")

    def fail(self, error: Exception) -> None:
        """
        Mark the job as failed and store the error.
        
        Args:
            error: The exception that caused the failure
        """
        self.status = JobStatus.FAILED
        self.end_time = datetime.now()
        self.error = error
        logger.error(f"Job {self.job_id} failed at {self.end_time}: {str(error)}")

    def cancel(self) -> None:
        """Mark the job as cancelled."""
        self.status = JobStatus.CANCELLED
        self.end_time = datetime.now()
        logger.info(f"Job {self.job_id} cancelled at {self.end_time}")

    def get_runtime(self) -> float:
        """
        Calculate the actual runtime of the job.
        
        Returns:
            Runtime in seconds, or 0 if the job hasn't completed
        """
        if self.start_time is None:
            return 0
            
        end = self.end_time or datetime.now()
        return (end - self.start_time).total_seconds()

    def get_wait_time(self) -> float:
        """
        Calculate the wait time of the job.
        
        Returns:
            Wait time in seconds
        """
        start = self.start_time or datetime.now()
        return (start - self.queued_time).total_seconds()

    def is_deadline_approaching(self, threshold_seconds: int = 60) -> bool:
        """
        Check if the job's deadline is approaching.
        
        Args:
            threshold_seconds: Number of seconds that defines "approaching"
            
        Returns:
            True if the deadline is within the threshold, False otherwise
        """
        if self.deadline is None:
            return False
            
        time_left = (self.deadline - datetime.now()).total_seconds()
        return 0 < time_left < threshold_seconds

    def get_priority_score(self) -> float:
        """
        Calculate a numerical priority score for scheduling.
        
        Returns:
            Priority score (higher is more urgent)
        """
        base_score = self.priority.value * 1000
        
        # Add deadline urgency
        if self.deadline:
            time_left = max(0, (self.deadline - datetime.now()).total_seconds())
            deadline_factor = 1000 / (time_left + 1)  # Avoid division by zero
            base_score += deadline_factor
        
        # Add wait time factor
        wait_time = self.get_wait_time()
        wait_factor = min(wait_time / 10, 100)  # Cap at 100
        base_score += wait_factor
        
        return base_score

    def __lt__(self, other):
        """
        Comparison operator for priority queue.
        
        Args:
            other: Another QuantumJob to compare with
            
        Returns:
            True if this job has higher priority than the other
        """
        return self.get_priority_score() > other.get_priority_score()


class ResourceManager:
    """
    Manages quantum computing resources for the scheduler.
    """
    
    def __init__(self, total_qubits: int = 50, max_parallel_jobs: int = 5):
        """
        Initialize the resource manager.
        
        Args:
            total_qubits: Total number of qubits available
            max_parallel_jobs: Maximum number of jobs that can run in parallel
        """
        self.total_qubits = total_qubits
        self.max_parallel_jobs = max_parallel_jobs
        self.available_qubits = total_qubits
        self.running_jobs = 0
        self.lock = threading.Lock()
        logger.info(f"Resource manager initialized with {total_qubits} qubits and {max_parallel_jobs} parallel jobs")

    def allocate(self, job: QuantumJob) -> bool:
        """
        Try to allocate resources for a job.
        
        Args:
            job: The job requesting resources
            
        Returns:
            True if resources were allocated, False otherwise
        """
        with self.lock:
            if (self.available_qubits >= job.qubit_count and 
                    self.running_jobs < self.max_parallel_jobs):
                self.available_qubits -= job.qubit_count
                self.running_jobs += 1
                logger.debug(f"Allocated {job.qubit_count} qubits for job {job.job_id}")
                return True
            return False

    def release(self, job: QuantumJob) -> None:
        """
        Release resources allocated to a job.
        
        Args:
            job: The job releasing resources
        """
        with self.lock:
            self.available_qubits += job.qubit_count
            self.running_jobs -= 1
            logger.debug(f"Released {job.qubit_count} qubits from job {job.job_id}")

    def can_allocate(self, job: QuantumJob) -> bool:
        """
        Check if resources can be allocated for a job without actually allocating.
        
        Args:
            job: The job to check
            
        Returns:
            True if resources could be allocated, False otherwise
        """
        with self.lock:
            return (self.available_qubits >= job.qubit_count and 
                    self.running_jobs < self.max_parallel_jobs)


class JobScheduler:
    """
    Scheduler for quantum database jobs.
    """
    
    def __init__(self, resource_manager: ResourceManager, 
                 strategy: ScheduleStrategy = ScheduleStrategy.PRIORITY,
                 polling_interval: float = 0.5):
        """
        Initialize the job scheduler.
        
        Args:
            resource_manager: Resource manager to use for resource allocation
            strategy: Scheduling strategy to use
            polling_interval: How often to check for jobs to run (seconds)
        """
        self.resource_manager = resource_manager
        self.strategy = strategy
        self.polling_interval = polling_interval
        
        # Job queues
        self.job_queue = PriorityQueue()
        self.running_jobs = {}  # job_id -> QuantumJob
        self.completed_jobs = {}  # job_id -> QuantumJob
        
        # User fairness tracking
        self.user_usage = {}  # user_id -> count of running jobs
        
        # Callback registry for job completion
        self.completion_callbacks = {}  # job_id -> callback function
        
        # Thread control
        self.running = False
        self.scheduler_thread = None
        self.lock = threading.Lock()
        
        logger.info(f"Job scheduler initialized with {strategy.name} strategy")

    def start(self) -> None:
        """Start the scheduler thread."""
        if self.running:
            return
            
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        logger.info("Job scheduler started")

    def stop(self) -> None:
        """Stop the scheduler thread."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5.0)
        logger.info("Job scheduler stopped")

    def submit_job(self, job: QuantumJob, 
                  completion_callback: Optional[Callable[[QuantumJob], None]] = None) -> str:
        """
        Submit a job to the scheduler.
        
        Args:
            job: The job to submit
            completion_callback: Function to call when the job completes
            
        Returns:
            Job ID
        """
        with self.lock:
            self.job_queue.put(job)
            
            if completion_callback:
                self.completion_callbacks[job.job_id] = completion_callback
                
            logger.info(f"Job {job.job_id} submitted with priority {job.priority.name}")
            return job.job_id

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.
        
        Args:
            job_id: ID of the job to cancel
            
        Returns:
            True if the job was cancelled, False if it couldn't be found
            or was already completed
        """
        with self.lock:
            # Check if job is running
            if job_id in self.running_jobs:
                job = self.running_jobs[job_id]
                job.cancel()
                self._handle_job_completion(job)
                return True
                
            # If the job is in the queue, we can't easily remove it from a PriorityQueue
            # Instead, we'll mark it for cancellation when it's dequeued
            for job in list(self.job_queue.queue):
                if job.job_id == job_id:
                    job.cancel()
                    return True
            
            # Check completed jobs
            if job_id in self.completed_jobs:
                # Cannot cancel completed jobs
                return False
                
            # Job not found
            logger.warning(f"Attempt to cancel unknown job {job_id}")
            return False

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """
        Get the status of a job.
        
        Args:
            job_id: ID of the job to query
            
        Returns:
            Dictionary with job status information, or None if not found
        """
        with self.lock:
            # Check running jobs
            if job_id in self.running_jobs:
                job = self.running_jobs[job_id]
            # Check completed jobs
            elif job_id in self.completed_jobs:
                job = self.completed_jobs[job_id]
            # Check queue
            else:
                for queued_job in list(self.job_queue.queue):
                    if queued_job.job_id == job_id:
                        job = queued_job
                        break
                else:
                    # Job not found
                    return None
            
            # Build status dict
            status = {
                'job_id': job.job_id,
                'status': job.status.name,
                'priority': job.priority.name,
                'user_id': job.user_id,
                'queued_time': job.queued_time.isoformat(),
                'wait_time': job.get_wait_time(),
                'qubit_count': job.qubit_count,
                'circuit_depth': job.circuit_depth
            }
            
            if job.start_time:
                status['start_time'] = job.start_time.isoformat()
                status['runtime'] = job.get_runtime()
                
            if job.end_time:
                status['end_time'] = job.end_time.isoformat()
                
            if job.result is not None:
                status['has_result'] = True
                
            if job.error is not None:
                status['error'] = str(job.error)
                
            return status

    def get_job_result(self, job_id: str) -> Optional[Dict]:
        """
        Get the result of a completed job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Dictionary with job result, or None if not completed or not found
        """
        with self.lock:
            if job_id in self.completed_jobs:
                job = self.completed_jobs[job_id]
                if job.status == JobStatus.COMPLETED and job.result is not None:
                    return {
                        'job_id': job.job_id,
                        'status': job.status.name,
                        'result': job.result,
                        'runtime': job.get_runtime()
                    }
            return None

    def get_queue_info(self) -> Dict:
        """
        Get information about the current job queue.
        
        Returns:
            Dictionary with queue statistics
        """
        with self.lock:
            queue_size = self.job_queue.qsize()
            running_count = len(self.running_jobs)
            completed_count = len(self.completed_jobs)
            
            # Count jobs by priority
            priority_counts = {p.name: 0 for p in JobPriority}
            for job in list(self.job_queue.queue):
                priority_counts[job.priority.name] += 1
                
            # Resource usage
            resource_usage = {
                'total_qubits': self.resource_manager.total_qubits,
                'available_qubits': self.resource_manager.available_qubits,
                'used_qubits': self.resource_manager.total_qubits - self.resource_manager.available_qubits,
                'max_parallel_jobs': self.resource_manager.max_parallel_jobs,
                'running_jobs': self.resource_manager.running_jobs
            }
            
            return {
                'queue_size': queue_size,
                'running_jobs': running_count,
                'completed_jobs': completed_count,
                'total_jobs': queue_size + running_count + completed_count,
                'priorities': priority_counts,
                'resources': resource_usage,
                'strategy': self.strategy.name
            }

    def _scheduler_loop(self) -> None:
        """Main scheduler loop that processes the job queue."""
        while self.running:
            try:
                self._process_queue()
                time.sleep(self.polling_interval)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")

    def _process_queue(self) -> None:
        """Process the job queue according to the scheduling strategy."""
        with self.lock:
            if self.job_queue.empty():
                return

            # Get candidate jobs based on strategy
            if self.strategy == ScheduleStrategy.FIFO:
                candidates = self._get_fifo_candidates()
            elif self.strategy == ScheduleStrategy.PRIORITY:
                candidates = self._get_priority_candidates()
            elif self.strategy == ScheduleStrategy.FAIR:
                candidates = self._get_fair_candidates()
            elif self.strategy == ScheduleStrategy.DEADLINE:
                candidates = self._get_deadline_candidates()
            else:
                candidates = self._get_priority_candidates()  # Default

            # Try to schedule candidates
            for job in candidates:
                if job.status == JobStatus.CANCELLED:
                    # Remove cancelled jobs
                    continue
                
                if self.resource_manager.allocate(job):
                    # Remove from queue
                    job.start()
                    self.running_jobs[job.job_id] = job
                    
                    # Update user usage
                    if job.user_id:
                        self.user_usage[job.user_id] = self.user_usage.get(job.user_id, 0) + 1
                    
                    # Start job in a separate thread
                    threading.Thread(target=self._run_job, args=(job,)).start()

    def _get_fifo_candidates(self) -> List[QuantumJob]:
        """
        Get jobs in FIFO order.
        
        Returns:
            List of jobs in queue order
        """
        jobs = []
        temp_queue = PriorityQueue()
        
        # Get all jobs from queue
        while not self.job_queue.empty():
            job = self.job_queue.get()
            jobs.append(job)
            temp_queue.put(job)
            
        # Restore queue
        while not temp_queue.empty():
            self.job_queue.put(temp_queue.get())
            
        return sorted(jobs, key=lambda j: j.queued_time)

    def _get_priority_candidates(self) -> List[QuantumJob]:
        """
        Get jobs in priority order.
        
        Returns:
            List of jobs in priority order
        """
        jobs = []
        temp_queue = PriorityQueue()
        
        # Get all jobs from queue
        while not self.job_queue.empty():
            job = self.job_queue.get()
            jobs.append(job)
            temp_queue.put(job)
            
        # Restore queue
        while not temp_queue.empty():
            self.job_queue.put(temp_queue.get())
            
        return sorted(jobs, key=lambda j: j.get_priority_score(), reverse=True)

    def _get_fair_candidates(self) -> List[QuantumJob]:
        """
        Get jobs ensuring fairness among users.
        
        Returns:
            List of jobs respecting user fairness
        """
        jobs = self._get_priority_candidates()
        
        # Sort by priority first, then by user usage
        return sorted(jobs, key=lambda j: (
            self.user_usage.get(j.user_id, 0),  # Users with fewer running jobs first
            -j.get_priority_score()  # Then by priority score (negative for descending)
        ))

    def _get_deadline_candidates(self) -> List[QuantumJob]:
        """
        Get jobs prioritizing those with approaching deadlines.
        
        Returns:
            List of jobs prioritized by deadline
        """
        jobs = self._get_priority_candidates()
        
        # Sort by deadline first (None deadlines last), then by priority
        def deadline_key(job):
            if job.deadline is None:
                return (datetime.max, -job.get_priority_score())
            time_left = (job.deadline - datetime.now()).total_seconds()
            return (time_left, -job.get_priority_score())
            
        return sorted(jobs, key=deadline_key)

    def _run_job(self, job: QuantumJob) -> None:
        """
        Run a job and handle its completion.
        
        Args:
            job: The job to run
        """
        try:
            # Simulate job execution
            logger.info(f"Running job {job.job_id}")
            
            # In a real system, this would execute the quantum circuit
            # and get the results
            time.sleep(min(job.estimated_runtime / 10, 2))  # Simulate execution time
            
            # Generate a sample result
            result = {
                "executed": True,
                "measurements": {"0000": 0.12, "0001": 0.08, "0010": 0.25, "0011": 0.55},
                "success_probability": 0.92
            }
            
            job.complete(result)
            
        except Exception as e:
            logger.error(f"Error executing job {job.job_id}: {str(e)}")
            job.fail(e)
            
        finally:
            self._handle_job_completion(job)

    def _handle_job_completion(self, job: QuantumJob) -> None:
        """
        Handle job completion, releasing resources and invoking callbacks.
        
        Args:
            job: The completed job
        """
        with self.lock:
            # Move from running to completed
            if job.job_id in self.running_jobs:
                del self.running_jobs[job.job_id]
            
            self.completed_jobs[job.job_id] = job
            
            # Release resources
            self.resource_manager.release(job)
            
            # Update user usage
            if job.user_id and job.user_id in self.user_usage:
                self.user_usage[job.user_id] = max(0, self.user_usage[job.user_id] - 1)
            
            # Invoke completion callback
            if job.job_id in self.completion_callbacks:
                try:
                    callback = self.completion_callbacks[job.job_id]
                    callback(job)
                except Exception as e:
                    logger.error(f"Error in completion callback for job {job.job_id}: {str(e)}")
                finally:
                    del self.completion_callbacks[job.job_id]