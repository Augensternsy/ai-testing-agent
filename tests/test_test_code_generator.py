# -*- coding: utf-8 -*-
"""
test_code_generator 测试（第三阶段）

只验证：Test Cases JSON -> 代码字符串 -> Python 语法合法（compile）。
不真实访问 HTTP 服务，不执行 pytest 跑业务 API。

运行方式：
    python test_test_code_generator.py   # 直接运行
    pytest test_test_code_generator.py    # pytest 运行（若已安装）
"""

import os
import tempfile

from ai_testing_agent.test_code_generator import (
    generate_pytest_code,
    save_pytest_code,
    generate_test_file,
    _normalize_func_name,
    _filename_from_path,
)


def _login_data():
    """第二阶段输出格式：POST /login"""
    return {
        "api": "/login",
        "method": "POST",
        "summary": "用户登录",
        "test_cases": [
            {
                "case_id": "LOGIN_001",
                "title": "正确用户名密码登录",
                "test_type": "normal",
                "priority": "P0",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {"Content-Type": "application/json"},
                    "body": {"username": "test", "password": "123456"},
                },
                "expected_status": 200,
                "expected_result": "登录成功",
            },
            {
                "case_id": "LOGIN_002",
                "title": "缺少 username",
                "test_type": "exception",
                "priority": "P0",
                "request": {
                    "path_params": {},
                    "query_params": {},
                    "headers": {},
                    "body": {"password": "123456"},
                },
                "expected_status": 422,
                "expected_result": "返回参数校验错误",
            },
        ],
    }


def _users_get_data():
    """GET /users/{id}，含 path/query/header"""
    return {
        "api": "/users/{id}",
        "method": "GET",
        "summary": "获取用户",
        "test_cases": [
            {
                "case_id": "USER_GET_001",
                "title": "获取已存在用户",
                "test_type": "normal",
                "priority": "P0",
                "request": {
                    "path_params": {"id": 123},
                    "query_params": {"page": 1},
                    "headers": {"Authorization": "Bearer xxx"},
                    "body": {},
                },
                "expected_status": 200,
                "expected_result": "返回用户信息",
            }
        ],
    }


def _delete_data():
    """DELETE 方法"""
    return {
        "api": "/users/{id}",
        "method": "DELETE",
        "summary": "删除用户",
        "test_cases": [
            {
                "case_id": "USER_DEL_001",
                "title": "删除用户",
                "test_type": "normal",
                "priority": "P0",
                "request": {
                    "path_params": {"id": 5},
                    "query_params": {},
                    "headers": {},
                    "body": {},
                },
                "expected_status": 200,
                "expected_result": "删除成功",
            }
        ],
    }


def test_post_login_generates_code():
    """1-4：POST /login 生成代码，含关键片段、body、assert"""
    code = generate_pytest_code(_login_data())
    assert "import requests" in code
    assert "BASE_URL" in code
    assert "requests.request" in code
    assert 'method="POST"' in code
    # body 写入
    assert "username" in code
    assert "password" in code
    # expected_status 断言
    assert "assert response.status_code == 200" in code
    assert "assert response.status_code == 422" in code


def test_get_users_with_path_params():
    """5：GET /users/{id} 生成代码含 path_params 与 _build_url"""
    code = generate_pytest_code(_users_get_data())
    assert "path_params" in code
    assert "_build_url" in code
    assert "123" in code  # path 参数值


def test_query_and_headers_written():
    """6/7：query_params 与 headers 正确写入"""
    code = generate_pytest_code(_users_get_data())
    assert "query_params" in code
    assert "page" in code
    assert "headers" in code
    assert "Authorization" in code


def test_delete_method_generates():
    """8：DELETE 方法正常生成"""
    code = generate_pytest_code(_delete_data())
    assert 'method="DELETE"' in code
    assert "assert response.status_code == 200" in code


def test_case_id_normalization():
    """9：非法 case_id LOGIN-001 -> test_login_001"""
    assert _normalize_func_name("LOGIN-001", 1) == "test_login_001"
    assert _normalize_func_name("USER_GET_002", 2) == "test_user_get_002"
    assert _normalize_func_name("", 1) == "test_case_001"
    assert _normalize_func_name(None, 2) == "test_case_002"


def test_invalid_data_raises_value_error():
    """10：test_cases_data 格式错误抛 ValueError"""
    bad_cases = [
        "not a dict",
        {},
        {"api": "/x"},
        {"api": "/x", "method": "GET"},
        {"api": "/x", "method": "GET", "test_cases": "notlist"},
    ]
    for bad in bad_cases:
        try:
            generate_pytest_code(bad)
            assert False, f"应抛 ValueError: {bad!r}"
        except ValueError:
            pass


def test_missing_expected_status_raises():
    """11：expected_status 缺失抛 ValueError（不静默猜测）"""
    data = {
        "api": "/login",
        "method": "POST",
        "test_cases": [
            {"case_id": "X_001", "request": {"body": {}}}
            # 缺 expected_status
        ],
    }
    try:
        generate_pytest_code(data)
        assert False, "应抛 ValueError"
    except ValueError:
        pass


def test_generated_code_compiles():
    """12：生成代码通过 compile() 语法检查"""
    for data in (_login_data(), _users_get_data(), _delete_data()):
        code = generate_pytest_code(data)
        compile(code, "<generated_test>", "exec")


def test_save_and_generate_file():
    """额外：save_pytest_code 与 generate_test_file 能写文件且语法合法"""
    with tempfile.TemporaryDirectory() as d:
        path = generate_test_file(_login_data(), output_dir=d)
        assert os.path.exists(path)
        assert path.endswith("test_login.py")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        compile(content, "<generated_test>", "exec")


def test_filename_from_path():
    """文件名映射：/login、/users/{id}、/api/v1/users"""
    assert _filename_from_path("/login") == "test_login.py"
    assert _filename_from_path("/users/{id}") == "test_users_id.py"
    assert _filename_from_path("/api/v1/users") == "test_api_v1_users.py"


def main():
    """直接运行入口"""
    tests = [
        test_post_login_generates_code,
        test_get_users_with_path_params,
        test_query_and_headers_written,
        test_delete_method_generates,
        test_case_id_normalization,
        test_invalid_data_raises_value_error,
        test_missing_expected_status_raises,
        test_generated_code_compiles,
        test_save_and_generate_file,
        test_filename_from_path,
    ]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n全部 {len(tests)} 个测试通过 ✓")


if __name__ == "__main__":
    main()
