"""Launch hidden owned subprocesses. Never enumerate or stop other applications."""
import os
import subprocess
import time


class Cancelled(Exception):
    pass


def run(args, *, cwd=None, timeout=120, cancel=None, input=None, env=None, log=None, combined=False):
    proc = subprocess.Popen([str(a) for a in args], cwd=cwd, env=env,
        stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    started = time.monotonic()
    try:
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled('Cancelled')
            if time.monotonic() - started > timeout:
                raise TimeoutError('This step timed out. Try a shorter clip or draft quality.')
            try:
                stdout, stderr = proc.communicate(input=input, timeout=.5)
                break
            except subprocess.TimeoutExpired:
                input = None
        if log:
            log.write_bytes(stdout + b'\n' + stderr)
        if proc.returncode:
            raise RuntimeError((stderr + stdout).decode('utf-8', errors='replace')[-3000:])
        return stdout + stderr if combined else stdout
    finally:
        if proc.poll() is None:
            proc.terminate()  # The exact process we just created; never a process-name match.
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
