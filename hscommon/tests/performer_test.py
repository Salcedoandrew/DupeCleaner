# Tests for the threaded job performer: worker threads must be daemons
# (quitting mid-scan must not leave the process lingering on them) and the
# running state must be observable (so the UI can refuse a second job
# before it wipes the current results).

import threading
import time

import pytest
from hscommon.testutil import eq_
from hscommon.jobprogress.performer import ThreadedJobPerformer
from hscommon.jobprogress.job import JobInProgressError


class Performer(ThreadedJobPerformer):
    pass


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_worker_thread_is_daemon():
    p = Performer()
    seen = []
    started = threading.Event()

    def target():
        seen.append(threading.current_thread().daemon)
        started.set()

    p.run_threaded(target, ())
    assert started.wait(timeout=5)
    eq_([True], seen)


def test_job_running_property():
    p = Performer()
    started = threading.Event()
    release = threading.Event()

    def target():
        started.set()
        release.wait(timeout=5)

    assert not p.job_running
    p.run_threaded(target, ())
    assert started.wait(timeout=5)
    assert p.job_running
    release.set()
    assert _wait_until(lambda: not p.job_running)
    assert not p.job_running


def test_second_run_while_running_raises():
    p = Performer()
    started = threading.Event()
    release = threading.Event()

    def target():
        started.set()
        release.wait(timeout=5)

    p.run_threaded(target, ())
    assert started.wait(timeout=5)
    with pytest.raises(JobInProgressError):
        p.run_threaded(target, ())
    release.set()
    assert _wait_until(lambda: not p.job_running)
