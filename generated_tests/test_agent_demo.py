import os
import requests

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:8000")


def _build_url(path_template, path_params):
    path = path_template
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))
    return BASE_URL.rstrip("/") + "/" + path.lstrip("/")


def test_agent_demo_001():
    path_params = {}
    query_params = {}
    headers = {}
    body = {'username': 'test', 'password': '123456'}

    url = _build_url('/login', path_params)

    response = requests.request(
        method="POST",
        url=url,
        params=query_params,
        headers=headers,
        json=body,
    )

    assert response.status_code == 200