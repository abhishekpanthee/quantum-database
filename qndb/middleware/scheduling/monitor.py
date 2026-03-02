"""Queue monitor with backpressure."""


class QueueMonitor:
    """Monitors queue depth and applies backpressure when needed."""

    def __init__(
        self,
        max_queue_depth: int = 500,
        warn_threshold: float = 0.8,
    ) -> None:
        self.max_queue_depth = max_queue_depth
        self.warn_threshold = warn_threshold
        self._rejected = 0

    def check(self, current_depth: int) -> str:
        """Return ``'accept'``, ``'warn'``, or ``'reject'``."""
        if current_depth >= self.max_queue_depth:
            self._rejected += 1
            return "reject"
        if current_depth >= int(self.max_queue_depth * self.warn_threshold):
            return "warn"
        return "accept"

    @property
    def rejected_count(self) -> int:
        return self._rejected
