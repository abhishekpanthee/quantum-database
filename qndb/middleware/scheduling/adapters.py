"""External scheduler adapters (Kubernetes, Slurm)."""

import logging
from typing import Optional

from qndb.middleware.scheduling.job import QuantumJob

logger = logging.getLogger(__name__)


class ExternalSchedulerAdapter:
    """Adapter base for external schedulers."""

    def submit(self, job: QuantumJob) -> Optional[str]:
        raise NotImplementedError

    def cancel(self, external_id: str) -> bool:
        raise NotImplementedError

    def status(self, external_id: str) -> Optional[str]:
        raise NotImplementedError


class KubernetesAdapter(ExternalSchedulerAdapter):
    """Kubernetes-based job scheduling adapter."""

    def __init__(self, namespace: str = "quantum-jobs") -> None:
        self.namespace = namespace
        logger.info("Kubernetes adapter initialised (namespace=%s)", namespace)

    def submit(self, job: QuantumJob) -> Optional[str]:
        logger.info("K8s: submitting job %s", job.job_id)
        return f"k8s-{job.job_id}"

    def cancel(self, external_id: str) -> bool:
        logger.info("K8s: cancelling %s", external_id)
        return True

    def status(self, external_id: str) -> Optional[str]:
        return "PENDING"


class SlurmAdapter(ExternalSchedulerAdapter):
    """Slurm-based job scheduling adapter."""

    def __init__(self, partition: str = "quantum") -> None:
        self.partition = partition
        logger.info("Slurm adapter initialised (partition=%s)", partition)

    def submit(self, job: QuantumJob) -> Optional[str]:
        logger.info("Slurm: submitting job %s", job.job_id)
        return f"slurm-{job.job_id}"

    def cancel(self, external_id: str) -> bool:
        logger.info("Slurm: cancelling %s", external_id)
        return True

    def status(self, external_id: str) -> Optional[str]:
        return "PENDING"
