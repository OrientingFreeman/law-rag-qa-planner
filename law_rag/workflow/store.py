from __future__ import annotations

from threading import RLock

from .models import AgentRun


class InMemoryTraceStore:
    """Process-local bounded run store; suitable for the synchronous demo API."""

    def __init__(self, max_runs: int = 200) -> None:
        self.max_runs = max_runs
        self._runs: dict[str, AgentRun] = {}
        self._lock = RLock()

    def save(self, run: AgentRun) -> None:
        with self._lock:
            self._runs[run.run_id] = run
            while len(self._runs) > self.max_runs:
                self._runs.pop(next(iter(self._runs)))

    def get(self, run_id: str) -> AgentRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self, limit: int = 20) -> list[AgentRun]:
        with self._lock:
            return list(reversed(list(self._runs.values())))[:limit]
