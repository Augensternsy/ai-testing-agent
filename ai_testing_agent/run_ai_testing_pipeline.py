# -*- coding: utf-8 -*-
"""
AI 测试流水线总编排器 - 五阶段统一入口

    Stage 1: FastAPI Source -> OpenAPI
    Stage 2: OpenAPI -> RAG + DeepSeek -> Test Cases JSON
    Stage 3: Test Cases JSON -> Deterministic PyTest Generator
    Stage 4: PyTest -> Execute -> Test Report JSON
    Stage 5: Failure -> Analyze -> Safe Repair -> Re-run

约束：
- 每个阶段打印 [Stage N/5] 日志
- 发生致命错误立即停止后续阶段（禁止吞掉异常继续）
- 配置与服务生命周期统一由 config 管理
"""

import os
import json

from . import config
from .config import get_logger

logger = get_logger("ai_testing.pipeline")


def _log_stage(n: int, msg: str):
    print(f"[Stage {n}/5] {msg}")


def _fatal(n: int, err: str):
    """致命错误：停止后续阶段"""
    logger.error(f"[Stage {n}/5] {err}")
    raise SystemExit(f"Stage {n} 失败，停止后续阶段: {err}")


# ---------- Stage 1 ----------

def stage1_openapi_from_source(out_dir: str = config.REPORTS_DIR) -> dict:
    """FastAPI 源码 -> OpenAPI（进程内 app.openapi()，无需起服务）"""
    _log_stage(1, "FastAPI 源码 -> OpenAPI")
    try:
        from ai_testing_agent.demos.demo_target_app import app
        openapi = app.openapi()
    except Exception as e:
        _fatal(1, f"获取 OpenAPI 失败: {e}")

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "openapi.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(openapi, f, ensure_ascii=False, indent=2)
    _log_stage(1, f"OpenAPI 已保存: {out_path}（{len(openapi.get('paths', {}))} paths）")
    return openapi


# ---------- Stage 2 ----------

