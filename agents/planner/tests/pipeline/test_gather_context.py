import asyncio
from unittest.mock import patch

from api.schemas import QueryRequest
from core.context_gathering import ContextGatherer
from core.prompts import PromptLibrary
from clients.llm_client import LLMClient


def _network_call_should_not_happen(*args, **kwargs):
    raise AssertionError("nessuna chiamata di rete attesa per questo dominio")


def _fake_llm_client():
    return LLMClient(verbose=True, provider="ollama")


def test_travel_full_success():
    async def fake_query_kg(question):
        return {"entities": ["Colosseo"]}

    async def fake_query_multiapi(question):
        return {"weather": "sereno"}

    async def fake_extract_json(*args, **kwargs):
        return {"kg_agent": "query kg", "multiapi_agent": "query meteo"}

    with patch.dict("context_gathering.TOOL_REGISTRY", {"kg_agent": fake_query_kg, "multiapi_agent": fake_query_multiapi}, clear=True), \
         patch.object(PromptLibrary, "extract_json", new=fake_extract_json):
         
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Weekend a Roma", allowed_tools=["kg_agent", "multiapi_agent"])
        context, errors = asyncio.run(gatherer.gather_deterministic("travel", request, _fake_llm_client()))

    assert errors == []
    assert context["kg_agent"] == [{"entities": ["Colosseo"]}]
    assert context["multiapi_agent"] == [{"weather": "sereno"}]


def test_travel_partial_degradation():
    async def fake_query_kg(question):
        return {"error": "kg-agent: timeout dopo 60.0s"}

    async def fake_query_multiapi(question):
        return {"weather": "sereno"}
        
    async def fake_extract_json(*args, **kwargs):
        return {"kg_agent": "query kg", "multiapi_agent": "query meteo"}

    with patch.dict("context_gathering.TOOL_REGISTRY", {"kg_agent": fake_query_kg, "multiapi_agent": fake_query_multiapi}, clear=True), \
         patch.object(PromptLibrary, "extract_json", new=fake_extract_json):
         
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Weekend a Roma", allowed_tools=["kg_agent", "multiapi_agent"])
        context, errors = asyncio.run(gatherer.gather_deterministic("travel", request, _fake_llm_client()))

    assert errors == ["kg-agent: timeout dopo 60.0s"]
    assert "kg_agent" not in context
    assert context["multiapi_agent"] == [{"weather": "sereno"}]


def test_travel_total_degradation():
    async def fake_query_kg(question):
        return {"error": "kg-agent: timeout dopo 5.0s"}

    async def fake_query_multiapi(question):
        return {"error": "multiapi-agent: errore di connessione (ConnectError)"}
        
    async def fake_extract_json(*args, **kwargs):
        return {"kg_agent": "query kg", "multiapi_agent": "query meteo"}

    with patch.dict("context_gathering.TOOL_REGISTRY", {"kg_agent": fake_query_kg, "multiapi_agent": fake_query_multiapi}, clear=True), \
         patch.object(PromptLibrary, "extract_json", new=fake_extract_json):
         
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Weekend a Roma", allowed_tools=["kg_agent", "multiapi_agent"])
        context, errors = asyncio.run(gatherer.gather_deterministic("travel", request, _fake_llm_client()))

    assert len(errors) == 2
    assert context == {}


def test_study_no_network_call():
    with patch.dict("context_gathering.TOOL_REGISTRY", {"kg_agent": _network_call_should_not_happen, "multiapi_agent": _network_call_should_not_happen}, clear=True):
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Esame di reti")
        context, errors = asyncio.run(gatherer.gather_deterministic("study", request, _fake_llm_client()))

    assert context == {}
    assert errors == []


def test_request_context_is_used_as_base_without_network_calls():
    with patch.dict("context_gathering.TOOL_REGISTRY", {}, clear=True):
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Esame di reti", context={"note": "preesistente"})
        context, errors = asyncio.run(
            gatherer.gather_deterministic("study", request, _fake_llm_client())
        )

    assert context == {"note": "preesistente"}
    assert errors == []


def test_travel_result_overwrites_conflicting_request_context_key():
    async def fake_query_kg(question):
        return {"entities": ["Colosseo"]}

    async def fake_extract_json(*args, **kwargs):
        return {"kg_agent": "query"}

    with patch.dict("context_gathering.TOOL_REGISTRY", {"kg_agent": fake_query_kg}, clear=True), \
         patch.object(PromptLibrary, "extract_json", new=fake_extract_json):
         
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Weekend a Roma", allowed_tools=["kg_agent"], context={"kg_agent": "valore precedente"})
        context, errors = asyncio.run(
            gatherer.gather_deterministic("travel", request, _fake_llm_client())
        )

    assert errors == []
    assert context["kg_agent"] == [{"entities": ["Colosseo"]}]


def test_gather_context_react_success():
    mock_decisions = [
        {"thought": "Mi serve il meteo", "action": "call_tool", "tool": "multiapi_agent", "tool_input": "Meteo a Roma?"},
        {"thought": "Ho tutto", "action": "finish"}
    ]
    
    async def mock_multiapi(question):
        return {"weather": "Sereno"}
    
    async def mock_extract_json(*args, **kwargs):
        return mock_decisions.pop(0)

    with patch.dict("context_gathering.TOOL_REGISTRY", {"multiapi_agent": mock_multiapi}, clear=True), \
         patch.object(PromptLibrary, "extract_json", new=mock_extract_json):
        
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Weekend a Roma", allowed_tools=["multiapi_agent"])
        context, errors, trace = asyncio.run(gatherer.gather_react("travel", request, _fake_llm_client()))
    
    assert errors == []
    assert len(trace) == 1
    assert trace[0]["tool"] == "multiapi_agent"
    assert trace[0]["observation"] == {"weather": "Sereno"}
    assert context["multiapi_agent"] == [{"weather": "Sereno"}]


def test_gather_context_react_dynamic_tool_removal_kg_fails():
    mock_decisions = [
        {"thought": "Provo KG", "action": "call_tool", "tool": "kg_agent", "tool_input": "Roma"},
        {"thought": "KG fallito, provo meteo", "action": "call_tool", "tool": "multiapi_agent", "tool_input": "meteo Roma"},
        {"thought": "Finito", "action": "finish"}
    ]

    tools_seen_by_llm = []

    async def mock_extract_json(*args, **kwargs):
        tools_seen_by_llm.append(kwargs.get("tools", ""))
        return mock_decisions.pop(0)

    async def mock_kg(question):
        return {"error": "Timeout simulato su KG"}
        
    async def mock_multiapi(question):
        return {"weather": "sereno"}

    with patch.dict("context_gathering.TOOL_REGISTRY", {"multiapi_agent": mock_multiapi, "kg_agent": mock_kg}, clear=True), \
         patch.object(PromptLibrary, "extract_json", new=mock_extract_json):
        
        gatherer = ContextGatherer(PromptLibrary(), verbose=True)
        request = QueryRequest(question="Weekend a Roma", allowed_tools=["kg_agent", "multiapi_agent"])
        context, errors, trace = asyncio.run(gatherer.gather_react("travel", request, _fake_llm_client()))

    assert "Timeout simulato su KG" in errors
    assert "kg_agent" not in context
    assert context["multiapi_agent"] == [{"weather": "sereno"}]
    
    assert "kg_agent" in tools_seen_by_llm[0]
    assert "kg_agent" not in tools_seen_by_llm[1]
    assert "multiapi_agent" in tools_seen_by_llm[1]