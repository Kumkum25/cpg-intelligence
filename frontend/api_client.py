"""Thin HTTP wrapper around the FastAPI backend. The frontend never touches
nexus_engine directly — everything goes through the API, exactly like a
real deployment would (backend and frontend as separate processes).
"""
from __future__ import annotations

import os

import requests

BASE_URL = os.environ.get("NEXUS_API_URL", "http://localhost:8000")


class APIError(Exception):
    pass


def _handle(resp: requests.Response):
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise APIError(f"{resp.status_code}: {detail}")
    return resp.json()


def get(path: str, params: dict | None = None):
    return _handle(requests.get(f"{BASE_URL}{path}", params=params, timeout=60))


def post(path: str, json: dict | None = None):
    return _handle(requests.post(f"{BASE_URL}{path}", json=json, timeout=120))


def get_raw(path: str, params: dict | None = None) -> requests.Response:
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=60)
    if resp.status_code >= 400:
        raise APIError(f"{resp.status_code}: {resp.text}")
    return resp


def health() -> dict:
    return get("/health")


def is_backend_up() -> bool:
    try:
        requests.get(f"{BASE_URL}/health", timeout=3)
        return True
    except requests.exceptions.RequestException:
        return False