def stage2_cases_from_openapi(openapi: dict, out_dir: str = config.REPORTS_DIR) -> list:
    """OpenAPI -> RAG + DeepSeek -> Test Cases JSON"""
    _log_stage(2, "OpenAPI -> RAG + DeepSeek -> Test Cases JSON")
    from .api_schema_parser import parse_openapi
    from .test_case_generator import generate_test_cases_from_api

    interfaces = parse_openapi(openapi)
    _log_stage(2, f"解析出 {len(interfaces)} 个接口")

    all_cases = []
    for iface in interfaces:
        try:
            cases = generate_test_cases_from_api(iface)
        except Exception as e:
            logger.warning(f"接口 {iface.get('path')} 用例生成异常: {e}")
            cases = None
        if cases is None:
            # 仅在 LLM 不可用/失败时使用确定性兜底，并明确告警（不静默掩盖）
            logger.warning(
                f"接口 {iface.get('path')} 使用确定性兜底用例（非 LLM 产物）"
            )
            cases = _deterministic_cases_fallback(iface)
        all_cases.append(cases)

    out_path = os.path.join(out_dir, "test_cases.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_cases, f, ensure_ascii=False, indent=2)
    total = sum(len(c.get("test_cases", [])) for c in all_cases)
    _log_stage(2, f"Test Cases 已保存: {out_path}（{total} 条用例）")
    return all_cases


def _deterministic_cases_fallback(iface: dict) -> dict:
    """无 LLM 时的确定性兜底（仅保证结构完整，质量弱于 LLM 设计）"""
    path = iface.get("path", "/")
    method = str(iface.get("method", "GET")).upper()
    return {
        "api": path,
        "method": method,
        "summary": iface.get("summary", ""),
        "test_cases": [
            {
                "case_id": f"{method}_{path}".replace("/", "_").strip("_") + "_001",
                "title": "正常请求（确定性兜底）",
                "test_point": "正常请求",
                "test_type": "normal",
                "priority": "P0",
                "request": {"path_params": {}, "query_params": {},
                            "headers": {}, "body": {}},
                "expected_status": 200,
                "expected_result": "请求成功",
            }
        ],
    }


# ---------- Stage 3 ----------

def stage3_pytest_from_cases(all_cases: list,
                             out_dir: str = config.GENERATED_TESTS_DIR) -> list:
    """Test Cases JSON -> Deterministic PyTest Generator"""
    _log_stage(3, "Test Cases JSON -> PyTest 代码（确定性模板，不调用 LLM）")
    from .test_code_generator import generate_test_file
    os.makedirs(out_dir, exist_ok=True)
    files = []
    for cases_data in all_cases:
        try:
            f = generate_test_file(cases_data, output_dir=out_dir)
        except Exception as e:
            _fatal(3, f"生成 PyTest 失败: {e}")
        files.append(f)
        _log_stage(3, f"生成: {f}")
    return files


# ---------- Stage 4 ----------

def stage4_run_pytest(test_files: list, base_url: str,
                      out_dir: str = config.REPORTS_DIR) -> list:
    """PyTest -> Execute -> Test Report JSON"""
    _log_stage(4, f"执行 pytest（base_url={base_url}）")
    from .test_runner import run_pytest
    reports = []
    for tf in test_files:
        rep = run_pytest(tf, base_url=base_url, report_dir=out_dir,
                         timeout=config.PYTEST_TIMEOUT)
        _log_stage(4, f"{tf}: passed={rep['passed']} failed={rep['failed']} "
                      f"errors={rep['errors']}")
        reports.append((tf, rep))
    return reports


# ---------- Stage 5 ----------

def stage5_agent_loop(test_files: list, base_url: str, all_cases: list,
                      out_dir: str = config.REPORTS_DIR, llm_call=None) -> list:
    """Failure -> Analyze -> Safe Repair -> Re-run"""
    _log_stage(5, "Failure Analyzer + Safe Repair Agent")
    from .agent_orchestrator import run_agent_loop
    from .test_code_generator import _normalize_func_name

    # 构建 test_name -> test_case 映射（enumerate 避免 O(n^2) index 查找）
    test_cases_map = {}
    for cd in all_cases:
        for idx, tc in enumerate(cd.get("test_cases", []), 1):
            test_cases_map[_normalize_func_name(tc.get("case_id"), idx)] = tc

    api_spec = all_cases[0] if all_cases else None
    results = []
    for tf in test_files:
        r = run_agent_loop(
            test_target=tf,
            base_url=base_url,
            report_dir=out_dir,
            api_spec=api_spec,
            test_cases=test_cases_map,
            max_repair_attempts=config.DEFAULT_REPAIR_ATTEMPTS,
            timeout=config.PYTEST_TIMEOUT,
            llm_call=llm_call,
        )
        _log_stage(5, f"{tf}: final_status={r['final_status']} "
                      f"repair_attempts={r['repair_attempts']}")
        results.append((tf, r))
    return results


def main():
    print("=" * 60)
    print("AI Agent 自动化测试平台 - 五阶段流水线")
    print("=" * 60)
    if config.has_llm_api_key():
        print(f"LLM: 已配置（model={config.get_llm_config()['model']}，密钥不打印）")
    else:
        print("LLM: 未配置 OPENAI_API_KEY（真实 LLM E2E = NOT RUN，将走确定性兜底）")

    # Stages 1-3 不需要被测服务
    openapi = stage1_openapi_from_source()
    all_cases = stage2_cases_from_openapi(openapi)
    test_files = stage3_pytest_from_cases(all_cases)

    # Stages 4-5 共享一个 demo 服务生命周期
    with config.demo_server() as base_url:
        stage4 = stage4_run_pytest(test_files, base_url)
        stage5 = stage5_agent_loop(test_files, base_url, all_cases)

    print("\n========== Pipeline Summary ==========")
    s4_total = sum(r["total"] for _, r in stage4)
    s4_pass = sum(r["passed"] for _, r in stage4)
    print(f"[Stage 1/5] OpenAPI paths: {len(openapi.get('paths', {}))}")
    print(f"[Stage 2/5] APIs: {len(all_cases)}")
    print(f"[Stage 3/5] Generated test files: {len(test_files)}")
    print(f"[Stage 4/5] Initial: {s4_pass}/{s4_total} passed")
    print(f"[Stage 5/5] Final statuses: {[r['final_status'] for _, r in stage5]}")


if __name__ == "__main__":
    main()
