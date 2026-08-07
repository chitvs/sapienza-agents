import asyncio
import httpx
import pytest
from pipeline import PlannerPipeline
from api.schemas import QueryRequest


def is_ollama_running():
    try:
        return httpx.get("http://localhost:11434/", timeout=1).status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_esame_universitario():
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(
        pipeline.run(QueryRequest(question="Devo preparare l'esame di Reti in 3 settimane, studio 2 ore al giorno nei feriali"))
    )
    assert response.domain == "study"
    assert len(response.days) > 0
    assert response.confidence > 0


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_weekend_fuori_porta():
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(pipeline.run(QueryRequest(question="Organizzami un weekend fuori porta a Firenze")))
    assert response.domain == "travel"
    assert len(response.days) > 0
    assert response.confidence > 0


@pytest.mark.skipif(not is_ollama_running(), reason="Ollama non è attivo")
def test_routine_lavorativa():
    pipeline = PlannerPipeline(verbose=True)
    response = asyncio.run(pipeline.run(QueryRequest(question="Voglio strutturare meglio le mie giornate lavorative")))
    assert response.domain == "routine"
    assert len(response.days) == 7