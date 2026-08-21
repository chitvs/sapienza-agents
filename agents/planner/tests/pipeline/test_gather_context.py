"""
Test per _gather_context: dispatch deterministico per
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
    assert context["kg_agent"] == [{"entities": ["Colosseo"]}]
    assert context["multiapi_agent"] == [{"weather": "sereno"}]


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
    assert context["multiapi_agent"] == [{"weather": "sereno"}]


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
    assert context["kg_agent"] == [{"entities": ["Colosseo"]}]

def test_gather_context_react_success():
    """Simula un loop ReAct: LLM chiama il meteo al primo step, poi decide di finire al secondo."""
    
    # Risposte sequenziali simulate dell'LLM
    mock_decisions = [
        {"thought": "Mi serve il meteo", "action": "call_tool", "tool": "multiapi_agent", "tool_input": "Meteo a Roma?"},
        {"thought": "Ho tutto", "action": "finish"}
    ]
    
    # Mock dello strumento reale
    async def mock_multiapi(question):
        return {"weather": "Sereno"}
    
    async def mock_llm_extract_json(*args, **kwargs):
        return mock_decisions.pop(0)

    with patch.object(PlannerPipeline, "_llm_extract_json", new=mock_llm_extract_json), \
         patch.dict("pipeline.TOOL_REGISTRY", {"multiapi_agent": mock_multiapi}, clear=True):
        
        pipeline = PlannerPipeline(verbose=True)
        context, errors, trace = asyncio.run(
            pipeline._gather_context_react("travel", QueryRequest(question="Weekend a Roma"))
        )
    
    # Verifiche
    assert errors == []
    assert len(trace) == 1 # Solo lo step "call_tool" finisce nel trace eseguito, il finish interrompe
    assert trace[0]["tool"] == "multiapi_agent"
    assert trace[0]["observation"] == {"weather": "Sereno"}
    # Il context è una lista, come abbiamo stabilito per il ReAct
    assert context["multiapi_agent"] == [{"weather": "Sereno"}]


def test_gather_context_react_dynamic_tool_removal_kg_fails():
    """Simula un loop ReAct dove il kg_agent fallisce e viene rimosso, poi il multiapi_agent ha successo."""
    from api.schemas import QueryRequest
    
    # 1. Simuliamo le decisioni in sequenza dell'LLM (prima KG, poi MultiAPI)
    mock_decisions = [
        {"thought": "Provo KG", "action": "call_tool", "tool": "kg_agent", "tool_input": "Roma"},
        {"thought": "KG fallito, provo meteo", "action": "call_tool", "tool": "multiapi_agent", "tool_input": "meteo Roma"},
        {"thought": "Finito", "action": "finish"}
    ]

    tools_seen_by_llm = []

    async def mock_llm_extract_json(*args, **kwargs):
        # Salviamo la stringa JSON dei tool che l'LLM "vede" ad ogni iterazione
        tools_seen_by_llm.append(kwargs.get("tools", ""))
        return mock_decisions.pop(0)

    # 2. Simuliamo il fallimento del KG e il successo del MultiAPI
    async def mock_kg(question):
        return {"error": "Timeout simulato su KG"}
        
    async def mock_multiapi(question):
        return {"weather": "sereno"}

    with patch.object(PlannerPipeline, "_llm_extract_json", new=mock_llm_extract_json), \
         patch.dict("pipeline.TOOL_REGISTRY", {"multiapi_agent": mock_multiapi, "kg_agent": mock_kg}, clear=True):
        
        pipeline = PlannerPipeline(verbose=True)
        context, errors, trace = asyncio.run(
            pipeline._gather_context_react("travel", QueryRequest(question="Weekend a Roma"))
        )

    # 3. Verifiche finali dell'output
    assert "Timeout simulato su KG" in errors
    assert "kg_agent" not in context
    assert context["multiapi_agent"] == [{"weather": "sereno"}]
    
    # 4. Verifica della RIMOZIONE DINAMICA
    # Al passo 1 l'LLM doveva vedere kg_agent nel prompt
    assert "kg_agent" in tools_seen_by_llm[0]
    
    # Al passo 2 (dopo l'errore) kg_agent deve essere sparito, ma multiapi_agent deve esserci
    assert "kg_agent" not in tools_seen_by_llm[1]
    assert "multiapi_agent" in tools_seen_by_llm[1]