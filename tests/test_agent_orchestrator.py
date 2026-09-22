# -*- coding: utf-8 -*-
"""
agent_orchestrator.py 单元测试 - AI 测试流水线第五阶段

覆盖场景：
11. max_repair_attempts=1 -> 不出现无限重试
12. 第一次失败 -> repair -> 第二次 PASS -> final_status == passed
+ 全部 PASS 直接完成
+ api_defect 不修复、生成 Bug Report
+ 准入不满足时不修复
"""

import os
import json

import pytest

from ai_testing_agent import config
from ai_testing_agent.agent_orchestrator import run_agent_loop


# ---------- demo server fixture（复用 config.demo_server 统一生命周期） ----------

@pytest.fixture
def demo_server():
    """启动 demo_target_app uvicorn 子进程，返回 base_url；测试结束自动清理"""
    with config.demo_server(port=8765) as base_url:
        yield base_url


# 构造一份含 NameError 的测试（确定性识别为 test_code_error）
BUGGY = """import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_demo_001():
    body = {'username': 'test', 'password': '123456'}
    url = _build_url('/login', {})
    response = requests.request(method="POST", url=url, json=body)
    assert respnose.status_code == 200
"""

# 修复后的代码（mock LLM 返回）
FIXED = BUGGY.replace("respnose", "response")


def _mock_llm_fix(system, user, temperature=0.2, response_format=None, **kw):
    """Mock LLM：返回修复后的代码"""
    return FIXED


def _setup_gen_tests(tmp_path, content):
    """在 generated_tests 子目录创建测试文件，返回路径"""
    gen_dir = tmp_path / "generated_tests"
    gen_dir.mkdir(exist_ok=True)
    src = gen_dir / "test_demo.py"
    src.write_text(content, encoding="utf-8")
    # 同时准备 .backups 目录占位
    (gen_dir / ".backups").mkdir(exist_ok=True)
    return str(src)


# ---------- 场景 12: 第一次失败 -> repair -> 第二次 PASS ----------

def test_fail_then_repair_then_pass(tmp_path, demo_server):
    test_path = _setup_gen_tests(tmp_path, BUGGY)
    report_dir = str(tmp_path / "reports")
    result = run_agent_loop(
        test_target=test_path,
        base_url=demo_server,
        report_dir=report_dir,
        api_spec={"api": "/login", "method": "POST"},
        test_cases={},
        max_repair_attempts=1,
        timeout=60,
        llm_call=_mock_llm_fix,
    )
    # 初始应有失败（NameError）
    assert result["initial_run"]["failed"] + result["initial_run"]["errors"] >= 1
    assert result["repair_attempts"] == 1
    # 修复后重新运行：服务可用 + 代码已修复 -> PASS
    assert result["rerun"] is not None
    assert result["rerun"]["failed"] == 0
    assert result["rerun"]["errors"] == 0
    assert result["final_status"] == "passed"
    # backup 存在
    backup_dir = os.path.join(os.path.dirname(test_path), ".backups")
    assert os.path.isdir(backup_dir)
    # 验证 test 文件已被修复写入
    with open(test_path, encoding="utf-8") as f:
        written = f.read()
    assert "respnose" not in written
    assert "response.status_code" in written


# ---------- 场景 11: max_repair_attempts=1 -> 不出现无限重试 ----------

def test_max_repair_attempts_one_no_infinite_retry(tmp_path, demo_server):
    test_path = _setup_gen_tests(tmp_path, BUGGY)
    report_dir = str(tmp_path / "reports")

    call_count = {"n": 0}

    def counting_llm(system, user, temperature=0.2, response_format=None, **kw):
        call_count["n"] += 1
        return FIXED

    result = run_agent_loop(
        test_target=test_path,
        base_url=demo_server,
        report_dir=report_dir,
        max_repair_attempts=1,
        timeout=60,
        llm_call=counting_llm,
    )
    # 最多修复 1 次
    assert result["repair_attempts"] == 1
    assert call_count["n"] == 1  # LLM 只被调用一次
    assert result["final_status"] == "passed"


