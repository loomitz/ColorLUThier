# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Bounded manual work executor for the disposable browser prototype."""

from __future__ import annotations

from collections.abc import Callable


_MAX_PENDING_JOBS = 16
_MAX_STEPS_PER_RUN = 1_000_000


class ManualExecutor:
    """Hold public engine work steps until a UI action advances them."""

    def __init__(self) -> None:
        self._steps: dict[int, Callable[[], bool]] = {}

    def submit(self, job_id: int, step: Callable[[], bool]) -> None:
        if job_id in self._steps:
            raise ValueError(f"job {job_id} is already pending")
        if len(self._steps) >= _MAX_PENDING_JOBS:
            raise ValueError("manual executor capacity is exhausted")
        self._steps[job_id] = step

    @property
    def pending_job_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self._steps))

    def step(self, job_id: int) -> bool:
        try:
            work_step = self._steps[job_id]
        except KeyError:
            raise ValueError(f"job {job_id} is not pending") from None
        terminal = work_step()
        if terminal:
            del self._steps[job_id]
        return terminal

    def run_to_terminal(self, job_id: int) -> None:
        for _ in range(_MAX_STEPS_PER_RUN):
            if self.step(job_id):
                return
        raise RuntimeError("manual job exceeded the bounded step limit")
