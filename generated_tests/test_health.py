import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_health_001():
    path_params = {}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/health',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200
    # Expected: 接口返回200状态码，响应体为JSON格式，包含服务健康状态信息（如status: ok）


def test_health_002():
    path_params = {}
    query_params = {'foo': 'bar'}
    headers = {}
    body = {}

    url = _build_url(
        '/health',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200
    # Expected: 接口忽略未定义参数，仍返回200健康状态


def test_health_003():
    path_params = {}
    query_params = {'': ''}
    headers = {}
    body = {}

    url = _build_url(
        '/health',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200
    # Expected: 接口忽略空参数，返回200健康状态


def test_health_004():
    path_params = {}
    query_params = {}
    headers = {'X-Custom-Header': 'test'}
    body = {}

    url = _build_url(
        '/health',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200
    # Expected: 接口忽略自定义header，返回200健康状态


def test_health_005():
    path_params = {}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/health',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200
    # Expected: 连续多次请求均返回200，响应内容一致，服务状态稳定

