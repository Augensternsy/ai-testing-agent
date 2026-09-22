# -*- coding: utf-8 -*-
"""
test_case_generator 的 API 模式测试（第二阶段）

使用 mock LLM，不真实调用 DeepSeek API。
使用 mock 隔离向量库（避免真实加载 BGE 模型导致测试缓慢），
仅 test_rag_degradation 故意让 load_vectorstore 抛异常以验证降级。

运行方式：
    python test_api_test_case_generator.py   # 直接运行
    pytest test_api_test_case_generator.py    # pytest 运行（若已安装）
"""

import json
import inspect
from unittest.mock import patch, MagicMock

from ai_testing_agent.test_case_generator import (
    generate_test_cases,            # 旧功能仍可用
    generate_test_cases_from_api,   # 新功能
    call_llm_api,
    _parse_api_response_json,
    _validate_api_cases,
    find_contract_conflicts,
)


def _build_login_api_spec():
    """构造一个 POST /login 接口结构（第一阶段 parse_openapi 的输出格式）"""
    return {
        "path": "/login",
        "method": "POST",
        "summary": "用户登录",
        "description": "通过用户名密码登录",
        "parameters": [],
        "request_body": {
            "required": True,
            "description": "",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "username": {"type": "string"},
                            "password": {"type": "string"},
                        },
                        "required": ["username", "password"],
                    }
                }
            },
        },
        "responses": {"200": {}, "422": {}},
    }


def _mock_llm_ok(system_prompt, user_prompt, **kwargs):
    """mock：返回合法结构化测试用例 JSON（覆盖 normal/boundary/exception）"""
    return json.dumps({
        "api": "/login",
        "method": "POST",
        "summary": "用户登录",
        "test_cases": [
            {
                "case_id": "LOGIN_001",
                "title": "正确用户名密码登录",
                "test_point": "正常登录",
                "test_type": "normal",
                "priority": "P0",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {},
                    "body": {"username": "test", "password": "123456"},
                },
                "expected_status": 200,
                "expected_result": "登录成功",
            },
            {
                "case_id": "LOGIN_002",
                "title": "缺少必填字段 username",
                "test_point": "必填缺失",
                "test_type": "exception",
                "priority": "P0",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {},
                    "body": {"password": "123456"},
                },
                "expected_status": 422,
                "expected_result": "返回参数校验错误",
            },
            {
                "case_id": "LOGIN_003",
                "title": "username 为空字符串",
                "test_point": "空值",
                "test_type": "exception",
                "priority": "P1",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {},
                    "body": {"username": "", "password": "123456"},
                },
                "expected_status": 422,
                "expected_result": "返回参数校验错误",
            },
            {
                "case_id": "LOGIN_004",
                "title": "username 类型错误（整数）",
                "test_point": "类型错误",
                "test_type": "exception",
                "priority": "P1",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {},
                    "body": {"username": 123, "password": "123456"},
                },
                "expected_status": 422,
                "expected_result": "返回参数校验错误",
            },
            {
                "case_id": "LOGIN_005",
                "title": "password 超长边界值",
                "test_point": "边界值",
                "test_type": "boundary",
                "priority": "P2",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {},
                    "body": {"username": "test", "password": "x" * 1000},
                },
                "expected_status": 200,
                "expected_result": "系统正常处理或按规则拒绝超长密码",
            },
        ],
    }, ensure_ascii=False)


# 隔离真实向量库：load_vectorstore 返回 mock，retrieve_context 返回空上下文
@patch("ai_testing_agent.test_case_generator.retrieve_context", return_value=("", []))
@patch("ai_testing_agent.test_case_generator.load_vectorstore", return_value=MagicMock())
def test_generate_from_api_basic(_mock_vs, _mock_rc):
    """1-5：POST /login 能生成结构化 test_cases，字段齐全"""
    api_spec = _build_login_api_spec()
    result = generate_test_cases_from_api(api_spec, llm_call=_mock_llm_ok)
    assert result is not None, "生成结果不应为 None"
    assert result["api"] == "/login"
    assert result["method"] == "POST"
    assert result["test_cases"], "test_cases 不能为空"
    required = ["case_id", "title", "test_type", "priority",
                "request", "expected_status", "expected_result"]
    for case in result["test_cases"]:
        for f in required:
            assert f in case, f"用例缺少字段 {f}"


def test_json_parse_correct():
    """6：JSON 解析正确（含 Markdown 代码块包裹也能解析）"""
    raw = "```json\n" + json.dumps(
        {"api": "/login", "method": "POST", "test_cases": []},
        ensure_ascii=False,
    ) + "\n```"
    data = _parse_api_response_json(raw)
    assert data is not None
    assert data["api"] == "/login"


