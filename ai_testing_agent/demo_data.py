# -*- coding: utf-8 -*-
"""
Verified demo data for the Safe Demo Backend.

All data in this module comes from real E2E verification runs (2026-09-23).
It does NOT invoke DeepSeek, does NOT run pytest, and does NOT modify source code.

Sources:
  - reports/real_llm_e2e_report.json (login: 11/11 PASS)
  - generated_tests/test_login_real_llm.py (login PyTest code)
  - generated_tests/test_health.py (health: 5/5 PASS)
  - generated_tests/test_users_user_id.py (users: 9 tests, 4 failed - non-test_code_error)
  - reports/agent_report.json (Stage 5 repair example)
"""

# ---------------------------------------------------------------------------
# Login Demo — Verified E2E (Real DeepSeek, 2026-09-23)
# Source: reports/real_llm_e2e_report.json + generated_tests/test_login_real_llm.py
# ---------------------------------------------------------------------------

LOGIN_TEST_CASES = [
    {"case_id": "LOGIN_001", "title": "Valid login", "type": "normal", "priority": "P0", "expected_status": 200},
    {"case_id": "LOGIN_002", "title": "Missing username", "type": "exception", "priority": "P0", "expected_status": 422},
    {"case_id": "LOGIN_003", "title": "Missing password", "type": "exception", "priority": "P0", "expected_status": 422},
    {"case_id": "LOGIN_004", "title": "Empty username", "type": "exception", "priority": "P1", "expected_status": 422},
    {"case_id": "LOGIN_005", "title": "Empty password", "type": "exception", "priority": "P1", "expected_status": 422},
    {"case_id": "LOGIN_006", "title": "Non-string username", "type": "exception", "priority": "P1", "expected_status": 422},
    {"case_id": "LOGIN_007", "title": "Non-string password", "type": "exception", "priority": "P1", "expected_status": 422},
    {"case_id": "LOGIN_008", "title": "Oversized password (128+ chars)", "type": "boundary", "priority": "P1", "expected_status": 422},
    {"case_id": "LOGIN_009", "title": "Wrong username", "type": "exception", "priority": "P0", "expected_status": 401},
    {"case_id": "LOGIN_010", "title": "Wrong password", "type": "exception", "priority": "P0", "expected_status": 401},
    {"case_id": "LOGIN_011", "title": "Both credentials wrong", "type": "exception", "priority": "P1", "expected_status": 401},
]

# Verified generated PyTest code (truncated for demo display, full file in generated_tests/)
LOGIN_GENERATED_CODE = '''import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_login_001():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': '123456'}

    url = _build_url('/login', path_params)
    response = requests.request(
        method="POST", url=url,
        params=query_params, headers=headers, json=body,
    )
    assert response.status_code == 200


def test_login_002():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'password': '123456'}

    url = _build_url('/login', path_params)
    response = requests.request(
        method="POST", url=url,
        params=query_params, headers=headers, json=body,
    )
    assert response.status_code == 422


def test_login_009():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'wronguser', 'password': '123456'}

    url = _build_url('/login', path_params)
    response = requests.request(
        method="POST", url=url,
        params=query_params, headers=headers, json=body,
    )
    assert response.status_code == 401
'''

# ---------------------------------------------------------------------------
# Users Demo — Verified E2E (Five-stage orchestration, 2026-09-23)
# Source: generated_tests/test_users_user_id.py + run_ai_testing_pipeline
# 9 tests generated; 4 failed because LLM assumed schema constraints not declared
# in OpenAPI (expected positive int / int32, but schema only says type:integer).
# Agent correctly classified as non-test_code_error, refused to repair.
# ---------------------------------------------------------------------------

