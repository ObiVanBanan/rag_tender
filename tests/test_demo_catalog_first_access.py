"""Access and budget contracts for browser demo on the catalog-first runtime."""
import base64
from types import SimpleNamespace

from fastapi.testclient import TestClient

from nomenclature_matcher.api import create_app
from nomenclature_matcher.models import MatchResult


def basic(username: str, password: str) -> dict[str, str]:
    encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": "Basic " + encoded}


class Runtime:
    def __init__(self, *, password="demo-secret", hourly_limit=20):
        self.settings = SimpleNamespace(
            app_env="production",
            api_auth_token="some-production-bearer-token-that-is-long-enough",
            api_max_batch_size=10,
            api_max_inflight_batches=1,
            api_max_items_per_hour=hourly_limit,
            public_demo_username="demo",
            public_demo_password=password,
            public_demo_admin_username="admin",
            public_demo_admin_password="independent-admin-secret",
            public_demo_max_batch_size=10,
            match_trace_enabled=False,
        )
        self.history = SimpleNamespace()
        self.matcher = self

    def close(self):
        pass

    def ready(self):
        return True

    def match_one_hybrid_with_rerank(self, query):
        return MatchResult(query=query, status="NOT_FOUND")


def test_browser_basic_is_scoped_to_demo_and_separate_from_api_bearer():
    with TestClient(create_app(runtime_factory=Runtime)) as client:
        denied = client.get("/demo")
        assert denied.status_code == 401
        assert denied.headers["www-authenticate"].startswith("Basic")
        assert client.get("/demo", headers=basic("demo", "demo-secret")).status_code == 200
        assert client.get("/demo/stats", headers=basic("demo", "demo-secret")).status_code == 401
        assert client.get("/demo/stats", headers=basic("admin", "independent-admin-secret")).status_code == 200
        assert client.post("/v1/match", json={"products": ["DN50"]},
                           headers=basic("demo", "demo-secret")).status_code == 401
        schema = client.get("/openapi.json").json()
        assert schema["paths"]["/v1/demo/match"]["post"]["security"] == [{"DemoBasicAuth": []}]
        assert schema["paths"]["/v1/match"]["post"]["security"] == [{"BearerAuth": []}]


def test_demo_uses_shared_admission_budget():
    with TestClient(create_app(runtime_factory=lambda: Runtime(hourly_limit=1))) as client:
        payload = {"products": ["Фланец DN50 PN16"]}
        headers = basic("demo", "demo-secret")
        assert client.post("/v1/demo/match", json=payload, headers=headers).status_code == 200
        response = client.post("/v1/demo/match", json=payload, headers=headers)
        assert response.status_code == 429
        assert response.headers["retry-after"]


def test_demo_fails_closed_in_production_without_password_and_uses_random_review_ids():
    with TestClient(create_app(runtime_factory=lambda: Runtime(password=""))) as client:
        assert client.get("/demo").status_code == 401
    with TestClient(create_app(runtime_factory=Runtime)) as client:
        headers = basic("demo", "demo-secret")
        payload = {"products": ["Фланец DN50"]}
        a = client.post("/v1/demo/match", json=payload, headers={**headers, "X-Request-ID": "reused-client-id"})
        b = client.post("/v1/demo/match", json=payload, headers={**headers, "X-Request-ID": "reused-client-id"})
        assert a.status_code == 200 and b.status_code == 200
        assert a.json()["request_id"] != b.json()["request_id"]
