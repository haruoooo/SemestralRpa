"""Runs the three flows on their schedules in a single process (docs/processDesign.md, section Gatilho)."""

import logging
from collections.abc import Callable

from apscheduler.schedulers.blocking import BlockingScheduler

from src.infrastructure.timeProvider import SAO_PAULO

_log = logging.getLogger("foraDoPicoRpa.scheduler")


def _safe(name: str, job: Callable[[], int]) -> Callable[[], None]:
    def wrapper() -> None:
        try:
            exitCode = job()
            _log.info("Job %s finished with exit code %s", name, exitCode, extra=_extra(name, "JobFinished", {"exitCode": exitCode}))
        except Exception:  # A crashing flow must never stop the scheduler (EX11)
            _log.exception("Job %s crashed; the scheduler keeps running", name, extra=_extra(name, "JobCrashed"))

    return wrapper


def _extra(name: str, event: str, data: dict | None = None) -> dict:
    return {"runId": "scheduler", "flow": name, "step": "-", "event": event, "itemRef": None, "data": data}


def buildScheduler(jobs: dict[str, tuple[Callable[[], int], int]]) -> BlockingScheduler:
    """jobs: name -> (callable returning an exit code, interval in minutes)."""
    scheduler = BlockingScheduler(timezone=SAO_PAULO)
    for name, (job, minutes) in jobs.items():
        # max_instances=1: a slow run is never overlapped by the next one; coalesce: missed runs collapse into one
        scheduler.add_job(_safe(name, job), "interval", minutes=minutes, id=name, max_instances=1, coalesce=True, next_run_time=None)
    return scheduler
