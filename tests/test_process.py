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
