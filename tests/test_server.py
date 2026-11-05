import io
from fastapi.testclient import TestClient
from app.server import create_app


def client(tmp_path):
    return TestClient(create_app(tmp_path, start_jobs=False), base_url='http://127.0.0.1:4327')


def test_import_requires_local_request_header(tmp_path):
    with client(tmp_path) as c:
        assert c.post('/api/jobs', data={'url': 'https://youtube.com/watch?v=test'}).status_code == 403


def test_rejects_cross_origin_mutation(tmp_path):
    with client(tmp_path) as c:
        r = c.post('/api/jobs', headers={'X-BlendRemake': '1', 'Origin': 'https://evil.example'}, data={'url': 'https://youtube.com/watch?v=test'})
        assert r.status_code == 403


def test_uploaded_project_survives_reopen(tmp_path):
    with client(tmp_path) as c:
        r = c.post('/api/jobs', headers={'X-BlendRemake': '1'}, data={'duration': '2', 'brief': 'Match the ball'}, files={'video': ('../../video.mp4', io.BytesIO(b'fixture data'), 'video/mp4')})
        assert r.status_code == 201, r.text
        job = r.json()
        assert (tmp_path / job['id'] / 'source.bin').read_bytes() == b'fixture data'
        assert c.get('/api/jobs/' + job['id']).json()['brief'] == 'Match the ball'
        assert c.get('/api/jobs/' + job['id'] + '/files/source.bin').status_code == 404


def test_rejects_invalid_clip_and_oversized_request(tmp_path):
    with client(tmp_path) as c:
        assert c.post('/api/jobs', headers={'X-BlendRemake': '1'}, data={'duration': '99'}).status_code == 422
        assert c.post('/api/jobs', headers={'X-BlendRemake': '1', 'Content-Length': str(300*1024*1024)}).status_code == 413


def test_refuses_unknown_host_and_missing_media(tmp_path):
    with client(tmp_path) as c:
        assert c.get('/', headers={'Host': 'evil.example'}).status_code == 400
        assert c.post('/api/jobs', headers={'X-BlendRemake': '1'}, data={'duration': '2'}).status_code == 400


def test_no_arbitrary_file_download(tmp_path):
    with client(tmp_path) as c:
        assert c.get('/api/jobs/aaaaaaaaaaaa/files/error.log').status_code == 404


def test_new_project_defaults_to_preview_and_retains_original_direction(tmp_path):
    with client(tmp_path) as c:
        response = c.post('/api/jobs', headers={'X-BlendRemake': '1'},
            data={'quality': 'final', 'brief': 'Preserve every cut'},
            files={'video': ('clip.mp4', io.BytesIO(b'fixture'), 'video/mp4')})
        assert response.status_code == 201, response.text
        job = response.json()
        assert job['preview_first'] is True
        assert job['original_brief'] == 'Preserve every cut'
        assert job['quality'] == 'final'


def test_render_uses_saved_preview_and_selected_quality(tmp_path, monkeypatch):
    with client(tmp_path) as c:
        store = c.app.state.store
        job = store.create(dict(title='Preview', quality='draft'))
        store.update(job['id'], status='preview')
        submitted = []
        monkeypatch.setattr(c.app.state.pipeline, 'submit', lambda job_id, **options: submitted.append((job_id, options)))
        response = c.post(f'/api/jobs/{job["id"]}/render', headers={'X-BlendRemake': '1'}, json={'quality': 'final'})
        assert response.status_code == 200, response.text
        assert response.json()['quality'] == 'final'
        assert submitted == [(job['id'], {'final': True})]


def test_render_requires_a_ready_preview(tmp_path):
    with client(tmp_path) as c:
        job = c.app.state.store.create(dict(title='Unfinished'))
        response = c.post(f'/api/jobs/{job["id"]}/render', headers={'X-BlendRemake': '1'})
        assert response.status_code == 409


def test_queue_rejection_is_reported_for_retry_and_revision(tmp_path, monkeypatch):
    with client(tmp_path) as c:
        store = c.app.state.store
        job = store.create(dict(title='Saved', brief='original direction'))
        store.update(job['id'], status='failed')

        def full_queue(*args, **kwargs):
            raise ValueError('Eight projects are already queued. Wait for one to finish.')

        monkeypatch.setattr(c.app.state.pipeline, 'submit', full_queue)
        for action, body in [('retry', None), ('revise', {'brief': 'new direction'})]:
            response = c.post(f'/api/jobs/{job["id"]}/{action}', headers={'X-BlendRemake': '1'}, json=body)
            assert response.status_code == 429, response.text
        assert store.get(job['id'])['brief'] == 'original direction'


def test_revision_keeps_an_intentionally_empty_original_brief(tmp_path, monkeypatch):
    with client(tmp_path) as c:
        store = c.app.state.store
        job = store.create(dict(title='Saved', brief='first revision', original_brief=''))
        store.update(job['id'], status='preview')
        monkeypatch.setattr(c.app.state.pipeline, 'submit', lambda *args, **kwargs: None)
        response = c.post(f'/api/jobs/{job["id"]}/revise', headers={'X-BlendRemake': '1'}, json={'brief': 'second revision'})
        assert response.status_code == 200, response.text
        assert response.json()['original_brief'] == ''
