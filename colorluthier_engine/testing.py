"""Deterministic execution adapters for engine acceptance tests."""

from __future__ import annotations

from collections.abc import Iterable

from .execution import WorkStep


class ControlledExecutor:
    """Hold bounded jobs until a test explicitly advances them."""

    def __init__(self, capacity: int = 16) -> None:
        self._capacity = _positive_integer(capacity, name="capacity")
        self._steps: dict[int, WorkStep] = {}

    def submit(self, job_id: int, step: WorkStep) -> None:
        if job_id in self._steps:
            raise ValueError(f"job {job_id} is already pending")
        if len(self._steps) >= self._capacity:
            raise ValueError(
                f"executor capacity of {self._capacity} pending jobs is exhausted"
            )
        self._steps[job_id] = step

    @property
    def pending_job_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._steps))

    def run_next(self, job_id: int) -> bool:
        step = self._pending_step(job_id)
        terminal = step()
        if terminal:
            del self._steps[job_id]
        return terminal

    def run_steps(self, job_id: int, count: int) -> bool:
        step_count = _positive_integer(count, name="count")
        for _ in range(step_count):
            if self.run_next(job_id):
                return True
        return False

    def run_all(self, job_id: int, max_steps: int = 1_000_000) -> None:
        step_limit = _positive_integer(max_steps, name="max_steps")
        for _ in range(step_limit):
            if self.run_next(job_id):
                return
        raise RuntimeError(
            f"job {job_id} did not terminate within {step_limit} steps"
        )

    def run_in_order(self, job_ids: Iterable[int]) -> None:
        for job_id in job_ids:
            self.run_all(job_id)

    def _pending_step(self, job_id: int) -> WorkStep:
        try:
            return self._steps[job_id]
        except KeyError:
            raise ValueError(f"job {job_id} is not pending") from None


def _positive_integer(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
