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
        "- 'planner_agent': per attività di pianificazione, scomposizione o piani complessi, quali creare un piano, un itinerario, una routine, un programma di studio.\n"
        "- 'multiapi_agent': per chiamate e integrazioni multi-API esterne.\n"
        "REGOLA IMPORTANTE: Se decidi di attivare il 'planner_agent', NON attivare 'kg_agent' o 'multiapi_agent', poiché il planner è autonomo nel recuperare il contesto di cui ha bisogno.\n"
        "Rispondi esclusivamente con un JSON in formato oggetto (es. {\"selected_agents\": [\"planner_agent\"]}) oppure un array (es. [\"planner_agent\"])."
    )

    response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=question)])

    selected = []
    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        
        parsed = json.loads(content)
        # Gestisce sia se l'LLM risponde con una lista sia con un dizionario
        if isinstance(parsed, list):
            selected = parsed
        elif isinstance(parsed, dict):
            selected = parsed.get("selected_agents", [])
            
        if not isinstance(selected, list):
            selected = []
    except Exception as err:
        logger.warning("Routing supervisor fallito: %s (Risposta grezza: %s)", err, response.content)
        selected = []

    return {"selected_agents": selected}

async def kg_node(state: AgentState) -> dict:
    """nodo che invoca direttamente il microservizio kg-agent via HTTP REST."""
    async with httpx.AsyncClient(timeout=330.0) as client:
        try:
            res = await client.post(f"{settings.kg_agent_url}/query", json={"question": state["question"]})
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
    
    # Integrazione del nuovo schema del Planner (title, summary, days)
    planner_res = state.get("planner_results")
    if planner_res:
        if "days" in planner_res and planner_res["days"]:
            plan_str = f"Titolo Piano: {planner_res.get('title', 'N/D')}\n"
            if planner_res.get("summary"):
                plan_str += f"Sommario: {planner_res.get('summary')}\n"
            for day in planner_res["days"]:
                plan_str += f"- Giorno {day.get('day_index')}"
                if day.get("label"):
                    plan_str += f" ({day.get('label')})"
                plan_str += ":\n"
                for slot in day.get("slots", []):
                    time_slot = f"[{slot.get('start_time')}] " if slot.get("start_time") else ""
                    plan_str += f"  * {time_slot}{slot.get('task')} ({slot.get('duration_minutes')} min)\n"
            evidences.append(f"Evidenze da Planning:\n{plan_str}")
        elif planner_res.get("results"):
            evidences.append(f"Evidenze da Planning: {planner_res['results']}")

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