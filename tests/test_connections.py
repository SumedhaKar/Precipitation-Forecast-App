"""SPEC 2.6: the connection limiter drops from 8 to 4, and comes back.

No network. The limiter is handed its own clock, so "fifteen quiet minutes"
is a number this test chooses rather than fifteen minutes of waiting.
"""
from __future__ import annotations

import threading

from pipeline import config as cfg
from pipeline.ecmwf_download import ConnectionLimiter


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def forward(self, seconds: float) -> None:
        self.t += seconds


def permits_free(limiter: ConnectionLimiter) -> int:
    """How many downloads could start right now."""
    taken = 0
    while limiter._sem.acquire(blocking=False):      # noqa: SLF001
        taken += 1
    for _ in range(taken):
        limiter.release()
    return taken


def test_it_starts_at_eight_and_says_so():
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS)
    assert limiter.limit == 8
    assert permits_free(limiter) == 8
    assert limiter.state() == {"connections": 8, "file_errors": 0,
                               "drops": 0, "recoveries": 0}


def test_two_errors_change_nothing():
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS)
    limiter.record_error()
    limiter.record_error()
    assert limiter.dropped is False
    assert limiter.limit == 8
    assert permits_free(limiter) == 8


def test_the_third_error_drops_it_to_four():
    said = []
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS)
    for _ in range(cfg.DROP_AFTER_FILE_ERRORS):
        limiter.record_error(said.append)

    assert limiter.dropped is True
    assert limiter.limit == cfg.REDUCED_CONNECTIONS == 4
    assert permits_free(limiter) == 4
    assert limiter.drops == 1
    assert said and "dropped to 4 connections" in said[-1]


def test_it_does_not_recover_before_the_quiet_time_is_up():
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    for _ in range(3):
        limiter.record_error()

    clock.forward(cfg.RECOVER_AFTER_SECONDS - 1)
    limiter.record_success()

    assert limiter.dropped is True
    assert limiter.limit == 4
    assert permits_free(limiter) == 4
    assert limiter.recoveries == 0


def test_fifteen_quiet_minutes_puts_it_back_to_eight():
    said = []
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    for _ in range(3):
        limiter.record_error(said.append)
    assert limiter.limit == 4

    clock.forward(cfg.RECOVER_AFTER_SECONDS)
    limiter.record_success(said.append)

    assert limiter.dropped is False
    assert limiter.limit == 8
    assert permits_free(limiter) == 8, "all eight permits are back"
    assert limiter.recoveries == 1
    assert "back to 8 connections after 15 minutes" in said[-1]


def test_an_error_during_the_quiet_time_starts_the_clock_again():
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    for _ in range(3):
        limiter.record_error()

    clock.forward(cfg.RECOVER_AFTER_SECONDS - 60)
    limiter.record_error()                      # one more thing goes wrong
    clock.forward(120)                          # the old deadline passes
    limiter.record_success()
    assert limiter.limit == 4, "the quiet spell restarted at the new error"

    clock.forward(cfg.RECOVER_AFTER_SECONDS)
    limiter.record_success()
    assert limiter.limit == 8


def test_it_can_drop_again_after_recovering():
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    for _ in range(3):
        limiter.record_error()
    clock.forward(cfg.RECOVER_AFTER_SECONDS)
    limiter.record_success()
    assert limiter.limit == 8

    # It takes three fresh errors, not one: the counter resets on a change.
    limiter.record_error()
    limiter.record_error()
    assert limiter.limit == 8
    limiter.record_error()

    assert limiter.limit == 4
    assert permits_free(limiter) == 4
    assert limiter.drops == 2
    assert limiter.recoveries == 1
    assert limiter.file_errors == 6, "the running total is still every error"


def test_recovering_never_hands_back_more_permits_than_it_took():
    """A BoundedSemaphore raises if over-released, which would end the run."""
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    for _ in range(3):
        limiter.record_error()
    clock.forward(cfg.RECOVER_AFTER_SECONDS)

    for _ in range(5):                 # four more files arrive after recovery
        limiter.record_success()

    assert limiter.limit == 8
    assert limiter.recoveries == 1
    assert permits_free(limiter) == 8


def test_a_run_that_never_errs_is_untouched_by_success():
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    clock.forward(10 * cfg.RECOVER_AFTER_SECONDS)
    for _ in range(20):
        limiter.record_success()

    assert limiter.limit == 8
    assert limiter.drops == 0
    assert limiter.recoveries == 0
    assert permits_free(limiter) == 8


def test_the_limiter_holds_under_threads():
    """Eight downloads at once, 4 after a drop, with real threads."""
    clock = Clock()
    limiter = ConnectionLimiter(cfg.MAX_CONNECTIONS, clock=clock)
    inside = []
    peak = [0]
    lock = threading.Lock()
    gate = threading.Event()

    def worker() -> None:
        with limiter:
            with lock:
                inside.append(1)
                peak[0] = max(peak[0], len(inside))
            gate.wait(2)
            with lock:
                inside.pop()

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for thread in threads:
        thread.start()
    # Let them pile up against the cap, then release.
    import time as real_time
    real_time.sleep(0.2)
    assert peak[0] <= 8, f"{peak[0]} downloads ran at once, cap is 8"
    gate.set()
    for thread in threads:
        thread.join(5)
    assert peak[0] == 8, "the cap should actually be reached"
