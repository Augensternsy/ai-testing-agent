# -*- coding: utf-8 -*-
"""
test_runner.py 单元测试 - AI 测试流水线第四阶段

覆盖 10 类场景，使用临时 pytest 文件隔离，不连接真实线上服务。
不依赖 DeepSeek / 真实服务。
"""

import os
import json
import time
import pytest

from ai_testing_agent.test_runner import run_pytest, parse_junit_report, save_test_report


# ---------- helpers ----------

def _write(tmp_path, name, content):
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    return str(f)


# ---------- 1. 全部 PASS ----------

def test_all_pass(tmp_path):
    code = (
        "def test_a():\n"
        "    assert 1 + 1 == 2\n\n"
        "def test_b():\n"
        "    assert 'a' in 'abc'\n"
    )
    target = _write(tmp_path, "test_pass.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    assert res["success"] is True
    assert res["return_code"] == 0
    assert res["total"] == 2
    assert res["passed"] == 2
    assert res["failed"] == 0
    assert res["errors"] == 0
    assert res["skipped"] == 0


# ---------- 2. 存在 FAILED ----------

def test_has_failed(tmp_path):
    code = (
        "def test_ok():\n"
        "    assert True\n\n"
        "def test_fail():\n"
        "    assert 1 == 2, 'expected failure'\n"
    )
    target = _write(tmp_path, "test_fail.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    # 测试失败但 runner 正常完成 -> success=True
    assert res["success"] is True
    assert res["return_code"] != 0
    assert res["total"] == 2
    assert res["passed"] == 1
    assert res["failed"] == 1
    assert res["errors"] == 0


# ---------- 3. collection / import ERROR ----------

def test_collection_import_error(tmp_path):
    code = "import nonexistent_module_xyz_123\n\ndef test_x():\n    assert True\n"
    target = _write(tmp_path, "test_import_err.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    # collection error 时 runner 仍正常完成 -> success=True（有 errors 统计）
    assert res["success"] is True
    assert res["return_code"] != 0
    assert res["errors"] >= 1
    # stdout/stderr 里应能看到 ModuleNotFoundError / ImportError 痕迹
    combined = (res["stdout"] or "") + (res["stderr"] or "")
    assert "nonexistent_module" in combined or res["errors"] >= 1


# ---------- 4. report 统计数量正确 ----------

def test_report_counts_correct(tmp_path):
    code = (
        "import pytest\n\n"
        "def test_a():\n    assert True\n\n"
        "def test_b():\n    assert True\n\n"
        "def test_c():\n    assert False\n\n"
        "@pytest.mark.skip(reason='skip')\n"
        "def test_d():\n    assert True\n"
    )
    target = _write(tmp_path, "test_counts.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    assert res["total"] == 4
    assert res["passed"] == 2
    assert res["failed"] == 1
    assert res["skipped"] == 1


# ---------- 5. pass_rate 正确 ----------

def test_pass_rate_correct(tmp_path):
    code = (
        "def test_a():\n    assert True\n\n"
        "def test_b():\n    assert True\n\n"
        "def test_c():\n    assert True\n\n"
        "def test_d():\n    assert False\n"
    )
    target = _write(tmp_path, "test_rate.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    assert res["total"] == 4
    assert res["passed"] == 3
    # 3/4 = 0.75
    assert abs(res["pass_rate"] - 0.75) < 1e-6


def test_pass_rate_zero_when_no_tests(tmp_path):
    # total==0 -> pass_rate = 0.0
    assert parse_junit_report.__doc__ is not None  # 占位
    code = "import pytest\n\n"  # 无 test 函数 -> pytest 报 no tests ran
    target = _write(tmp_path, "test_empty.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)
    # pytest no tests ran: return_code 5，XML 可能无 testcase
    assert res["success"] is True
    assert res["pass_rate"] == 0.0


# ---------- 6. traceback 能提取 ----------

def test_traceback_extracted(tmp_path):
    code = "def test_boom():\n    assert 1 == 2, 'boom traceback'\n"
    target = _write(tmp_path, "test_tb.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    assert res["failed"] == 1
    failed_cases = [tc for tc in res["test_cases"] if tc["status"] == "failed"]
    assert len(failed_cases) == 1
    fc = failed_cases[0]
    # message 或 traceback 中应能找到失败线索
    blob = (fc["message"] or "") + (fc["traceback"] or "")
    assert "boom traceback" in blob or "assert 1 == 2" in blob


# ---------- 7. test_target 不存在 ----------

def test_target_not_exist(tmp_path):
    res = run_pytest(str(tmp_path / "no_such_file.py"), report_dir=str(tmp_path), timeout=30)
    assert res["success"] is False
    assert res["error"] is not None
    assert "不存在" in res["error"]


# ---------- 7b. 路径越界（.. 逃逸）拒绝执行 ----------

def test_path_traversal_rejected(tmp_path):
    target = os.path.join(str(tmp_path), "..", "..", "escaped_evil.py")
    res = run_pytest(target, report_dir=str(tmp_path), timeout=30)
    assert res["success"] is False
    assert res["error"] is not None
    assert "越界" in res["error"]


# ---------- 8. timeout 能处理 ----------

def test_timeout_handled(tmp_path):
    code = "import time\n\ndef test_slow():\n    time.sleep(15)\n    assert True\n"
    target = _write(tmp_path, "test_slow.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=3)

    assert res["success"] is False
    assert res["error"] is not None
    assert "超时" in res["error"]


# ---------- 9. JSON report 能保存 ----------

def test_json_report_saved(tmp_path):
    code = "def test_a():\n    assert True\n"
    target = _write(tmp_path, "test_save.py", code)
    res = run_pytest(target, report_dir=str(tmp_path), timeout=60)

    assert res["report_json"]
    assert os.path.exists(res["report_json"])
    with open(res["report_json"], encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["total"] == res["total"]
    assert loaded["passed"] == res["passed"]


def test_save_test_report_writes_file(tmp_path):
    report = {"total": 5, "passed": 5, "failed": 0, "pass_rate": 1.0}
    out = str(tmp_path / "custom_report.json")
    save_test_report(report, out)
    with open(out, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded["passed"] == 5


# ---------- 10. JUnit XML 能正确解析 ----------

def test_parse_junit_report_basic(tmp_path):
    # 构造一个标准 JUnit XML 并直接解析
    xml = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="suite" tests="3" failures="1" errors="1" skipped="1" time="0.5">
    <testcase classname="m" name="test_pass" time="0.1"/>
    <testcase classname="m" name="test_fail" time="0.1">
      <failure message="assert failed">Traceback (most recent call last):
  assert False</failure>
    </testcase>
    <testcase classname="m" name="test_err" time="0.1">
      <error message="err">error traceback</error>
    </testcase>
    <testcase classname="m" name="test_skip" time="0.1">
      <skipped message="why"/>
    </testcase>
  </testsuite>
</testsuites>
"""
    xml_file = tmp_path / "result.xml"
    xml_file.write_text(xml, encoding="utf-8")

    parsed = parse_junit_report(str(xml_file))
    assert parsed["total"] == 4
    assert parsed["passed"] == 1
    assert parsed["failed"] == 1
    assert parsed["errors"] == 1
    assert parsed["skipped"] == 1
    assert abs(parsed["pass_rate"] - 0.25) < 1e-6

    failed_tc = [tc for tc in parsed["test_cases"] if tc["status"] == "failed"][0]
    assert "Traceback" in failed_tc["traceback"]


def test_parse_junit_xml_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_junit_report(str(tmp_path / "no.xml"))


# ---------- 额外：base_url 传递 + stdout 非空 ----------

def test_base_url_passed_and_stdout(tmp_path):
    # 验证 base_url 通过 TEST_BASE_URL 真的被传进子进程
    code = (
        "import os\n\n"
        "def test_env():\n"
        "    assert os.getenv('TEST_BASE_URL') == 'http://example.test:9999'\n"
    )
    target = _write(tmp_path, "test_env.py", code)
    res = run_pytest(target, base_url="http://example.test:9999",
                     report_dir=str(tmp_path), timeout=60)
    assert res["success"] is True
    assert res["passed"] == 1
    assert res["base_url"] == "http://example.test:9999"
    assert res["stdout"]  # pytest 至少有非空输出


if __name__ == "__main__":
    # 直接运行入口
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
