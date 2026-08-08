import json
import httpx
import logging
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from src.config import settings
from src.graph.state import AgentState

logger = logging.getLogger(__name__)
llm = ChatOllama(base_url=settings.ollama_host, model=settings.ollama_model, temperature=0.0)

async def supervisor_node(state: AgentState) -> dict:
    """nodo supervisor: analizza la domanda e seleziona gli agenti da attivare."""
    question = state["question"]

    system_prompt = (
        "Sei il supervisor di un sistema multi-agente. Analizza la domanda e decidi quali agenti attivare.\n"
        "Agenti disponibili:\n"
        "- 'kg_agent': per domande su entità, relazioni strutturate, fatti e conoscenze.\n"
        "- 'planner_agent': per attività di pianificazione, scomposizione o piani complessi.\n"
        "- 'multiapi_agent': per chiamate e integrazioni multi-API esterne.\n"
        "Rispondi esclusivamente con un JSON array contenente i nomi degli agenti necessari, es: [\"kg_agent\"] oppure [\"planner_agent\", \"multiapi_agent\"]."
    )

    response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=question)])

    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        selected = json.loads(content)
        if not isinstance(selected, list):
            selected = []
    except Exception as err:
        logger.warning("Routing supervisor fallito: %s", err)
        selected = []

    return {"selected_agents": selected}

async def kg_node(state: AgentState) -> dict:
    """nodo che invoca direttamente il microservizio kg-agent via HTTP REST."""
    payload = {"question": state["question"]}
    if state.get("target_kg"):
        payload["target_kg"] = state["target_kg"]

    async with httpx.AsyncClient(timeout=330.0) as client:
        try:
            res = await client.post(f"{settings.kg_agent_url}/query", json=payload)
            res.raise_for_status()
            return {"kg_results": res.json()}
        except Exception as err:
            logger.warning("Chiamata a kg-agent fallita: %s", err)
            return {"kg_results": {"error": str(err), "results": []}}

async def planner_node(state: AgentState) -> dict:
    """nodo che invoca direttamente il microservizio planner-agent via HTTP REST."""
    async with httpx.AsyncClient(timeout=330.0) as client:
        try:
            res = await client.post(f"{settings.planner_agent_url}/query", json={"question": state["question"]})
            res.raise_for_status()
            return {"planner_results": res.json()}
        except Exception as err:
            logger.warning("Chiamata a planner-agent fallita: %s", err)
            return {"planner_results": {"error": str(err), "results": []}}

async def multiapi_node(state: AgentState) -> dict:
    """nodo che invoca direttamente il microservizio multiapi-agent via HTTP REST."""
    async with httpx.AsyncClient(timeout=330.0) as client:
        try:
            res = await client.post(f"{settings.multiapi_agent_url}/query", json={"question": state["question"]})
            res.raise_for_status()
            return {"multiapi_results": res.json()}
        except Exception as err:
            logger.warning("Chiamata a multiapi-agent fallita: %s", err)
            return {"multiapi_results": {"error": str(err), "results": []}}

async def synthesizer_node(state: AgentState) -> dict:
    """nodo sintetizzatore: unisce le evidenze raccolte dagli agenti attivati e genera la risposta finale."""
    question = state["question"]
    evidences = []

    if state.get("kg_results") and state["kg_results"].get("results"):
        evidences.append(f"Evidenze da Knowledge Graph: {state['kg_results']['results']}")
    if state.get("planner_results") and state["planner_results"].get("results"):
        evidences.append(f"Evidenze da Planning: {state['planner_results']['results']}")
    if state.get("multiapi_results") and state["multiapi_results"].get("results"):
        evidences.append(f"Evidenze da Multi-API: {state['multiapi_results']['results']}")

    context_str = "\n".join(evidences) if evidences else "Nessuna evidenza trovata dagli agenti."

    system_prompt = (
        "Sei un assistente AI integrato. Rispondi alla domanda dell'utente in modo chiaro, naturale e professionale "
        "basandoti esclusivamente sulle seguenti evidenze raccolte dagli agenti."
    )
    user_content = f"Domanda: {question}\n\nEvidenze:\n{context_str}"

    response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_content)])
    return {"final_response": response.content}