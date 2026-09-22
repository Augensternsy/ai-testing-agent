# -*- coding: utf-8 -*-
"""
失败分析器 - AI 测试流水线第五阶段

功能：对 pytest 失败用例进行分类与根因分析

设计原则：
1. 先做确定性预检（deterministic pre-check），命中即直接输出，不调用 LLM
2. 确定性无法判定时，再调用 DeepSeek/OpenAI-compatible API
3. 强制结构化 JSON 输出，category 只能取限定值
4. 不允许仅凭一次失败断言接口 Bug；证据不足必须输出 unknown
5. repair_allowed 只对 test_code_error 且根因明确时为 True

失败分类：
- test_code_error：测试代码本身有问题（SyntaxError/IndentationError/NameError/ImportError/请求代码错误）
- api_defect：接口实际行为与接口定义/明确预期不一致（需充分证据）
- test_data_error：测试输入数据本身不合理或与已知约束冲突
- environment_error：连接被拒/超时/服务未启动/DNS/网络/缺依赖/环境变量缺失
- unknown：证据不足，不能可靠判断
"""

import json

from . import config


VALID_CATEGORIES = set(config.CATEGORIES)


# ---------- 确定性预检 ----------

# 环境类错误特征（小写匹配）
_ENV_PATTERNS = [
    "connectionerror",
    "connection refused",
    "readtimeout",
    "read timeout",
    "connecttimeouterror",
    "connect timeout",
    "max retries exceeded",
    "connectionaborted",
    "connectionreseterror",
    "newconnectionerror",
    "name or service not known",
    "nodename nor servname",
    "failed to establish a new connection",
    "errno 111",            # connection refused (linux)
    "errno 10061",          # connection refused (windows)
    "temporary failure in name resolution",
]

# 测试代码类错误特征
_CODE_PATTERNS = [
    ("syntaxerror", "SyntaxError"),
    ("indentationerror", "IndentationError"),
    ("nameerror", "NameError"),
    ("importerror", "ImportError"),
    ("modulenotfounderror", "ModuleNotFoundError"),
]