USERS_TEST_CASES = [
    {"case_id": "GET_USER_001", "title": "Get user with valid ID", "type": "normal", "priority": "P0", "expected_status": 200},
    {"case_id": "GET_USER_002", "title": "Get user (duplicate valid ID)", "type": "normal", "priority": "P1", "expected_status": 200},
    {"case_id": "GET_USER_003", "title": "Get user with max int32 boundary", "type": "boundary", "priority": "P1", "expected_status": 200},
    {"case_id": "GET_USER_004", "title": "Missing user_id path parameter", "type": "exception", "priority": "P0", "expected_status": 422},
    {"case_id": "GET_USER_005", "title": "Non-integer user_id (string)", "type": "exception", "priority": "P0", "expected_status": 422},
    {"case_id": "GET_USER_006", "title": "Negative user_id", "type": "boundary", "priority": "P1", "expected_status": 422},
    {"case_id": "GET_USER_007", "title": "Zero user_id", "type": "boundary", "priority": "P1", "expected_status": 422},
    {"case_id": "GET_USER_008", "title": "Float user_id", "type": "exception", "priority": "P2", "expected_status": 422},
    {"case_id": "GET_USER_009", "title": "Oversized integer user_id", "type": "boundary", "priority": "P2", "expected_status": 422},
]

USERS_GENERATED_CODE = '''import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_get_user_001():
    path_params = {'user_id': 1}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url('/users/{user_id}', path_params)
    response = requests.request(
        method="GET", url=url,
        params=query_params, headers=headers, json=body,
    )
    assert response.status_code == 200


def test_get_user_004():
    path_params = {}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url('/users/{user_id}', path_params)
    response = requests.request(
        method="GET", url=url,
        params=query_params, headers=headers, json=body,
    )
    assert response.status_code == 422
'''

# ---------------------------------------------------------------------------
# Health Demo — Verified E2E (2026-09-23)
# Source: generated_tests/test_health.py (5/5 PASS)
# ---------------------------------------------------------------------------

HEALTH_TEST_CASES = [
    {"case_id": "HEALTH_001", "title": "Health check returns 200", "type": "normal", "priority": "P0", "expected_status": 200},
    {"case_id": "HEALTH_002", "title": "Health check ignores undefined query params", "type": "normal", "priority": "P1", "expected_status": 200},
    {"case_id": "HEALTH_003", "title": "Health check ignores empty params", "type": "boundary", "priority": "P2", "expected_status": 200},
    {"case_id": "HEALTH_004", "title": "Health check ignores custom headers", "type": "normal", "priority": "P1", "expected_status": 200},
    {"case_id": "HEALTH_005", "title": "Consecutive requests return consistent status", "type": "normal", "priority": "P1", "expected_status": 200},
]

HEALTH_GENERATED_CODE = '''import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_health_001():
    path_params = {}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url('/health', path_params)
    response = requests.request(
        method="GET", url=url,
        params=query_params, headers=headers, json=body,
    )
    assert response.status_code == 200
'''

# ---------------------------------------------------------------------------
# Stage 5 Repair Example — Verified (from reports/agent_report.json)
# Source: demo_agent_pipeline.py E2E (NameError -> test_code_error -> repair)
# ---------------------------------------------------------------------------

REPAIR_EXAMPLE = {
    "error": "NameError",
    "category": "test_code_error",
    "confidence": 0.92,
    "repair_allowed": True,
    "safety_validation": "passed",
    "repair_attempts": 1,
    "rerun": {
        "total": 1,
        "passed": 1,
        "failed": 0,
    },
}

# ---------------------------------------------------------------------------
# Pipeline Stages (shared structure for all demo scenarios)
# ---------------------------------------------------------------------------

PIPELINE_STAGES = [
    {"stage": 1, "name": "OpenAPI Parser", "status": "completed"},
    {"stage": 2, "name": "RAG + DeepSeek Test Design", "status": "completed"},
    {"stage": 3, "name": "PyTest Generator", "status": "completed"},
    {"stage": 4, "name": "Test Runner", "status": "completed"},
    {"stage": 5, "name": "Failure Analyzer", "status": "completed"},
]
