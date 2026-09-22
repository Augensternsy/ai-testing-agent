# -*- coding: utf-8 -*-
"""
安全测试代码修复器 - AI 测试流水线第五阶段

功能：在严格准入条件下，让 LLM 修复 generated_tests/ 下的测试代码

安全设计：
1. 准入条件（同时满足才允许修复）：
   - analysis["category"] == "test_code_error"
   - analysis["confidence"] >= 0.80
   - analysis["repair_allowed"] == True
   否则一律不修复，只生成建议。
2. 修复后依次安全验证：
   - 非空
   - compile(code, "<repaired>", "exec") 通过
   - 仍是 Python 测试文件（含 test_ 函数）
   - 未删除所有 test_ 函数（数量不少于原始）
   - 不含危险调用（os.system / subprocess.Popen / shutil.rmtree / eval / exec 等）
3. 修改前必须备份到 generated_tests/.backups/test_X.<timestamp>.py
4. 记录 audit log（原文件、修改后、分析、时间、重试次数）
5. 绝对禁止修改业务源码，只能修改 generated_tests/ 下文件
"""

import os
import ast
import json
import shutil
import datetime

from . import config


# ---------- 危险调用检测 ----------

# 命中即拒绝（subprocess 全家族，测试 runner 自身可用 subprocess，但 LLM 生成的测试文件禁用）
_DANGEROUS_ATTR = {
    ("os", "system"),
    ("os", "popen"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("shutil", "rmtree"),
}

_DANGEROUS_BUILTIN = {"eval", "exec", "__import__"}

# 禁止以跳过 / 预期失败方式制造 PASS
_SUPPRESS_NAMES = {"skip", "skipif", "xfail"}


def _collect_test_funcs(code: str) -> list:
    """收集代码中所有 test_ 开头的函数名"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    return [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]


def _count_asserts(code: str) -> int:
    """统计代码中的断言数量；无法解析返回 -1"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return -1
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.Assert))


def _decorator_tails(dec) -> set:
    """提取装饰器末端名称，如 pytest.mark.skip -> {'skip'}"""
    node = dec
    while isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, ast.Name):
        return {node.id}
    return set()


def _contains_test_suppression(code: str) -> bool:
    """
    检测是否通过 pytest.skip / @pytest.mark.skip / skipif / xfail 抑制测试。
    无法解析视为存在抑制（保守拒绝）。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True

    for node in ast.walk(tree):
        # 装饰器形式：@pytest.mark.skip / @pytest.mark.skipif / @pytest.mark.xfail
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _decorator_tails(dec) & _SUPPRESS_NAMES:
                    return True
        # 调用形式：pytest.skip(...) / pytest.mark.xfail(...)
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _SUPPRESS_NAMES:
                return True
            if isinstance(func, ast.Name) and func.id in _SUPPRESS_NAMES:
                return True
    return False


def _contains_dangerous_calls(code: str) -> bool:
    """AST 检测是否包含危险调用"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return True  # 无法解析视为危险

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # os.system / subprocess.Popen / shutil.rmtree 风格
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if (func.value.id, func.attr) in _DANGEROUS_ATTR:
                    return True
            # eval / exec / __import__ 风格
            if isinstance(func, ast.Name) and func.id in _DANGEROUS_BUILTIN:
                return True
    return False


