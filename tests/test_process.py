import sys
import threading
import time
import pytest
from app.process import run, Cancelled


def test_cancellation_stops_only_the_owned_child():
    cancel = threading.Event()
    timer = threading.Timer(.2, cancel.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            run([sys.executable, '-c', 'import time; time.sleep(30)'], cancel=cancel)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 8
    assert run([sys.executable, '-c', 'print("still works")']).strip() == b'still works'


def test_process_timeout_is_bounded():
    with pytest.raises(TimeoutError):
        run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.1)


def test_running_child_reports_progress_without_losing_output():
    ticks = []
    output = run([sys.executable, '-c', 'import time; time.sleep(.8); print("finished")'], on_tick=lambda: ticks.append(True))
    assert ticks and output.strip() == b'finished'


def test_timed_out_process_retains_diagnostics(tmp_path):
    log = tmp_path / 'process.log'
    with pytest.raises(TimeoutError):
        run([sys.executable, '-u', '-c', 'import time; print("before timeout", flush=True); time.sleep(30)'], timeout=.6, log=log)
    assert b'before timeout' in log.read_bytes()


def test_cancelled_process_retains_diagnostics(tmp_path):
    cancel = threading.Event()
    log = tmp_path / 'process.log'
    with pytest.raises(Cancelled):
        run([sys.executable, '-u', '-c', 'import time; print("before cancel", flush=True); time.sleep(30)'],
            cancel=cancel, on_tick=cancel.set, log=log)
    assert b'before cancel' in log.read_bytes()
