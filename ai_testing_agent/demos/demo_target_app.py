# -*- coding: utf-8 -*-
"""
本地演示目标 API - AI 测试流水线第四阶段

提供被测 FastAPI 服务，配合 generated_tests 真实端到端验证。

接口：
- POST /login
    * body 必须含 username/password（Pydantic 自动校验缺失/类型 -> 422）
    * username/password 为空字符串 -> 422
    * password 长度 > 128 -> 422
    * username=="test" 且 password=="123456" -> 200（合法凭据通过 OpenAPI example 暴露）
    * 其余凭据 -> 401
- GET  /users/{id}   返回 {id, name}
- GET  /health       存活探针

不引入数据库、不引入外部网络依赖。

注：本模块是流水线的“被测演示目标”（测试夹具），不是受 Agent 保护的业务源码；
其确定性校验用于让 normal / missing-field / invalid-input / boundary 用例可重复验证。
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

app = FastAPI(title="Demo Target API")

PASSWORD_MAX_LENGTH = 128


class LoginRequest(BaseModel):
    # 通过 OpenAPI example 暴露合法凭据，供 LLM 据此设计“正常登录”用例
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"username": "test", "password": "123456"}
        }
    )

    username: str = Field(..., description="用户名，非空字符串")
    password: str = Field(
        ...,
        max_length=PASSWORD_MAX_LENGTH,
        description="密码，非空，长度不超过 128",
    )


@app.post(
    "/login",
    summary="用户登录",
    description=(
        "登录接口精确返回契约（设计断言时必须遵守）：\n"
        "1) 仅当 username=='test' 且 password=='123456' 时返回 200"
        "（唯一合法凭据，见 requestBody schema 的 example，正常用例必须使用该值）；\n"
        "2) 请求体缺少 username/password、字段为空字符串、字段类型不是字符串、"
        "password 长度超过 128，均返回 422（参数校验失败）；\n"
        "3) 字段齐全且格式合法、但用户名或密码不匹配（含任意非 test/123456 的合法字符串），"
        "返回 401（鉴权失败），此类场景不得标注为 422。"
    ),
    responses={
        200: {"description": "登录成功，返回 token"},
        401: {"description": "凭据格式合法，但用户名或密码错误"},
        422: {"description": "参数校验失败：字段缺失/空串/类型错误/密码超长"},
    },
)
def login(req: LoginRequest):
    # 空值校验（Pydantic str 允许空串，显式拒绝）
    if not req.username.strip() or not req.password:
        raise HTTPException(status_code=422, detail="username/password 不能为空")
    # 超长密码（>128）由 Pydantic Field(max_length=...) 在进入本函数前直接拒绝为 422，
    # 边界同时以结构化形式出现在 OpenAPI schema（maxLength）中，供测试设计读取。
    if req.username == "test" and req.password == "123456":
        return {"token": "fake-login-token", "user": req.username}
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@app.get("/users/{user_id}")
def get_user(user_id: int):
    return {"id": user_id, "name": f"user_{user_id}"}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
