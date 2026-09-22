# -*- coding: utf-8 -*-
"""
API Schema 解析器 - AI 测试流水线第一阶段

功能：FastAPI app -> OpenAPI Schema -> 结构化接口描述 JSON

说明：
1. 通过 app.openapi() 获取 OpenAPI Schema
2. 解析 paths 下的每个 path + HTTP method
3. 提取 summary / description / parameters / requestBody / responses
4. 自动展开 $ref 引用（#/components/schemas/...），输出结构化 JSON

本阶段不涉及 LLM / RAG / 测试用例生成 / Agent 调度。
"""

from typing import Any, List


# 合法的 HTTP 方法（小写）。用白名单过滤，避免把 summary/description
# /servers/parameters 等 path item 字段误解析为接口。
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def _resolve_ref(ref: str, root: dict) -> dict:
    """解析 $ref 引用，例如 '#/components/schemas/LoginRequest'"""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {"$ref": ref} if isinstance(ref, str) else {}
    parts = ref.lstrip("#/").split("/")
    node: Any = root
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return {"$ref": ref}
    return node if isinstance(node, dict) else {"$ref": ref}


def _resolve_node(node: Any, root: dict, depth: int = 0) -> Any:
    """递归展开节点中的 $ref。限制深度避免自引用 schema 无限递归。"""
    if depth > 6:
        return node
    if isinstance(node, dict):
        # 仅当 $ref 独占一个 dict 时才展开（OpenAPI 规范约定）
        if "$ref" in node and len(node) == 1:
            return _resolve_node(_resolve_ref(node["$ref"], root), root, depth + 1)
        return {k: _resolve_node(v, root, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_node(item, root, depth + 1) for item in node]
    return node


def _parse_parameters(parameters: Any, root: dict) -> list:
    """解析 parameters 列表（展开 $ref）"""
    if not isinstance(parameters, list) or not parameters:
        return []
    result = []
    for param in parameters:
        if not isinstance(param, dict):
            continue
        resolved = _resolve_node(param, root)
        result.append({
            "name": resolved.get("name", ""),
            "in": resolved.get("in", ""),
            "required": resolved.get("required", False),
            "description": resolved.get("description", ""),
            "schema": resolved.get("schema", {}),
        })
    return result


def _parse_request_body(body: Any, root: dict) -> dict:
    """解析 requestBody（展开 $ref）"""
    if not isinstance(body, dict) or not body:
        return {}
    resolved = _resolve_node(body, root)
    return {
        "required": resolved.get("required", False),
        "description": resolved.get("description", ""),
        "content": resolved.get("content", {}),
    }


def _parse_responses(responses: Any, root: dict) -> dict:
    """解析 responses（展开 $ref）"""
    if not isinstance(responses, dict) or not responses:
        return {}
    result = {}
    for status, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        resolved = _resolve_node(resp, root)
        result[status] = {
            "description": resolved.get("description", ""),
            "content": resolved.get("content", {}),
        }
    return result


def parse_openapi(openapi_schema: dict) -> list[dict]:
    """
    解析 OpenAPI Schema，提取接口信息列表

    参数:
        openapi_schema: OpenAPI 字典（app.openapi() 的返回值）

    返回:
        接口描述列表，每项包含:
        - path: 接口路径
        - method: HTTP 方法（大写）
        - summary: 摘要
        - description: 描述
        - parameters: 参数列表（含 path/query/header/cookie 参数）
        - request_body: 请求体（无则为 {}）
        - responses: 响应字典，key 为状态码字符串
    """
    if not isinstance(openapi_schema, dict):
        raise TypeError("openapi_schema 必须是 dict")

    paths = openapi_schema.get("paths")
    if not isinstance(paths, dict) or not paths:
        return []

    # 整个 schema 作为 root，用于解析 #/components/... 引用
    root = openapi_schema

    interfaces: list[dict] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        # path 级别共享的 parameters（会被该 path 下所有 method 继承）
        path_level_params = path_item.get("parameters", [])

        for key, operation in path_item.items():
            # 仅处理合法 HTTP 方法，排除 summary/description/servers/parameters 等
            if key.lower() not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue

            # 合并 path 级别 + operation 级别的 parameters
            all_params = (path_level_params or []) + (operation.get("parameters", []) or [])

            interfaces.append({
                "path": path,
                "method": key.lower().upper(),
                "summary": operation.get("summary", ""),
                "description": operation.get("description", ""),
                "parameters": _parse_parameters(all_params, root),
                "request_body": _parse_request_body(operation.get("requestBody"), root),
                "responses": _parse_responses(operation.get("responses", {}), root),
            })

    return interfaces


def extract_openapi_from_app(app) -> list[dict]:
    """
    从 FastAPI app 中获取 OpenAPI Schema 并解析为接口列表

    参数:
        app: FastAPI 实例（需具备 openapi() 方法）

    返回:
        接口描述列表
    """
    if app is None:
        raise ValueError("app 不能为 None")
    if not hasattr(app, "openapi") or not callable(getattr(app, "openapi")):
        raise TypeError("app 不是 FastAPI 应用（缺少 openapi 方法）")

    schema = app.openapi()
    return parse_openapi(schema)


if __name__ == "__main__":
    # 自演示：用最小 FastAPI 验证
    from fastapi import FastAPI
    from pydantic import BaseModel
    import json

    class Login(BaseModel):
        username: str
        password: str

    demo = FastAPI()

    @demo.get("/users/{id}", summary="获取用户")
    def get_user(id: int):
        return {"id": id}

    @demo.post("/login", summary="用户登录")
    def login(body: Login):
        return {"token": "x"}

    result = parse_openapi(demo.openapi())
    print(f"解析到 {len(result)} 个接口")
    print(json.dumps(result, ensure_ascii=False, indent=2))
