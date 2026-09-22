import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_get_user_001():
    path_params = {'user_id': 1}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
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
    # Expected: 返回200状态码，响应体包含用户信息，格式符合schema定义


def test_get_user_002():
    path_params = {'user_id': 1}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
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
    # Expected: 返回200状态码，成功获取用户信息


def test_get_user_003():
    path_params = {'user_id': 2147483647}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
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
    # Expected: 返回200状态码，成功获取用户信息（若用户不存在则返回404，但根据schema仅定义200和422，此处预期200）


def test_get_user_004():
    path_params = {}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 返回422状态码，响应体包含验证错误详情，提示缺少user_id参数


def test_get_user_005():
    path_params = {'user_id': 'abc'}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 返回422状态码，响应体包含类型验证错误，提示user_id应为整数


def test_get_user_006():
    path_params = {'user_id': -1}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 返回422状态码，响应体包含验证错误，提示user_id必须为正整数


def test_get_user_007():
    path_params = {'user_id': 0}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 返回422状态码，响应体包含验证错误，提示user_id必须大于0


def test_get_user_008():
    path_params = {'user_id': 1.5}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 返回422状态码，响应体包含类型验证错误，提示user_id应为整数


def test_get_user_009():
    path_params = {'user_id': 999999999999999999999}
    query_params = {}
    headers = {}
    body = {}

    url = _build_url(
        '/users/{user_id}',
        path_params
    )

    response = requests.request(
        method="GET",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 返回422状态码，响应体包含验证错误，提示user_id超出整数范围

