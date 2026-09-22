# -*- coding: utf-8 -*-
"""
真实 DeepSeek 全链路验收脚本（仅用于真实 LLM 验收，不使用任何 Mock）

链路：
    FastAPI Demo App (in-process)
        ↓ OpenAPI Parser
    结构化接口
        ↓ RAG（本地 Chroma 向量库，真实加载）
    检索测试规范
        ↓ DeepSeek（OpenAI-compatible，JSON mode）
    Test Cases JSON（严格 Schema 校验）
        ↓ Deterministic PyTest Generator
    generated_tests/test_login_real_llm.py（compile 校验）
        ↓ 启动 demo 服务 + Test Runner（真实 pytest 子进程）
    执行结果 -> reports/real_llm_e2e_report.json

无 OPENAI_API_KEY 时：
    打印 REAL_LLM_E2E = NOT RUN / Reason: OPENAI_API_KEY unavailable
    写入 NOT RUN 报告并正常退出，绝不用 Mock 冒充。

全程不打印 API Key。
"""

import os
import json
import datetime

from ai_testing_agent import config
from ai_testing_agent.api_schema_parser import parse_openapi
from ai_testing_agent.test_case_generator import (
    generate_test_cases_from_api,
    find_contract_conflicts,
)
from ai_testing_agent.test_code_generator import generate_pytest_code, save_pytest_code
from ai_testing_agent.test_runner import run_pytest


TARGET_API = "/login"
TARGET_METHOD = "POST"
REAL_LLM_TEST_FILE = os.path.join(
    config.GENERATED_TESTS_DIR, "test_login_real_llm.py"
)