def validate_repaired_code(original_code: str, repaired_code: str) -> tuple[bool, str]:
    """
    依次执行安全验证，返回 (是否通过, 失败原因)

    顺序：
    1. 非空
    2. compile 通过
    3. 仍是 Python 测试文件（含 test_ 函数）
    4. 未删除任何 test_ 函数（数量不少于原始）
    5. 不含危险调用（os.system/os.popen/subprocess.*/shutil.rmtree/eval/exec/__import__）
    6. assert 数量不减少（禁止注释/删除断言制造 PASS）
    7. 不含 skip/skipif/xfail 等测试抑制手段
    """
    if not repaired_code or not repaired_code.strip():
        return False, "修复后代码为空"

    # 2. compile
    try:
        compile(repaired_code, "<repaired>", "exec")
    except SyntaxError as e:
        return False, f"修复后代码语法错误: {e}"

    # 3. 仍是 Python 测试文件
    orig_tests = _collect_test_funcs(original_code)
    new_tests = _collect_test_funcs(repaired_code)
    if not new_tests:
        return False, "修复后代码不含任何 test_ 函数（不再是测试文件）"

    # 4. 未删除任何 test_ 函数（数量不少于原始）
    if len(new_tests) < len(orig_tests):
        return False, (
            f"修复后 test_ 函数数量 {len(new_tests)} 少于原始 {len(orig_tests)}，"
            "禁止通过删除测试来制造 PASS"
        )

    # 5. 不含危险调用
    if _contains_dangerous_calls(repaired_code):
        return False, "修复后代码含危险调用（os.system/os.popen/subprocess.*/shutil.rmtree/eval/exec/__import__）"

    # 6. assert 数量不得减少（禁止注释/删除断言制造 PASS）
    orig_asserts = _count_asserts(original_code)
    new_asserts = _count_asserts(repaired_code)
    if orig_asserts >= 0 and new_asserts < orig_asserts:
        return False, (
            f"修复后 assert 数量 {new_asserts} 少于原始 {orig_asserts}，"
            "禁止删除或注释断言来制造 PASS"
        )

    # 7. 禁止 skip/skipif/xfail 抑制测试
    if _contains_test_suppression(repaired_code):
        return False, "修复后代码含 skip/skipif/xfail，禁止以跳过或预期失败制造 PASS"

    return True, ""


# ---------- 准入条件 ----------

