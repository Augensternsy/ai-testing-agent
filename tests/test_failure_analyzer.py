# -*- coding: utf-8 -*-
"""
failure_analyzer.py 单元测试 - AI 测试流水线第五阶段

使用 Mock LLM，不调用真实 DeepSeek。
覆盖场景：
1. Connection refused -> environment_error -> 不允许 repair
2. SyntaxError -> test_code_error -> repair_allowed=true
3. unknown failure -> mock DeepSeek 返回结构化结果
4. confidence < 0.8 -> 不允许 repair（通过 is_repair_allowed）
5. api_defect -> 不允许 repair
6. test_data_error -> 不允许 repair
7. test_code_error + confidence >= 0.8 -> 允许 repair
"""

import pytest

from ai_testing_agent.failure_analyzer import (
    analyze_failure,
    _normalize_analysis,
)
from ai_testing_agent.safe_test_repair import is_repair_allowed


# ---------- 场景 1: Connection refused -> environment_error ----------

def test_connection_refused_classified_as_environment_error():
    failure = {
        "name": "test_x",
        "status": "error",
        "message": "ConnectionError: HTTPConnectionPool: Max retries exceeded",
        "traceback": (
            "requests.exceptions.ConnectionError: "
            "HTTPConnectionPool(host='127.0.0.1', port=8000): "
            "Max retries exceeded with url: /login (Caused by "
            "NewConnectionError('<urllib3.connection.HTTPConnection object>: "
            "Failed to establish a new connection: "
            "[Errno 111] Connection refused'))"
        ),
    }
    result = analyze_failure(failure, "import requests\n")
    assert result["category"] == "environment_error"
    assert result["confidence"] >= 0.9
    assert result["repair_allowed"] is False
    # 不允许 repair
    allowed, _ = is_repair_allowed(result)
    assert allowed is False


def test_read_timeout_classified_as_environment_error():
    failure = {
        "name": "test_t",
        "status": "failed",
        "message": "ReadTimeout",
        "traceback": "requests.exceptions.ReadTimeout: Read timed out",
    }
    result = analyze_failure(failure, "import requests\n")
    assert result["category"] == "environment_error"
    assert result["repair_allowed"] is False


# ---------- 场景 2: SyntaxError / NameError -> test_code_error ----------

def test_syntax_error_classified_as_test_code_error():
    failure = {
        "name": "test_s",
        "status": "failed",
        "message": "SyntaxError: invalid syntax",
        "traceback": (
            "E   File 'test_s.py', line 3\n"
            "E     def test_s(:\n"
            "E                ^\n"
            "E   SyntaxError: invalid syntax"
        ),
    }
    result = analyze_failure(failure, "def test_s(:\n    pass\n")
    assert result["category"] == "test_code_error"
    assert result["repair_allowed"] is True
    assert result["confidence"] >= 0.8


def test_name_error_classified_as_test_code_error():
    failure = {
        "name": "test_n",
        "status": "failed",
        "message": "NameError: name 'respnose' is not defined",
        "traceback": (
            "Traceback (most recent call last):\n"
            "  File 'test_n.py', line 5, in test_n\n"
            "    assert respnose.status_code == 200\n"
            "NameError: name 'respnose' is not defined"
        ),
    }
    result = analyze_failure(failure, "assert respnose.status_code == 200\n")
    assert result["category"] == "test_code_error"
    assert result["repair_allowed"] is True


# ---------- 场景 3: unknown failure -> mock DeepSeek ----------

def test_unknown_failure_uses_mock_llm():
    """确定性未命中时调用 LLM，LLM 返回结构化结果"""
    call_log = {"count": 0}

    def mock_llm(system_prompt, user_prompt, temperature=0.7,
                 response_format=None, **kwargs):
        call_log["count"] += 1
        # 模拟 LLM 返回 api_defect（充分证据场景）
        import json
        return json.dumps({
            "category": "api_defect",
            "confidence": 0.88,
            "root_cause": "接口返回字段与 schema 不符",
            "evidence": ["expected token, got error"],
            "recommended_action": "提交 Bug Report",
            "repair_allowed": False,
        })

    # 构造一个不命中确定性模式的失败（断言失败，无连接/语法/命名特征）
    failure = {
        "name": "test_a",
        "status": "failed",
        "message": "AssertionError: assert 401 == 200",
        "traceback": "assert response.status_code == 200\nE   assert 401 == 200",
    }
    result = analyze_failure(failure, "assert response.status_code == 200\n",
                             llm_call=mock_llm)
    assert call_log["count"] == 1  # LLM 确实被调用
    assert result["category"] == "api_defect"
    assert 0 <= result["confidence"] <= 1.0
    assert result["repair_allowed"] is False  # api_defect -> 强制 False


