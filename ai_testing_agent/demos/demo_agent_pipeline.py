# -*- coding: utf-8 -*-
"""
第五阶段 Agent Repair Loop 端到端演示

构造一个可控的 test_code_error（拼写错误 respnose -> NameError）：

    Generated Test (含 NameError)
        ↓
    pytest FAILED
        ↓
    Failure Analyzer（确定性识别 NameError -> test_code_error）
        ↓
    Safe Repair（备份 -> 修复 -> 安全验证）
        ↓
    重新运行
        ↓
    PASS

LLM 策略（真实与 Mock 严格区分，禁止冒充）：
- 若 OPENAI_API_KEY 可用（.env 已由 config 自动加载）：使用真实 DeepSeek 修复
- 否则：使用 Mock LLM（仅针对本 demo 的 respnose 拼写做定向修复），
  并明确标注 REAL_LLM_E2E = NOT RUN。
- 全程不打印 API Key。
"""

import os
import re
import json

from ai_testing_agent import config
from ai_testing_agent.agent_orchestrator import run_agent_loop


DEMO_TEST_FILE = os.path.join(config.GENERATED_TESTS_DIR, "test_agent_demo.py")


# ---------- 构造可控的 test_code_error ----------

BUGGY_CODE = """import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_agent_demo_001():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': '123456'}

    url = _build_url('/login', path_params)

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert respnose.status_code == 200  # 故意拼写错误: respnose -> NameError
"""


def _write_buggy_test():
    os.makedirs(config.GENERATED_TESTS_DIR, exist_ok=True)
    with open(DEMO_TEST_FILE, "w", encoding="utf-8") as f:
        f.write(BUGGY_CODE)
    print(f"[demo] 已写入含 test_code_error 的测试: {DEMO_TEST_FILE}")


# ---------- Mock LLM（仅本 demo 使用，定向修复 respnose） ----------

def _mock_llm_call(system_prompt, user_prompt, temperature=0.2,
                   response_format=None, **kwargs):
    """无 API Key 时的降级 Mock：定向把 respnose 修复为 response（明确标注 Mock）。

    待修复文件即本 demo 写入的 BUGGY_CODE，直接对其做确定性替换，
    不依赖提示词中的代码围栏格式，避免与修复 prompt 模板耦合。
    """
    return BUGGY_CODE.replace("respnose", "response")


def _make_llm_call():
    """根据 API Key 可用性返回 LLM 调用器；None 表示走真实 call_llm_api"""
    if config.has_llm_api_key():
        print("[demo] OPENAI_API_KEY 已配置，使用真实 LLM 修复")
        return None
    print("[demo] OPENAI_API_KEY 未配置，使用 Mock LLM（定向修复 respnose）")
    print("REAL_LLM_E2E = NOT RUN")
    print("Reason: OPENAI_API_KEY unavailable")
    return _mock_llm_call


def main():
    _write_buggy_test()
    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    llm_call = _make_llm_call()

    with config.demo_server() as base_url:
        print(f"[demo] 服务就绪: {base_url}/health")
        print("[demo] 执行 Agent Repair Loop ...")
        result = run_agent_loop(
            test_target=DEMO_TEST_FILE,
            base_url=base_url,
            report_dir=config.REPORTS_DIR,
            api_spec={"api": "/login", "method": "POST"},
            test_cases={
                "test_agent_demo_001": {
                    "case_id": "AGENT_DEMO_001",
                    "request": {"body": {"username": "test", "password": "123456"}},
                    "expected_status": 200,
                }
            },
            max_repair_attempts=config.DEFAULT_REPAIR_ATTEMPTS,
            timeout=60,
            llm_call=llm_call,
        )

    print("\n========== Agent Final Report ==========")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n========== Demo Summary ==========")
    print(f"initial_run   : {result['initial_run']}")
    print(f"failures      : {len(result['failures'])} 条")
    for f in result["failures"]:
        print(f"  - {f['test']}: {f['analysis']['category']} "
              f"(conf={f['analysis']['confidence']}, "
              f"repair_allowed={f['analysis']['repair_allowed']})")
    print(f"rerun         : {result['rerun']}")
    print(f"final_status  : {result['final_status']}")
    print(f"repair_attempts: {result['repair_attempts']}")

    if result["final_status"] == "passed":
        print("\n[demo] Agent Repair Loop 成功：失败 -> 分析 -> 修复 -> 重新运行 -> PASS")
        return 0
    print("\n[demo] Agent Repair Loop 未达到 PASS")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
