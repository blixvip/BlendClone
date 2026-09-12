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
