"""Downloading AIFS ENS files from ECMWF open data.

One file is one (date, type, step). SPEC 2.6 caps the number of files being
downloaded at once across the whole run, which is what ConnectionLimiter does.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from ecmwf.opendata import Client

from . import config as cfg

# Seconds. The read timeout is per socket read, not per file: a healthy
# download reads a chunk every fraction of a second, so 120 s of silence
# means the connection is dead.
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 120


class ConnectionLimiter:
    """Caps concurrent downloads, drops from 8 to 4 on errors, and recovers.

    SPEC 2.6: if errors appear at 8 the downloader drops to 4 and records
    that it did so; if nothing then goes wrong for 15 minutes it goes back to
    8. Dropping works by taking 4 permits out of the semaphore and holding
    them, because a thread pool cannot be resized once created; recovering
    gives the same permits back.
    """

    def __init__(self, limit: int = cfg.MAX_CONNECTIONS,
                 clock=None):
        self._sem = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._now = clock or time.monotonic   # a test can hand in its own
        self._taken = 0
        self.limit = limit
        self.file_errors = 0
        self.errors_since_change = 0
        self.last_error_at = self._now()
        self.dropped = False
        self.drops = 0
        self.recoveries = 0

    def acquire(self):
        return self._sem.acquire()

    def release(self):
        self._sem.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False

    def record_error(self, log=None) -> None:
        """Count a file-level failure and drop to 4 connections if needed."""
        with self._lock:
            self.file_errors += 1
            self.errors_since_change += 1
            self.last_error_at = self._now()
            should_drop = (
                not self.dropped
                and self.errors_since_change >= cfg.DROP_AFTER_FILE_ERRORS
            )
            if not should_drop:
                return
            self.dropped = True
            self.errors_since_change = 0

        # Take permits outside the lock so we never block holding it.
        taken = 0
        for _ in range(cfg.MAX_CONNECTIONS - cfg.REDUCED_CONNECTIONS):
            self._sem.acquire()
            taken += 1
        with self._lock:
            self._taken += taken
            self.limit = cfg.MAX_CONNECTIONS - self._taken
            self.drops += 1
        if log:
            log(
                f"dropped to {self.limit} connections after "
                f"{self.file_errors} file errors (SPEC 2.6)"
            )

    def record_success(self, log=None) -> None:
        """A file arrived. Go back to 8 after a quiet spell (SPEC 2.6).

        The drop used to be permanent, which is the safe thing to do while a
        run is burning and nobody is watching, and it is also what Pile A
        actually ran under: one bad quarter of an hour at 09:57 on 12
        November 2026 held the rest of a six-hour run at half speed. The
        errors that caused it were a laptop's Wi-Fi, not ECMWF rate limiting
        — per-connection speed never changed — so the right answer is to try
        8 again once nothing has gone wrong for
        `cfg.RECOVER_AFTER_SECONDS`, and to drop again if it was premature.

        Called after every file that arrives, so no timer thread exists and
        nothing happens in a run that never dropped.
        """
        with self._lock:
            if not self.dropped or not self._taken:
                return
            if self._now() - self.last_error_at < cfg.RECOVER_AFTER_SECONDS:
                return
            quiet = self._now() - self.last_error_at
            giving_back, self._taken = self._taken, 0
            self.dropped = False
            self.errors_since_change = 0
            self.recoveries += 1

        for _ in range(giving_back):
            self._sem.release()
        with self._lock:
            self.limit = cfg.MAX_CONNECTIONS - self._taken
        if log:
            log(
                f"back to {self.limit} connections after {quiet / 60:.0f} "
                f"minutes with no file error (SPEC 2.6)"
            )

    def state(self) -> dict:
        """What the done record keeps about the connection count."""
        with self._lock:
            return {
                "connections": self.limit,
                "file_errors": self.file_errors,
                "drops": self.drops,
                "recoveries": self.recoveries,
            }


def _force_socket_timeout(session) -> None:
    """Make stalled downloads fail instead of hanging forever.

    Found on 12 November 2026 during the two-date test: a download stalled at
    27 MB and sat there with no progress and no error, because
    ``ecmwf-opendata`` calls ``multiurl.download()`` without a ``timeout``,
    so ``multiurl`` passes ``timeout=None`` to requests and the socket read
    blocks indefinitely.

    A plain ``setdefault`` does not help, because ``timeout`` is present and
    explicitly ``None``. So the session's own ``get`` and ``head`` are wrapped
    to replace a ``None`` timeout with a real one. ``multiurl`` already treats
    ``requests.exceptions.ReadTimeout`` as retryable, so the existing
    ``maximum_retries`` policy then applies and the run moves on instead of
    freezing. This matters most for the unattended background run.
    """
    if getattr(session, "_pf_timeout_wrapped", False):
        return

    for name in ("get", "head"):
        original = getattr(session, name)

        def wrapped(*args, _original=original, **kwargs):
            if kwargs.get("timeout") is None:
                kwargs["timeout"] = (CONNECT_TIMEOUT, READ_TIMEOUT)
            return _original(*args, **kwargs)

        setattr(session, name, wrapped)

    session._pf_timeout_wrapped = True


def make_client(source: str = cfg.ARCHIVE_SOURCE) -> Client:
    """A client with the retry and timeout policy from SPEC 2.6.

    The library defaults are 500 retries over 120 s each, which is the
    "retry forever" behaviour SPEC 2.6 forbids.
    """
    client = Client(
        source=source,
        model=cfg.MODEL,
        maximum_retries=cfg.MAX_RETRIES,
        retry_after=cfg.RETRY_AFTER,
    )
    _force_socket_timeout(client.session)
    return client


def download_one(
    date: str,
    typ: str,
    step: int,
    source: str = cfg.ARCHIVE_SOURCE,
    limiter: ConnectionLimiter | None = None,
    log=None,
) -> Path:
    """Download one (date, type, step) file and return its path.

    Downloads to a .part file and renames on success, so an interrupted run
    never leaves a short file that looks complete (SPEC 2.6 point 5).
    """
    target = cfg.raw_path(date, typ, step)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")

    if part.exists():
        part.unlink()

    def _fetch():
        client = make_client(source)
        client.retrieve(
            date=date,
            time=cfg.RUN_TIME,
            stream=cfg.STREAM,
            type=typ,
            param=cfg.PARAM,
            step=step,
            target=str(part),
        )

    if limiter is None:
        _fetch()
    else:
        with limiter:
            _fetch()

    if not part.exists() or part.stat().st_size == 0:
        raise RuntimeError(f"{date} {typ} step {step}: empty download")

    part.replace(target)
    if limiter is not None:
        # A whole file arrived. If the run is at 4 connections and has been
        # quiet for long enough, this is where it goes back to 8 (SPEC 2.6).
        limiter.record_success(log)
    return target


def files_for_date(date: str) -> list[tuple[str, str, int]]:
    """Every (date, type, step) file one date needs: 2 types x 6 steps."""
    return [(date, typ, step) for typ in cfg.TYPES for step in cfg.STEPS]
