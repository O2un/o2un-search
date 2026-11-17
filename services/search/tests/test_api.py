"""DB 에 닿기 전에 끝나는 경로(인증, 입력 검사)만 본다."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "test-key")
    monkeypatch.setenv("SEARCH_READER_URL", "postgresql://unused")
    import main

    return TestClient(main.app)


def test_missing_or_wrong_key_is_401(client) -> None:
    assert client.post("/search", json={"query": "검색"}).status_code == 401
    assert client.post("/search", json={"query": "검색"}, headers={"x-search-key": "nope"}).status_code == 401


def test_unset_key_rejects_everything(client, monkeypatch) -> None:
    monkeypatch.delenv("SEARCH_API_KEY")
    assert client.post("/search", json={"query": "검색"}, headers={"x-search-key": ""}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"query": "   "},
        {"query": "가" * 201},
        {"query": "검색", "limit": 0},
        {"query": "검색", "limit": 21},
        {"query": "검색", "section": "../x"},
        {"query": 3},
        {},
    ],
)
def test_bad_input_is_400_without_details(client, body) -> None:
    response = client.post("/search", json=body, headers={"x-search-key": "test-key"})
    assert response.status_code == 400
    assert response.json() == {"detail": "bad request"}
