"""Worker requests and lifecycle exercised without launching any real process."""
import json
import subprocess
import threading
from pathlib import Path

import pytest

from app import worker
from app.models import Material, Timeline, fixture_plan
from app.process import Cancelled


class FakeInput:
    def __init__(self, process):
        self.process = process
        self.closed = False

    def write(self, raw):
        request = json.loads(raw)
        self.process.requests.append(request)
        if self.process.respond:
            result = self.process.folder / f"{request['id']:06d}.json"
            result.write_text(json.dumps(dict(ok=True, image=f"fresh-{self.process.number}.png")))
        if self.process.on_write:
            self.process.on_write()

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, args, number):
        self.folder = Path(args[-1])
        self.number = number
        self.stdin = FakeInput(self)
        self.requests = []
        self.respond = True
        self.on_write = None
        self.waits = []
        self.terminations = 0
        self.stall_once = False

    def poll(self):
        return None

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.stall_once:
            self.stall_once = False
            raise subprocess.TimeoutExpired('fake-owned-worker', timeout)
        return 0

    def terminate(self):
        self.terminations += 1


@pytest.fixture
def fake_children(monkeypatch):
    children = []

    def popen(args, **kwargs):
        child = FakeProcess(args, len(children) + 1)
        children.append(child)
        return child

    monkeypatch.setattr(worker.subprocess, 'Popen', popen)
    monkeypatch.setattr(worker, 'blender_binary', lambda: 'fake-blender.exe')
    return children


def test_worker_instances_use_unique_folders_and_never_reuse_stale_result(tmp_path, fake_children):
    parent = tmp_path / 'workers'
    parent.mkdir()
    (parent / '000001.json').write_text(json.dumps(dict(ok=True, image='stale.png')))
    with worker.BlenderWorker(tmp_path / 'scene.blend', parent, threading.Event()) as first:
        first_image = first.render(fixture_plan())
        first_folder = first.folder
    with worker.BlenderWorker(tmp_path / 'scene.blend', parent, threading.Event()) as second:
        second_image = second.render(fixture_plan())
        assert second.folder != first_folder
        assert first_folder.parent == second.folder.parent == parent.resolve()
        assert first_image == first_folder / 'fresh-1.png'
        assert second_image == second.folder / 'fresh-2.png'
    assert [child.requests[0]['id'] for child in fake_children] == [1, 1]


def test_worker_omits_unused_materials_from_render_request(tmp_path, fake_children):
    plan = fixture_plan()
    plan.materials.append(Material(id='unused', color='#ffffff'))
    with worker.BlenderWorker(tmp_path / 'scene.blend', tmp_path, threading.Event()) as instance:
        instance.render(plan, frame=0, size=(270, 480), samples=12)
    request = fake_children[0].requests[0]
    assert {m['id'] for m in request['materials']} == {'coral', 'chalk', 'floor'}
    assert len(plan.materials) == 4
    assert request['size'] == [270, 480]
    assert request['samples'] == 12


def test_cancellation_while_waiting_raises_and_closes_owned_child(tmp_path, fake_children):
    cancel = threading.Event()
    with pytest.raises(Cancelled):
        with worker.BlenderWorker(tmp_path / 'scene.blend', tmp_path, cancel) as instance:
            child = fake_children[0]
            child.respond = False
            child.on_write = cancel.set
            instance.render(fixture_plan())
    assert child.stdin.closed
    assert child.waits == [10]
    assert instance.log.closed


def test_context_exit_signals_only_its_owned_child(tmp_path, fake_children):
    with worker.BlenderWorker(tmp_path / 'other.blend', tmp_path, threading.Event()) as other:
        with worker.BlenderWorker(tmp_path / 'scene.blend', tmp_path, threading.Event()) as owned:
            owned.process.stall_once = True
        assert owned.process.stdin.closed
        assert owned.process.waits == [10, 10]
        assert owned.process.terminations == 1
        assert not other.process.stdin.closed
        assert other.process.waits == []
        assert other.process.terminations == 0
    assert other.process.stdin.closed
    assert other.process.terminations == 0


@pytest.mark.parametrize('size', [(1, 480), (270, 8193), (270.5, 480), (True, 480), (270,)])
def test_invalid_dimensions_are_rejected_before_submission(tmp_path, fake_children, size):
    with worker.BlenderWorker(tmp_path / 'scene.blend', tmp_path, threading.Event()) as instance:
        with pytest.raises(ValueError, match='dimensions'):
            instance.render(fixture_plan(), size=size)
        assert fake_children[0].requests == []
        assert instance.index == 0


@pytest.mark.parametrize('frame', [-1, 60, 1.5])
def test_invalid_frame_indices_are_rejected_before_submission(tmp_path, fake_children, frame):
    plan = fixture_plan()
    plan.timeline = Timeline(frame_count=60, fps_num=30, fps_den=1)
    with worker.BlenderWorker(tmp_path / 'scene.blend', tmp_path, threading.Event()) as instance:
        with pytest.raises(ValueError, match='[Ff]rame'):
            instance.render(plan, frame=frame)
        assert fake_children[0].requests == []
        assert instance.index == 0
