"""
Test unitari per tools.py: verificano che query_kg/
query_multiapi rispettino il contratto {"error": "..."} in caso di fallimento - mai
un'eccezione propagata - sia in caso di successo che di timeout/errore HTTP/errore di
connessione.

Stesso pattern di mock già in uso in test_domain_classification.py: si sostituisce
httpx.AsyncClient.post con una funzione async fittizia, nessuna dipendenza da
pytest-asyncio.
"""

import asyncio
from unittest.mock import patch

import httpx

from core.tools import query_kg, query_multiapi


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://fake/query")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("errore http", request=request, response=response)

    def json(self):
        return self._payload


def _fake_post_returning(payload: dict, status_code: int = 200):
    async def fake_post(self, url, json=None, **kwargs):
        return _FakeResponse(payload, status_code)

    return fake_post


def _fake_post_raising(exc: Exception):
    async def fake_post(self, url, json=None, **kwargs):
        raise exc

    return fake_post


# ---------------------------------------------------------------------------
# query_kg
# ---------------------------------------------------------------------------

def test_query_kg_success():
    fake_post = _fake_post_returning({"results": ["entità trovata"]})
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_kg("Cosa vedere a Roma?"))
    assert result == {"results": ["entità trovata"]}
    assert "error" not in result


def test_query_kg_timeout():
    fake_post = _fake_post_raising(httpx.TimeoutException("timeout"))
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_kg("Cosa vedere a Roma?"))
    assert "error" in result
    assert "kg-agent" in result["error"]
    assert "timeout" in result["error"].lower()


def test_query_kg_http_error():
    fake_post = _fake_post_returning({"detail": "internal error"}, status_code=500)
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_kg("Cosa vedere a Roma?"))
    assert "error" in result
    assert "kg-agent" in result["error"]


def test_query_kg_connection_error():
    fake_post = _fake_post_raising(httpx.ConnectError("connection refused"))
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_kg("Cosa vedere a Roma?"))
    assert "error" in result
    assert "kg-agent" in result["error"]


# ---------------------------------------------------------------------------
# query_multiapi
# ---------------------------------------------------------------------------

def test_query_multiapi_success():
    fake_post = _fake_post_returning({"weather": "sereno"})
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_multiapi("Che tempo fa a Firenze?"))
    assert result == {"weather": "sereno"}
    assert "error" not in result


def test_query_multiapi_timeout():
    fake_post = _fake_post_raising(httpx.TimeoutException("timeout"))
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_multiapi("Che tempo fa a Firenze?"))
    assert "error" in result
    assert "multiapi-agent" in result["error"]


def test_query_multiapi_http_error():
    fake_post = _fake_post_returning({"detail": "bad gateway"}, status_code=502)
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_multiapi("Che tempo fa a Firenze?"))
    assert "error" in result
    assert "multiapi-agent" in result["error"]


def test_query_multiapi_connection_error():
    fake_post = _fake_post_raising(httpx.ConnectError("connection refused"))
    with patch("httpx.AsyncClient.post", new=fake_post):
        result = asyncio.run(query_multiapi("Che tempo fa a Firenze?"))
    assert "error" in result
    assert "multiapi-agent" in result["error"]