@patch("ai_testing_agent.test_case_generator.retrieve_context", return_value=("", []))
@patch("ai_testing_agent.test_case_generator.load_vectorstore", return_value=MagicMock())
def test_retry_on_invalid_json(_mock_vs, _mock_rc):
    """7：LLM 返回非法 JSON 时能重试一次并成功"""
    call_count = {"n": 0}

    def flaky_llm(system_prompt, user_prompt, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "这不是合法 JSON {{{{"
        return _mock_llm_ok(system_prompt, user_prompt, **kwargs)

    api_spec = _build_login_api_spec()
    result = generate_test_cases_from_api(api_spec, llm_call=flaky_llm)
    assert result is not None, "重试后应成功"
    assert call_count["n"] == 2, "应调用 2 次（首次失败 + 重试 1 次）"
    assert result["api"] == "/login"


def test_rag_degradation():
    """8：RAG 加载失败时能降级继续生成（不阻断）"""
    api_spec = _build_login_api_spec()
    with patch("ai_testing_agent.test_case_generator.load_vectorstore",
               side_effect=RuntimeError("no chroma db")):
        result = generate_test_cases_from_api(api_spec, llm_call=_mock_llm_ok)
    assert result is not None, "RAG 失败应降级继续生成"
    assert result["api"] == "/login"


def test_old_generate_cases_exists():
    """9：旧 generate_test_cases() 未被删除，且 call_llm_api 支持新可选参数"""
    assert callable(generate_test_cases), "旧函数 generate_test_cases 应保留"
    sig = inspect.signature(call_llm_api)
    assert "temperature" in sig.parameters
    assert "response_format" in sig.parameters


def test_validate_rejects_missing_fields():
    """校验：缺少必需字段判为无效"""
    bad = {"api": "/login", "method": "POST",
           "test_cases": [{"case_id": "X"}]}  # 缺多个字段
    assert _validate_api_cases(bad, _build_login_api_spec()) is False


# ---------- 入参契约 vs 预期状态 守门（find_contract_conflicts） ----------

def _bounded_spec(max_len=128):
    """声明 password maxLength 的 api_spec（对齐 demo_target_app 的真实契约）"""
    spec = _build_login_api_spec()
    props = spec["request_body"]["content"]["application/json"]["schema"]["properties"]
    props["password"] = {"type": "string", "maxLength": max_len}
    return spec


def _case(expected_status, password="123456", username="test"):
    return {
        "case_id": "C1",
        "expected_status": expected_status,
        "request": {"path_params": {}, "query_params": {}, "headers": {},
                    "body": {"username": username, "password": password}},
    }


def test_contract_conflict_overlong_password_expecting_401():
    """超长密码（>maxLength）却预期 401：必先触发 422，判为矛盾（LLM 高频无效用例）"""
    conflicts = find_contract_conflicts(_case(401, password="x" * 140), _bounded_spec())
    assert len(conflicts) == 1
    assert "password" in conflicts[0] and "maxLength=128" in conflicts[0]


def test_contract_ok_overlong_password_expecting_422():
    """超长密码且预期 422：这是正确的边界用例，不构成矛盾"""
    assert find_contract_conflicts(_case(422, password="x" * 140), _bounded_spec()) == []


def test_contract_ok_short_wrong_password_expecting_401():
    """普通长度的错误密码预期 401：合法（不得误拒，否则会掩盖真实鉴权路径）"""
    assert find_contract_conflicts(_case(401, password="wrongpass"), _bounded_spec()) == []


def test_contract_ok_normal_login_expecting_200():
    """合法凭据预期 200：无矛盾"""
    assert find_contract_conflicts(_case(200), _bounded_spec()) == []


def test_contract_no_conflict_when_schema_has_no_limit():
    """schema 未声明长度约束时守门保持沉默（保守，不凭空推断）"""
    assert find_contract_conflicts(
        _case(401, password="x" * 999), _build_login_api_spec()
    ) == []


def test_validate_accepts_valid():
    """校验：合法结构判为有效"""
    data = _parse_api_response_json(_mock_llm_ok("", ""))
    assert _validate_api_cases(data, _build_login_api_spec()) is True


def main():
    """直接运行入口：依次执行所有 test_ 函数"""
    tests = [
        test_generate_from_api_basic,
        test_json_parse_correct,
        test_retry_on_invalid_json,
        test_rag_degradation,
        test_old_generate_cases_exists,
        test_validate_rejects_missing_fields,
        test_validate_accepts_valid,
    ]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n全部 {len(tests)} 个测试通过 ✓")


if __name__ == "__main__":
    main()