def _normalize_analysis(result: dict) -> dict:
    """规范化分析结果，补全字段并校验 category"""
    category = result.get("category")
    if category not in VALID_CATEGORIES:
        category = "unknown"

    try:
        confidence = float(result.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    evidence = result.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = [str(evidence)] if evidence else []
    evidence = [str(e) for e in evidence]

    root_cause = str(result.get("root_cause", "") or "")
    recommended_action = str(result.get("recommended_action", "") or "")

    repair_allowed = result.get("repair_allowed", False)
    if not isinstance(repair_allowed, bool):
        repair_allowed = bool(repair_allowed)

    # 非 test_code_error 一律不允许修复
    if category != "test_code_error":
        repair_allowed = False

    return {
        "category": category,
        "confidence": confidence,
        "root_cause": root_cause,
        "evidence": evidence,
        "recommended_action": recommended_action,
        "repair_allowed": repair_allowed,
    }


def _deterministic_analysis(failure: dict, test_code: str):
    """
    确定性预检：基于 traceback 关键字命中直接判定

    命中返回规范化 dict，未命中返回 None
    """
    message = str(failure.get("message") or "")
    traceback = str(failure.get("traceback") or "")
    blob = (message + "\n" + traceback).lower()

    # 1. 环境错误优先（连接类）
    for pat in _ENV_PATTERNS:
        if pat in blob:
            return _normalize_analysis({
                "category": "environment_error",
                "confidence": 0.95,
                "root_cause": f"检测到网络/连接类错误（命中模式: {pat}）",
                "evidence": [f"traceback 命中: {pat}"],
                "recommended_action": "检查被测服务是否启动、网络/DNS、环境变量(TEST_BASE_URL)、依赖是否安装",
                "repair_allowed": False,
            })

    # 2. 测试代码错误（语法/缩进/命名/导入）
    for pat, name in _CODE_PATTERNS:
        if pat in blob:
            return _normalize_analysis({
                "category": "test_code_error",
                "confidence": 0.92,
                "root_cause": f"检测到测试代码错误: {name}",
                "evidence": [f"traceback 命中 {name}"],
                "recommended_action": "修正测试代码中的语法/命名/导入错误",
                "repair_allowed": True,
            })

    return None  # 确定性预检未命中


# ---------- LLM 分析 ----------

_SYSTEM_PROMPT = """你是一名资深测试失败分析专家。你的任务是基于现有证据，对 pytest 失败用例进行分类与根因分析。

## 严格约束
1. 只能基于以下证据：API Schema、Test Case、Test Code、Traceback。禁止虚构业务规则。
2. 不确定时必须输出 category="unknown"，禁止强行分类。
3. 不允许仅凭一次失败就断言接口存在 Bug。
4. 只有存在充分证据时才分类 api_defect。
5. repair_allowed 只有在 category=test_code_error 且根因明确时为 true，其余一律 false。

## 分类（category 只能取以下之一）
- test_code_error：生成的测试 Python 代码本身有问题（语法/导入/命名/请求代码错误）
- api_defect：接口实际行为与接口定义/明确预期不一致（需充分证据）
- test_data_error：测试输入数据本身不合理或与已知约束冲突
- environment_error：连接被拒/超时/服务未启动/DNS/网络/缺依赖/环境变量缺失
- unknown：证据不足，不能可靠判断

## 输出格式（必须且只能输出合法 JSON，不要包含任何额外文字）
{
  "category": "...",
  "confidence": 0.0,
  "root_cause": "...",
  "evidence": ["...", "..."],
  "recommended_action": "...",
  "repair_allowed": true
}

confidence 取值 0.0~1.0。"""


def _build_user_prompt(failure, test_code, test_case, api_spec):
    def _fmt(obj):
        if obj is None:
            return "（未提供）"
        try:
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(obj)

    return f"""请分析以下 pytest 失败用例。

## API Schema
{_fmt(api_spec)}

## Test Case
{_fmt(test_case)}

## Test Code
```
{test_code or "（未提供）"}
```

## Failure Message
{failure.get('message') or ''}

## Traceback
{failure.get('traceback') or ''}

请严格基于以上证据输出分类 JSON。"""


def _llm_analysis(failure, test_code, test_case, api_spec, llm_call):
    """调用 LLM 进行失败分析"""
    user_prompt = _build_user_prompt(failure, test_code, test_case, api_spec)
    response_text = llm_call(
        _SYSTEM_PROMPT,
        user_prompt,
        temperature=config.LLM_TEMPERATURE_ANALYSIS,
        response_format={"type": "json_object"},
    )
    parsed = config.parse_lenient_json(response_text) or {}
    return _normalize_analysis(parsed)


# ---------- 主入口 ----------

def analyze_failure(
    failure: dict,
    test_code: str,
    test_case: dict | None = None,
    api_spec: dict | None = None,
    llm_call=None,
) -> dict:
    """
    分析单条 pytest 失败

    参数:
        failure: 失败用例 dict，至少包含 message/traceback 字段
        test_code: 当前测试代码字符串
        test_case: 对应的 Test Case JSON（可选）
        api_spec: 对应的 API Schema（可选）
        llm_call: 可选的 LLM 调用函数，签名为
                  (system_prompt, user_prompt, temperature=, response_format=) -> str
                  为 None 时使用 test_case_generator.call_llm_api

    返回:
        {
            "category": str,
            "confidence": float,
            "root_cause": str,
            "evidence": [str],
            "recommended_action": str,
            "repair_allowed": bool
        }
    """
    if not isinstance(failure, dict):
        raise ValueError("failure 必须是 dict")

    # 1. 确定性预检优先
    det = _deterministic_analysis(failure, test_code)
    if det is not None:
        return det

    # 2. 需 LLM 分析
    if llm_call is None:
        # 无 API Key 时不得伪造，直接输出 unknown
        if not config.has_llm_api_key():
            return _normalize_analysis({
                "category": "unknown",
                "confidence": 0.3,
                "root_cause": "无法调用 LLM（OPENAI_API_KEY 未配置），且确定性规则未能分类",
                "evidence": ["确定性预检未命中", "OPENAI_API_KEY 不可用"],
                "recommended_action": "配置 OPENAI_API_KEY 后重试，或人工分析",
                "repair_allowed": False,
            })
        from .test_case_generator import call_llm_api
        llm_call = call_llm_api

    try:
        result = _llm_analysis(failure, test_code, test_case, api_spec, llm_call)
    except Exception as e:
        result = _normalize_analysis({
            "category": "unknown",
            "confidence": 0.2,
            "root_cause": f"LLM 分析异常: {e}",
            "evidence": [f"LLM 异常: {e}"],
            "recommended_action": "人工分析",
            "repair_allowed": False,
        })
    return result


if __name__ == "__main__":
    # 自测入口：演示一个 NameError 确定性命中
    sample_failure = {
        "name": "test_demo",
        "status": "failed",
        "message": "NameError: name 'respnose' is not defined",
        "traceback": "Traceback (most recent call last):\n  File 'test_demo.py', line 5, in test_demo\n    assert respnose.status_code == 200\nNameError: name 'respnose' is not defined",
    }
    print(json.dumps(analyze_failure(sample_failure, "assert respnose.status_code == 200"),
                     ensure_ascii=False, indent=2))