def _write_report(report: dict) -> str:
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    path = os.path.join(config.REPORTS_DIR, config.REAL_LLM_REPORT_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


def _not_run_report(reason: str) -> dict:
    return {
        "llm_provider": "DeepSeek",
        "model": config.get_llm_config()["model"],
        "rag_used": False,
        "api": TARGET_API,
        "generated_cases": 0,
        "schema_valid_cases": 0,
        "generated_test_file": REAL_LLM_TEST_FILE,
        "compile_success": False,
        "pytest": {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0},
        "real_llm_called": False,
        "status": "NOT_RUN",
        "reason": reason,
        "timestamp": datetime.datetime.now().isoformat(),
    }


def _allowed_body_fields(api_spec: dict) -> set:
    """从 OpenAPI requestBody schema 提取允许的 body 字段名"""
    try:
        schema = api_spec["request_body"]["content"]["application/json"]["schema"]
        return set(schema.get("properties", {}).keys())
    except (KeyError, TypeError, AttributeError):
        return set()


def _validate_cases_against_schema(data: dict, api_spec: dict) -> tuple[list, list, list]:
    """
    严格校验真实 LLM 输出。

    返回:
      valid_cases: 既满足结构校验、又不存在“入参契约 vs 预期状态”矛盾的可执行用例列表
      problems:    全部问题（含结构问题与契约矛盾）的可读说明
      rejected:    被确定性守门拒绝的用例 [{"case_id", "reasons"}]

    校验项：api/method、test_cases 列表、case_id、expected_status、request 结构、
    body 字段不得超出 OpenAPI schema；以及字符串字段越过 min/maxLength 却预期非 422
    （此类请求必被参数校验拦截，预期 401/200 客观不成立，属无效用例）。
    """
    problems = []

    if not isinstance(data, dict):
        return [], ["顶层不是 dict"], []
    if data.get("api") != TARGET_API:
        problems.append(f"api 不匹配: {data.get('api')!r}")
    if str(data.get("method", "")).upper() != TARGET_METHOD:
        problems.append(f"method 不匹配: {data.get('method')!r}")

    cases = data.get("test_cases")
    if not isinstance(cases, list) or not cases:
        return [], problems + ["test_cases 不是非空 list"], []

    allowed_fields = _allowed_body_fields(api_spec)
    valid_cases = []
    rejected = []

    for i, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            problems.append(f"用例 {i} 不是 dict")
            continue
        ok = True
        if not case.get("case_id"):
            problems.append(f"用例 {i} 缺少 case_id")
            ok = False
        if "expected_status" not in case or not isinstance(
                case["expected_status"], int):
            problems.append(f"用例 {i} 缺少/非法 expected_status")
            ok = False
        req = case.get("request")
        if not isinstance(req, dict):
            problems.append(f"用例 {i} request 不是 dict")
            ok = False
        else:
            for key in ("path_params", "query_params", "headers", "body"):
                if key in req and not isinstance(req[key], dict):
                    problems.append(f"用例 {i} request.{key} 不是 dict")
                    ok = False
            # 不得生成 OpenAPI schema 中不存在的 body 字段
            if allowed_fields:
                body = req.get("body") or {}
                unknown = set(body.keys()) - allowed_fields
                if unknown:
                    problems.append(
                        f"用例 {i} body 含 schema 不存在字段: {sorted(unknown)}"
                    )
                    ok = False

        # 确定性守门：入参长度契约与预期状态矛盾的用例不可执行（拒绝而非篡改）
        conflicts = find_contract_conflicts(case, api_spec)
        if conflicts:
            cid = case.get("case_id", f"#{i}")
            for c in conflicts:
                problems.append(f"用例 {i}({cid}) 契约矛盾: {c}")
            rejected.append({"case_id": cid, "reasons": conflicts})
            ok = False

        if ok:
            valid_cases.append(case)

    return valid_cases, problems, rejected


def main():
    # ---------- 0. API Key 检查（不打印密钥） ----------
    if not config.has_llm_api_key():
        print("REAL_LLM_E2E = NOT RUN")
        print("Reason: OPENAI_API_KEY unavailable")
        report = _not_run_report("OPENAI_API_KEY unavailable")
        path = _write_report(report)
        print(f"[real-llm] 已写入 NOT RUN 报告: {path}")
        return 0

    llm_cfg = config.get_llm_config()
    provider = (
        "DeepSeek"
        if "deepseek" in (llm_cfg["base_url"] + llm_cfg["model"]).lower()
        else "OpenAI-compatible"
    )
    print(f"[real-llm] provider={provider} model={llm_cfg['model']}")

    # ---------- 1. Stage 1：进程内取 OpenAPI 并解析 ----------
    print("[Stage 1/5] FastAPI -> OpenAPI（in-process app.openapi()）")
    from ai_testing_agent.demos.demo_target_app import app
    openapi = app.openapi()
    interfaces = parse_openapi(openapi)
    api_spec = next(
        (it for it in interfaces
         if it.get("path") == TARGET_API and it.get("method") == TARGET_METHOD),
        None,
    )
    if api_spec is None:
        report = _not_run_report("未在 OpenAPI 中找到 POST /login")
        report["status"] = "FAIL"
        _write_report(report)
        print("REAL_LLM_E2E = FAIL (未找到目标接口)")
        return 1
    print(f"[Stage 1/5] 解析到目标接口，允许 body 字段: "
          f"{sorted(_allowed_body_fields(api_spec))}")

    # ---------- 2. Stage 2：RAG + 真实 DeepSeek ----------
    print("[Stage 2/5] RAG（真实加载 Chroma）-> DeepSeek -> Test Cases")
    rag_used = False
    vectorstore = None
    try:
        from ai_testing_agent.test_case_generator import load_vectorstore
        vectorstore = load_vectorstore()
        rag_used = True
        print("[Stage 2/5] RAG 向量库加载成功，将参与检索")
    except Exception as e:
        rag_used = False
        print(f"[Stage 2/5] WARNING: RAG 加载失败，降级为 api_spec + LLM: {e}")

    data = generate_test_cases_from_api(api_spec, top_k=3, vectorstore=vectorstore)
    if not data:
        report = _not_run_report("DeepSeek 用例生成失败（解析/校验未通过，已重试 1 次）")
        report["status"] = "FAIL"
        report["llm_provider"] = provider
        report["model"] = llm_cfg["model"]
        report["rag_used"] = rag_used
        report["real_llm_called"] = True
        report["reason"] = "LLM 返回无法通过校验（retry=1 后仍失败）"
        _write_report(report)
        print("REAL_LLM_E2E = FAIL (LLM 输出校验失败)")
        return 1

    generated_cases = len(data.get("test_cases", []))
    valid_cases, problems, rejected = _validate_cases_against_schema(data, api_spec)
    exec_count = len(valid_cases)
    # 每条用例恰归于：可执行(valid) / 契约矛盾被拒(rejected) / 结构非法。
    # 仅“可客观证明的契约矛盾”允许被确定性守门拦截；任何结构非法都必须判 FAIL。
    structural_invalid = generated_cases - exec_count - len(rejected)
    print(f"[Stage 2/5] LLM 生成 {generated_cases} 条；守门拒绝契约矛盾 "
          f"{len(rejected)} 条；可执行 {exec_count} 条")
    if rejected:
        for r in rejected:
            print(f"  [guard] 拒绝 {r['case_id']}: {'; '.join(r['reasons'])}")
    if structural_invalid:
        for p in problems:
            print(f"  [schema] {p}")

    # 用例类型 / 状态码覆盖（按实际落地执行的用例统计）
    types = sorted({c.get("test_type", "?") for c in valid_cases})
    statuses = sorted({c.get("expected_status") for c in valid_cases})
    print(f"[Stage 2/5] 覆盖 test_type={types} expected_status={statuses}")

    # 仅把通过结构校验与契约守门的用例交给确定性代码生成器（拒绝而非篡改）
    exec_data = dict(data)
    exec_data["test_cases"] = valid_cases

    # ---------- 3. Stage 3：确定性 PyTest 生成 + compile ----------
    print("[Stage 3/5] Deterministic PyTest Generator + compile()")
    code = generate_pytest_code(exec_data)
    compile_success = True
    compile_error = ""
    try:
        compile(code, "<real_llm_generated>", "exec")
    except SyntaxError as e:
        compile_success = False
        compile_error = str(e)
    os.makedirs(config.GENERATED_TESTS_DIR, exist_ok=True)
    save_pytest_code(code, REAL_LLM_TEST_FILE)
    print(f"[Stage 3/5] compile_success={compile_success} file={REAL_LLM_TEST_FILE}")

    # ---------- 4. Stage 4：启动服务 + 真实 pytest ----------
    print("[Stage 4/5] 启动 demo 服务并执行真实 pytest")
    with config.demo_server() as base_url:
        print(f"[Stage 4/5] 服务就绪 {base_url}，执行 pytest ...")
        run_result = run_pytest(
            test_target=REAL_LLM_TEST_FILE,
            base_url=base_url,
            report_dir=config.REPORTS_DIR,
            timeout=config.PYTEST_TIMEOUT,
        )

    pytest_summary = {
        "total": run_result["total"],
        "passed": run_result["passed"],
        "failed": run_result["failed"],
        "errors": run_result["errors"],
        "skipped": run_result["skipped"],
    }
    print(f"[Stage 4/5] pytest 结果: {pytest_summary}")

    # ---------- 5. 汇总并写真实报告 ----------
    # PASS 口径：可执行用例非空、compile 通过、pytest 全部通过；
    # 允许存在“契约矛盾被守门拒绝”的用例（透明记录），但不允许任何结构非法用例。
    passed_all = (
        compile_success
        and exec_count > 0
        and structural_invalid == 0
        and pytest_summary["total"] == exec_count
        and pytest_summary["failed"] == 0
        and pytest_summary["errors"] == 0
        and pytest_summary["passed"] == exec_count
    )

    report = {
        "llm_provider": provider,
        "model": llm_cfg["model"],
        "rag_used": rag_used,
        "api": TARGET_API,
        "generated_cases": generated_cases,
        "schema_valid_cases": exec_count,
        "executed_cases": exec_count,
        "rejected_contract_cases": rejected,
        "structural_invalid_cases": structural_invalid,
        "schema_problems": problems,
        "generated_test_file": REAL_LLM_TEST_FILE,
        "compile_success": compile_success,
        "compile_error": compile_error,
        "pytest": pytest_summary,
        "covered_test_types": types,
        "covered_expected_status": statuses,
        "real_llm_called": True,
        "status": "PASS" if passed_all else "FAIL",
        "timestamp": datetime.datetime.now().isoformat(),
    }
    path = _write_report(report)
    print(f"[real-llm] 报告已写入: {path}")

    if passed_all:
        print("REAL_LLM_E2E = PASS")
        return 0
    print("REAL_LLM_E2E = FAIL")
    print(f"  compile={compile_success} executable={exec_count}/"
          f"{generated_cases} rejected_contract={len(rejected)} "
          f"structural_invalid={structural_invalid} pytest={pytest_summary}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
