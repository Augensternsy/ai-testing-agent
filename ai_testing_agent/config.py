# -*- coding: utf-8 -*-
"""
统一配置与公共工具 - AI Agent 自动化测试平台

集中管理：
1. 环境变量（自动加载项目根目录 .env，不打印任何密钥）
2. 目录 / 端口 / 超时 / 安全阈值等常量（消除 magic number）
3. LLM 配置读取（DeepSeek / OpenAI-compatible）
4. LLM 返回 JSON 的统一解析（剥离 markdown 代码块）
5. 演示服务（uvicorn 子进程）生命周期上下文，统一健康检查与清理
6. 轻量 logging（INFO / WARNING / ERROR）

不引入 Pydantic Settings 等额外框架；python-dotenv 为环境已安装依赖，
缺失时静默降级（不影响无 .env 的 CI）。
"""

import os
import sys
import json
import time
import logging
import subprocess
from contextlib import contextmanager


# ---------- 加载 .env（不输出密钥） ----------

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover - dotenv 缺失时降级
    pass


# ---------- 目录常量 ----------

GENERATED_TESTS_DIR = "generated_tests"
REPORTS_DIR = "reports"
BACKUP_DIR = os.path.join(GENERATED_TESTS_DIR, ".backups")
AUDIT_LOG_PATH = os.path.join(BACKUP_DIR, "audit.jsonl")
BUG_REPORTS_DIR = os.path.join(REPORTS_DIR, "bug_reports")
JUNIT_XML_NAME = "pytest_result.xml"
TEST_REPORT_NAME = "test_report.json"
AGENT_REPORT_NAME = "agent_report.json"
REAL_LLM_REPORT_NAME = "real_llm_e2e_report.json"


# ---------- 被测服务常量 ----------

DEFAULT_TEST_BASE_URL = "http://127.0.0.1:8000"
DEMO_HOST = "127.0.0.1"
DEMO_PORT = 8000
DEMO_APP = "ai_testing_agent.demos.demo_target_app:app"
HEALTH_WAIT_TIMEOUT = 20.0
PYTEST_TIMEOUT = 120


# ---------- Agent 安全常量 ----------

REPAIR_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_REPAIR_ATTEMPTS = 1
MAX_REPAIR_ATTEMPTS = 2

# 失败分类
CATEGORIES = (
    "test_code_error",
    "api_defect",
    "test_data_error",
    "environment_error",
    "unknown",
)

# LLM 温度
LLM_TEMPERATURE_CASES = 0.3
LLM_TEMPERATURE_ANALYSIS = 0.2
LLM_TEMPERATURE_REPAIR = 0.2

# LLM 输出 token 上限（用例 JSON 较长，过小会被截断导致非法 JSON）
LLM_MAX_TOKENS_CASES = 8192
LLM_MAX_TOKENS_ANALYSIS = 2048
LLM_MAX_TOKENS_REPAIR = 4096


# ---------- 环境变量读取 ----------

def get_llm_config() -> dict:
    """
    读取 LLM 配置（每次调用实时读取，便于测试中 monkeypatch / pop）

    返回: {"api_key": str, "base_url": str, "model": str}
    """
    return {
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "model": os.getenv("MODEL_NAME", "gpt-3.5-turbo"),
    }


def has_llm_api_key() -> bool:
    """是否已配置 OPENAI_API_KEY（不返回/不打印密钥）"""
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_test_base_url() -> str:
    """被测服务地址：优先环境变量 TEST_BASE_URL"""
    return os.getenv("TEST_BASE_URL", DEFAULT_TEST_BASE_URL)


# ---------- LLM JSON 解析（统一剥离 markdown 代码块） ----------

def strip_json_fences(text: str) -> str:
    """剥离 LLM 输出中可能的 ```json / ``` 代码块包裹"""
    if not text:
        return ""
    s = text.strip()
    if "```json" in s:
        s = s.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in s:
        s = s.split("```", 1)[1].split("```", 1)[0].strip()
    return s


def parse_lenient_json(text: str):
    """宽松解析 LLM 返回的 JSON；失败返回 None（不抛异常）"""
    if not text:
        return None
    try:
        return json.loads(strip_json_fences(text))
    except (json.JSONDecodeError, TypeError):
        return None


# ---------- 日志 ----------

def get_logger(name: str = "ai_testing") -> logging.Logger:
    """获取统一格式的 logger（INFO / WARNING / ERROR）"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


# ---------- 演示服务生命周期（统一 4 处重复的启动/健康检查/清理） ----------

def _wait_for_health(base_url: str, timeout: float = HEALTH_WAIT_TIMEOUT) -> bool:
    """轮询 /health 直到服务就绪"""
    import requests
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{base_url}/health", timeout=1).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


@contextmanager
def demo_server(app: str = DEMO_APP, host: str = DEMO_HOST, port: int = DEMO_PORT,
                timeout: float = HEALTH_WAIT_TIMEOUT):
    """
    启动 uvicorn 演示服务（子进程），yield base_url，退出时确保 terminate/kill。

    使用 DEVNULL 而非 PIPE，避免服务持续输出写满管道导致死锁。
    """
    base_url = f"http://{host}:{port}"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", app, "--host", host, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    try:
        if not _wait_for_health(base_url, timeout):
            raise RuntimeError(f"演示服务 {base_url} 在 {timeout}s 内未就绪")
        yield base_url
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
