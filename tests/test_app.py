import fakeredis
import pytest
import redis

from app.main import create_app


@pytest.fixture
def client():
    app = create_app(redis_client=fakeredis.FakeRedis(decode_responses=True))
    return app.test_client()


def test_health(client):
    assert client.get("/health").json == {"status": "ok"}


def test_ready_when_redis_up(client):
    assert client.get("/ready").json == {"status": "ready"}


def test_ready_503_when_redis_down():
    class Broken:
        def ping(self):
            raise redis.ConnectionError("down")

    resp = create_app(redis_client=Broken()).test_client().get("/ready")
    assert resp.status_code == 503


def test_hit_counter_increments(client):
    assert client.get("/").json["hits"] == 1
    assert client.get("/").json["hits"] == 2


def test_add_and_list_todos(client):
    assert client.post("/todos", json={"text": "learn docker"}).status_code == 201
    assert client.get("/todos").json == {"todos": ["learn docker"]}


def test_add_todo_requires_text(client):
    assert client.post("/todos", json={}).status_code == 400


def test_metrics_exposed(client):
    client.get("/health")
    body = client.get("/metrics").get_data(as_text=True)
    assert "http_requests_total" in body
    assert 'endpoint="/health"' in body