def is_repair_allowed(analysis: dict) -> tuple[bool, str]:
    """
    判断是否允许自动修复

    准入（同时满足）：
    category==test_code_error AND confidence>=config.REPAIR_CONFIDENCE_THRESHOLD
    AND repair_allowed==True
    """
    if not isinstance(analysis, dict):
        return False, "analysis 不是 dict"
    if analysis.get("category") != "test_code_error":
        return False, f"category={analysis.get('category')} 非 test_code_error，不允许修复"
    try:
        conf = float(analysis.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    if conf < config.REPAIR_CONFIDENCE_THRESHOLD:
        return False, (
            f"confidence={conf} < {config.REPAIR_CONFIDENCE_THRESHOLD:.2f}，不允许修复"
        )
    if not analysis.get("repair_allowed", False):
        return False, "repair_allowed=False，不允许修复"
    return True, ""


# ---------- LLM 修复 ----------

_REPAIR_SYSTEM_PROMPT = """你是一名 pytest 测试代码修复专家。

【最高优先级 · 输出格式，必须严格遵守】
- 输出必须是一个【完整、独立、可直接保存为 .py 并运行】的 Python 测试文件全文。
- 输出的第一个字符起就是 Python 源码，第一行必须是 `import os`。
- 必须原样保留：全部 import、BASE_URL、辅助函数（如 _build_url）、以及每一个 test_ 函数。
- 严禁输出：diff / patch / 代码片段 / 行号 / 省略号 / markdown 围栏(```) / 任何解释或前后缀文字。
- 严禁只输出被修改的那几行；必须重写并输出整个文件。

【修复范围】
1. 只修复 test_code_error：语法错误、命名错误（如变量名拼写错误导致 NameError）、导入错误、请求构造错误。
2. 禁止删除或重命名任何 test_ 函数。
3. 禁止注释、删除或弱化 assert 来“假装通过”。
4. 禁止危险调用：os.system / os.popen / subprocess.* / shutil.rmtree / eval / exec / __import__。
5. 禁止 pytest.skip / skipif / xfail。"""


def _build_repair_user_prompt(original_code, analysis, test_case, api_spec):
    def _fmt(obj):
        if obj is None:
            return "（未提供）"
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(obj)

    return f"""请修复下面这份 pytest 文件中的 test_code_error，并输出【修复后的完整文件全文】。

## 失败分析
- root_cause: {analysis.get('root_cause', '')}
- evidence: {_fmt(analysis.get('evidence', []))}
- recommended_action: {analysis.get('recommended_action', '')}

## 对应 Test Case
{_fmt(test_case)}

## 对应 API Schema
{_fmt(api_spec)}

## 待修复的完整文件（仅供阅读，不要把它当作续写上文）
{original_code}

现在请直接输出修复后的完整文件：从 `import os` 第一行开始，到最后一个 test_ 函数结束，
包含全部 import、辅助函数和所有 test_ 函数。不要 markdown 围栏，不要解释，不要 diff，不要只给片段。"""


def repair_test_code(
    original_code: str,
    analysis: dict,
    test_case: dict | None = None,
    api_spec: dict | None = None,
    llm_call=None,
) -> str | None:
    """
    在满足准入条件时，调用 LLM 修复测试代码，并执行安全验证

    参数:
        original_code: 原始测试代码
        analysis: analyze_failure 的结果
        test_case: 对应 Test Case JSON
        api_spec: 对应 API Schema
        llm_call: LLM 调用函数，None 时使用 test_case_generator.call_llm_api

    返回:
        修复后且通过安全验证的代码字符串；不满足准入或验证失败返回 None
    """
    # 1. 准入检查
    allowed, reason = is_repair_allowed(analysis)
    if not allowed:
        return None

    # 2. 取 LLM 调用器
    if llm_call is None:
        if not config.has_llm_api_key():
            return None
        from .test_case_generator import call_llm_api
        llm_call = call_llm_api

    # 3. 调用 LLM 生成修复代码
    try:
        repaired = llm_call(
            _REPAIR_SYSTEM_PROMPT,
            _build_repair_user_prompt(original_code, analysis, test_case, api_spec),
            temperature=config.LLM_TEMPERATURE_REPAIR,
            response_format=None,  # 修复要返回代码，不能用 json_object
        )
    except Exception:
        return None

    if not repaired:
        return None

    # 去除可能的 markdown 包裹
    repaired = repaired.strip()
    if repaired.startswith("```"):
        # 去掉首行 ```python / ```
        lines = repaired.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        repaired = "\n".join(lines).strip()

    # 4. 安全验证
    ok, msg = validate_repaired_code(original_code, repaired)
    if not ok:
        return None

    return repaired


# ---------- 备份与 audit ----------

def backup_test_file(original_path: str, backup_dir: str = config.BACKUP_DIR) -> str:
    """
    修改前备份原始测试文件

    生成: backup_dir/test_X.<timestamp>.py
    """
    os.makedirs(backup_dir, exist_ok=True)
    basename = os.path.basename(original_path)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{basename}.{ts}.py")
    shutil.copy2(original_path, backup_path)
    return backup_path


def apply_repair_to_file(
    original_path: str,
    repaired_code: str,
    analysis: dict,
    attempt: int = 1,
    backup_dir: str = config.BACKUP_DIR,
    audit_log: str = config.AUDIT_LOG_PATH,
) -> dict:
    """
    对磁盘上的测试文件执行：备份 -> 写入修复代码 -> 记录 audit

    返回 audit 条目 dict
    """
    # 安全限制：只允许修改 generated_tests/ 下文件（解析绝对路径后逐段校验，
    # 覆盖符号链接/相对路径写法）
    norm = os.path.normpath(os.path.abspath(original_path))
    parts = norm.split(os.sep)
    if config.GENERATED_TESTS_DIR not in parts:
        raise ValueError(f"Agent 修复只允许修改 generated_tests/ 下文件，拒绝: {original_path}")

    backup_path = backup_test_file(original_path, backup_dir)

    with open(original_path, "w", encoding="utf-8") as f:
        f.write(repaired_code)

    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "original_file": original_path,
        "backup_file": backup_path,
        "modified_file": original_path,
        "analysis": analysis,
        "attempt": attempt,
    }

    os.makedirs(os.path.dirname(audit_log), exist_ok=True)
    with open(audit_log, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


if __name__ == "__main__":
    # 自测：准入拒绝
    print(is_repair_allowed({"category": "api_defect", "confidence": 0.9, "repair_allowed": False}))
    print(is_repair_allowed({"category": "test_code_error", "confidence": 0.5, "repair_allowed": True}))
    print(is_repair_allowed({"category": "test_code_error", "confidence": 0.92, "repair_allowed": True}))
