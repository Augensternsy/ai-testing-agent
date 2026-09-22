# -*- coding: utf-8 -*-
"""
测试代码生成器 - AI 测试流水线第三阶段

功能：Test Cases JSON -> 确定性 Python 模板 -> PyTest + Requests 测试代码

设计原则：
1. 不调用 LLM / RAG / DeepSeek，采用确定性模板生成，避免语法错误与不可执行代码
2. 统一使用 requests.request(method=...) 支持 GET/POST/PUT/PATCH/DELETE
3. BASE_URL 从环境变量 TEST_BASE_URL 读取，不硬编码线上地址
4. path/query/header/body 缺失自动用 {}；expected_status 缺失则报错（不静默猜测）
5. 字面量使用 pprint.pformat 安全转换，避免手工字符串拼接
"""

import os
import re
from pprint import pformat


def _normalize_func_name(case_id, index):
    """
    将 case_id 转为合法 Python 测试函数名

    规则：转小写、非字母数字字符转 _、合并连续 _、自动加 test_ 前缀
    case_id 缺失时使用 case_{index:03d}
    """
    if not case_id:
        base = f"case_{index:03d}"
    else:
        base = re.sub(r'[^a-zA-Z0-9]', '_', str(case_id))
        base = base.lower()
        base = re.sub(r'_+', '_', base).strip('_')
        if not base:
            base = f"case_{index:03d}"
        elif base[0].isdigit():
            base = "_" + base
    return "test_" + base


def _filename_from_path(api_path):
    """根据 api path 生成文件名，如 /users/{id} -> test_users_id.py"""
    name = str(api_path).replace("{", "").replace("}", "")
    name = re.sub(r'[^a-zA-Z0-9]', '_', name)
    name = re.sub(r'_+', '_', name).strip('_').lower()
    if not name:
        name = "api"
    return f"test_{name}.py"


def _safe_literal(value):
    """将 Python 值安全转为字面量字符串；None 转为 {}"""
    if value is None:
        return "{}"
    return pformat(value, width=100, sort_dicts=False)


def generate_pytest_code(test_cases_data: dict) -> str:
    """
    将第二阶段 Test Cases JSON 转为可执行的 PyTest + Requests 代码字符串

    参数:
        test_cases_data: 第二阶段输出 {api, method, summary, test_cases:[...]}

    返回:
        完整 Python 源代码字符串

    异常:
        ValueError: 数据格式不合法或单条用例缺少 expected_status
    """
    if not isinstance(test_cases_data, dict):
        raise ValueError("test_cases_data 必须是 dict")
    for field in ("api", "method", "test_cases"):
        if field not in test_cases_data:
            raise ValueError(f"test_cases_data 缺少 {field}")
    if not isinstance(test_cases_data["test_cases"], list):
        raise ValueError("test_cases 必须是 list")

    api = test_cases_data["api"]
    method = str(test_cases_data["method"]).upper()
    cases = test_cases_data["test_cases"]

    lines = []
    # 文件头
    lines.append("import os")
    lines.append("import requests")
    lines.append("")
    lines.append('BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")')
    lines.append("")
    lines.append("")
    # 公共辅助函数：替换路径参数 {id} -> 实际值
    lines.append("def _build_url(path_template, path_params):")
    lines.append("    path = path_template")
    lines.append("    for key, value in path_params.items():")
    lines.append('        path = path.replace("{" + key + "}", str(value))')
    lines.append('    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")')
    lines.append("")
    lines.append("")

    for i, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            raise ValueError(f"第 {i} 条用例不是 dict")

        case_id = case.get("case_id")
        func_name = _normalize_func_name(case_id, i)

        # request 子字段缺失一律安全降级为 {}
        request = case.get("request") or {}
        if not isinstance(request, dict):
            request = {}
        path_params = request.get("path_params") or {}
        query_params = request.get("query_params") or {}
        headers = request.get("headers") or {}
        body = request.get("body") or {}

        # expected_status 不允许静默猜测，缺失即报错
        if "expected_status" not in case or case["expected_status"] is None:
            raise ValueError(f"用例 {case_id or i} 缺少 expected_status")
        expected_status = case["expected_status"]
        expected_result = case.get("expected_result", "")

        lines.append(f"def {func_name}():")
        lines.append(f"    path_params = {_safe_literal(path_params)}")
        lines.append(f"    query_params = {_safe_literal(query_params)}")
        lines.append(f"    headers = {_safe_literal(headers)}")
        lines.append(f"    body = {_safe_literal(body)}")
        lines.append("")
        lines.append(f"    url = _build_url(")
        lines.append(f"        {_safe_literal(api)},")
        lines.append(f"        path_params")
        lines.append(f"    )")
        lines.append("")
        lines.append(f"    response = requests.request(")
        lines.append(f'        method="{method}",')
        lines.append(f"        url=url,")
        lines.append(f"        params=query_params,")
        lines.append(f"        headers=headers,")
        lines.append(f"        json=body,")
        lines.append(f"    )")
        lines.append("")
        lines.append(f"    assert response.status_code == {_safe_literal(expected_status)}")
        # expected_result 为自然语言，仅作为注释保留，不生成业务断言
        if expected_result:
            lines.append(f"    # Expected: {expected_result}")
        lines.append("")
        lines.append("")

    return "\n".join(lines)


def save_pytest_code(code: str, output_file: str) -> str:
    """保存生成的测试代码到文件，目录不存在则自动创建"""
    out_dir = os.path.dirname(output_file) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(code)
    return output_file


def generate_test_file(test_cases_data: dict, output_dir: str = "generated_tests") -> str:
    """
    Test Cases JSON -> generate_pytest_code -> 保存 .py -> 返回文件路径

    参数:
        test_cases_data: 第二阶段输出
        output_dir: 输出目录，默认 generated_tests

    返回:
        生成的 .py 文件路径
    """
    code = generate_pytest_code(test_cases_data)
    filename = _filename_from_path(test_cases_data["api"])
    output_file = os.path.join(output_dir, filename)
    return save_pytest_code(code, output_file)
