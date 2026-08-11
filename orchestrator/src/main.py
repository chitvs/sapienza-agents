from fastapi import FastAPI
from pydantic import BaseModel
from src.graph.workflow import orchestrator_graph

app = FastAPI(title="Orchestrator")

class QueryRequest(BaseModel):
    question: str
    # knowledge graph da interrogare: se assente decide il kg-agent
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
        "question_en": "",
        "language": "",
        "target_kg": req.target_kg,
        "selected_agents": [],
        "kg_results": None,
        "planner_results": None,
        "multiapi_results": None,
        "final_response": "",
    }

    # esecuzione asincrona del grafo LangGraph
    final_state = await orchestrator_graph.ainvoke(initial_state)

    return QueryResponse(
        question=req.question,
        response=final_state["final_response"],
        selected_agents=final_state["selected_agents"],
        details={
            "kg_results": final_state.get("kg_results"),
            "planner_results": final_state.get("planner_results"),
            "multiapi_results": final_state.get("multiapi_results"),
        },
    )