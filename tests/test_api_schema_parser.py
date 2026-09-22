# -*- coding: utf-8 -*-
"""
api_schema_parser 测试

构造最小 FastAPI 示例（GET /users/{id} + POST /login），
验证 parse_openapi / extract_openapi_from_app 的解析结果。

运行方式：
    python test_api_schema_parser.py        # 直接运行
    pytest test_api_schema_parser.py         # pytest 运行
"""

import json

from fastapi import FastAPI
from pydantic import BaseModel

from ai_testing_agent.api_schema_parser import parse_openapi, extract_openapi_from_app


class LoginRequest(BaseModel):
    username: str
    password: str


def create_app() -> FastAPI:
    """构造最小 FastAPI 示例"""
    app = FastAPI(title="Test API")

    @app.get("/users/{id}", summary="获取用户", description="根据用户 ID 获取用户信息")
    def get_user(id: int):
        return {"id": id, "name": "alice"}

    @app.post("/login", summary="用户登录", description="通过用户名密码登录")
    def login(body: LoginRequest):
        return {"token": "xxx"}

    return app


def test_parse_two_interfaces():
    """验证：能识别 2 个接口"""
    app = create_app()
    interfaces = extract_openapi_from_app(app)
    assert len(interfaces) == 2, f"期望 2 个接口，实际 {len(interfaces)}"


def test_method_and_path_correct():
    """验证：method 与 path 正确"""
    app = create_app()
    interfaces = extract_openapi_from_app(app)
    by_key = {(i["path"], i["method"]) for i in interfaces}
    assert ("/users/{id}", "GET") in by_key
    assert ("/login", "POST") in by_key


def test_get_user_path_parameter():
    """验证：GET /users/{id} 的路径参数解析，无 requestBody"""
    app = create_app()
    interfaces = extract_openapi_from_app(app)
    get_user = [i for i in interfaces if i["method"] == "GET"][0]

    assert get_user["summary"] == "获取用户"
    # 路径参数 id 存在
    params = get_user["parameters"]
    assert any(p["name"] == "id" and p["in"] == "path" for p in params), \
        "未解析出 path 参数 id"
    # GET 请求无 requestBody
    assert get_user["request_body"] == {}


def test_login_request_body_and_responses():
    """验证：POST /login 的 requestBody 与 responses"""
    app = create_app()
    interfaces = extract_openapi_from_app(app)
    login = [i for i in interfaces if i["method"] == "POST"][0]

    assert login["summary"] == "用户登录"
    # requestBody 存在
    assert login["request_body"], "login 应有 requestBody"
    assert "application/json" in login["request_body"]["content"], \
        "requestBody 缺少 application/json"
    # responses 存在（FastAPI 默认生成 200 与 422）
    assert "200" in login["responses"], "缺少 200 响应"
    assert "422" in login["responses"], "缺少 422 校验错误响应"


def test_parse_openapi_with_dict():
    """验证：直接传入 dict schema 也能解析"""
    app = create_app()
    schema = app.openapi()
    interfaces = parse_openapi(schema)
    assert len(interfaces) == 2


def test_empty_and_invalid_schema():
    """验证：异常情况处理"""
    assert parse_openapi({}) == []                       # paths 不存在
    assert parse_openapi({"paths": {}}) == []            # paths 为空
    assert parse_openapi({"paths": "not a dict"}) == []  # paths 非 dict
    try:
        parse_openapi("not a dict")                      # 非法类型
        assert False, "应抛出 TypeError"
    except TypeError:
        pass


def test_non_http_fields_not_parsed():
    """验证：非 HTTP 方法字段不被误解析为接口"""
    schema = {
        "paths": {
            "/foo": {
                "summary": "path summary",
                "description": "path desc",
                "parameters": [],
                "servers": [{"url": "/"}],
                "get": {
                    "summary": "get foo",
                    "responses": {"200": {"description": "ok"}},
                },
            }
        }
    }
    interfaces = parse_openapi(schema)
    # 只解析出 GET 一个接口，不把 summary/description/servers/parameters 当接口
    assert len(interfaces) == 1
    assert interfaces[0]["method"] == "GET"


def main():
    """直接运行：打印示例并执行所有 test_ 函数"""
    app = create_app()
    interfaces = extract_openapi_from_app(app)

    print("=" * 60)
    print(f"解析到 {len(interfaces)} 个接口")
    print("=" * 60)
    print(json.dumps(interfaces, ensure_ascii=False, indent=2))

    print("\n" + "=" * 60)
    print("运行测试")
    print("=" * 60)
    tests = [
        test_parse_two_interfaces,
        test_method_and_path_correct,
        test_get_user_path_parameter,
        test_login_request_body_and_responses,
        test_parse_openapi_with_dict,
        test_empty_and_invalid_schema,
        test_non_http_fields_not_parsed,
    ]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\n全部 {len(tests)} 个测试通过 ✓")


if __name__ == "__main__":
    main()
