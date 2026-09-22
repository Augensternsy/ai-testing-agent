# -*- coding: utf-8 -*-
"""
safe_test_repair.py 单元测试 - AI 测试流水线第五阶段

覆盖场景：
8. repaired code compile 失败 -> 拒绝写入
9. repaired code 含危险函数 -> 拒绝写入
10. backup 正确生成
+ 准入拒绝时不修复
+ mock LLM 返回合法修复 -> 通过验证
+ 删除 test_ 函数 -> 拒绝
+ apply_repair_to_file 写入并备份
+ 拒绝修改 generated_tests 之外的文件
"""

import os
import pytest

from ai_testing_agent.safe_test_repair import (
    repair_test_code,
    validate_repaired_code,
    is_repair_allowed,
    apply_repair_to_file,
    backup_test_file,
    _contains_dangerous_calls,
    _collect_test_funcs,
)


ORIGINAL = """import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_login_001():
    body = {'username': 'test', 'password': '123456'}
    url = _build_url('/login', {})
    response = requests.request(method="POST", url=url, json=body)
    assert respnose.status_code == 200
"""


# ---------- 场景 8: repaired code compile 失败 -> 拒绝 ----------

def test_validate_rejects_compile_failure():
    bad_code = "def test_x(:\n    pass\n"  # 语法错误
    ok, msg = validate_repaired_code(ORIGINAL, bad_code)
    assert ok is False
    assert "语法错误" in msg


def test_repair_rejects_compile_failure_via_mock_llm():
    analysis = {"category": "test_code_error", "confidence": 0.92, "repair_allowed": True}

    def bad_llm(system, user, temperature=0.2, response_format=None, **kw):
        return "def test_x(:\n    pass\n"  # 语法错误代码

    result = repair_test_code(ORIGINAL, analysis, llm_call=bad_llm)
    assert result is None


# ---------- 场景 9: repaired code 含危险函数 -> 拒绝 ----------

def test_validate_rejects_dangerous_os_system():
    dangerous = (
        "import os\n"
        "def test_a():\n"
        "    os.system('rm -rf /')\n"
        "    assert True\n"
        "def test_b():\n"
        "    assert True\n"
    )
    ok, msg = validate_repaired_code("def test_a():\n    assert True\ndef test_b():\n    assert True\n", dangerous)
    assert ok is False
    assert "危险" in msg


def test_validate_rejects_dangerous_eval_exec():
    code = (
        "def test_a():\n"
        "    eval('1+1')\n"
        "    assert True\n"
        "def test_b():\n"
        "    assert True\n"
    )
    ok, _ = validate_repaired_code(
        "def test_a():\n    assert True\ndef test_b():\n    assert True\n", code)
    assert ok is False


def test_validate_rejects_dangerous_subprocess_popen():
    code = (
        "import subprocess\n"
        "def test_a():\n"
        "    subprocess.Popen(['ls'])\n"
        "    assert True\n"
        "def test_b():\n"
        "    assert True\n"
    )
    ok, _ = validate_repaired_code(
        "def test_a():\n    assert True\ndef test_b():\n    assert True\n", code)
    assert ok is False


def test_validate_rejects_dangerous_shutil_rmtree():
    code = (
        "import shutil\n"
        "def test_a():\n"
        "    shutil.rmtree('/tmp/x')\n"
        "    assert True\n"
        "def test_b():\n"
        "    assert True\n"
    )
    ok, _ = validate_repaired_code(
        "def test_a():\n    assert True\ndef test_b():\n    assert True\n", code)
    assert ok is False


def test_contains_dangerous_calls_negative_for_clean_code():
    clean = (
        "import requests\n"
        "def test_a():\n"
        "    assert True\n"
    )
    assert _contains_dangerous_calls(clean) is False


# ---------- 反造假：禁止删除/注释 assert、skip/skipif/xfail ----------

def test_validate_rejects_commented_or_removed_assert():
    original = "def test_a():\n    x = 1\n    assert x == 1\n"
    # 断言被注释掉（assert 数量从 1 降到 0）
    repaired = "def test_a():\n    x = 1\n    # assert x == 1\n"
    ok, msg = validate_repaired_code(original, repaired)
    assert ok is False
    assert "assert" in msg


def test_validate_rejects_pytest_mark_skip_decorator():
    original = "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
    repaired = (
        "import pytest\n"
        "@pytest.mark.skip(reason='broken')\n"
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert True\n"
    )
    ok, msg = validate_repaired_code(original, repaired)
    assert ok is False
    assert "skip" in msg


def test_validate_rejects_pytest_skip_call():
    original = "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
    repaired = (
        "import pytest\n"
        "def test_a():\n"
        "    pytest.skip('skip at runtime')\n"
        "def test_b():\n"
        "    assert True\n"
    )
    ok, _ = validate_repaired_code(original, repaired)
    assert ok is False


def test_validate_rejects_xfail_decorator():
    original = "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
    repaired = (
        "import pytest\n"
        "@pytest.mark.xfail\n"
        "def test_a():\n    assert True\n"
        "def test_b():\n    assert True\n"
    )
    ok, _ = validate_repaired_code(original, repaired)
    assert ok is False


