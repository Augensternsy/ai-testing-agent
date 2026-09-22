# -*- coding: utf-8 -*-
"""
Agent 编排器 - AI 测试流水线第五阶段

功能：编排 Agent Repair Loop

流程：
    run_pytest()
        ↓
    全部 PASS？
        ├─ Yes → 完成
        └─ No
             ↓
         获取 failed/error cases
             ↓
         analyze_failure()
             ↓
         是否允许 Repair？
             ├─ No → 输出分析报告，结束
             └─ Yes
                  ↓
             repair_test_code()
                  ↓
             compile / safety check
                  ↓
             backup
                  ↓
             保存 repaired test
                  ↓
             run_pytest() 再执行一次
                  ↓
         Final Report

严格限制：
- max_repair_attempts 默认 1，最多 2，禁止 while True 无限循环
- 每次修复留下 audit log
- 只允许修改 generated_tests/ 下文件
- api_defect 不修复测试，只生成 Bug Report
"""

import os
import json
import datetime
from . import config

from .test_runner import run_pytest
from .failure_analyzer import analyze_failure
from .safe_test_repair import (
    repair_test_code,
    validate_repaired_code,
    is_repair_allowed,
    apply_repair_to_file,
)


def _read_test_code(test_target: str) -> str:
    """读取测试文件源码用于分析"""
    try:
        with open(test_target, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _summary(report: dict) -> dict:
    """从 run_pytest 报告提取汇总"""
    return {
        "total": report.get("total", 0),
        "passed": report.get("passed", 0),
        "failed": report.get("failed", 0),
        "errors": report.get("errors", 0),
    }


def _write_bug_report(
    test_name: str,
    failure: dict,
    analysis: dict,
    test_case: dict | None,
    api_spec: dict | None,
    test_code: str,
    report_dir: str,
) -> str:
    """
    为 api_defect 生成 Bug Report（markdown）

    证据不充分时不写 "Confirmed Bug"，写 "Potential API Defect"
    """
    bug_dir = os.path.join(report_dir, "bug_reports")
    os.makedirs(bug_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() else "-" for c in test_name).strip("-")
    ts = datetime.datetime.now().strftime("%Y%m%d")
    path = os.path.join(bug_dir, f"BUG-{safe_name}-{ts}.md")

    confidence = analysis.get("confidence", 0)
    title_prefix = "Confirmed API Defect" if confidence >= 0.85 else "Potential API Defect"

    content = f"""# {title_prefix}: {test_name}

- **Date**: {datetime.datetime.now().isoformat()}
- **Category**: {analysis.get('category', 'unknown')}
- **Confidence**: {analysis.get('confidence', 0)}

## API
```json
{json.dumps(api_spec or {}, ensure_ascii=False, indent=2)}
```

## Test Case
```json
{json.dumps(test_case or {}, ensure_ascii=False, indent=2)}
```

## Expected
{failure.get('message', '')}

## Actual
{failure.get('traceback', '')}

## Failure Message
{failure.get('message', '')}

## Traceback
```
{failure.get('traceback', '')}
```

## Test Code
```
{test_code}
```

## Agent Analysis
- **root_cause**: {analysis.get('root_cause', '')}
- **evidence**: {json.dumps(analysis.get('evidence', []), ensure_ascii=False)}
- **recommended_action**: {analysis.get('recommended_action', '')}

> 本报告由 AI Agent 自动生成。除非证据完全充分，否则仅为 Potential Defect，需人工确认。
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def run_agent_loop(
    test_target: str,
    base_url: str | None = None,
    report_dir: str = config.REPORTS_DIR,
    api_spec: dict | None = None,
    test_cases: dict | None = None,
    max_repair_attempts: int = config.DEFAULT_REPAIR_ATTEMPTS,
    timeout: int = config.PYTEST_TIMEOUT,
    llm_call=None,
) -> dict:
    """
    执行 Agent Repair Loop

    参数:
        test_target: 测试文件路径（必须位于 generated_tests/ 下才能被修复）
        base_url: 被测服务地址
        report_dir: 报告输出目录
        api_spec: 对应 API Schema（用于分析与修复）
        test_cases: {test_name: test_case_dict} 映射，用于分析与修复
        max_repair_attempts: 最大修复尝试次数（默认 1，最多 2）
        timeout: pytest 超时秒数
        llm_call: 可选 LLM 调用函数

    返回:
        {
            "initial_run": {total, passed, failed},
            "failures": [
                {
                    "test": str,
                    "analysis": {...},
                    "repair_attempted": bool,
                    "repair_success": bool
                }
            ],
            "rerun": {total, passed, failed} | None,
            "final_status": "passed"|"failed",
            "repair_attempts": int,
            "agent_report": str
        }
    """
    # 限制 max_repair_attempts（禁止无限循环）
    max_repair_attempts = max(0, min(max_repair_attempts, config.MAX_REPAIR_ATTEMPTS))

    os.makedirs(report_dir, exist_ok=True)

    failures_out = []
    repair_attempts = 0

    # ---------- 1. 初次运行 ----------
    print(f"[Agent] 初次运行 pytest: {test_target}")
    initial = run_pytest(test_target, base_url=base_url,
                        report_dir=report_dir, timeout=timeout)
    initial_summary = _summary(initial)

    # 全部 PASS → 直接完成（显式括号消除 or/and 优先级歧义）
    failing_cases = [
        tc for tc in initial.get("test_cases", [])
        if tc.get("status") in ("failed", "error")
    ]

    if (not failing_cases) or (initial_summary["failed"] == 0
                               and initial_summary["errors"] == 0):
        result = {
            "initial_run": initial_summary,
            "failures": [],
            "rerun": None,
            "final_status": "passed" if initial.get("success") else "failed",
            "repair_attempts": 0,
        }
        _save_agent_report(result, report_dir)
        return result

    # ---------- 2. 逐个分析失败 ----------
    test_code = _read_test_code(test_target)

    # 收集可修复的失败（仅 test_code_error + 满足准入）
    repairable = []  # [(failure, analysis, test_case)]

    for tc in failing_cases:
        test_name = tc.get("name", "")
        case = None
        if isinstance(test_cases, dict):
            case = test_cases.get(test_name)

        analysis = analyze_failure(
            failure=tc,
            test_code=test_code,
            test_case=case,
            api_spec=api_spec,
            llm_call=llm_call,
        )

        allowed, _ = is_repair_allowed(analysis)

        # api_defect 生成 Bug Report，不修复
        if analysis.get("category") == "api_defect":
            _write_bug_report(test_name, tc, analysis, case, api_spec,
                              test_code, report_dir)

        failures_out.append({
            "test": test_name,
            "analysis": {
                "category": analysis.get("category"),
                "confidence": analysis.get("confidence"),
                "root_cause": analysis.get("root_cause"),
                "repair_allowed": analysis.get("repair_allowed"),
            },
            "repair_attempted": False,
            "repair_success": False,
        })

        if allowed:
            repairable.append((tc, analysis, case))

    # ---------- 3. 修复（若允许且有配额） ----------
    rerun_summary = None
    final_status = "failed"

    if repairable and repair_attempts < max_repair_attempts:
        # 修复：对整份测试文件做一次综合修复（基于第一个可修复失败的 analysis）
        # 若有多个可修复失败，取合并的 root_cause 证据
        combined_analysis = repairable[0][1]
        # 合并所有可修复失败的 evidence / root_cause
        all_evidence = []
        all_root_causes = []
        for _f, a, _c in repairable:
            all_evidence.extend(a.get("evidence", []))
            all_root_causes.append(a.get("root_cause", ""))
        combined_analysis = dict(combined_analysis)
        combined_analysis["evidence"] = list(dict.fromkeys(all_evidence))
        combined_analysis["root_cause"] = " || ".join(filter(None, all_root_causes))

        print(f"[Agent] 尝试修复测试代码（attempt {repair_attempts + 1}/{max_repair_attempts}）")
        repaired_code = repair_test_code(
            original_code=test_code,
            analysis=combined_analysis,
            test_case=repairable[0][2],
            api_spec=api_spec,
            llm_call=llm_call,
        )

        if repaired_code is not None:
            # 二次安全验证（orchestrator 层冗余校验）
            ok, msg = validate_repaired_code(test_code, repaired_code)
            if ok:
                try:
                    apply_repair_to_file(
                        original_path=test_target,
                        repaired_code=repaired_code,
                        analysis=combined_analysis,
                        attempt=repair_attempts + 1,
                    )
                    repair_attempts += 1
                    print(f"[Agent] 修复已写入并备份: {test_target}")

                    # 标记修复尝试
                    for entry in failures_out:
                        entry["repair_attempted"] = True

                    # 重新运行
                    print("[Agent] 重新运行 pytest")
                    rerun = run_pytest(test_target, base_url=base_url,
                                       report_dir=report_dir, timeout=timeout)
                    rerun_summary = _summary(rerun)

                    # 修复成功判定：rerun 中原本失败的用例全部转为 passed
                    rerun_failures = [
                        tc for tc in rerun.get("test_cases", [])
                        if tc.get("status") in ("failed", "error")
                    ]
                    if not rerun_failures and rerun_summary["failed"] == 0 \
                            and rerun_summary["errors"] == 0:
                        final_status = "passed"
                        for entry in failures_out:
                            entry["repair_success"] = True
                    else:
                        final_status = "failed"
                except Exception as e:
                    print(f"[Agent] 应用修复失败: {e}")
                    final_status = "failed"
            else:
                print(f"[Agent] 修复后安全验证失败: {msg}")
                final_status = "failed"
        else:
            print("[Agent] repair_test_code 返回 None（准入不满足/LLM 失败/验证失败）")
            final_status = "failed"
    else:
        # 不允许修复或无配额
        if not repairable:
            print("[Agent] 无可修复失败（均为非 test_code_error 或准入不满足），仅输出分析报告")
        else:
            print(f"[Agent] 已达 max_repair_attempts={max_repair_attempts}，停止修复")
        final_status = "failed"

    result = {
        "initial_run": initial_summary,
        "failures": failures_out,
        "rerun": rerun_summary,
        "final_status": final_status,
        "repair_attempts": repair_attempts,
    }
    _save_agent_report(result, report_dir)
    return result


def _save_agent_report(result: dict, report_dir: str) -> str:
    """保存 reports/agent_report.json"""
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, config.AGENT_REPORT_NAME)
    result["agent_report"] = path
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    # 自测入口：对一个不存在的目标快速返回
    r = run_agent_loop("generated_tests/test_login.py",
                       base_url="http://127.0.0.1:8000",
                       max_repair_attempts=1)
    print(json.dumps(r, ensure_ascii=False, indent=2))