def test_unknown_failure_llm_returns_invalid_category_falls_back_to_unknown():
    def bad_llm(system_prompt, user_prompt, temperature=0.7,
               response_format=None, **kwargs):
        import json
        return json.dumps({"category": "nonsense", "confidence": 0.5})

    failure = {
        "name": "test_u",
        "status": "failed",
        "message": "AssertionError",
        "traceback": "assert False",
    }
    result = analyze_failure(failure, "assert False\n", llm_call=bad_llm)
    assert result["category"] == "unknown"


def test_no_api_key_no_llm_returns_unknown():
    """无 API Key 且确定性未命中 -> unknown（不伪造）"""
    # 确保环境无 key（测试进程内 monkeypatch env）
    import os
    old = os.environ.get("OPENAI_API_KEY")
    os.environ.pop("OPENAI_API_KEY", None)
    try:
        failure = {
            "name": "test_z",
            "status": "failed",
            "message": "AssertionError",
            "traceback": "assert False",
        }
        result = analyze_failure(failure, "assert False\n")
        assert result["category"] == "unknown"
        assert result["repair_allowed"] is False
    finally:
        if old is not None:
            os.environ["OPENAI_API_KEY"] = old


# ---------- 场景 4-7: is_repair_allowed 准入 ----------

def test_admission_confidence_below_0_8_rejected():
    analysis = {
        "category": "test_code_error",
        "confidence": 0.79,
        "repair_allowed": True,
    }
    allowed, reason = is_repair_allowed(analysis)
    assert allowed is False
    assert "0.80" in reason


def test_admission_api_defect_rejected():
    analysis = {
        "category": "api_defect",
        "confidence": 0.95,
        "repair_allowed": True,  # 即使 LLM 说 true，normalize 后强制 false
    }
    norm = _normalize_analysis(analysis)
    assert norm["repair_allowed"] is False
    allowed, _ = is_repair_allowed(norm)
    assert allowed is False


def test_admission_test_data_error_rejected():
    analysis = {
        "category": "test_data_error",
        "confidence": 0.95,
        "repair_allowed": True,
    }
    norm = _normalize_analysis(analysis)
    assert norm["repair_allowed"] is False
    allowed, _ = is_repair_allowed(norm)
    assert allowed is False


def test_admission_environment_error_rejected():
    analysis = {
        "category": "environment_error",
        "confidence": 0.95,
        "repair_allowed": True,
    }
    norm = _normalize_analysis(analysis)
    assert norm["repair_allowed"] is False


def test_admission_test_code_error_high_confidence_allowed():
    analysis = {
        "category": "test_code_error",
        "confidence": 0.92,
        "repair_allowed": True,
    }
    allowed, _ = is_repair_allowed(analysis)
    assert allowed is True


def test_admission_repair_allowed_false_rejected():
    analysis = {
        "category": "test_code_error",
        "confidence": 0.92,
        "repair_allowed": False,
    }
    allowed, _ = is_repair_allowed(analysis)
    assert allowed is False


def test_normalize_clamps_confidence():
    norm = _normalize_analysis({"category": "test_code_error", "confidence": 1.5})
    assert norm["confidence"] == 1.0
    norm = _normalize_analysis({"category": "test_code_error", "confidence": -0.3})
    assert norm["confidence"] == 0.0


def test_normalize_rejects_invalid_category():
    norm = _normalize_analysis({"category": "bug_defect", "confidence": 0.9})
    assert norm["category"] == "unknown"
    assert norm["repair_allowed"] is False


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
