# -*- coding: utf-8 -*-
"""
测试执行器 - AI 测试流水线第四阶段

功能：Generated PyTest Code -> 自动执行 pytest -> 结构化 Test Report JSON

设计原则：
1. 使用当前 Python 解释器 (sys.executable -m pytest)，禁用 shell=True
2. 通过环境变量 TEST_BASE_URL 把 base_url 传给生成的测试文件
3. 使用 pytest 原生 --junitxml，用标准库 xml.etree.ElementTree 解析
4. success 区分：runner 本身异常 vs 测试用例失败（return_code != 0 但流程完成仍算 success=True）
5. 不 eval/exec 外部内容，只执行明确指定的 generated_tests 测试文件
"""

import os
import sys
import time
import json
import subprocess
import xml.etree.ElementTree as ET


def parse_junit_report(xml_file: str) -> dict:
    """
    解析 pytest 生成的 JUnit XML 报告

    参数:
        xml_file: JUnit XML 文件路径

    返回:
        {
            "total": int,
            "passed": int,
            "failed": int,
            "errors": int,
            "skipped": int,
            "duration": float,
            "pass_rate": float,   # total==0 时为 0.0
            "test_cases": [
                {
                    "name": str,
                    "classname": str,
                    "status": "passed"|"failed"|"error"|"skipped",
                    "duration": float,
                    "message": str,
                    "traceback": str
                }
            ]
        }

    异常:
        FileNotFoundError: XML 文件不存在
        ET.ParseError: XML 解析失败
    """
    if not os.path.exists(xml_file):
        raise FileNotFoundError(f"JUnit XML 报告不存在: {xml_file}")

    tree = ET.parse(xml_file)  # 可能抛 ET.ParseError
    root = tree.getroot()

    total = passed = failed = errors = skipped = 0
    duration = 0.0
    test_cases = []

    # 遍历所有 testcase 节点
    for testcase in root.iter("testcase"):
        name = testcase.get("name", "")
        classname = testcase.get("classname", "")
        try:
            dur = float(testcase.get("time", "0") or "0")
        except (ValueError, TypeError):
            dur = 0.0
        duration += dur

        failure_el = testcase.find("failure")
        error_el = testcase.find("error")
        skipped_el = testcase.find("skipped")

        status = "passed"
        message = ""
        traceback = ""
        if failure_el is not None:
            status = "failed"
            message = failure_el.get("message", "") or ""
            traceback = failure_el.text or ""
        elif error_el is not None:
            status = "error"
            message = error_el.get("message", "") or ""
            traceback = error_el.text or ""
        elif skipped_el is not None:
            status = "skipped"
            message = skipped_el.get("message", "") or ""

        total += 1
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed += 1
        elif status == "error":
            errors += 1
        elif status == "skipped":
            skipped += 1

        test_cases.append({
            "name": name,
            "classname": classname,
            "status": status,
            "duration": round(dur, 3),
            "message": message,
            "traceback": traceback,
        })

    # 兼容：testsuite 级别的 <error>（pytest collection error 有时挂在这里）
    for testsuite in root.iter("testsuite"):
        for err_el in testsuite.findall("error"):
            # 只统计不嵌套在 testcase 下的顶层 error
            if err_el in [tc.find("error") for tc in testsuite.findall("testcase")]:
                continue
            errors += 1
            total += 1
            test_cases.append({
                "name": "collection_error",
                "classname": testsuite.get("name", ""),
                "status": "error",
                "duration": 0.0,
                "message": err_el.get("message", "") or "",
                "traceback": err_el.text or "",
            })

    pass_rate = (passed / total) if total > 0 else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "duration": round(duration, 3),
        "pass_rate": round(pass_rate, 4),
        "test_cases": test_cases,
    }


def save_test_report(report: dict, output_file: str) -> str:
    """
    保存测试报告为 JSON

    参数:
        report: 报告 dict
        output_file: 输出路径

    返回:
        保存的文件路径
    """
    out_dir = os.path.dirname(output_file) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output_file


