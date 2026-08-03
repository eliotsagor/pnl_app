"""In-memory background job registry for TradeSteward fetch/backfill.

Single-user local app: only one TradeSteward-touching job may run at a time
(there's only one real Playwright/browser session that makes sense anyway).
Job state lives in memory and is lost on backend restart -- an acceptable
simplification for a personal tool with no multi-user/durability needs.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["queued", "awaiting_login", "running", "done", "error", "cancelled"]


@dataclass
class Job:
    id: str
    kind: str
    status: JobStatus = "queued"
    progress: dict[str, Any] = field(default_factory=dict)
    log: list[str] = field(default_factory=list)
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": self.progress,
            "log": self.log,
            "result": self.result,
            "error": self.error,
        }


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_active_kind: str | None = None  # non-None while a TradeSteward job is running


def create_job(kind: str) -> Job:
    with _lock:
        global _active_kind
        if _active_kind is not None:
            raise RuntimeError(f"A TradeSteward job ({_active_kind}) is already running.")
        job = Job(id=str(uuid.uuid4()), kind=kind)
        _jobs[job.id] = job
        _active_kind = kind
        return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def update_job(job_id: str, **fields):
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        for k, v in fields.items():
            setattr(job, k, v)


def append_log(job_id: str, line: str):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            job.log.append(line)


def finish_job(job_id: str):
    """Release the single-job lock once a job reaches a terminal status."""
    with _lock:
        global _active_kind
        _active_kind = None
