"""In-container scheduler: runs the daily pipeline at a fixed local time, every day.

Runs `poll`, `extract` and `commit` in order, logs the result, and never raises: a failed poll
must not stop the commit, since the commitment log is the record and a missed day is a hole in
it. Time of day and time zone come from RASAD_PIPELINE_TIME (HH:MM, default 06:00) and TZ.
"""

from __future__ import annotations

import os
import time
import traceback
from datetime import datetime, timedelta

from ..db import init_db
from . import run as pipeline


def _next_run(now: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def run_once() -> None:
    for name, fn in (("poll", pipeline.poll), ("extract", pipeline.extract), ("commit", pipeline.commit)):
        try:
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {name}: {fn()}", flush=True)
        except Exception:  # noqa: BLE001
            print(f"[{datetime.now().isoformat(timespec='seconds')}] {name} failed:\n{traceback.format_exc()}", flush=True)


def main() -> None:
    init_db()
    at = os.getenv("RASAD_PIPELINE_TIME", "06:00")
    if os.getenv("RASAD_PIPELINE_RUN_ON_START", "false").lower() in ("1", "true", "yes"):
        run_once()
    while True:
        nxt = _next_run(datetime.now(), at)
        print(f"next pipeline run at {nxt.isoformat(timespec='minutes')} ({os.getenv('TZ', 'container time')})", flush=True)
        time.sleep(max(1.0, (nxt - datetime.now()).total_seconds()))
        run_once()


if __name__ == "__main__":
    main()
