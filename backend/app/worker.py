"""Background worker: python -m app.worker

Runs queued analysis jobs and the overdue-task reminder sweep. Safe to run several copies: jobs are claimed with a
lease, and reminders are idempotent. Use ANALYSIS_WORKER=external on the web process when this runs separately."""
import logging
import signal
import threading

from .services.jobs import worker_loop


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    logging.getLogger(__name__).info("graft worker started")
    worker_loop(stop)


if __name__ == "__main__":
    main()