def run_pytest(
    test_target: str,
    base_url: str | None = None,
    report_dir: str = "reports",
    timeout: int = 120,
) -> dict:
    """
    使用当前 Python 解释器运行 pytest 并返回结构化报告

    参数:
        test_target: 测试文件/目录路径（明确指定的 generated_tests 文件）
        base_url: 被测服务地址，通过 TEST_BASE_URL 环境变量传递
        report_dir: 报告输出目录
        timeout: 超时秒数

    返回:
        {
            "success": bool,        # runner 是否正常完成（区分 runner 异常 vs 测试失败）
            "return_code": int,
            "test_target": str,
            "base_url": str,
            "total": int,
            "passed": int,
            "failed": int,
            "errors": int,
            "skipped": int,
            "pass_rate": float,
            "duration": float,
            "test_cases": [...],
            "stdout": str,
            "stderr": str,
            "junit_xml": str,
            "report_json": str,
            "error": str | None
        }
    """
    result = {
        "success": False,
        "return_code": None,
        "test_target": test_target,
        "base_url": base_url,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "pass_rate": 0.0,
        "duration": 0.0,
        "test_cases": [],
        "stdout": "",
        "stderr": "",
        "junit_xml": "",
        "report_json": "",
        "error": None,
    }

    # 路径越界检查：在归一化之前检查原始片段中的 ".."，
    # 防止 "a/../../x" 这类路径被 normpath 解析后逃逸检测
    raw_segments = str(test_target).replace("\\", "/").split("/")
    if test_target and ".." in raw_segments:
        result["error"] = f"test_target 路径越界，拒绝执行: {test_target}"
        return result

    # 前置检查：test_target 必须存在
    if not test_target or not os.path.exists(test_target):
        result["error"] = f"test_target 不存在: {test_target}"
        return result

    os.makedirs(report_dir, exist_ok=True)
    junit_xml = os.path.abspath(os.path.join(report_dir, "pytest_result.xml"))
    # 清理旧 XML，避免解析到陈旧报告
    if os.path.exists(junit_xml):
        try:
            os.remove(junit_xml)
        except OSError:
            pass

    env = os.environ.copy()
    if base_url:
        env["TEST_BASE_URL"] = base_url

    cmd = [
        sys.executable, "-m", "pytest",
        test_target,
        "-q",
        f"--junitxml={junit_xml}",
    ]

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # 显式禁用 shell=True
        )
        result["return_code"] = proc.returncode
        result["stdout"] = proc.stdout or ""
        result["stderr"] = proc.stderr or ""
    except subprocess.TimeoutExpired as e:
        result["error"] = f"pytest 执行超时（{timeout}s）"
        result["stdout"] = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", "ignore") if e.stdout else "")
        result["stderr"] = (e.stderr or "") if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", "ignore") if e.stderr else "")
        result["duration"] = float(timeout)
        # 超时视为 runner 异常，success 保持 False
        return result
    except FileNotFoundError:
        result["error"] = "无法启动 pytest（找不到 Python 解释器）"
        return result
    except Exception as e:  # pragma: no cover - 防御性
        result["error"] = f"pytest 启动异常: {e}"
        return result

    result["duration"] = round(time.time() - start, 3)
    result["junit_xml"] = junit_xml

    # 若 XML 未生成，视为 runner 异常
    if not os.path.exists(junit_xml):
        result["error"] = "JUnit XML 报告未生成（pytest 可能 collection 失败或崩溃）"
        return result

    # 解析 JUnit XML
    try:
        parsed = parse_junit_report(junit_xml)
    except ET.ParseError as e:
        result["error"] = f"JUnit XML 解析失败: {e}"
        return result
    except Exception as e:
        result["error"] = f"JUnit XML 解析异常: {e}"
        return result

    # 合并解析结果
    for k in ("total", "passed", "failed", "errors", "skipped",
              "duration", "pass_rate", "test_cases"):
        result[k] = parsed[k]

    # success = runner 流程正常完成（即使有测试失败也 True）
    # 仅当 pytest 进程完成且 XML 解析成功即视为 True
    result["success"] = True

    # 保存 JSON 报告
    report_json = os.path.join(report_dir, "test_report.json")
    try:
        save_test_report(result, report_json)
        result["report_json"] = report_json
    except Exception as e:
        result["error"] = f"保存 JSON 报告失败: {e}"

    return result


if __name__ == "__main__":
    # 直接运行入口：以 generated_tests 为默认目标
    target = sys.argv[1] if len(sys.argv) > 1 else "generated_tests"
    base_url = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")
    rep = run_pytest(target, base_url=base_url)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
