"""
httpx.AsyncClient.post è mockato: questi test sono deterministici e non richiedono Ollama.
"""

import asyncio
import json
from unittest.mock import patch

from api.schemas import QueryRequest
from pipeline import PlannerPipeline


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": json.dumps(self._payload)}


def _fake_post_returning(payload: dict):
    async def fake_post(self, url, json=None, **kwargs):
        return _FakeResponse(payload)

    return fake_post


async def _draft_should_not_be_called(self, request, domain):
    raise AssertionError("_draft non deve essere invocato per un dominio 'unknown'")


def test_explicit_unknown_domain_short_circuits():
    """il llm classifica esplicitamente la richiesta come fuori scope."""
    fake_post = _fake_post_returning({"domain": "unknown"})

    with patch("httpx.AsyncClient.post", new=fake_post), patch.object(
        PlannerPipeline, "_draft", new=_draft_should_not_be_called
    ):
        pipeline = PlannerPipeline(verbose=True)
        response = asyncio.run(pipeline.run(QueryRequest(question="Che tempo fa domani?")))

    assert response.domain == "unknown"
    assert response.days == []
    assert response.confidence == 0.0
    assert response.summary  # deve contenere una spiegazione, non essere vuoto


def test_malformed_classification_is_treated_as_unknown_not_forced_into_a_domain():
    """un json di classificazione senza il campo 'domain' non deve MAI produrre
    un fallback silenzioso su un dominio valido (es. 'routine')."""
    fake_post = _fake_post_returning({"nonsense": "campo inatteso"})

    with patch("httpx.AsyncClient.post", new=fake_post), patch.object(
        PlannerPipeline, "_draft", new=_draft_should_not_be_called
    ):
        pipeline = PlannerPipeline(verbose=True)
        response = asyncio.run(pipeline.run(QueryRequest(question="???")))

    assert response.domain == "unknown"
    assert response.confidence == 0.0


def test_domain_hint_still_bypasses_classification():
    """domain_hint continua a bypassare la classificazione (non è affetto dal fix)."""
    fake_post = _fake_post_returning({"title": "x", "days": [{"day_index": 1, "slots": [{"task": "a", "duration_minutes": 30}]}]})

    with patch("httpx.AsyncClient.post", new=fake_post):
        pipeline = PlannerPipeline(verbose=True)
        response = asyncio.run(
            pipeline.run(QueryRequest(question="qualsiasi cosa", domain_hint="study"))
        )

    assert response.domain == "study"