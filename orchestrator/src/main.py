from fastapi import FastAPI
from pydantic import BaseModel
from src.graph.workflow import orchestrator_graph
from src.config import settings

app = FastAPI(title="Orchestrator")

class QueryRequest(BaseModel):
    question: str
    target_kg: str | None = None

class QueryResponse(BaseModel):
    question: str
    response: str
    selected_agents: list[str]
    details: dict

@app.get("/health")
def health():
    return {"status": "ok", "service": "orchestrator"}

@app.post("/query", response_model=QueryResponse)
async def run_query(req: QueryRequest):
    initial_state = {
        "question": req.question,
        "language": "",
        "target_kg": req.target_kg,
        "selected_agents": [],
        "final_response": "",
        "agent_results": {},
    }

    final_state = await orchestrator_graph.ainvoke(initial_state)
    selected_agents = final_state.get("selected_agents", [])
    agent_results = final_state.get("agent_results", {})
    
    # Raccogliamo i JSON grezzi in 'details' iterando su tutti gli agenti supportati
    details = {}
    for agent_name in settings.agent_registry:
        res = agent_results.get(agent_name)
        if res:
            prefix = agent_name.removesuffix('_agent')
            details[f"{prefix}_results"] = res

    return QueryResponse(
        question=req.question,
        response=final_state.get("final_response", ""),
        selected_agents=selected_agents,
        details=details
    )