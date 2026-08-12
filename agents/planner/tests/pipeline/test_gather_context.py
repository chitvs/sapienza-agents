"""
Test per _gather_context (Step 5 della roadmap planner): dispatch deterministico per
dominio, degrado parziale/totale su 'travel', nessuna chiamata di rete per study/routine
- stesso principio già verificato per il dominio 'unknown' in test_domain_classification.py.

query_kg/query_multiapi vengono patchati direttamente nel namespace di pipeline (dove
sono importati), non in tools: così i test restano indipendenti dai dettagli di
implementazione di tools.py, già coperti separatamente in test_tools.py.
"""

import asyncio
from unittest.mock import patch

from api.schemas import QueryRequest
from pipeline import PlannerPipeline


def _network_call_should_not_happen(*args, **kwargs):
    raise AssertionError("nessuna chiamata di rete attesa per questo dominio")


def test_travel_full_success():
    async def fake_query_kg(question):
        return {"entities": ["Colosseo"]}

    async def fake_query_multiapi(question):
        return {"weather": "sereno"}

    with patch("pipeline.query_kg", new=fake_query_kg), patch("pipeline.query_multiapi", new=fake_query_multiapi):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(pipeline._gather_context("travel", QueryRequest(question="Weekend a Roma")))

    assert errors == []
    assert context["kg_agent"] == {"entities": ["Colosseo"]}
    assert context["multiapi_agent"] == {"weather": "sereno"}


def test_travel_partial_degradation():
    async def fake_query_kg(question):
        return {"error": "kg-agent: timeout dopo 60.0s"}

    async def fake_query_multiapi(question):
        return {"weather": "sereno"}

    with patch("pipeline.query_kg", new=fake_query_kg), patch("pipeline.query_multiapi", new=fake_query_multiapi):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(pipeline._gather_context("travel", QueryRequest(question="Weekend a Roma")))

    assert errors == ["kg-agent: timeout dopo 60.0s"]
    assert "kg_agent" not in context
    assert context["multiapi_agent"] == {"weather": "sereno"}


def test_travel_total_degradation():
    async def fake_query_kg(question):
        return {"error": "kg-agent: timeout dopo 5.0s"}

    async def fake_query_multiapi(question):
        return {"error": "multiapi-agent: errore di connessione (ConnectError)"}

    with patch("pipeline.query_kg", new=fake_query_kg), patch("pipeline.query_multiapi", new=fake_query_multiapi):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(pipeline._gather_context("travel", QueryRequest(question="Weekend a Roma")))

    assert len(errors) == 2
    assert context == {}


def test_study_no_network_call():
    with patch("pipeline.query_kg", side_effect=_network_call_should_not_happen), patch(
        "pipeline.query_multiapi", side_effect=_network_call_should_not_happen
    ):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(pipeline._gather_context("study", QueryRequest(question="Esame di reti")))

    assert context == {}
    assert errors == []


def test_routine_no_network_call():
    with patch("pipeline.query_kg", side_effect=_network_call_should_not_happen), patch(
        "pipeline.query_multiapi", side_effect=_network_call_should_not_happen
    ):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(pipeline._gather_context("routine", QueryRequest(question="Giornate lavorative")))

    assert context == {}
    assert errors == []


def test_request_context_is_used_as_base_without_network_calls():
    """study/routine: request.context viene comunque riportato in output, senza alcuna
    chiamata di rete."""
    with patch("pipeline.query_kg", side_effect=_network_call_should_not_happen), patch(
        "pipeline.query_multiapi", side_effect=_network_call_should_not_happen
    ):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(
            pipeline._gather_context(
                "study", QueryRequest(question="Esame di reti", context={"note": "preesistente"})
            )
        )

    assert context == {"note": "preesistente"}
    assert errors == []


def test_travel_result_overwrites_conflicting_request_context_key():
    async def fake_query_kg(question):
        return {"entities": ["Colosseo"]}

    async def fake_query_multiapi(question):
        return {"weather": "sereno"}

    with patch("pipeline.query_kg", new=fake_query_kg), patch("pipeline.query_multiapi", new=fake_query_multiapi):
        pipeline = PlannerPipeline(verbose=True)
        context, errors = asyncio.run(
            pipeline._gather_context(
                "travel", QueryRequest(question="Weekend a Roma", context={"kg_agent": "valore precedente"})
            )
        )

    assert errors == []
    assert context["kg_agent"] == {"entities": ["Colosseo"]}