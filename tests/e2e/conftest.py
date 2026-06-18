"""Shared fixtures for end-to-end API journey tests."""

import uuid

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_id():
    return f"e2e-{uuid.uuid4().hex[:10]}"
