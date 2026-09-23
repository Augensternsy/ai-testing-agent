# -*- coding: utf-8 -*-
"""
Safe Demo Backend API for AI Testing Agent.

This module provides a FastAPI router that serves *verified* demo results only.
It does NOT:
  - invoke DeepSeek or any LLM
  - execute arbitrary URLs
  - execute generated code
  - run pytest
  - modify source code
  - call subprocess

All data comes from ai_testing_agent/demo_data.py (verified E2E runs).
"""

import os
import time
from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class DemoScenario(BaseModel):
    id: str
    method: str
    path: str
    name: str


class DemoScenarioList(BaseModel):
    scenarios: list[DemoScenario]


class DemoRunRequest(BaseModel):
    scenario: Literal["login", "users", "health"]
    input: dict = Field(default_factory=dict)

    @field_validator("input")
    @classmethod
    def check_input_size(cls, v: dict) -> dict:
        import json
        encoded = json.dumps(v, ensure_ascii=False)
        if len(encoded) > 4096:
            raise ValueError("Input too large (max 4KB)")
        return v


class DemoStage(BaseModel):
    stage: int
    name: str
    status: Literal["pending", "running", "completed", "failed"]


class DemoTestCase(BaseModel):
    case_id: str
    title: str
    type: Literal["normal", "boundary", "exception"]
    priority: Literal["P0", "P1", "P2"]
    expected_status: int


class DemoTestReport(BaseModel):
    total: int
    passed: int
    failed: int
    skipped: int
    pass_rate: float
    duration: float


class DemoAgentResult(BaseModel):
    triggered: bool
    category: str | None = None
    confidence: float | None = None
    root_cause: str | None = None
    repair_allowed: bool | None = None
    repair_attempted: bool | None = None
    repair_success: bool | None = None
    final_status: str | None = None
    repair_attempts: int | None = None
    reason: str | None = None


class DemoRunResponse(BaseModel):
    run_id: str
    mode: Literal["demo"] = "demo"
    source: Literal["verified_e2e"] = "verified_e2e"
    scenario: DemoScenario
    stages: list[DemoStage]
    test_cases: list[DemoTestCase]
    generated_code: str
    report: DemoTestReport
    agent: DemoAgentResult


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "ai-testing-agent-demo"
    mode: str = "demo"


class RepairExampleResponse(BaseModel):
    error: str
    category: str
    confidence: float
    repair_allowed: bool
    safety_validation: str
    repair_attempts: int
    rerun: dict


# ---------------------------------------------------------------------------
# In-memory rate limiter (lightweight, no Redis/DB)
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple in-memory rate limiter: max N requests per window per IP."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, client_ip: str) -> bool:
        """Return True if request is allowed, False if rate-limited."""
        now = time.time()
        hits = self._hits[client_ip]
        # Prune old entries
        self._hits[client_ip] = [t for t in hits if now - t < self.window]
        if len(self._hits[client_ip]) >= self.max_requests:
            return False
        self._hits[client_ip].append(now)
        return True


_run_limiter = RateLimiter(max_requests=5, window_seconds=60)
_all_limiter = RateLimiter(max_requests=20, window_seconds=60)


# ---------------------------------------------------------------------------
# Preset Scenarios (static, no dynamic definitions accepted)
# ---------------------------------------------------------------------------

SCENARIOS: list[DemoScenario] = [
    DemoScenario(id="login", method="POST", path="/login", name="Login API"),
    DemoScenario(id="users", method="GET", path="/users/{id}", name="User API"),
    DemoScenario(id="health", method="GET", path="/health", name="Health API"),
]


# ---------------------------------------------------------------------------
# Build demo responses from verified data
# ---------------------------------------------------------------------------

