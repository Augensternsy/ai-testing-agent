# -*- coding: utf-8 -*-
"""Tests for the Safe Demo Backend API."""

import pytest
from fastapi.testclient import TestClient

from ai_testing_agent.demo_api import create_demo_app


@pytest.fixture
def client():
    from ai_testing_agent.demo_api import _run_limiter, _all_limiter
    # Reset rate limiter state before each test
    _run_limiter._hits.clear()
    _all_limiter._hits.clear()
    app = create_demo_app()
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "ai-testing-agent-demo"
        assert data["mode"] == "demo"


class TestScenarios:
    def test_scenarios_returns_exactly_3(self, client):
        resp = client.get("/api/demo/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scenarios"]) == 3

    def test_scenarios_ids(self, client):
        resp = client.get("/api/demo/scenarios")
        ids = [s["id"] for s in resp.json()["scenarios"]]
        assert ids == ["login", "users", "health"]

    def test_scenarios_have_required_fields(self, client):
        resp = client.get("/api/demo/scenarios")
        for s in resp.json()["scenarios"]:
            assert "id" in s
            assert "method" in s
            assert "path" in s
            assert "name" in s


class TestRunDemoLogin:
    def test_login_returns_200(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {"username": "test", "password": "123456"},
        })
        assert resp.status_code == 200

    def test_login_mode_is_demo(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        assert resp.json()["mode"] == "demo"

    def test_login_source_is_verified(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        assert resp.json()["source"] == "verified_e2e"

    def test_login_report_total_11(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        assert resp.json()["report"]["total"] == 11

    def test_login_report_passed_11(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        assert resp.json()["report"]["passed"] == 11

    def test_login_report_failed_0(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        assert resp.json()["report"]["failed"] == 0

    def test_login_agent_not_triggered(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        assert resp.json()["agent"]["triggered"] is False

    def test_login_has_test_cases(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        cases = resp.json()["test_cases"]
        assert len(cases) == 11

    def test_login_has_generated_code(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        code = resp.json()["generated_code"]
        assert "def test_login" in code
        assert "import" in code

    def test_login_has_stages(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": {},
        })
        stages = resp.json()["stages"]
        assert len(stages) == 5
        for s in stages:
            assert s["status"] == "completed"


class TestRunDemoUsers:
    def test_users_returns_200(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "users",
            "input": {"user_id": 1},
        })
        assert resp.status_code == 200

    def test_users_report_total_9(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "users",
            "input": {},
        })
        assert resp.json()["report"]["total"] == 9

    def test_users_agent_triggered(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "users",
            "input": {},
        })
        agent = resp.json()["agent"]
        assert agent["triggered"] is True
        assert agent["repair_allowed"] is False


class TestRunDemoHealth:
    def test_health_scenario_returns_200(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "health",
            "input": {},
        })
        assert resp.status_code == 200

    def test_health_report_total_5(self, client):
        resp = client.post("/api/demo/run", json={
            "scenario": "health",
            "input": {},
        })
        assert resp.json()["report"]["total"] == 5
        assert resp.json()["report"]["passed"] == 5


class TestInvalidScenario:
    def test_invalid_scenario_returns_422(self, client):
        """Pydantic Literal validator rejects unknown scenarios with 422."""
        resp = client.post("/api/demo/run", json={
            "scenario": "invalid_scenario",
            "input": {},
        })
        assert resp.status_code == 422


class TestRepairExample:
    def test_repair_example_confidence(self, client):
        resp = client.get("/api/demo/repair-example")
        assert resp.status_code == 200
        assert resp.json()["confidence"] == 0.92

    def test_repair_example_allowed(self, client):
        resp = client.get("/api/demo/repair-example")
        assert resp.json()["repair_allowed"] is True

    def test_repair_example_category(self, client):
        resp = client.get("/api/demo/repair-example")
        assert resp.json()["category"] == "test_code_error"

    def test_repair_example_rerun(self, client):
        resp = client.get("/api/demo/repair-example")
        rerun = resp.json()["rerun"]
        assert rerun["total"] == 1
        assert rerun["passed"] == 1


class TestCORS:
    def test_cors_header_present(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "https://ai-testing-agent-web.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware should return 200 for preflight
        assert resp.status_code == 200
        assert "access-control-allow-origin" in resp.headers

    def test_cors_allows_localhost(self, client):
        resp = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200


class TestInputValidation:
    def test_oversized_input_rejected(self, client):
        """Input larger than 4KB should be rejected."""
        big_input = {"data": "x" * 5000}
        resp = client.post("/api/demo/run", json={
            "scenario": "login",
            "input": big_input,
        })
        assert resp.status_code == 422  # Pydantic validation error
