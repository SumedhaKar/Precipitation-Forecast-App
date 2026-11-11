"""Downloading AIFS ENS files from ECMWF open data.

One file is one (date, type, step). SPEC 2.6 caps the number of files being
downloaded at once across the whole run, which is what ConnectionLimiter does.
"""
from __future__ import annotations

import threading
from pathlib import Path

from ecmwf.opendata import Client

from . import config as cfg

# Seconds. The read timeout is per socket read, not per file: a healthy
# download reads a chunk every fraction of a second, so 120 s of silence
# means the connection is dead.
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 120


class ConnectionLimiter:
    """Caps concurrent downloads, and can drop from 8 to 4 permanently.

    SPEC 2.6: if errors appear at 8 the downloader drops to 4 and records that
    it did so. Dropping works by permanently taking 4 permits out of the
    semaphore, because a thread pool cannot be resized once created.
    """

    def __init__(self, limit: int = cfg.MAX_CONNECTIONS):
        self._sem = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self.limit = limit
        self.file_errors = 0
        self.dropped = False

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
            should_drop = (
                not self.dropped
                and self.file_errors >= cfg.DROP_AFTER_FILE_ERRORS
            )
            if not should_drop:
                return
            self.dropped = True

        # Take permits outside the lock so we never block holding it.
        taken = 0
        for _ in range(cfg.MAX_CONNECTIONS - cfg.REDUCED_CONNECTIONS):
            self._sem.acquire()
            taken += 1
        self.limit = cfg.MAX_CONNECTIONS - taken
        if log:
            log(
                f"dropped to {self.limit} connections after "
                f"{self.file_errors} file errors (SPEC 2.6)"
            )


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
    return target


def files_for_date(date: str) -> list[tuple[str, str, int]]:
    """Every (date, type, step) file one date needs: 2 types x 6 steps."""
    return [(date, typ, step) for typ in cfg.TYPES for step in cfg.STEPS]
