import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_login_001():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': '123456'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200
    # Expected: 登录成功，返回token


def test_login_002():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'password': '123456'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_003():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_004():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': '', 'password': '123456'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_005():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': ''}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_006():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 123, 'password': '123456'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_007():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': True}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_008():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test',
 'password': '1234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 422
    # Expected: 参数校验失败，返回422


def test_login_009():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'wronguser', 'password': '123456'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 401
    # Expected: 鉴权失败，返回401


def test_login_010():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': 'wrongpass'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 401
    # Expected: 鉴权失败，返回401


def test_login_011():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'wronguser', 'password': 'wrongpass'}

    url = _build_url(
        '/login',
        path_params
    )

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 401
    # Expected: 鉴权失败，返回401

