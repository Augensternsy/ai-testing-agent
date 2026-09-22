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
    # Expected: 返回200状态码，响应体包含用户信息


def test_get_user_002():
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
    # Expected: 返回422状态码，提示user_id校验失败


def test_get_user_003():
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
    # Expected: 返回422状态码，提示user_id校验失败


def test_get_user_004():
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
    # Expected: 返回200状态码，响应体包含用户信息（若用户存在）


def test_get_user_005():
    path_params = {'user_id': 2147483648}
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
    # Expected: 返回422状态码，提示user_id类型或范围校验失败


def test_get_user_006():
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
    # Expected: 返回422状态码，提示缺少必填参数user_id


def test_get_user_007():
    path_params = {'user_id': ''}
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
    # Expected: 返回422状态码，提示user_id类型校验失败


def test_get_user_008():
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
    # Expected: 返回422状态码，提示user_id类型校验失败


def test_get_user_009():
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
    # Expected: 返回422状态码，提示user_id类型校验失败


def test_get_user_010():
    path_params = {'user_id': '@#$'}
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
    # Expected: 返回422状态码，提示user_id类型校验失败