def test_max_repair_attempts_capped_at_two(tmp_path):
    test_path = _setup_gen_tests(tmp_path, BUGGY)
    report_dir = str(tmp_path / "reports")
    # 设置 >2 应被截断为 2
    result = run_agent_loop(
        test_target=test_path,
        base_url="http://127.0.0.1:1",
        report_dir=report_dir,
        max_repair_attempts=5,
        timeout=60,
        llm_call=_mock_llm_fix,
    )
    assert result["repair_attempts"] <= 2


# ---------- 全部 PASS 直接完成 ----------

def test_all_pass_no_repair(tmp_path):
    passing_code = (
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert True\n"
    )
    test_path = _setup_gen_tests(tmp_path, passing_code)
    report_dir = str(tmp_path / "reports")

    def llm_should_not_be_called(*a, **k):
        raise AssertionError("不应调用 LLM")

    result = run_agent_loop(
        test_target=test_path,
        base_url=None,
        report_dir=report_dir,
        max_repair_attempts=1,
        timeout=60,
        llm_call=llm_should_not_be_called,
    )
    assert result["final_status"] == "passed"
    assert result["repair_attempts"] == 0
    assert result["failures"] == []
    assert result["rerun"] is None


# ---------- api_defect -> 不修复、生成 Bug Report ----------

def test_api_defect_generates_bug_report_no_repair(tmp_path):
    # 用一个断言失败（不命中确定性）+ mock LLM 返回 api_defect
    code = (
        "def test_a():\n"
        "    x = 1\n"
        "    assert x == 2\n"
    )
    test_path = _setup_gen_tests(tmp_path, code)
    report_dir = str(tmp_path / "reports")

    def llm_returns_api_defect(system, user, temperature=0.2, response_format=None, **kw):
        return json.dumps({
            "category": "api_defect",
            "confidence": 0.88,
            "root_cause": "接口返回值与预期不符",
            "evidence": ["assert 1 == 2"],
            "recommended_action": "提交 Bug Report",
            "repair_allowed": False,
        })

    result = run_agent_loop(
        test_target=test_path,
        base_url=None,
        report_dir=report_dir,
        max_repair_attempts=1,
        timeout=60,
        llm_call=llm_returns_api_defect,
    )
    assert result["final_status"] == "failed"
    assert result["repair_attempts"] == 0  # api_defect 不修复
    # Bug Report 应已生成
    bug_dir = os.path.join(report_dir, "bug_reports")
    assert os.path.isdir(bug_dir)
    files = os.listdir(bug_dir)
    assert any(f.startswith("BUG-") and f.endswith(".md") for f in files)
    # 测试文件未被修改
    with open(test_path, encoding="utf-8") as f:
        assert f.read() == code


# ---------- 准入不满足（低 confidence）-> 不修复 ----------

def test_low_confidence_no_repair(tmp_path):
    code = (
        "def test_a():\n"
        "    assert 1 == 2\n"
    )
    test_path = _setup_gen_tests(tmp_path, code)
    report_dir = str(tmp_path / "reports")

    def llm_low_conf(system, user, temperature=0.2, response_format=None, **kw):
        return json.dumps({
            "category": "test_code_error",
            "confidence": 0.5,  # 低于 0.8
            "root_cause": "不确定",
            "evidence": [],
            "recommended_action": "人工",
            "repair_allowed": False,
        })

    result = run_agent_loop(
        test_target=test_path,
        base_url=None,
        report_dir=report_dir,
        max_repair_attempts=1,
        timeout=60,
        llm_call=llm_low_conf,
    )
    assert result["repair_attempts"] == 0
    assert result["final_status"] == "failed"


# ---------- agent_report.json 保存 ----------

def test_agent_report_saved(tmp_path):
    passing_code = "def test_a():\n    assert True\n"
    test_path = _setup_gen_tests(tmp_path, passing_code)
    report_dir = str(tmp_path / "reports")
    result = run_agent_loop(
        test_target=test_path,
        base_url=None,
        report_dir=report_dir,
        max_repair_attempts=1,
        timeout=60,
        llm_call=lambda *a, **k: None,
    )
    assert result["agent_report"]
    assert os.path.exists(result["agent_report"])
    with open(result["agent_report"], encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["final_status"] == result["final_status"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
