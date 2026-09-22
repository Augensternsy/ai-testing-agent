# -*- coding: utf-8 -*-
"""
第四阶段端到端演示：

1. 启动本地 demo_target_app（统一由 config.demo_server 管理 uvicorn 子进程）
2. 设置 TEST_BASE_URL 并调用 run_pytest() 执行 generated_tests/test_login.py
3. 输出结构化结果并保存 reports/test_report.json
4. 服务进程在退出上下文时自动 terminate/kill（禁止留下后台僵尸进程）
"""

import os
import sys
import json

from ai_testing_agent import config
from ai_testing_agent.test_runner import run_pytest


def main():
    test_target = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(config.GENERATED_TESTS_DIR, "test_login.py")
    if not os.path.exists(test_target):
        print(f"[demo] 测试目标不存在: {test_target}")
        return 2

    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    # 1-2. 启动并等待服务就绪（DEVNULL，避免管道阻塞；退出自动清理）
    with config.demo_server() as base_url:
        print(f"[demo] 服务就绪: {base_url}/health")
        print(f"[demo] 运行 pytest: {test_target}")

        # 3. 执行 pytest
        result = run_pytest(
            test_target=test_target,
            base_url=base_url,
            report_dir=config.REPORTS_DIR,
            timeout=config.PYTEST_TIMEOUT,
        )

        # 4. 输出结果
        print("\n========== Test Report ==========")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        print("\n========== Summary ==========")
        print(f"success    : {result['success']}")
        print(f"return_code: {result['return_code']}")
        print(f"total      : {result['total']}")
        print(f"passed     : {result['passed']}")
        print(f"failed     : {result['failed']}")
        print(f"errors     : {result['errors']}")
        print(f"skipped    : {result['skipped']}")
        print(f"pass_rate  : {result['pass_rate']}")
        print(f"duration   : {result['duration']}s")
        print(f"junit_xml  : {result['junit_xml']}")
        print(f"report_json: {result['report_json']}")

        # PASS / FAILED 区分
        if result["failed"] == 0 and result["errors"] == 0 and result["total"] > 0:
            print("\n[demo] 结果: ALL PASS")
            return 0
        print("\n[demo] 结果: 存在 FAILED/ERROR")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
