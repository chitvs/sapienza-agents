import asyncio

import pytest
from core.pipeline import PlannerPipeline
from api.schemas import QueryRequest

@pytest.mark.requires_llm
def test_esame_universitario():
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(
        pipeline.run(QueryRequest(question="Devo preparare l'esame di Reti in 3 settimane, studio 2 ore al giorno nei feriali"))
    )
    assert response.domain == "study"
    assert len(response.days) > 0
    assert response.confidence > 0


@pytest.mark.requires_llm
def test_weekend_fuori_porta():
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(pipeline.run(QueryRequest(question="Organizzami un weekend fuori porta a Firenze")))
    assert response.domain == "travel"
    assert len(response.days) > 0
    assert response.confidence > 0


@pytest.mark.requires_llm
def test_weekend_fuori_porta_con_contesto_recuperato():
    """dominio 'travel': verifica il nuovo step di context gathering (Step 5). kg-agent e
    multiapi-agent possono non essere in esecuzione in locale: la pipeline non deve MAI
    crashare per questo - in quel caso ogni fallimento finisce descritto singolarmente in
    contingency_notes (mai un errore silenzioso) e la confidence resta comunque > 0 grazie
    al floor. Skip solo su Ollama, non su kg-agent/multiapi-agent (nessuna dipendenza dura)."""
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(pipeline.run(QueryRequest(question="Organizzami un weekend fuori porta a Firenze")))

    assert response.domain == "travel"
    assert len(response.days) > 0
    assert response.confidence > 0

    if response.gathered_context:
        # kg-agent/multiapi-agent raggiungibili: risposte grezze sotto le chiavi note
        assert set(response.gathered_context.keys()) <= {"kg_agent", "multiapi_agent"}
    else:
        # kg-agent/multiapi-agent non raggiungibili: il degrado è tracciato, non silenzioso
        assert response.contingency_notes


@pytest.mark.requires_llm
def test_routine_lavorativa():
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(pipeline.run(QueryRequest(question="Voglio strutturare meglio le mie giornate lavorative")))
    assert response.domain == "routine"
    assert len(response.days) == 7


@pytest.mark.requires_llm   
def test_domanda_fuori_scope():
    """esempio del prompt di classificazione: non deve produrre un piano forzato."""
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(pipeline.run(QueryRequest(question="Che tempo fa domani?")))
    assert response.domain == "unknown"
    assert response.days == []
    assert response.confidence == 0.0