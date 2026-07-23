"""Shared test fixtures.

Each test gets a fresh Storage backed by a pytest tmp_path, wired in through the
get_storage dependency override, so tests never touch the repository's real JSON
data files and never interfere with each other.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from storage import Storage


@pytest.fixture
def storage(tmp_path):
    store = Storage(tmp_path)
    store.ensure_initialised()
    return store


@pytest.fixture
def client(storage):
    main.app.dependency_overrides[main.get_storage] = lambda: storage
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
