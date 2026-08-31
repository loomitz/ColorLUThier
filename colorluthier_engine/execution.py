"""Framework-neutral execution seam for headless engine jobs."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Protocol, TypeAlias


WorkStep: TypeAlias = Callable[[], bool]
"""Advance one job once and return whether the job is terminal."""


class WorkExecutor(Protocol):
    """Schedule incremental work without exposing a concurrency framework.

    One executor instance belongs to one ``ColorDocument``. Implementations
    must serialize its work-step callbacks; ``submit`` may execute inline.
    """

    def submit(self, job_id: int, step: WorkStep) -> None:
        """Submit a uniquely identified job for execution."""


class InlineExecutor:
    """Run submitted jobs synchronously to completion in FIFO step order.

    The explicit drain guard permits a running step to submit another job
    without recursive execution. Work-step exceptions are intentionally not
    translated here; the engine owns their domain-level interpretation.
    """

    def __init__(self) -> None:
        self._queue: deque[tuple[int, WorkStep]] = deque()
        self._active_job_ids: set[int] = set()
        self._draining = False

    def submit(self, job_id: int, step: WorkStep) -> None:
        if job_id in self._active_job_ids:
            raise ValueError(f"job {job_id} is already active")

        self._active_job_ids.add(job_id)
        self._queue.append((job_id, step))

        if self._draining:
            return

        self._draining = True
        try:
            while self._queue:
                active_job_id, active_step = self._queue.popleft()
                try:
                    terminal = active_step()
                except BaseException:
                    self._active_job_ids.remove(active_job_id)
                    raise

                if terminal:
                    self._active_job_ids.remove(active_job_id)
                else:
                    self._queue.append((active_job_id, active_step))
        finally:
            self._draining = False
