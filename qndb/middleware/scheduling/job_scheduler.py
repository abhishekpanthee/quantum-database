"""Job scheduler with multi-strategy scheduling, preemption, and quotas."""

import logging
import time
import threading
from datetime import datetime
from queue import PriorityQueue
from typing import Any, Callable, Dict, List, Optional

from qndb.middleware.scheduling.enums import (
    JobStatus, JobPriority, ScheduleStrategy,
)
from qndb.middleware.scheduling.job import QuantumJob
from qndb.middleware.scheduling.quota import ResourceQuota
from qndb.middleware.scheduling.monitor import QueueMonitor
from qndb.middleware.scheduling.adapters import ExternalSchedulerAdapter
from qndb.middleware.scheduling.resources import ResourceManager

logger = logging.getLogger(__name__)


class JobScheduler:
    """Scheduler for quantum database jobs."""

    def __init__(
        self,
        resource_manager: ResourceManager,
        strategy: ScheduleStrategy = ScheduleStrategy.PRIORITY,
        polling_interval: float = 0.5,
        max_queue_depth: int = 500,
    ) -> None:
        self.resource_manager = resource_manager
        self.strategy = strategy
        self.polling_interval = polling_interval

        self.job_queue: PriorityQueue = PriorityQueue()
        self.running_jobs: Dict[str, QuantumJob] = {}
        self.completed_jobs: Dict[str, QuantumJob] = {}

        self.user_usage: Dict[str, int] = {}
        self.quotas: Dict[str, ResourceQuota] = {}
        self.queue_monitor = QueueMonitor(max_queue_depth)
        self.completion_callbacks: Dict[str, Callable[[QuantumJob], None]] = {}

        self.running = False
        self.scheduler_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()
        self.external_adapter: Optional[ExternalSchedulerAdapter] = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.scheduler_thread.start()

    def stop(self) -> None:
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5.0)

    # -- quota management --------------------------------------------------

    def set_quota(self, user_id: str, max_qubits: int = 20,
                  max_concurrent_jobs: int = 3) -> None:
        self.quotas[user_id] = ResourceQuota(user_id, max_qubits, max_concurrent_jobs)

    # -- submit / cancel ---------------------------------------------------

    def submit_job(
        self,
        job: QuantumJob,
        completion_callback: Optional[Callable[[QuantumJob], None]] = None,
    ) -> str:
        status = self.queue_monitor.check(self.job_queue.qsize())
        if status == "reject":
            raise RuntimeError(f"Queue full ({self.queue_monitor.max_queue_depth}). Job rejected.")
        if status == "warn":
            logger.warning(
                "Queue approaching capacity (%d/%d)",
                self.job_queue.qsize(), self.queue_monitor.max_queue_depth,
            )

        if job.user_id and job.user_id in self.quotas:
            q = self.quotas[job.user_id]
            if not q.can_allocate(job.qubit_count):
                raise RuntimeError(f"Quota exceeded for user {job.user_id}")

        with self.lock:
            self.job_queue.put(job)
            if completion_callback:
                self.completion_callbacks[job.job_id] = completion_callback
            return job.job_id

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            if job_id in self.running_jobs:
                job = self.running_jobs[job_id]
                job.cancel()
                self._handle_job_completion(job)
                return True
            for job in list(self.job_queue.queue):
                if job.job_id == job_id:
                    job.cancel()
                    return True
            return False

    # -- preemption --------------------------------------------------------

    def preempt_job(self, job_id: str) -> bool:
        with self.lock:
            if job_id not in self.running_jobs:
                return False
            job = self.running_jobs[job_id]
            job.preempt()
            self._handle_job_completion(job)
            job.status = JobStatus.QUEUED
            job.priority = JobPriority.CRITICAL
            job.end_time = None
            self.job_queue.put(job)
            return True

    def preempt_for(self, incoming: QuantumJob) -> bool:
        with self.lock:
            if not self.running_jobs:
                return False
            victim = min(self.running_jobs.values(), key=lambda j: j.get_priority_score())
            if incoming.get_priority_score() <= victim.get_priority_score():
                return False
        return self.preempt_job(victim.job_id)

    # -- status queries ----------------------------------------------------

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            if job_id in self.running_jobs:
                job = self.running_jobs[job_id]
            elif job_id in self.completed_jobs:
                job = self.completed_jobs[job_id]
            else:
                for queued_job in list(self.job_queue.queue):
                    if queued_job.job_id == job_id:
                        job = queued_job
                        break
                else:
                    return None

            result: Dict[str, Any] = {
                "job_id": job.job_id,
                "status": job.status.name,
                "priority": job.priority.name,
                "user_id": job.user_id,
                "queued_time": job.queued_time.isoformat(),
                "wait_time": job.get_wait_time(),
                "qubit_count": job.qubit_count,
                "circuit_depth": job.circuit_depth,
            }
            if job.start_time:
                result["start_time"] = job.start_time.isoformat()
                result["runtime"] = job.get_runtime()
            if job.end_time:
                result["end_time"] = job.end_time.isoformat()
            if job.result is not None:
                result["has_result"] = True
            if job.error is not None:
                result["error"] = str(job.error)
            return result

    def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            if job_id in self.completed_jobs:
                job = self.completed_jobs[job_id]
                if job.status == JobStatus.COMPLETED and job.result is not None:
                    return {
                        "job_id": job.job_id,
                        "status": job.status.name,
                        "result": job.result,
                        "runtime": job.get_runtime(),
                    }
            return None

    def get_queue_info(self) -> Dict[str, Any]:
        with self.lock:
            queue_size = self.job_queue.qsize()
            running_count = len(self.running_jobs)
            completed_count = len(self.completed_jobs)
            priority_counts = {p.name: 0 for p in JobPriority}
            for job in list(self.job_queue.queue):
                priority_counts[job.priority.name] += 1
            resource_usage = {
                "total_qubits": self.resource_manager.total_qubits,
                "available_qubits": self.resource_manager.available_qubits,
                "used_qubits": self.resource_manager.total_qubits - self.resource_manager.available_qubits,
                "max_parallel_jobs": self.resource_manager.max_parallel_jobs,
                "running_jobs": self.resource_manager.running_jobs,
            }
            return {
                "queue_size": queue_size,
                "running_jobs": running_count,
                "completed_jobs": completed_count,
                "total_jobs": queue_size + running_count + completed_count,
                "priorities": priority_counts,
                "resources": resource_usage,
                "strategy": self.strategy.name,
                "rejected": self.queue_monitor.rejected_count,
            }

    # -- scheduler loop ----------------------------------------------------

    def _scheduler_loop(self) -> None:
        while self.running:
            try:
                self._process_queue()
                time.sleep(self.polling_interval)
            except Exception as e:
                logger.error("Error in scheduler loop: %s", e)

    def _process_queue(self) -> None:
        with self.lock:
            if self.job_queue.empty():
                return

            strategy_map = {
                ScheduleStrategy.FIFO: self._get_fifo_candidates,
                ScheduleStrategy.PRIORITY: self._get_priority_candidates,
                ScheduleStrategy.FAIR: self._get_fair_candidates,
                ScheduleStrategy.DEADLINE: self._get_deadline_candidates,
            }
            candidates = strategy_map.get(self.strategy, self._get_priority_candidates)()

            for job in candidates:
                if job.status == JobStatus.CANCELLED:
                    continue
                if job.user_id and job.user_id in self.quotas:
                    if not self.quotas[job.user_id].can_allocate(job.qubit_count):
                        continue
                if self.resource_manager.allocate(job):
                    job.start()
                    self.running_jobs[job.job_id] = job
                    if job.user_id:
                        self.user_usage[job.user_id] = self.user_usage.get(job.user_id, 0) + 1
                        if job.user_id in self.quotas:
                            self.quotas[job.user_id].allocate(job.qubit_count)
                    threading.Thread(target=self._run_job, args=(job,), daemon=True).start()

    # -- candidate helpers -------------------------------------------------

    def _drain_queue(self) -> List[QuantumJob]:
        jobs: List[QuantumJob] = []
        temp: PriorityQueue = PriorityQueue()
        while not self.job_queue.empty():
            j = self.job_queue.get()
            jobs.append(j)
            temp.put(j)
        while not temp.empty():
            self.job_queue.put(temp.get())
        return jobs

    def _get_fifo_candidates(self) -> List[QuantumJob]:
        return sorted(self._drain_queue(), key=lambda j: j.queued_time)

    def _get_priority_candidates(self) -> List[QuantumJob]:
        return sorted(self._drain_queue(), key=lambda j: j.get_priority_score(), reverse=True)

    def _get_fair_candidates(self) -> List[QuantumJob]:
        jobs = self._get_priority_candidates()
        return sorted(jobs, key=lambda j: (
            self.user_usage.get(j.user_id, 0),
            -j.get_priority_score(),
        ))

    def _get_deadline_candidates(self) -> List[QuantumJob]:
        jobs = self._get_priority_candidates()

        def key(j: QuantumJob):
            if j.deadline is None:
                return (datetime.max, -j.get_priority_score())
            return ((j.deadline - datetime.now()).total_seconds(), -j.get_priority_score())

        return sorted(jobs, key=key)

    # -- job execution -----------------------------------------------------

    def _run_job(self, job: QuantumJob) -> None:
        try:
            time.sleep(min(job.estimated_runtime / 10, 2))
            result = {
                "executed": True,
                "measurements": {"0000": 0.12, "0001": 0.08, "0010": 0.25, "0011": 0.55},
                "success_probability": 0.92,
            }
            job.complete(result)
        except Exception as e:
            logger.error("Error executing job %s: %s", job.job_id, e)
            job.fail(e)
        finally:
            self._handle_job_completion(job)

    def _handle_job_completion(self, job: QuantumJob) -> None:
        with self.lock:
            if job.job_id in self.running_jobs:
                del self.running_jobs[job.job_id]
            self.completed_jobs[job.job_id] = job
            self.resource_manager.release(job)
            if job.user_id:
                if job.user_id in self.user_usage:
                    self.user_usage[job.user_id] = max(0, self.user_usage[job.user_id] - 1)
                if job.user_id in self.quotas:
                    self.quotas[job.user_id].release(job.qubit_count)
            if job.job_id in self.completion_callbacks:
                try:
                    self.completion_callbacks[job.job_id](job)
                except Exception as e:
                    logger.error("Completion callback error for %s: %s", job.job_id, e)
                finally:
                    del self.completion_callbacks[job.job_id]
