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
    # Expected: 返回200，响应体包含token字段，登录成功


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
    # Expected: 返回422，提示username为必填字段


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
    # Expected: 返回422，提示password为必填字段


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
    # Expected: 返回422，提示username不能为空字符串


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
    # Expected: 返回422，提示password不能为空字符串


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
    # Expected: 返回422，提示username类型必须为字符串


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
    # Expected: 返回422，提示password类型必须为字符串


def test_login_008():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'wronguser',
 'password': '12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678'}

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
    # Expected: 返回401，用户名错误导致鉴权失败


def test_login_009():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test',
 'password': '123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789'}

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
    # Expected: 返回422，提示password长度超过128


def test_login_010():
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
    # Expected: 返回401，提示用户名或密码错误


def test_login_011():
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
    # Expected: 返回401，提示用户名或密码错误


def test_login_012():
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
    # Expected: 返回401，提示用户名或密码错误