def test_validate_rejects_skipif_decorator():
    original = "def test_a():\n    assert True\n"
    repaired = (
        "import pytest\n"
        "@pytest.mark.skipif(True, reason='x')\n"
        "def test_a():\n    assert True\n"
    )
    ok, _ = validate_repaired_code(original, repaired)
    assert ok is False


def test_validate_accepts_legit_repair_with_same_asserts():
    # 正常修复：test 数与 assert 数都保持一致 -> 通过
    original = (
        "def test_a():\n"
        "    respnose = 1\n"
        "    assert respnose == 1\n"
    )
    repaired = (
        "def test_a():\n"
        "    response = 1\n"
        "    assert response == 1\n"
    )
    ok, msg = validate_repaired_code(original, repaired)
    assert ok is True, msg


# ---------- 场景 10: backup 正确生成 ----------

def test_backup_test_file_creates_backup(tmp_path):
    src = tmp_path / "test_login.py"
    src.write_text(ORIGINAL, encoding="utf-8")
    backup_dir = str(tmp_path / ".backups")
    backup_path = backup_test_file(str(src), backup_dir=backup_dir)
    assert os.path.exists(backup_path)
    assert backup_path.endswith(".py")
    with open(backup_path, encoding="utf-8") as f:
        assert f.read() == ORIGINAL


def test_apply_repair_to_file_backs_up_and_writes(tmp_path):
    # 在 generated_tests 下创建文件
    gen_dir = tmp_path / "generated_tests"
    gen_dir.mkdir()
    src = gen_dir / "test_login.py"
    src.write_text(ORIGINAL, encoding="utf-8")

    repaired = ORIGINAL.replace("respnose", "response")
    analysis = {"category": "test_code_error", "confidence": 0.92, "repair_allowed": True}

    entry = apply_repair_to_file(
        original_path=str(src),
        repaired_code=repaired,
        analysis=analysis,
        attempt=1,
        backup_dir=str(gen_dir / ".backups"),
        audit_log=str(gen_dir / ".backups" / "audit.jsonl"),
    )
    assert os.path.exists(entry["backup_file"])
    with open(src, encoding="utf-8") as f:
        written = f.read()
    assert "respnose" not in written  # 已被修复
    assert "response.status_code" in written
    # audit log 存在且非空
    assert os.path.exists(str(gen_dir / ".backups" / "audit.jsonl"))


def test_apply_repair_rejects_path_outside_generated_tests(tmp_path):
    bad_path = str(tmp_path / "main.py")
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("print('hi')")
    with pytest.raises(ValueError):
        apply_repair_to_file(
            original_path=bad_path,
            repaired_code="print('fixed')",
            analysis={"category": "test_code_error", "confidence": 0.92, "repair_allowed": True},
        )


# ---------- 准入拒绝时不修复 ----------

def test_repair_returns_none_when_admission_denied():
    # api_defect 不允许修复
    analysis = {"category": "api_defect", "confidence": 0.95, "repair_allowed": True}
    def llm(*a, **k):
        raise AssertionError("不应调用 LLM")
    result = repair_test_code(ORIGINAL, analysis, llm_call=llm)
    assert result is None


def test_repair_returns_none_when_confidence_low():
    analysis = {"category": "test_code_error", "confidence": 0.5, "repair_allowed": True}
    def llm(*a, **k):
        raise AssertionError("不应调用 LLM")
    result = repair_test_code(ORIGINAL, analysis, llm_call=llm)
    assert result is None


# ---------- mock LLM 返回合法修复 -> 通过验证 ----------

def test_repair_returns_fixed_code_with_mock_llm():
    analysis = {"category": "test_code_error", "confidence": 0.92, "repair_allowed": True}

    def good_llm(system, user, temperature=0.2, response_format=None, **kw):
        # 返回修复后的代码（修正 respnose -> response）
        return ORIGINAL.replace("respnose", "response")

    result = repair_test_code(ORIGINAL, analysis, llm_call=good_llm)
    assert result is not None
    assert "respnose" not in result
    assert "response.status_code" in result
    # 应保留全部 test_ 函数
    assert _collect_test_funcs(result) == _collect_test_funcs(ORIGINAL)


# ---------- 删除 test_ 函数 -> 拒绝 ----------

def test_validate_rejects_deleted_test_function():
    # 原始 2 个 test，修复后只剩 1 个
    original = "def test_a():\n    assert True\ndef test_b():\n    assert True\n"
    repaired = "def test_a():\n    assert True\n"  # 删了 test_b
    ok, msg = validate_repaired_code(original, repaired)
    assert ok is False
    assert "test_" in msg


def test_validate_rejects_no_test_functions():
    original = "def test_a():\n    assert True\n"
    repaired = "x = 1\n"  # 完全没有 test_ 函数
    ok, msg = validate_repaired_code(original, repaired)
    assert ok is False


def test_validate_rejects_empty_code():
    ok, msg = validate_repaired_code(ORIGINAL, "")
    assert ok is False
    assert "空" in msg


def test_validate_accepts_clean_repair():
    repaired = ORIGINAL.replace("respnose", "response")
    ok, msg = validate_repaired_code(ORIGINAL, repaired)
    assert ok is True


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