def _build_login_response() -> DemoRunResponse:
    from . import demo_data as dd

    return DemoRunResponse(
        run_id="demo-login",
        scenario=SCENARIOS[0],
        stages=[DemoStage(**s) for s in dd.PIPELINE_STAGES],
        test_cases=[DemoTestCase(**c) for c in dd.LOGIN_TEST_CASES],
        generated_code=dd.LOGIN_GENERATED_CODE,
        report=DemoTestReport(
            total=11, passed=11, failed=0, skipped=0,
            pass_rate=1.0, duration=1.23,
        ),
        agent=DemoAgentResult(triggered=False),
    )


def _build_users_response() -> DemoRunResponse:
    from . import demo_data as dd

    return DemoRunResponse(
        run_id="demo-users",
        scenario=SCENARIOS[1],
        stages=[DemoStage(**s) for s in dd.PIPELINE_STAGES],
        test_cases=[DemoTestCase(**c) for c in dd.USERS_TEST_CASES],
        generated_code=dd.USERS_GENERATED_CODE,
        report=DemoTestReport(
            total=9, passed=5, failed=4, skipped=0,
            pass_rate=0.556, duration=0.89,
        ),
        agent=DemoAgentResult(
            triggered=True,
            category="non_test_code_error",
            confidence=0.85,
            root_cause="LLM assumed schema constraints (positive int, int32) not declared in OpenAPI spec",
            repair_allowed=False,
            repair_attempted=False,
            final_status="failed",
            reason="Failure classified as non-test_code_error — repair not allowed",
        ),
    )


def _build_health_response() -> DemoRunResponse:
    from . import demo_data as dd

    return DemoRunResponse(
        run_id="demo-health",
        scenario=SCENARIOS[2],
        stages=[DemoStage(**s) for s in dd.PIPELINE_STAGES],
        test_cases=[DemoTestCase(**c) for c in dd.HEALTH_TEST_CASES],
        generated_code=dd.HEALTH_GENERATED_CODE,
        report=DemoTestReport(
            total=5, passed=5, failed=0, skipped=0,
            pass_rate=1.0, duration=0.45,
        ),
        agent=DemoAgentResult(triggered=False),
    )


_DEMO_BUILDERS = {
    "login": _build_login_response,
    "users": _build_users_response,
    "health": _build_health_response,
}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["demo"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check — frontend uses this to detect if backend is online."""
    return HealthResponse()


@router.get("/demo/scenarios", response_model=DemoScenarioList)
async def get_scenarios():
    """Return fixed preset scenarios. No dynamic scenario definitions accepted."""
    return DemoScenarioList(scenarios=SCENARIOS)


@router.post("/demo/run", response_model=DemoRunResponse)
async def run_demo(req: DemoRunRequest, request: Request):
    """Run a preset demo scenario. Returns verified E2E data, not live LLM results."""
    client_ip = request.client.host if request.client else "unknown"

    if not _run_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit: max 5 demo runs per minute")

    builder = _DEMO_BUILDERS.get(req.scenario)
    if builder is None:
        raise HTTPException(status_code=400, detail="Unsupported demo scenario")

    return builder()


@router.get("/demo/repair-example", response_model=RepairExampleResponse)
async def get_repair_example(request: Request):
    """Return a fixed, verified Stage 5 Agent Repair example."""
    from . import demo_data as dd

    client_ip = request.client.host if request.client else "unknown"
    if not _all_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    return RepairExampleResponse(**dd.REPAIR_EXAMPLE)


# ---------------------------------------------------------------------------
# CORS Middleware Setup
# ---------------------------------------------------------------------------

DEFAULT_ORIGINS = [
    "https://ai-testing-agent-web.vercel.app",
    "http://localhost:5173",
]


def get_allowed_origins() -> list[str]:
    env_origins = os.getenv("DEMO_ALLOWED_ORIGINS")
    if env_origins:
        return [o.strip() for o in env_origins.split(",")]
    return DEFAULT_ORIGINS


def create_demo_app():
    """Create a standalone FastAPI app with the demo router and CORS."""
    from fastapi import FastAPI

    app = FastAPI(
        title="AI Testing Agent — Safe Demo Backend",
        description="Serves verified demo results only. Does NOT invoke DeepSeek, execute code, or run pytest.",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app
