import json
import re
import httpx
import logging
from typing import Any
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from src.config import settings
from src.graph.state import AgentState

logger = logging.getLogger(__name__)
llm = ChatOllama(base_url=settings.ollama_host, model=settings.ollama_model, temperature=0.0)

def _parse_json(content: str) -> Any:
    """estrae il json dalla risposta del modello, che spesso lo incapsula in un blocco markdown."""
    text = content.strip()
    if "```" in text:
        text = re.sub(r"^json\b", "", text.split("```")[1].strip(), flags=re.IGNORECASE).strip()
    return json.loads(text)

async def _translate_question(question: str) -> tuple[str, str]:
    """Helper interno per il KG agent: traduce in inglese e rileva la lingua."""
    system_prompt = (
        "Identifica la lingua della domanda dell'utente e traducila in inglese.\n"
        "Se è già in inglese riportala invariata. Mantieni i nomi propri intatti.\n"
        "Rispondi esclusivamente con un JSON: {\"language\": \"<lingua>\", \"question\": \"<domanda in inglese>\"}"
    )
    try:
        response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=question)])
        data = _parse_json(response.content)
        q_en = str(data.get("question") or "").strip() or question
        lang = str(data.get("language") or "").strip() or "italiano"
    except Exception as err:
        logger.warning("Traduzione fallita: %s", err)
        q_en, lang = question, "italiano"
    return q_en, lang

async def supervisor_node(state: AgentState) -> dict:
    """Nodo supervisor: pianifica e delega attivando uno o più agenti."""
    question = state["question"]
    agent_names = list(settings.agent_registry.keys())
    descriptions = "\n".join(f"- '{name}': {settings.agent_descriptions.get(name, '')}" for name in agent_names)

    system_prompt = (
        "Sei il supervisor di un sistema multi-agente. Analizza la domanda e decidi quali agenti attivare.\n"
        "Agenti disponibili:\n"
        "- 'kg_agent': per domande su entità, relazioni strutturate, fatti e conoscenze.\n"
        
        "- 'planner_agent': per attività di pianificazione, scomposizione o piani complessi, quali creare un piano, un itinerario, una routine, un programma di studio.\n"
        "- 'multiapi_agent': per dati in tempo reale che richiedono un'api esterna: "
        "meteo e temperatura attuali di una città, tasso di cambio fra due valute, "
        "ora locale corrente in una città o fuso orario e le informazioni su un paese: capitale, popolazione, superficie, lingue, valuta, confini.\n"
        "REGOLA IMPORTANTE: Se decidi di attivare il 'planner_agent', NON attivare 'kg_agent' o 'multiapi_agent', poiché il planner è autonomo nel recuperare il contesto di cui ha bisogno.\n"
        "Rispondi esclusivamente con un JSON in formato oggetto (es. {\"selected_agents\": [\"planner_agent\"]}) oppure un array (es. [\"planner_agent\"])."
    )

    try:
        response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=question)])
        parsed = _parse_json(response.content)
        selected = parsed.get("selected_agents", [])
        if not isinstance(selected, list):
            selected = [selected] if isinstance(selected, str) else []
    except Exception as err:
        logger.warning("Routing supervisor fallito: %s", err)
        selected = []

    valid_selected = [a for a in selected if a in agent_names]
    return {"selected_agents": valid_selected}

AGENT_TIMEOUT = httpx.Timeout(settings.agent_request_timeout_seconds)

def make_agent_node(agent_name: str):
    """Genera dinamicamente il nodo per interrogare il singolo agente."""
    agent_url = settings.agent_registry[agent_name]

    async def _node(state: AgentState) -> dict:
        payload = {"question": state["question"]}
        state_updates = {}
        
        # Gestione specifica di traduzione e parametri aggiuntivi per il KG
        if agent_name == "kg_agent":
            q_en, lang = await _translate_question(state["question"])
            payload["question"] = q_en
            state_updates["language"] = lang
            if state.get("target_kg"):
                payload["target_kg"] = state.get("target_kg")

        async with httpx.AsyncClient(timeout=AGENT_TIMEOUT) as client:
            try:
                res = await client.post(f"{agent_url}/query", json=payload)
                res.raise_for_status()
                state_updates["agent_results"] = {agent_name: res.json()}
            except Exception as err:
                logger.warning("Chiamata a %s fallita: %s", agent_name, err)
                state_updates["agent_results"] = {agent_name: {"error": str(err)}}
                
        return state_updates

    return _node

async def unsupported_node(state: AgentState) -> dict:
    return {"final_response": settings.out_of_scope_message}

async def synthesizer_node(state: AgentState) -> dict:
    """Nodo sintetizzatore: integra i risultati di TUTTI gli agenti chiamati in un'unica risposta."""
    question = state["question"]
    selected_agents = state.get("selected_agents", [])
    agent_results = state.get("agent_results", {})
    
    evidences = []
    for agent in selected_agents:
        res = agent_results.get(agent)
        if res and "error" not in res:
            evidences.append(f"--- Risultati da {agent} ---\n{json.dumps(res, ensure_ascii=False)}")
        elif res and "error" in res:
            evidences.append(f"--- Fallimento da {agent} ---\nL'agente ha riportato un errore: {res['error']}")
            
    if not evidences:
        return {"final_response": "Mi dispiace, si è verificato un errore o gli agenti non hanno restituito dati."}

    context_str = "\n\n".join(evidences)
    language = state.get("language") or "italiano"

    system_prompt = (
        "Sei un assistente AI integrato. Hai delegato una richiesta in parallelo a vari agenti "
        "e hai ricevuto i loro risultati strutturati in formato JSON.\n"
        "Rispondi alla domanda dell'utente in modo chiaro, naturale e professionale, "
        "integrando tutti i risultati in un'unica risposta discorsiva basandoti esclusivamente "
        "sulle seguenti evidenze raccolte dagli agenti.\n"
        "Le evidenze sono già state recuperate da fonti attendibili e sono valide, comprese quelle "
        "su dati in tempo reale o su giorni futuri: riportale come fatti accertati. "
        "Non mostrare JSON grezzi, markdown tecnici o strutture dati. "
        "Non premettere che non puoi conoscere queste informazioni e non invitare a verificarle altrove.\n"
        f"Le evidenze possono essere in inglese: scrivi comunque la risposta in {language}."
    )
    
    user_content = f"Domanda utente: {question}\n\nRisultati grezzi:\n{context_str}"

    try:
        response = await llm.ainvoke([SystemMessage(content=system_prompt), HumanMessage(content=user_content)])
        final_text = response.content
    except Exception as err:
        logger.warning("Sintesi della risposta fallita: %s", err)
        final_text = "Ecco i risultati strutturati trovati dagli agenti."

    return {"final_response": final_text}