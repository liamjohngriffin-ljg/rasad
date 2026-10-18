"""In-container scheduler.

Two cadences:
  * every RASAD_POLL_INTERVAL_HOURS (default 4): poll the feeds and extract, so UKMTO warnings,
    MSCIO alerts and wire stories reach the queue and the alert inbox the same day
  * once a day at RASAD_PIPELINE_TIME (HH:MM local, default 06:00): poll, extract, commit the
    day's forecasts to the chain, raise alerts and send the digest

Nothing here raises: a failed poll must not stop the commit, since the commitment log is the
record and a missed day is a hole in it. Each step's result or traceback is printed for the
container log.
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


def _step(name: str, fn) -> None:
    try:
        print(f"[{datetime.now().isoformat(timespec='seconds')}] {name}: {fn()}", flush=True)
    except Exception:  # noqa: BLE001
        print(f"[{datetime.now().isoformat(timespec='seconds')}] {name} failed:\n{traceback.format_exc()}", flush=True)


def run_once() -> None:
    """The full daily pipeline."""
    for name, fn in (("poll", pipeline.poll), ("extract", pipeline.extract), ("commit", pipeline.commit), ("digest", pipeline.digest)):
        _step(name, fn)


def poll_once() -> None:
    for name, fn in (("poll", pipeline.poll), ("extract", pipeline.extract)):
        _step(name, fn)


def main() -> None:
    init_db()
    at = os.getenv("RASAD_PIPELINE_TIME", "06:00")
    interval = float(os.getenv("RASAD_POLL_INTERVAL_HOURS", "4"))
    if os.getenv("RASAD_PIPELINE_RUN_ON_START", "false").lower() in ("1", "true", "yes"):
        run_once()
    next_poll = datetime.now() + timedelta(hours=interval) if interval > 0 else None
    while True:
        now = datetime.now()
        next_daily = _next_run(now, at)
        target = min([t for t in (next_daily, next_poll) if t is not None])
        print(f"next daily run at {next_daily.isoformat(timespec='minutes')}; next poll at {next_poll.isoformat(timespec='minutes') if next_poll else 'off'} ({os.getenv('TZ', 'container time')})", flush=True)
        time.sleep(max(1.0, (target - datetime.now()).total_seconds()))
        if target == next_daily:
            run_once()
            if next_poll is not None:
                next_poll = datetime.now() + timedelta(hours=interval)
        else:
            poll_once()
            next_poll = datetime.now() + timedelta(hours=interval)


if __name__ == "__main__":
    main()
